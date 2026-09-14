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
        self._convert_to_ply(model_dir)
        logger.info(f"[COLMAP] 완료: {self.workspace}")
        return self.workspace

    def _feature_extraction(self):
        logger.info("[COLMAP] 특징점 추출")
        cmd = ["colmap","feature_extractor",
            "--database_path", self.database,
            # "--image_path", self.pattern_dir,
            "--image_path", self.upload_dir,
            # 같은 폰/카메라로 찍은 다각도 세트는 intrinsics 하나로 공유해야
            # 자유도가 줄어 포즈가 안정된다. 0(=이미지마다 다른 카메라) 이면
            # fx/fy/주점이 사진마다 흔들려 3DGS 가 빈 공간에 가우시안을 띄움
            # → refine 후 "스파이크 섬"이 다수 나오던 원인.
            "--ImageReader.single_camera","1",
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
                # RGBA → 흰 배경 합성 후 원본 파일명으로 저장.
                # BiRefNet 알파 가장자리는 0~255 그라데이션이라 그대로 합성하면
                # 가장자리에 반투명 회색 띠가 남아 3DGS 가 "공중에 떠있는
                # 가우시안" 으로 학습 → refine 후 본체 주변에 스파이크 섬을
                # 생산한다. 알파를 (a) 작은 값은 0, (b) 큰 값은 255 로 강하게
                # 이진화해 부드러운 가장자리를 제거하고, 안쪽으로 1px 침식해
                # 합성 후 흰 배경이 안쪽으로 살짝 깎이게 한다.
                import numpy as np
                from PIL import Image as PILImage
                dst = os.path.join(self.images_dir, src_img.name)
                rgba_img = PILImage.open(rgba_src).convert("RGBA")
                arr = np.array(rgba_img)
                alpha = arr[:, :, 3]
                # 강한 이진화 (소프트 엣지 제거)
                alpha = np.where(alpha >= 200, 255, 0).astype(np.uint8)
                # 1픽셀 침식 (수평·수직 이웃 모두 255 일 때만 255)
                try:
                    from scipy import ndimage as _ndi
                    alpha = _ndi.binary_erosion(alpha > 0, iterations=1).astype(np.uint8) * 255
                except Exception:
                    pass  # scipy 없으면 이진화까지만
                arr[:, :, 3] = alpha
                rgba_img = PILImage.fromarray(arr, "RGBA")
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

    def _convert_to_ply(self, model_dir):
        """sparse points3D 를 PLY 로 추출 — 프론트 포인트클라우드 미리보기용.

        주의: 파일명을 `points3D.ply` 로 쓰면 3DGS 의 dataset_readers.py 가
        "이미 3DGS 포맷으로 변환된 PLY" 로 오인해 자기네 fetchPly() 로 읽으려다
        실패하고 `pcd=None` → `'NoneType' object has no attribute 'points'` 로
        train.py 가 죽는다. 그래서 `points3D_preview.ply` 별도 파일에 쓴다.
        백엔드 `/preview` 가 같은 파일명을 찾도록 동기화돼 있어야 한다.
        """
        try:
            ply_path = os.path.join(model_dir, "points3D_preview.ply")
            self._run([
                "colmap", "model_converter",
                "--input_path", model_dir,
                "--output_path", ply_path,
                "--output_type", "PLY",
            ], "ply_converter")
            if os.path.exists(ply_path) and os.path.getsize(ply_path) > 0:
                logger.info(f"[COLMAP] points3D_preview.ply 생성: {os.path.getsize(ply_path)/1024:.1f}KB")
            else:
                logger.warning("[COLMAP] points3D_preview.ply 비어있음")
        except Exception as e:
            logger.warning(f"[COLMAP] PLY 변환 실패(무시): {e}")

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
