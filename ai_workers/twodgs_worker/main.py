"""2D Gaussian Splatting (2DGS) 3D 재구성 Worker (torch 2.0+cu118).

Pipeline:
  1) /opt/2d-gaussian-splatting/train.py   — 2DGS 학습
  2) /opt/2d-gaussian-splatting/render.py  — TSDF 융합으로 메쉬(.ply) 추출
  3) common.meshbake.mesh_ply_to_assets    — 정점색 PLY → OBJ/MTL/PNG/GLB 풀세트

기본은 bounded(=오브젝트/피규어) 모드. unbounded(야외씬)는 요청 플래그로 전환.
"""
import os, json, subprocess, threading
from pathlib import Path
from pydantic import BaseModel
from fastapi import FastAPI
from loguru import logger

app = FastAPI(title="2DGS Worker")


class TwoDGSRequest(BaseModel):
    dataset_dir: str
    output_dir: str
    iterations: int = 30000
    eval: bool = False
    unbounded: bool = False    # 피규어는 False (bounded TSDF). 야외씬일 때만 True.
    mesh_res: int = 1024       # unbounded 일 때만 사용 (TSDF voxel 해상도)
    # bounded TSDF 가 voxel_size 를 너무 잘게 자동 설정해 OOM 나는 걸 방지.
    # 0.004 ≈ 1 unit 당 250 voxel → 피규어 케이스에서 적당한 디테일/메모리 균형.
    # depth_trunc 는 카메라 기준 통합 거리 컷. 3.0 이면 멀리 있는 점 무시.
    voxel_size: float = 0.004
    depth_trunc: float = 3.0
    # post_process_mesh 가 상위 N 클러스터 유지. render.py 기본 50 이지만
    # 깔끔한 피규어 메쉬는 클러스터 수가 50 미만 → IndexError 크래시.
    # 1 = 가장 큰 연결요소(=피규어 본체)만 유지, 나머지 노이즈 자동 제거.
    num_cluster: int = 1
    # depth_ratio: 0=mean(언바운디드/야외), 1=median(오브젝트/포워드 페이싱).
    # 피규어/오브젝트는 1 이 메쉬 잡음이 훨씬 적음 (2DGS 논문 권장).
    depth_ratio: float = 1.0
    # lambda_normal: 표면 법선 정합성 가중치. 기본 0.05 도 동작하지만
    # 0.1 이 피규어 표면이 더 매끈해진다 (저자 후속 코멘트).
    lambda_normal: float = 0.1


def _env():
    e = os.environ.copy()
    e["TORCH_CUDA_ARCH_LIST"] = "7.5;8.0;8.6;8.9"
    # SuGaR 워커와 동일한 정책: VRAM 단편화 회피 위해 max_split_size_mb 미지정,
    # GC 는 느슨하게 (200스텝 만에 죽지 않도록).
    e["PYTORCH_CUDA_ALLOC_CONF"] = "garbage_collection_threshold:0.85"
    e["PYTHONUNBUFFERED"] = "1"
    return e


class _ProcResult:
    def __init__(self):
        self.crashed = False
        self.crash_line = ""


def _stream_pipe(pipe, step, result):
    """tqdm \r 갱신까지 한 줄로 잘라 흘리고, traceback 보이면 실패로 마킹."""
    buf = ""
    while True:
        ch = pipe.read(1)
        if not ch:
            break
        if ch in ("\n", "\r"):
            if buf.strip():
                logger.info(f"[{step}] {buf}")
                if "Traceback (most recent call last)" in buf:
                    result.crashed = True
                    if not result.crash_line:
                        result.crash_line = buf.strip()
            buf = ""
        else:
            buf += ch
    if buf.strip():
        logger.info(f"[{step}] {buf}")


