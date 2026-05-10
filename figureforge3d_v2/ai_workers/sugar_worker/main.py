"""SuGaR 3D 재구성 Worker (torch 2.0+cu118)"""
import os, json, subprocess
from pathlib import Path
from pydantic import BaseModel
from typing import Optional
from fastapi import FastAPI
from loguru import logger

app = FastAPI(title="SuGaR Worker")

class SuGaRRequest(BaseModel):
    dataset_dir: str; output_dir: str
    gs_iterations: int = 30000; refinement_time: str = "short"
    high_poly: bool = False; eval: bool = False

def _env():
    e = os.environ.copy()
    e["TORCH_CUDA_ARCH_LIST"] = "8.9"
    return e

def _exec(cmd, step, cwd=None):
    logger.info(f"[{step}] 실행")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, env=_env())
    if r.returncode != 0:
        logger.error(f"[{step}] 실패:\n{r.stderr[-2000:]}")
        raise RuntimeError(f"{step} 실패\n{r.stderr[-500:]}")
    logger.info(f"[{step}] 완료")

# def _patch_sugar():
#     f = "/opt/SuGaR/sugar_scene/sugar_model.py"
#     if not os.path.exists(f): return
#     code = open(f).read()
#     changed = False
#     if "antialiasing=False" not in code:
#         code = code.replace("raster_settings = GaussianRasterizationSettings(","raster_settings = GaussianRasterizationSettings(antialiasing=False,")
#         changed = True
#     if "rendered_image, radii, _" not in code and "rendered_image, radii = rasterizer(" in code:
#         code = code.replace("rendered_image, radii = rasterizer(","rendered_image, radii, _ = rasterizer(")
#         changed = True
#     if changed:
#         open(f,"w").write(code)
#         logger.info("[SuGaR] 패치 완료")

def _patch_sugar():
    """SuGaR 호환성 패치"""
    # 1. sugar_model.py 패치
    f = "/opt/SuGaR/sugar_scene/sugar_model.py"
    if os.path.exists(f):
        code = open(f).read()
        changed = False
        if "antialiasing=False" not in code:
            code = code.replace(
                "raster_settings = GaussianRasterizationSettings(",
                "raster_settings = GaussianRasterizationSettings(antialiasing=False,")
            changed = True
        if "rendered_image, radii, _" not in code and "rendered_image, radii = rasterizer(" in code:
            code = code.replace(
                "rendered_image, radii = rasterizer(",
                "rendered_image, radii, _ = rasterizer(")
            changed = True
        # pytorch3d knn → torch 순수 구현으로 교체
        if ("from pytorch3d.ops import knn_points" in code or 
            "estimate_pointcloud_normals" in code) and "# KNN_PATCHED" not in code:
            knn_patch = '''
# KNN_PATCHED
import torch as _torch

def _knn_points_torch(points, K=16):
    """pytorch3d 없이 순수 torch로 KNN 구현"""
    p = points[0]
    diff = p.unsqueeze(0) - p.unsqueeze(1)
    dist2 = (diff ** 2).sum(-1)
    topk = _torch.topk(dist2, k=min(K+1, dist2.shape[1]), dim=1, largest=False)
    dists = topk.values[:, 1:]
    idx   = topk.indices[:, 1:]
    class KNNResult:
        def __init__(self, dists, idx):
            self.dists = dists.unsqueeze(0)
            self.idx   = idx.unsqueeze(0)
    return KNNResult(dists, idx)

def estimate_pointcloud_normals(points, neighborhood_size=16, disambiguate_directions=True):
    """pytorch3d 없이 순수 torch로 법선 벡터 추정"""
    import torch
    p = points[0]  # (N, 3)
    N = p.shape[0]
    diff = p.unsqueeze(0) - p.unsqueeze(1)
    dist2 = (diff ** 2).sum(-1)
    K = min(neighborhood_size, N - 1)
    topk = torch.topk(dist2, k=K+1, dim=1, largest=False)
    idx = topk.indices[:, 1:]  # (N, K) 자기 자신 제외
    neighbors = p[idx]  # (N, K, 3)
    centroid = neighbors.mean(dim=1, keepdim=True)
    centered = neighbors - centroid
    cov = torch.bmm(centered.transpose(1, 2), centered) / K
    try:
        _, _, Vt = torch.linalg.svd(cov)
        normals = Vt[:, -1, :]  # 가장 작은 고유값의 벡터
    except Exception:
        normals = torch.zeros(N, 3, device=p.device)
        normals[:, 2] = 1.0
    if disambiguate_directions:
        view_dir = -p / (p.norm(dim=1, keepdim=True) + 1e-8)
        flip = (normals * view_dir).sum(dim=1) < 0
        normals[flip] = -normals[flip]
    return normals.unsqueeze(0)

'''
            code = code.replace(
                "from pytorch3d.ops import knn_points",
                "# from pytorch3d.ops import knn_points (replaced)\nknn_points = _knn_points_torch"
            )
            code = code.replace(
                "from pytorch3d.ops import knn_points, estimate_pointcloud_normals",
                "# from pytorch3d.ops import knn_points, estimate_pointcloud_normals (replaced)\nknn_points = _knn_points_torch"
            )
            code = knn_patch + code
            changed = True
        if changed:
            open(f, "w").write(code)
            logger.info("[SuGaR] sugar_model.py 패치 완료")

    # 2. coarse_density_and_dn_consistency.py 패치
    f2 = "/opt/SuGaR/sugar_trainers/coarse_density_and_dn_consistency.py"
    if os.path.exists(f2):
        code2 = open(f2).read()
        if "from pytorch3d.ops import knn_points" in code2 and "# KNN_PATCHED" not in code2:
            code2 = code2.replace(
                "from pytorch3d.ops import knn_points",
                "# from pytorch3d.ops import knn_points\nfrom sugar_scene.sugar_model import _knn_points_torch as knn_points"
            )
            open(f2, "w").write(code2)
            logger.info("[SuGaR] coarse_density 패치 완료")

    # 3. 다른 파일들도 pytorch3d knn 사용하는지 확인
    import glob
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
    if changed: json.dump(data, open(cj,"w"), indent=2); logger.info("[SuGaR] cameras.json 패치")

