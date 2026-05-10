"""GOF 3D 재구성 Worker (torch 1.12+cu113)"""
import os, subprocess
from pathlib import Path
from pydantic import BaseModel
from fastapi import FastAPI
from loguru import logger

app = FastAPI(title="GOF Worker")

class GOFRequest(BaseModel):
    dataset_dir: str; output_dir: str
    iterations: int = 30000; eval: bool = False

def _env():
    e = os.environ.copy(); e["TORCH_CUDA_ARCH_LIST"] = "8.9"; return e

def _exec(cmd, step, cwd=None):
    logger.info(f"[{step}] 실행")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, env=_env())
    if r.returncode != 0:
        logger.error(f"[{step}] 실패:\n{r.stderr[-2000:]}")
        raise RuntimeError(f"{step} 실패\n{r.stderr[-500:]}")
    logger.info(f"[{step}] 완료")

def _collect_assets(output_dir, iterations):
    import trimesh
    assets = []
    for ply_p in [os.path.join(output_dir,"mesh.ply"), os.path.join(output_dir,f"test/ours_{iterations}/fusion/mesh_binary_search_7.ply")]:
        if os.path.exists(ply_p):
            assets.append({"format":"ply","path":ply_p,"size":os.path.getsize(ply_p)})
            glb_p = ply_p.replace(".ply",".glb")
            try:
                trimesh.load(ply_p).export(glb_p)
                assets.append({"format":"glb","path":glb_p,"size":os.path.getsize(glb_p)})
            except Exception as e: logger.warning(f"GLB 변환 실패: {e}")
            break
    return assets

@app.post("/process")
async def process(req: GOFRequest):
    os.makedirs(req.output_dir, exist_ok=True)
    logger.info(f"[GOF] 학습 ({req.iterations:,}스텝)")
    _exec(["python","/opt/GOF/train.py","-s",req.dataset_dir,"-m",req.output_dir,
        "--iterations",str(req.iterations),"--white_background","--eval",str(req.eval)])
    logger.info("[GOF] 메쉬 추출")
    _exec(["python","/opt/GOF/extract_mesh.py","-m",req.output_dir,"--iteration",str(req.iterations)])
    assets = _collect_assets(req.output_dir, req.iterations)
    return {"assets": assets, "status": "success"}

@app.get("/health")
async def health():
    import torch
    return {"status":"ok","worker":"gof","torch":torch.__version__,"cuda":torch.cuda.is_available()}