def _exec(cmd, step, cwd=None):
    logger.info(f"[{step}] 실행: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, cwd=cwd, env=_env(), bufsize=1,
    )
    result = _ProcResult()
    t = threading.Thread(target=_stream_pipe, args=(proc.stdout, step, result), daemon=True)
    t.start()
    rc = proc.wait()
    # 자식 종료 후 stdout 잔여 버퍼(특히 traceback) 가 완전히 흘러나올 때까지 대기.
    # 5초로는 큰 traceback 이 잘려나가 rc=0 인데 실패한 것을 놓치는 사례가 있었다.
    t.join(timeout=60)
    if rc != 0:
        logger.error(f"[{step}] 실패 (returncode={rc})")
        raise RuntimeError(f"{step} 실패 (rc={rc})")
    if result.crashed:
        logger.error(f"[{step}] 자식 프로세스 traceback 감지 (rc=0이지만 실패)")
        raise RuntimeError(f"{step} 실패 (자식 crash, rc=0): {result.crash_line}")
    logger.info(f"[{step}] 완료 (returncode=0)")


def _patch_cameras(model_dir):
    """3DGS 계열 train.py 가 cameras.json img_name 에 .png 를 붙이는 문제 회피.
    (SuGaR 워커의 _patch_cameras 와 동일한 사유. 2DGS 도 같은 코드 베이스에서 파생.)"""
    cj = os.path.join(model_dir, "cameras.json")
    if not os.path.exists(cj):
        return
    data = json.load(open(cj))
    changed = False
    for cam in data:
        if "img_name" in cam and cam["img_name"].endswith(".png"):
            cam["img_name"] = cam["img_name"][:-4]
            changed = True
    if changed:
        json.dump(data, open(cj, "w"), indent=2)
        logger.info("[2DGS] cameras.json 패치")


def _find_mesh_ply(model_dir, iterations, unbounded):
    """render.py 산출물 우선순위:
       1) fuse_post.ply  (cluster cleanup 완료된 추천 버전)
       2) fuse.ply       (raw TSDF 융합 결과)
       unbounded 모드면 파일명이 fuse_unbounded* 로 바뀐다.

    render.py 는 `<model>/train/ours_<iter>/` 에 저장한다. iterations 가 30000
    이 아닐 수 있어서 `f"ours_{iterations}"` 로 동적 매칭.
    """
    base = Path(model_dir)
    stem = "fuse_unbounded" if unbounded else "fuse"
    train_dir = base / "train" / f"ours_{iterations}"

    standard = [
        train_dir / f"{stem}_post.ply",
        train_dir / f"{stem}.ply",
        base / f"{stem}_post.ply",
        base / f"{stem}.ply",
    ]
    for p in standard:
        if p.exists() and p.stat().st_size > 0:
            return str(p)

    # 폴백: 어떤 iteration 으로 떨어졌든 잡아낸다 (예: train.py 가 save 단계에서
    # 다른 iter 로 저장한 경우, 또는 render.py 가 다른 폴더에 떨굼)
    for pat in (f"{stem}_post.ply", f"{stem}.ply", "fuse_post.ply", "fuse.ply"):
        cands = sorted(base.rglob(pat), key=lambda x: x.stat().st_size, reverse=True)
        for p in cands:
            if p.stat().st_size > 0:
                return str(p)
    return None


def _find_gs_ply(model_dir, iterations):
    """학습된 2DGS point_cloud.ply (프리뷰/디버그용)."""
    base = Path(model_dir) / "point_cloud"
    for it in (iterations, 30000, 7000):
        p = base / f"iteration_{it}" / "point_cloud.ply"
        if p.exists() and p.stat().st_size > 0:
            return str(p)
    if base.exists():
        cands = sorted(base.glob("iteration_*/point_cloud.ply"),
                       key=lambda x: x.stat().st_size, reverse=True)
        if cands:
            return str(cands[0])
    return None


def _collect_assets(model_dir, iterations, unbounded):
    """2DGS fuse_post.ply → 텍스처드 OBJ/MTL/PNG/GLB (+ 원본 PLY 첨부)."""
    import sys
    if "/app" not in sys.path:
        sys.path.insert(0, "/app")
    from common.meshbake import mesh_ply_to_assets

    mesh_ply = _find_mesh_ply(model_dir, iterations, unbounded)
    if not mesh_ply:
        logger.error(f"[2DGS] fuse*.ply 를 찾을 수 없음 (model_dir={model_dir})")
        return []
    logger.info(f"[2DGS] 메쉬 PLY: {mesh_ply} ({os.path.getsize(mesh_ply)/1024/1024:.1f}MB)")

    out = os.path.join(model_dir, "refined_mesh")
    assets = mesh_ply_to_assets(mesh_ply, out, name="mesh")

    if assets:
        assets.append({"format": "ply", "path": mesh_ply, "size": os.path.getsize(mesh_ply)})

    gs_ply = _find_gs_ply(model_dir, iterations)
    if gs_ply:
        # gs PLY 는 디버그용으로 같이 첨부 (이미 mesh ply 가 있으면 중복 ply 두 개)
        assets.append({"format": "ply", "path": gs_ply, "size": os.path.getsize(gs_ply)})

    logger.info(f"[2DGS] 에셋 목록: {[a['format'] for a in assets]}")
    return assets


