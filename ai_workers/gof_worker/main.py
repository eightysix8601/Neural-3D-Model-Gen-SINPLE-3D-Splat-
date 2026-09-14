"""GOF 3D 재구성 Worker (torch 1.12+cu113)"""
import os, subprocess, threading
from pathlib import Path
from pydantic import BaseModel
from fastapi import FastAPI
from loguru import logger

app = FastAPI(title="GOF Worker")

class GOFRequest(BaseModel):
    dataset_dir: str; output_dir: str
    iterations: int = 30000; eval: bool = False

def _env():
    e = os.environ.copy()
    e["TORCH_CUDA_ARCH_LIST"] = "8.9"
    # expandable_segments 는 PyTorch 2.1+ 전용. GOF 는 1.12 라 지원 안 함.
    e["PYTORCH_CUDA_ALLOC_CONF"] = "garbage_collection_threshold:0.6,max_split_size_mb:512"
    e["PYTHONUNBUFFERED"] = "1"
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
        logger.error(f"[{step}] 실패 (returncode={rc})")
        raise RuntimeError(f"{step} 실패 (rc={rc})")
    if result.crashed:
        logger.error(f"[{step}] 자식 프로세스 traceback 감지 (rc=0이지만 실패)")
        raise RuntimeError(f"{step} 실패 (자식 crash, rc=0): {result.crash_line}")
    logger.info(f"[{step}] 완료")

def _find_gof_mesh_ply(output_dir, iterations):
    for p in [os.path.join(output_dir, "mesh.ply"),
              os.path.join(output_dir, f"test/ours_{iterations}/fusion/mesh_binary_search_7.ply")]:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return p
    return None


def _find_gof_gs_ply(output_dir, iterations):
    base = os.path.join(output_dir, "point_cloud")
    for it in (iterations, 30000, 10000, 7000):
        p = os.path.join(base, f"iteration_{it}", "point_cloud.ply")
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return p
    if os.path.isdir(base):
        cands = sorted(Path(base).glob("iteration_*/point_cloud.ply"),
                       key=lambda x: x.stat().st_size, reverse=True)
        if cands:
            return str(cands[0])
    return None


def _collect_assets(output_dir, iterations):
    """GOF 표면 메쉬(ply) → 텍스처드 OBJ/MTL/PNG/GLB (meshbake 재사용)."""
    import sys
    if "/app" not in sys.path:
        sys.path.insert(0, "/app")
    from common.meshbake import mesh_ply_to_assets

    mesh_ply = _find_gof_mesh_ply(output_dir, iterations)
    if not mesh_ply:
        return []
    out = os.path.join(output_dir, "refined_mesh")
    assets = mesh_ply_to_assets(mesh_ply, out, name="mesh")
    if assets:
        assets.append({"format": "ply", "path": mesh_ply, "size": os.path.getsize(mesh_ply)})
    return assets


def _fallback_assets(output_dir, iterations):
    """GOF 메쉬 추출이 죽었을 때: 학습된 GOF Gaussian → Poisson 메쉬."""
    import sys
    if "/app" not in sys.path:
        sys.path.insert(0, "/app")
    from common.meshbake import gs_ply_to_assets

    gs_ply = _find_gof_gs_ply(output_dir, iterations)
    if not gs_ply:
        logger.error("[GOF] 폴백 실패: 학습된 point_cloud.ply 없음")
        return []
    logger.warning(f"[GOF] ⚠️ 자동 폴백 가동 (Gaussian → Poisson 메쉬): {gs_ply}")
    out = os.path.join(output_dir, "refined_mesh")
    assets = gs_ply_to_assets(gs_ply, out, name="mesh")
    if assets:
        assets.append({"format": "ply", "path": gs_ply, "size": os.path.getsize(gs_ply)})
    return assets


@app.post("/process")
async def process(req: GOFRequest):
    os.makedirs(req.output_dir, exist_ok=True)
    logger.info(f"[GOF] 학습 ({req.iterations:,}스텝)")
    # 3DGS/GOF 학습 실패는 치명적 (폴백 입력 자체가 없음)
    _exec(["python","/opt/GOF/train.py","-s",req.dataset_dir,"-m",req.output_dir,
        "--iterations",str(req.iterations),"--white_background","--eval",str(req.eval)])

    assets, gof_ok = [], False
    try:
        logger.info("[GOF] 메쉬 추출")
        _exec(["python","/opt/GOF/extract_mesh.py","-m",req.output_dir,"--iteration",str(req.iterations)])
        assets = _collect_assets(req.output_dir, req.iterations)
        gof_ok = any(a["format"] in ("obj", "glb") for a in assets)
        if not gof_ok:
            logger.error("[GOF] 추출은 끝났으나 OBJ/GLB 없음 → 폴백 전환")
    except Exception as e:
        logger.error(f"[GOF] 메쉬 추출 실패: {e} → 자동 폴백 전환")

    if not gof_ok:
        fb = _fallback_assets(req.output_dir, req.iterations)
        if any(a["format"] in ("obj", "glb") for a in fb):
            assets = fb

    if not any(a["format"] in ("obj", "glb") for a in assets):
        raise RuntimeError(
            f"GOF 실패 + 자동 폴백도 실패 (결과물 없음) {[a.get('format') for a in assets]}"
        )

    logger.info(f"[GOF] 완료: {len(assets)}개 에셋 "
                f"(방식={'GOF 정품' if gof_ok else 'Poisson 폴백'})")
    return {"assets": assets, "status": "success", "fallback": (not gof_ok)}

@app.get("/health")
async def health():
    import torch
    return {"status":"ok","worker":"gof","torch":torch.__version__,"cuda":torch.cuda.is_available()}
