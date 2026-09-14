"""SuGaR 3D 재구성 Worker (torch 2.0+cu118)"""
import os, json, subprocess, shutil, glob, threading
from pathlib import Path
from pydantic import BaseModel
from fastapi import FastAPI
from loguru import logger

app = FastAPI(title="SuGaR Worker")

class SuGaRRequest(BaseModel):
    dataset_dir: str; output_dir: str
    gs_iterations: int = 30000; refinement_time: str = "short"
    high_poly: bool = False; eval: bool = False

def _env():
    e = os.environ.copy()
    e["TORCH_CUDA_ARCH_LIST"] = "7.5;8.0;8.6;8.9"  # RTX 20/30/40xx 모두 지원
    # refine 단계 'CUDA error: device not ready' 의 실체는 VRAM 단편화/고갈이다.
    # max_split_size_mb:512 는 rasterizer 가 필요로 하는 큰 연속 블록을 강제로 쪼개
    # 오히려 단편화를 악화시키고, GC threshold 0.6 은 매 step GC 를 돌려 200 step 에
    # 8 분 걸리는 극단적 저속을 유발했다. 큰 블록 분할을 풀고 GC 는 느슨하게 둔다.
    # (expandable_segments 는 PyTorch 2.1+ 전용이라 2.0 컨테이너에선 사용 불가)
    e["PYTORCH_CUDA_ALLOC_CONF"] = "garbage_collection_threshold:0.85"
    e["PYTHONUNBUFFERED"] = "1"  # tqdm/print 실시간 flush
    return e

class _ProcResult:
    def __init__(self):
        self.crashed = False
        self.crash_line = ""

def _stream_pipe(pipe, step, result):
    # tqdm 의 \r 진행 갱신도 한 줄로 잘라 흘려보낸다
    buf = ""
    while True:
        ch = pipe.read(1)
        if not ch:
            break
        if ch in ("\n", "\r"):
            if buf.strip():
                logger.info(f"[{step}] {buf}")
                # 부모 프로세스가 자식 exit code 를 삼키는 경우 대비:
                # 자식 stdout 에 Python traceback 이 보이면 실패로 마킹
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