@app.post("/process")
async def process(req: TwoDGSRequest):
    os.makedirs(req.output_dir, exist_ok=True)
    logger.info(f"[2DGS] 학습 ({req.iterations:,}스텝, unbounded={req.unbounded})")

    # ── 1) 2DGS 학습 ─────────────────────────────────────────────────
    # depth_ratio=1 (median) 이 피규어/오브젝트에서 메쉬 잡음을 줄임.
    # lambda_normal=0.1 로 법선 정합성을 default(0.05) 보다 강하게 잡아
    # 표면이 더 매끈해진다.
    train_cmd = [
        "python", "/opt/2d-gaussian-splatting/train.py",
        "-s", req.dataset_dir,
        "-m", req.output_dir,
        "--iterations", str(req.iterations),
        "--white_background",
        "--depth_ratio", str(req.depth_ratio),
        "--lambda_normal", str(req.lambda_normal),
    ]
    if req.eval:
        train_cmd.append("--eval")
    _exec(train_cmd, "2DGS학습", cwd="/opt/2d-gaussian-splatting")

    _patch_cameras(req.output_dir)

    # ── 2) render.py 로 TSDF 융합 + 메쉬 추출 ────────────────────────
    logger.info(
        f"[2DGS] 메쉬 추출 (TSDF 융합, "
        f"unbounded={req.unbounded}, voxel_size={req.voxel_size}, depth_trunc={req.depth_trunc})"
    )
    render_cmd = [
        "python", "/opt/2d-gaussian-splatting/render.py",
        "-s", req.dataset_dir,
        "-m", req.output_dir,
        "--iteration", str(req.iterations),
        "--skip_test",
        "--skip_train",  # 렌더링용 train 셋 이미지 미저장 → 시간/디스크 절약
        # post_process_mesh 가 클러스터 수 < cluster_to_keep 일 때 IndexError 로
        # 죽음 (2DGS 본가의 알려진 버그). 피규어용 num_cluster=1 로 회피하고
        # 동시에 본체 외 노이즈 섬도 자동 제거됨.
        "--num_cluster", str(req.num_cluster),
        # train.py 와 동일한 depth_ratio 를 써야 일관성 있음.
        "--depth_ratio", str(req.depth_ratio),
    ]
    if req.unbounded:
        render_cmd += ["--unbounded", "--mesh_res", str(req.mesh_res)]
    else:
        # bounded TSDF — voxel_size / depth_trunc 캡 적용 (OOM 방지).
        # render.py 의 자동 추정이 가까운 카메라/소규모 씬에서 voxel 을 너무 잘게
        # 잡아 10억 셀 가까이 RAM 폭주하는 케이스 차단.
        render_cmd += [
            "--voxel_size", str(req.voxel_size),
            "--depth_trunc", str(req.depth_trunc),
        ]
    _exec(render_cmd, "2DGS메쉬추출", cwd="/opt/2d-gaussian-splatting")

    # ── 3) PLY → OBJ/MTL/PNG/GLB ─────────────────────────────────────
    assets = _collect_assets(req.output_dir, req.iterations, req.unbounded)

    if not any(a["format"] in ("obj", "glb") for a in assets):
        raise RuntimeError(
            f"2DGS 메쉬 생성 실패: 최종 에셋에 OBJ/GLB 없음 "
            f"{[a.get('format') for a in assets]}"
        )

    logger.info(f"[2DGS] 완료: {len(assets)}개 에셋")
    return {"assets": assets, "status": "success"}


@app.get("/health")
async def health():
    import torch
    return {"status": "ok", "worker": "2dgs",
            "torch": torch.__version__, "cuda": torch.cuda.is_available()}
