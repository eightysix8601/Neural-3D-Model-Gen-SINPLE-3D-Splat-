"""NeRF(nerfstudio / nerfacto) 3D 재구성 Worker.

입력은 colmap_worker 가 만든 워크스페이스(`images/` + `sparse/0/`).
파이프라인:
  COLMAP(txt) → transforms.json 직접 변환  (ns-process-data 플래그 드리프트 회피)
  → ns-train nerfacto (헤드리스)
  → ns-export poisson|tsdf|pointcloud  (단계별 폴백)
  → common.meshbake 로 OBJ/MTL/PNG/GLB 생성

다른 워커(SuGaR/GOF)와 동일한 에셋 계약을 돌려준다:
  [{"format": "obj|mtl|texture|glb|ply", "path", "size"}, ...]
"""
import os
import sys
import glob
import json
import shutil
import subprocess
import threading
from pathlib import Path

import numpy as np
from pydantic import BaseModel
from fastapi import FastAPI
from loguru import logger

app = FastAPI(title="NeRF Worker")

if "/app" not in sys.path:
    sys.path.insert(0, "/app")


class NeRFRequest(BaseModel):
    dataset_dir: str
    output_dir: str
    iterations: int = 20000
    eval: bool = False


def _env():
    e = os.environ.copy()
    e["PYTHONUNBUFFERED"] = "1"
    e["PYTORCH_CUDA_ALLOC_CONF"] = "garbage_collection_threshold:0.85"
    return e


class _ProcResult:
    def __init__(self):
        self.crashed = False
        self.crash_line = ""


def _stream_pipe(pipe, step, result):
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
    t.join(timeout=5)
    if rc != 0:
        raise RuntimeError(f"{step} 실패 (rc={rc})")
    if result.crashed:
        raise RuntimeError(f"{step} 실패 (자식 crash, rc=0): {result.crash_line}")
    logger.info(f"[{step}] 완료")


# ──────────────────────────────────────────────────────────────────────────
# COLMAP(txt) → nerfstudio transforms.json
# ──────────────────────────────────────────────────────────────────────────
def _qvec2rotmat(q):
    w, x, y, z = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w),     2 * (x * z + y * w)],
        [2 * (x * y + z * w),     1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w),     2 * (y * z + x * w),     1 - 2 * (x * x + y * y)],
    ], dtype=np.float64)


def _read_cameras_txt(path):
    cams = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            e = line.split()
            cid = int(e[0]); model = e[1]
            w, h = int(e[2]), int(e[3])
            p = list(map(float, e[4:]))
            if model in ("SIMPLE_PINHOLE", "SIMPLE_RADIAL", "RADIAL"):
                fx = fy = p[0]; cx, cy = p[1], p[2]
            elif model in ("PINHOLE", "OPENCV", "FULL_OPENCV"):
                fx, fy, cx, cy = p[0], p[1], p[2], p[3]
            else:
                fx = fy = p[0]; cx, cy = w / 2.0, h / 2.0
            cams[cid] = dict(w=w, h=h, fx=fx, fy=fy, cx=cx, cy=cy)
    return cams


def _read_images_txt(path):
    """COLMAP images.txt → [(name, cam_id, qvec, tvec), ...]."""
    out = []
    with open(path) as f:
        lines = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    # 짝수 인덱스 줄만 포즈 (홀수 줄은 2D 포인트)
    for i in range(0, len(lines), 2):
        e = lines[i].split()
        if len(e) < 10:
            continue
        q = np.array(list(map(float, e[1:5])))   # qw qx qy qz
        t = np.array(list(map(float, e[5:8])))
        cam_id = int(e[8])
        name = e[9]
        out.append((name, cam_id, q, t))
    return out