def _patch_sugar():
    """SuGaR 호환성 패치 - 모든 수정사항 영구 적용"""

    f = "/opt/SuGaR/sugar_scene/sugar_model.py"
    if not os.path.exists(f):
        return

    code = open(f).read()
    changed = False

    # 0-a. 기존 패치된 파일의 chunk_size 를 적응형으로 마이그레이션
    # 점 개수 N 에 따라 자동 조정: 작으면 4096, 크면 작게 (메모리 ~1GB 예산)
    adaptive_chunk = "chunk_size = max(32, min(4096, 80_000_000 // (N * 3)))"
    for old in ("chunk_size = 4096", "chunk_size = 512"):
        if old in code and adaptive_chunk not in code:
            code = code.replace(old, adaptive_chunk)
            changed = True
            logger.info(f"[SuGaR] KNN chunk_size 적응형으로 마이그레이션 ({old} → adaptive)")

    # 0. 이전 잘못된 패치 복원 (knn_points = _knn_points_torch, estimate_pointcloud_normals (replaced))
    broken_line = "knn_points = _knn_points_torch, estimate_pointcloud_normals (replaced)"
    if broken_line in code:
        code = code.replace(
            broken_line + "\n",
            ""  # 깨진 줄 자체 제거 (바로 아래에 정상 줄이 이미 있음)
        )
        changed = True
        logger.warning("[SuGaR] 이전 깨진 KNN 패치 자동 복원")

    # 1. antialiasing 인자 제거 (버전 호환)
    if "antialiasing=False" in code:
        code = code.replace(
            "raster_settings = GaussianRasterizationSettings(antialiasing=False,",
            "raster_settings = GaussianRasterizationSettings(")
        changed = True

    # 2. radii 언패킹 수정 (3개 → 2개)
    if "rendered_image, radii, _ = rasterizer(" in code:
        code = code.replace(
            "rendered_image, radii, _ = rasterizer(",
            "rendered_image, radii = rasterizer(")
        changed = True

    # 3. KNN 청크 방식으로 교체 (OOM 방지)
    if "# KNN_PATCHED" not in code:
        knn_impl = '''
# KNN_PATCHED
# 작은 N(<200k)은 pytorch3d CUDA knn_points 를 그대로 쓰고, N 이 커질 때만
# 토치 chunk 폴백으로 떨어진다. 무조건 폴백을 쓰면 12GB GPU 에서 refinement 가
# 분 단위로 느려져 사실상 학습이 끝나지 않았다(과거 회귀).
import torch as _torch
try:
    from pytorch3d.ops import knn_points as _real_knn_points
    from pytorch3d.ops import estimate_pointcloud_normals as _real_est_normals
except Exception:
    _real_knn_points = None
    _real_est_normals = None

_KNN_CUDA_THRESHOLD = 200_000  # 12GB 안전 상한


def _knn_points_torch(p1, p2=None, K=16, **kwargs):
    """N<200k 면 pytorch3d CUDA knn, 그 이상이면 청크 폴백."""
    if p1.dim() == 2:
        p1 = p1.unsqueeze(0)
    if p2 is None:
        p2 = p1
    elif p2.dim() == 2:
        p2 = p2.unsqueeze(0)
    N = p1.shape[1]

    if _real_knn_points is not None and N < _KNN_CUDA_THRESHOLD:
        try:
            return _real_knn_points(p1, p2, K=K, **{k: v for k, v in kwargs.items()
                                                    if k in {"lengths1", "lengths2", "norm",
                                                              "version", "return_nn", "return_sorted"}})
        except Exception:
            pass  # OOM 등 → 폴백

    p = p2[0]
    q = p1[0]
    M = q.shape[0]
    K = min(K, p.shape[0] - 1) if p.shape[0] > 1 else 1
    chunk_size = max(64, min(8192, 200_000_000 // max(p.shape[0] * 3, 1)))
    all_dists = []
    all_idx = []
    for i in range(0, M, chunk_size):
        chunk = q[i:i+chunk_size]
        diff = chunk.unsqueeze(1) - p.unsqueeze(0)
        dist2 = (diff ** 2).sum(-1)
        topk = _torch.topk(dist2, k=K+1, dim=1, largest=False)
        all_dists.append(topk.values[:, 1:])
        all_idx.append(topk.indices[:, 1:])
    dists = _torch.cat(all_dists, dim=0)
    idx = _torch.cat(all_idx, dim=0)

    class KNNResult:
        def __init__(self, dists, idx):
            self.dists = dists.unsqueeze(0)
            self.idx   = idx.unsqueeze(0)
    return KNNResult(dists, idx)


def estimate_pointcloud_normals(points, neighborhood_size=16, disambiguate_directions=True):
    """N<200k 면 pytorch3d 사용, 아니면 chunk 폴백."""
    import torch
    if points.dim() == 2:
        points_b = points.unsqueeze(0)
    else:
        points_b = points
    N = points_b.shape[1]
    if _real_est_normals is not None and N < _KNN_CUDA_THRESHOLD:
        try:
            return _real_est_normals(points_b,
                                      neighborhood_size=neighborhood_size,
                                      disambiguate_directions=disambiguate_directions)
        except Exception:
            pass

    p = points_b[0]
    K = min(neighborhood_size, N - 1) if N > 1 else 1
    chunk_size = max(64, min(8192, 200_000_000 // max(N * 3, 1)))
    all_normals = []
    for i in range(0, N, chunk_size):
        chunk = p[i:i+chunk_size]
        diff = chunk.unsqueeze(1) - p.unsqueeze(0)
        dist2 = (diff ** 2).sum(-1)
        topk = torch.topk(dist2, k=K+1, dim=1, largest=False)
        idx = topk.indices[:, 1:]
        neighbors = p[idx]
        centroid = neighbors.mean(dim=1, keepdim=True)
        centered = neighbors - centroid
        cov = torch.bmm(centered.transpose(1, 2), centered) / K
        try:
            _, _, Vt = torch.linalg.svd(cov)
            normals = Vt[:, -1, :]
        except Exception:
            normals = torch.zeros(chunk.shape[0], 3, device=p.device)
            normals[:, 2] = 1.0
        all_normals.append(normals)
    normals = torch.cat(all_normals, dim=0)
    if disambiguate_directions:
        view_dir = -p / (p.norm(dim=1, keepdim=True) + 1e-8)
        flip = (normals * view_dir).sum(dim=1) < 0
        normals[flip] = -normals[flip]
    return normals.unsqueeze(0)

'''
        # knn_points import 교체 (둘 중 하나만 매칭, 연쇄 치환 방지)
        full_import = "from pytorch3d.ops import knn_points, estimate_pointcloud_normals"
        short_import = "from pytorch3d.ops import knn_points"
        if full_import in code:
            code = code.replace(
                full_import,
                f"# {full_import} (replaced)\nknn_points = _knn_points_torch"
            )
        elif short_import in code:
            code = code.replace(
                short_import,
                f"# {short_import} (replaced)\nknn_points = _knn_points_torch"
            )
        code = knn_impl + code
        changed = True

    if changed:
        open(f, "w").write(code)
        logger.info("[SuGaR] sugar_model.py 패치 완료")

    # 4. 다른 파일 KNN import 패치
    for fp in glob.glob("/opt/SuGaR/**/*.py", recursive=True):
        try:
            code3 = open(fp).read()
            if "from pytorch3d.ops import knn_points" in code3 and "# KNN_PATCHED" not in code3:
                code3 = code3.replace(
                    "from pytorch3d.ops import knn_points",
                    "# from pytorch3d.ops import knn_points\nfrom sugar_scene.sugar_model import _knn_points_torch as knn_points"
                )
                open(fp, "w").write(code3)
                logger.info(f"[SuGaR] KNN 패치: {fp}")
        except Exception:
            pass

