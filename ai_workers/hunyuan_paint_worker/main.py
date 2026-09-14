"""Hunyuan3D-Paint 워커 (port 8018)

메쉬(GLB/OBJ) + 컨디션 이미지 → 텍스쳐 입혀진 GLB.

흐름:
1. 업로드된 메쉬 + 이미지를 임시파일로 저장
2. trimesh.load() 로 메쉬 로드
3. Hunyuan3DPaintPipeline(메쉬, image=img) 호출
4. 결과 메쉬를 GLB 로 export

VRAM: ~10~14GB (subfolder turbo) / ~16~20GB (v2-0). 첫 호출 시 가중치 ~6GB 다운로드.
환경 변수:
- HUNYUAN_PAINT_SUBFOLDER: hunyuan3d-paint-v2-0-turbo (기본) | hunyuan3d-paint-v2-0
- HUNYUAN_REPO_DIR: /opt/Hunyuan3D-2 (clone 위치)
- HUNYUAN_WEIGHTS: /weights/hunyuan3d (HF 캐시 디렉토리)
"""
import os
import sys
import gc
import uuid
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from PIL import Image
from loguru import logger

# Hunyuan3D-2 repo 경로 (clone 위치) — hy3dgen 임포트 안 되면 sys.path 폴백
HUNYUAN_REPO_DIR = os.environ.get("HUNYUAN_REPO_DIR", "/opt/Hunyuan3D-2")
if os.path.isdir(HUNYUAN_REPO_DIR) and HUNYUAN_REPO_DIR not in sys.path:
    sys.path.insert(0, HUNYUAN_REPO_DIR)

app = FastAPI(title="Hunyuan3D-Paint Worker", version="1.0.0")

_paint_pipeline = None

WEIGHTS_DIR = os.environ.get("HUNYUAN_WEIGHTS", "/weights/hunyuan3d")
HF_REPO = os.environ.get("HUNYUAN_REPO", "tencent/Hunyuan3D-2")
PAINT_SUBFOLDER = os.environ.get("HUNYUAN_PAINT_SUBFOLDER", "hunyuan3d-paint-v2-0-turbo")


def _free_vram():
    try:
        import torch
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def _ensure_weights(local_dir: str, repo: str) -> str:
    p = Path(local_dir)
    if p.exists() and any(p.iterdir()):
        return str(p)
    p.mkdir(parents=True, exist_ok=True)
    logger.info(f"[Weights] HF 다운로드 시작: {repo} → {p}")
    from huggingface_hub import snapshot_download
    snapshot_download(repo_id=repo, local_dir=str(p))
    logger.info(f"[Weights] 다운로드 완료: {p}")
    return str(p)


def _load_paint():
    """Hunyuan3DPaintPipeline 로드. 일부 버전은 from_pretrained 시그니처가 다르므로
    여러 호출 형태를 차례로 시도한다."""
    global _paint_pipeline
    if _paint_pipeline is not None:
        return _paint_pipeline
    import torch
    from hy3dgen.texgen import Hunyuan3DPaintPipeline  # type: ignore

    weights = _ensure_weights(WEIGHTS_DIR, HF_REPO)
    last_exc = None
    pipe = None

    # 가장 일반적인 시그니처
    try:
        pipe = Hunyuan3DPaintPipeline.from_pretrained(weights, subfolder=PAINT_SUBFOLDER)
    except Exception as e:
        last_exc = e
        logger.warning(f"[Paint] from_pretrained(weights, subfolder=...) 실패: {e}")

    if pipe is None:
        # subfolder 가 path 형태로 들어가는 경우
        try:
            pipe = Hunyuan3DPaintPipeline.from_pretrained(
                os.path.join(weights, PAINT_SUBFOLDER)
            )
        except Exception as e:
            last_exc = e
            logger.warning(f"[Paint] from_pretrained(weights/sub) 실패: {e}")

    if pipe is None:
        # 그냥 HF repo id 로 한 번
        try:
            pipe = Hunyuan3DPaintPipeline.from_pretrained(HF_REPO, subfolder=PAINT_SUBFOLDER)
        except Exception as e:
            last_exc = e
            logger.error(f"[Paint] 모든 from_pretrained 시도 실패: {e}")
            raise RuntimeError(f"Hunyuan3DPaintPipeline 로드 실패: {last_exc}")

    # GPU 로 이동 (일부 빌드는 .to(device) 지원, 일부는 내부에서 처리)
    try:
        if torch.cuda.is_available():
            pipe = pipe.to("cuda")
    except Exception as e:
        logger.warning(f"[Paint] .to(cuda) 경고(무시): {e}")

    _paint_pipeline = pipe
    logger.info(f"[Paint] 로드 완료 (subfolder={PAINT_SUBFOLDER})")
    return pipe


@app.get("/health")
def health():
    import torch
    return {
        "status": "ok",
        "service": "hunyuan_paint_worker",
        "cuda": torch.cuda.is_available(),
        "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
        "loaded": _paint_pipeline is not None,
        "subfolder": PAINT_SUBFOLDER,
    }


@app.post("/paint")
async def paint(
    mesh: UploadFile = File(...),
    image: UploadFile = File(...),
    output_dir: str = Form(...),
):
    """업로드 mesh + 컨디션 이미지 → 텍스쳐 입혀진 GLB."""
    import trimesh

    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(400, "image 는 이미지 파일이어야 합니다")

    mesh_suffix = os.path.splitext(mesh.filename or "")[1].lower() or ".glb"
    if mesh_suffix not in (".glb", ".obj", ".ply"):
        mesh_suffix = ".glb"
    img_suffix = os.path.splitext(image.filename or "")[1].lower() or ".png"

    fd_m, mesh_path = tempfile.mkstemp(suffix=mesh_suffix)
    fd_i, image_path = tempfile.mkstemp(suffix=img_suffix)

    try:
        # 임시 파일로 저장
        with os.fdopen(fd_m, "wb") as f:
            f.write(await mesh.read())
        with os.fdopen(fd_i, "wb") as f:
            f.write(await image.read())

        # 로드
        mesh_obj = trimesh.load(mesh_path, force="mesh")
        if mesh_obj is None or len(getattr(mesh_obj, "vertices", [])) == 0:
            raise HTTPException(400, "메쉬 로드 실패 / 빈 메쉬")
        image_pil = Image.open(image_path).convert("RGBA")

        pipe = _load_paint()
        logger.info(f"[Paint] 베이크 시작: V={len(mesh_obj.vertices)} F={len(mesh_obj.faces)}")

        # 호출 시그니처도 버전별로 다를 수 있어 두 형태 시도
        try:
            result_mesh = pipe(mesh_obj, image=image_pil)
        except TypeError:
            result_mesh = pipe(mesh=mesh_obj, image=image_pil)

        if result_mesh is None:
            raise HTTPException(500, "Hunyuan paint 결과가 비어있음")

        os.makedirs(output_dir, exist_ok=True)
        base = uuid.uuid4().hex[:8]
        glb_path = os.path.join(output_dir, f"textured_{base}.glb")
        result_mesh.export(glb_path)
        size = os.path.getsize(glb_path)
        logger.info(f"[Paint] 베이크 완료: {glb_path} ({size:,}B)")

        _free_vram()
        return {
            "assets": [
                {"format": "glb", "path": glb_path, "size": size, "has_texture": True},
            ],
        }
    finally:
        for p in (mesh_path, image_path):
            try: os.unlink(p)
            except Exception: pass
