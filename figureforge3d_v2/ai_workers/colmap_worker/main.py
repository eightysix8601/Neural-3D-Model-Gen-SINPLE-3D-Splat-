"""COLMAP SfM 포즈 추정 Worker - CPU only"""
import os, sqlite3, subprocess
from pathlib import Path
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from loguru import logger

app = FastAPI(title="COLMAP Worker")

# class ColmapRequest(BaseModel):
#     pattern_dir: str; rgba_dir: str; workspace: str
class ColmapRequest(BaseModel):
    pattern_dir: str; rgba_dir: str; workspace: str
    upload_dir: str = ""

class ColmapRunner:
    # def __init__(self, pattern_dir, rgba_dir, workspace):
    #     self.pattern_dir = pattern_dir
    def __init__(self, pattern_dir, rgba_dir, workspace, upload_dir=""):
        self.pattern_dir = pattern_dir
        self.upload_dir = upload_dir if upload_dir else pattern_dir
        self.rgba_dir = rgba_dir
        self.workspace = workspace
        self.database = os.path.join(workspace, "database.db")
        self.sparse_dir = os.path.join(workspace, "sparse")
        self.images_dir = os.path.join(workspace, "images")
        os.makedirs(self.sparse_dir, exist_ok=True)
        os.makedirs(self.images_dir, exist_ok=True)

    def run(self) -> str:
        n_imgs = len(list(Path(self.pattern_dir).glob("*.png")))
        logger.info(f"[COLMAP] 시작: {n_imgs}장")
        self._feature_extraction()
        self._feature_matching(n_imgs)
        self._sparse_reconstruction()
        model_dir = os.path.join(self.sparse_dir, "0")
        if not os.path.exists(model_dir):
            raise RuntimeError(f"COLMAP 포즈 추정 실패. 현재 {n_imgs}장 (최소 20장 권장)")
        self._replace_with_rgba()
        self._convert_to_txt(model_dir)
        logger.info(f"[COLMAP] 완료: {self.workspace}")
        return self.workspace

    def _feature_extraction(self):
        logger.info("[COLMAP] 특징점 추출")
        cmd = ["colmap","feature_extractor",
            "--database_path", self.database,
            # "--image_path", self.pattern_dir,
            "--image_path", self.upload_dir,
            "--ImageReader.single_camera","0",
            "--ImageReader.camera_model","SIMPLE_PINHOLE",
            "--SiftExtraction.use_gpu","0",
            "--SiftExtraction.num_threads","4",
            "--SiftExtraction.max_num_features", "16384",
            "--SiftExtraction.max_image_size","3200",
            "--SiftExtraction.estimate_affine_shape", "1",
            "--SiftExtraction.domain_size_pooling", "1",]
        self._run(cmd, "feature_extraction")
        conn = sqlite3.connect(self.database)
        n = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]
        kp = conn.execute("SELECT COUNT(*) FROM keypoints").fetchone()[0]
        conn.close()
        logger.info(f"[COLMAP] 추출: {n}장, 키포인트 {kp}개")
        if n < 3: raise RuntimeError(f"COLMAP 이미지 인식 실패: {n}장")

    def _feature_matching(self, n_imgs):
        logger.info(f"[COLMAP] 매칭 ({n_imgs}장)")
        matcher = "exhaustive_matcher" if n_imgs <= 80 else "sequential_matcher"
        self._run(["colmap", matcher, "--database_path", self.database, "--SiftMatching.use_gpu","0"], "matching")

    def _sparse_reconstruction(self):
        logger.info("[COLMAP] 희소 재구성")
        self._run(["colmap","mapper",
            "--database_path", self.database,
            # "--image_path", self.pattern_dir,
            "--image_path", self.upload_dir,
            "--output_path", self.sparse_dir,
            "--Mapper.num_threads","16",
            "--Mapper.init_min_tri_angle","2",
            "--Mapper.multiple_models","0",
            "--Mapper.init_max_error","4",
            "--Mapper.abs_pose_min_num_inliers","10",
            "--Mapper.abs_pose_min_inlier_ratio","0.1",
            "--Mapper.ba_global_max_num_iterations","20"], "mapper")

    # def _replace_with_rgba(self):
    #     import shutil
    #     rgba_map = {p.stem.replace("_rgba",""): str(p) for p in Path(self.rgba_dir).iterdir() if p.suffix.lower()==".png"}
    #     for pat in Path(self.pattern_dir).glob("*.png"):
    #         dst = os.path.join(self.images_dir, pat.name)
    #         shutil.copy(rgba_map.get(pat.stem, str(pat)), dst)
    #     logger.info(f"[COLMAP] RGBA 교체 완료")
    def _replace_with_rgba(self):
        import shutil
        rgba_map = {
            p.stem.replace("_rgba", ""): str(p)
            for p in Path(self.rgba_dir).iterdir()
            if p.suffix.lower() == ".png"
        }
        # upload_dir의 원본 파일명 기준으로 교체
        src_dir = Path(self.upload_dir) if self.upload_dir else Path(self.pattern_dir)
        src_imgs = sorted(list(src_dir.iterdir()))
        logger.info(f"[COLMAP] RGBA 교체: {len(src_imgs)}장")
        for src_img in src_imgs:
            if src_img.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                continue
            stem = src_img.stem
            rgba_src = rgba_map.get(stem)
            if rgba_src:
                # RGBA → 흰 배경 합성 후 원본 파일명으로 저장
                from PIL import Image as PILImage
                dst = os.path.join(self.images_dir, src_img.name)
                rgba_img = PILImage.open(rgba_src).convert("RGBA")
                bg = PILImage.new("RGB", rgba_img.size, (255, 255, 255))
                bg.paste(rgba_img, mask=rgba_img.split()[3])
                bg.save(dst, quality=95)
            else:
                dst = os.path.join(self.images_dir, src_img.name)
                shutil.copy(str(src_img), dst)

    def _convert_to_txt(self, model_dir):
        try:
            self._run(["colmap","model_converter","--input_path",model_dir,"--output_path",model_dir,"--output_type","TXT"], "converter")
            logger.info("[COLMAP] .bin→.txt 완료")
        except Exception as e:
            logger.warning(f"[COLMAP] txt 변환 실패(무시): {e}")

    def _run(self, cmd, step):
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["DISPLAY"] = ""
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if result.returncode != 0:
            raise RuntimeError(f"COLMAP {step} 실패 (exit={result.returncode})\n{result.stderr[-800:]}")

@app.post("/process")
async def process(req: ColmapRequest):
    # runner = ColmapRunner(req.pattern_dir, req.rgba_dir, req.workspace)
    runner = ColmapRunner(req.pattern_dir, req.rgba_dir, req.workspace, req.upload_dir)
    dataset_dir = runner.run()
    return {"dataset_dir": dataset_dir, "status": "success"}

@app.get("/health")
async def health(): return {"status": "ok", "worker": "colmap"}