def _patch_cameras(gs_out):
    cj = os.path.join(gs_out, "cameras.json")
    if not os.path.exists(cj): return
    data = json.load(open(cj))
    changed = False
    for cam in data:
        if "img_name" in cam and cam["img_name"].endswith(".png"):
            cam["img_name"] = cam["img_name"][:-4]; changed = True
    if changed:
        json.dump(data, open(cj, "w"), indent=2)
        logger.info("[SuGaR] cameras.json 패치")

def _find_gs_ply(output_dir, gs_iterations):
    """학습된 3DGS point_cloud.ply 경로 탐색 (폴백 입력용)."""
    base = Path(output_dir) / "gs_pretrain" / "point_cloud"
    for it in (gs_iterations, 30000, 10000, 7000):
        p = base / f"iteration_{it}" / "point_cloud.ply"
        if p.exists() and p.stat().st_size > 0:
            return str(p)
    # 알 수 없는 iteration 폴더까지 폭넓게 탐색
    if base.exists():
        cands = sorted(base.glob("iteration_*/point_cloud.ply"),
                       key=lambda x: x.stat().st_size, reverse=True)
        if cands:
            return str(cands[0])
    return None


def _collect_assets(output_dir):
    """SuGaR 정상 출력(refined_mesh)에서 OBJ/MTL/PNG/GLB/PLY 수집."""
    import trimesh
    assets = []
    sugar_output = Path("/opt/SuGaR/output/refined_mesh")

    project_mesh_dir = Path(output_dir) / "refined_mesh"
    project_mesh_dir.mkdir(parents=True, exist_ok=True)

    for obj_p in sugar_output.rglob("*.obj"):
        # MTL/PNG 를 먼저 프로젝트 폴더로 복사 (GLB 변환 전에 텍스처가 곁에 있어야 함)
        mtl_p = obj_p.with_suffix(".mtl")
        if mtl_p.exists():
            dst_mtl = project_mesh_dir / mtl_p.name
            shutil.copy2(str(mtl_p), str(dst_mtl))
        for png in obj_p.parent.glob("*.png"):
            shutil.copy2(str(png), str(project_mesh_dir / png.name))

        dst_obj = project_mesh_dir / obj_p.name
        shutil.copy2(str(obj_p), str(dst_obj))
        assets.append({"format": "obj", "path": str(dst_obj), "size": os.path.getsize(str(dst_obj))})
        if mtl_p.exists():
            dst_mtl = project_mesh_dir / mtl_p.name
            assets.append({"format": "mtl", "path": str(dst_mtl), "size": os.path.getsize(str(dst_mtl))})
        for png in project_mesh_dir.glob("*.png"):
            assets.append({"format": "texture", "path": str(png), "size": os.path.getsize(str(png))})

        # GLB 변환은 트라이멤시 1패스로만. 이전엔 split(only_watertight=False)
        # 으로 스파이크 섬을 제거했는데, HDD 압박/27MB OBJ + 텍스처 케이스에서
        # 분 단위로 늘어져 uvicorn 워커 응답이 끊겼다("Server disconnected").
        # 스파이크 정리는 이제 상류 단계 (BG 알파 erode + COLMAP single_camera)
        # 에서 처리하므로 여기선 단순 로드/익스포트만 하고 빨리 응답한다.
        # GLB 가 실패해도 OBJ 만 있으면 파이프라인은 정상 통과.
        glb_p = str(dst_obj).replace(".obj", ".glb")
        try:
            loaded = trimesh.load(str(obj_p))  # MTL/PNG 자동 로딩
            if isinstance(loaded, trimesh.Scene):
                try:
                    loaded = loaded.dump(concatenate=True)
                except Exception:
                    cands = [g for g in loaded.geometry.values()
                             if isinstance(g, trimesh.Trimesh) and len(g.faces)]
                    loaded = max(cands, key=lambda g: len(g.faces)) if cands else None
            if loaded is None or not hasattr(loaded, "faces") or len(loaded.faces) == 0:
                raise RuntimeError("로드된 메쉬가 비어있음")
            loaded.export(glb_p)
            if os.path.exists(glb_p) and os.path.getsize(glb_p) > 0:
                assets.append({"format": "glb", "path": glb_p, "size": os.path.getsize(glb_p)})
                logger.info(f"[SuGaR] GLB 완료: {os.path.getsize(glb_p)/1024/1024:.1f}MB")
            else:
                raise RuntimeError("GLB 파일이 생성되지 않았거나 빈 파일")
        except Exception as e:
            logger.error(f"[SuGaR] GLB 변환 실패(OBJ만으로 진행): {e}")

    # 3DGS point cloud
    gs_ply = _find_gs_ply(output_dir, 30000)
    if gs_ply:
        assets.append({"format": "ply", "path": gs_ply, "size": os.path.getsize(gs_ply)})

    if not any(a["format"] == "obj" for a in assets):
        logger.error(f"[SuGaR] ⚠️ OBJ 파일이 없습니다. SuGaR 출력 경로 확인 필요: {sugar_output}")
    logger.info(f"[SuGaR] 에셋 목록: {[a['format'] for a in assets]}")
    return assets