def _colmap_to_transforms(ws: str, nerf_data: str) -> str:
    """colmap 워크스페이스 → nerf_data/transforms.json (+ images 복사)."""
    sparse = os.path.join(ws, "sparse", "0")
    cams_txt = os.path.join(sparse, "cameras.txt")
    imgs_txt = os.path.join(sparse, "images.txt")
    src_imgs = os.path.join(ws, "images")

    # colmap_worker 의 txt 변환이 실패했어도 .bin 이 있으면 여기서 직접 변환
    if not (os.path.exists(cams_txt) and os.path.exists(imgs_txt)):
        if os.path.exists(os.path.join(sparse, "cameras.bin")):
            logger.warning("[NeRF] COLMAP txt 없음 → .bin 직접 변환 시도")
            try:
                _exec(["colmap", "model_converter",
                       "--input_path", sparse,
                       "--output_path", sparse,
                       "--output_type", "TXT"], "colmap-txt변환")
            except Exception as e:
                raise RuntimeError(f"COLMAP .bin→.txt 변환 실패: {e}")
    if not (os.path.exists(cams_txt) and os.path.exists(imgs_txt)):
        raise RuntimeError(f"COLMAP txt 모델 없음: {sparse}")

    cams = _read_cameras_txt(cams_txt)
    imgs = _read_images_txt(imgs_txt)
    if not imgs:
        raise RuntimeError("COLMAP images.txt 에 등록된 카메라가 없음")

    os.makedirs(nerf_data, exist_ok=True)
    dst_imgs = os.path.join(nerf_data, "images")
    os.makedirs(dst_imgs, exist_ok=True)

    frames = []
    for name, cam_id, q, t in imgs:
        src = os.path.join(src_imgs, name)
        if not os.path.exists(src):
            continue
        shutil.copy2(src, os.path.join(dst_imgs, name))

        R = _qvec2rotmat(q)             # world→cam
        Rt = R.T                        # cam→world 회전
        c = -Rt @ t                     # 카메라 중심
        c2w = np.eye(4)
        c2w[:3, :3] = Rt
        c2w[:3, 3] = c
        # COLMAP(x right, y down, z fwd) → nerfstudio/OpenGL(x right, y up, z back)
        c2w[:3, 1] *= -1
        c2w[:3, 2] *= -1

        cam = cams.get(cam_id, next(iter(cams.values())))
        frames.append({
            "file_path": f"images/{name}",
            "w": cam["w"], "h": cam["h"],
            "fl_x": cam["fx"], "fl_y": cam["fy"],
            "cx": cam["cx"], "cy": cam["cy"],
            "transform_matrix": c2w.tolist(),
        })

    if not frames:
        raise RuntimeError("transforms.json 프레임 0개 (이미지 매칭 실패)")

    any_cam = next(iter(cams.values()))
    meta = {
        "camera_model": "OPENCV",
        "w": any_cam["w"], "h": any_cam["h"],
        "fl_x": any_cam["fx"], "fl_y": any_cam["fy"],
        "cx": any_cam["cx"], "cy": any_cam["cy"],
        "frames": frames,
    }
    tj = os.path.join(nerf_data, "transforms.json")
    with open(tj, "w") as f:
        json.dump(meta, f, indent=2)
    logger.info(f"[NeRF] transforms.json 생성: {len(frames)}개 프레임")
    return tj


def _find_config(nerf_out: str):
    cfgs = glob.glob(os.path.join(nerf_out, "**", "config.yml"), recursive=True)
    if not cfgs:
        return None
    return max(cfgs, key=os.path.getmtime)


def _find_first(*paths):
    for p in paths:
        if p and os.path.exists(p) and os.path.getsize(p) > 0:
            return p
    return None