# def _collect_assets(output_dir):
#     import trimesh
#     assets = []

#     # SuGaR 출력은 /opt/SuGaR/output 에 저장됨
#     sugar_output = Path("/opt/SuGaR/output")

#     # obj 파일 찾기
#     for obj_p in sugar_output.rglob("*.obj"):
#         glb_p = str(obj_p).replace(".obj", ".glb")
#         try:
#             mesh = trimesh.load(str(obj_p), force="mesh")
#             mesh.export(glb_p)
#             assets.append({"format": "glb", "path": glb_p, "size": os.path.getsize(glb_p)})
#             logger.info(f"GLB 변환 완료: {glb_p}")
#         except Exception as e:
#             logger.warning(f"GLB 변환 실패: {e}")
#         assets.append({"format": "obj", "path": str(obj_p), "size": os.path.getsize(str(obj_p))})

#     # ply 파일 찾기 (SuGaR refined + 3DGS point cloud)
#     for ply in sugar_output.rglob("*.ply"):
#         assets.append({"format": "ply", "path": str(ply), "size": os.path.getsize(str(ply))})

#     # 3DGS point cloud (30000 스텝)
#     gs_ply = Path(output_dir) / "gs_pretrain" / "point_cloud" / "iteration_30000" / "point_cloud.ply"
#     if gs_ply.exists():
#         assets.append({"format": "ply", "path": str(gs_ply), "size": os.path.getsize(str(gs_ply))})

#     logger.info(f"[SuGaR] 에셋 목록: {[a['format'] for a in assets]}")
#     return assets

def _collect_assets(output_dir):
    import trimesh
    assets = []
    sugar_output = Path("/opt/SuGaR/output/refined_mesh")

    # OBJ + MTL + PNG 수집
    for obj_p in sugar_output.rglob("*.obj"):
        assets.append({"format": "obj", "path": str(obj_p), "size": os.path.getsize(str(obj_p))})
        # GLB 변환
        glb_p = str(obj_p).replace(".obj", ".glb")
        try:
            mesh = trimesh.load(str(obj_p), force="mesh")
            mesh.export(glb_p)
            assets.append({"format": "glb", "path": glb_p, "size": os.path.getsize(glb_p)})
        except Exception as e:
            logger.warning(f"GLB 변환 실패: {e}")
        # MTL
        mtl_p = str(obj_p).replace(".obj", ".mtl")
        if os.path.exists(mtl_p):
            assets.append({"format": "obj", "path": mtl_p, "size": os.path.getsize(mtl_p)})
        # PNG 텍스처
        for png in Path(obj_p).parent.glob("*.png"):
            assets.append({"format": "ply", "path": str(png), "size": os.path.getsize(str(png))})

    # 3DGS point cloud
    gs_ply = Path(output_dir) / "gs_pretrain" / "point_cloud" / "iteration_30000" / "point_cloud.ply"
    if not gs_ply.exists():
        gs_ply = Path(output_dir) / "gs_pretrain" / "point_cloud" / "iteration_10000" / "point_cloud.ply"
    if gs_ply.exists():
        assets.append({"format": "ply", "path": str(gs_ply), "size": os.path.getsize(str(gs_ply))})

    logger.info(f"[SuGaR] 에셋 목록: {[a['format'] for a in assets]}")
    return assets

@app.post("/process")
async def process(req: SuGaRRequest):
    os.makedirs(req.output_dir, exist_ok=True)
    gs_out = os.path.join(req.output_dir, "gs_pretrain")
    logger.info(f"[SuGaR] 3DGS 학습 ({req.gs_iterations:,}스텝)")

    train_cmd = [
        "python", "/opt/SuGaR/gaussian_splatting/train.py",
        "-s", req.dataset_dir,
        "-m", gs_out,
        "--iterations", str(req.gs_iterations),
        "--densify_until_iter", str(int(req.gs_iterations * 0.8)),
        "--white_background",
    ]
    # eval은 항상 False (이미지 수가 적을 때 문제 발생)
    # if req.eval:
    #     train_cmd.append("--eval")
    _exec(train_cmd, "3DGS학습")

    _patch_sugar(); _patch_cameras(gs_out)
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
    ]
    # eval 비활성화
    # if req.eval:
    #     cmd.append("--eval")
    if req.high_poly:
        cmd += ["--high_poly", "True"]
    _exec(cmd, "SuGaR", cwd="/opt/SuGaR")

    assets = _collect_assets(req.output_dir)
    logger.info(f"[SuGaR] 완료: {len(assets)}개 에셋")
    return {"assets": assets, "status": "success"}

@app.get("/health")
async def health():
    import torch
    return {"status":"ok","worker":"sugar","torch":torch.__version__,"cuda":torch.cuda.is_available()}