@app.post("/process")
async def process(req: SuGaRRequest):
    os.makedirs(req.output_dir, exist_ok=True)
    gs_out = os.path.join(req.output_dir, "gs_pretrain")
    logger.info(f"[SuGaR] 3DGS 학습 ({req.gs_iterations:,}스텝)")

    # 이전 SuGaR 출력 정리 (다른 프로젝트 파일 혼입 방지)
    sugar_out_dir = Path("/opt/SuGaR/output")
    if sugar_out_dir.exists():
        shutil.rmtree(str(sugar_out_dir))
        logger.info("[SuGaR] 이전 output 정리 완료")

    # 업스트림 기본값(densify_until_iter=15000, densification_interval=100,
    # opacity_reset_interval=3000, densify_grad_threshold=0.0002)을 그대로 사용.
    # 우리 파이프라인이 COLMAP._replace_with_rgba 로 흰 배경 합성 이미지를 만드므로
    # --white_background 만 SuGaR 측 추출 단계와 짝맞춰 켜둔다.
    train_cmd = [
        "python", "/opt/SuGaR/gaussian_splatting/train.py",
        "-s", req.dataset_dir,
        "-m", gs_out,
        "--iterations", str(req.gs_iterations),
        "--white_background",
    ]
    # cwd 를 gaussian_splatting 으로 둬야 train.py 의 from arguments / from scene
    # 같은 상대 import 가 안정적이다 (Python 이 자동으로 sys.path 에 추가하지만,
    # 일부 환경에서 가져오기 순서가 꼬여 ModuleNotFoundError 가 나는 사례 회피).
    _exec(train_cmd, "3DGS학습", cwd="/opt/SuGaR/gaussian_splatting")

    _patch_sugar()
    _patch_cameras(gs_out)
    logger.info("[SuGaR] 메쉬 추출")

    cmd = [
        "python", "train_full_pipeline.py",
        "-s", req.dataset_dir,
        "--gs_output_dir", gs_out,
        "--regularization_type", "dn_consistency",
        "--refinement_time", req.refinement_time,
        "--export_ply", "True",
        "-t", "True",
        "--white_background", "True",
        "--low_poly", "True",
        "-g", "1",
        # NOTE: --postprocess_mesh True 는 이 SuGaR 커밋(7c10c4ae) 에서
        # refined_mesh.py:149 face_mask 형상 불일치로 IndexError 가 났던 적이
        # 있어 끄고 간다. 스파이크 제거는 _collect_assets 의 자체 정리
        # (최대 연결요소만 유지) 로 텍스처를 보존하며 처리한다.
    ]
    if req.high_poly:
        # --low_poly True 쌍만 정확히 제거 (이전 코드는 모든 "True" 토큰을 날려
        # --export_ply/-t/--white_background 값까지 깨뜨리는 버그가 있었다)
        lp = cmd.index("--low_poly")
        del cmd[lp:lp + 2]
        cmd += ["--high_poly", "True", "-g", "6"]

    # SuGaR 메쉬 추출 (실패 시 그대로 에러 — 폴백 없음)
    _exec(cmd, "SuGaR", cwd="/opt/SuGaR")
    assets = _collect_assets(req.output_dir)

    if not any(a["format"] in ("obj", "glb") for a in assets):
        raise RuntimeError(
            f"SuGaR 메쉬 생성 실패: 최종 에셋에 OBJ/GLB 없음 "
            f"{[a.get('format') for a in assets]}"
        )

    logger.info(f"[SuGaR] 완료: {len(assets)}개 에셋")
    return {"assets": assets, "status": "success"}

@app.get("/health")
async def health():
    import torch
    return {"status": "ok", "worker": "sugar", "torch": torch.__version__, "cuda": torch.cuda.is_available()}