# ──────────────────────────────────────────────────────────────────────────
@app.post("/process")
async def process(req: NeRFRequest):
    os.makedirs(req.output_dir, exist_ok=True)
    nerf_data = os.path.join(req.output_dir, "nerf_data")
    nerf_out = os.path.join(req.output_dir, "nerf_out")
    mesh_out = os.path.join(req.output_dir, "nerf_mesh")
    refined = os.path.join(req.output_dir, "refined_mesh")
    for d in (nerf_out, mesh_out, refined):
        os.makedirs(d, exist_ok=True)

    # 1) COLMAP → transforms.json (치명적 단계: 실패 시 폴백 입력도 없음)
    logger.info("[NeRF] COLMAP → nerfstudio 데이터 변환")
    _colmap_to_transforms(req.dataset_dir, nerf_data)

    # 2) nerfacto 학습 (헤드리스)
    logger.info(f"[NeRF] nerfacto 학습 ({req.iterations:,} 스텝)")
    _exec([
        "ns-train", "nerfacto",
        "--data", nerf_data,
        "--output-dir", nerf_out,
        "--experiment-name", "ff3d",
        "--max-num-iterations", str(req.iterations),
        "--pipeline.model.predict-normals", "True",
        "--viewer.quit-on-train-completion", "True",
        "--vis", "tensorboard",
    ], "NeRF학습")

    cfg = _find_config(nerf_out)
    if not cfg:
        raise RuntimeError("nerfstudio config.yml 을 찾을 수 없음 (학습 실패)")
    logger.info(f"[NeRF] config: {cfg}")

    # 3) 메쉬 추출: poisson → tsdf → pointcloud 순으로 폴백
    from common.meshbake import mesh_ply_to_assets, gs_ply_to_assets

    assets, mode = [], None

    try:
        _exec([
            "ns-export", "poisson",
            "--load-config", cfg,
            "--output-dir", mesh_out,
            "--target-num-faces", "200000",
            "--num-pixels-per-side", "2048",
            "--num-points", "1000000",
            "--remove-outliers", "True",
            "--normal-method", "open3d",
            "--save-point-cloud", "False",
        ], "NeRF-poisson")
        mp = _find_first(os.path.join(mesh_out, "poisson_mesh.ply"))
        if mp:
            assets = mesh_ply_to_assets(mp, refined, name="mesh")
            if any(a["format"] in ("obj", "glb") for a in assets):
                mode = "poisson"
    except Exception as e:
        logger.error(f"[NeRF] poisson 실패: {e}")

    if mode is None:
        try:
            _exec([
                "ns-export", "tsdf",
                "--load-config", cfg,
                "--output-dir", mesh_out,
                "--target-num-faces", "200000",
                "--num-pixels-per-side", "2048",
            ], "NeRF-tsdf")
            mp = _find_first(os.path.join(mesh_out, "tsdf_mesh.ply"),
                             os.path.join(mesh_out, "mesh.ply"))
            if mp:
                assets = mesh_ply_to_assets(mp, refined, name="mesh")
                if any(a["format"] in ("obj", "glb") for a in assets):
                    mode = "tsdf"
        except Exception as e:
            logger.error(f"[NeRF] tsdf 실패: {e}")

    if mode is None:
        # 최후 폴백: 포인트클라우드만 뽑아 meshbake 가 Poisson 재구성
        try:
            _exec([
                "ns-export", "pointcloud",
                "--load-config", cfg,
                "--output-dir", mesh_out,
                "--num-points", "1000000",
                "--remove-outliers", "True",
                "--save-world-frame", "False",
            ], "NeRF-pcd")
            pc = _find_first(os.path.join(mesh_out, "point_cloud.ply"))
            if pc:
                assets = gs_ply_to_assets(pc, refined, name="mesh")
                if any(a["format"] in ("obj", "glb") for a in assets):
                    mode = "pointcloud-poisson"
        except Exception as e:
            logger.error(f"[NeRF] pointcloud 폴백 실패: {e}")

    if not any(a["format"] in ("obj", "glb") for a in assets):
        raise RuntimeError("NeRF 메쉬 생성 실패 (poisson/tsdf/pointcloud 모두 실패)")

    # 원본 메쉬/포인트 ply 도 함께 첨부
    raw = _find_first(
        os.path.join(mesh_out, "poisson_mesh.ply"),
        os.path.join(mesh_out, "tsdf_mesh.ply"),
        os.path.join(mesh_out, "point_cloud.ply"),
    )
    if raw and not any(a.get("path") == raw for a in assets):
        assets.append({"format": "ply", "path": raw, "size": os.path.getsize(raw)})

    logger.info(f"[NeRF] 완료: {len(assets)}개 에셋 (방식={mode})")
    return {"assets": assets, "status": "success", "mode": mode}


@app.get("/health")
async def health():
    try:
        import torch
        return {"status": "ok", "worker": "nerf",
                "torch": torch.__version__, "cuda": torch.cuda.is_available()}
    except Exception:
        return {"status": "ok", "worker": "nerf"}
