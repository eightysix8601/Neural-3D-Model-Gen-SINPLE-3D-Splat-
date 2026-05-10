"""배경 분리 Worker - BiRefNet (torch 2.0+cu118)"""
import os, io, uuid
import numpy as np
import cv2
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from PIL import Image
from loguru import logger

app = FastAPI(title="BG Removal Worker")
_model = None

def _load_model():
    global _model
    if _model is not None: return _model
    import torch
    from transformers import AutoModelForImageSegmentation
    logger.info("[BiRefNet] 모델 로드 중...")
    _model = AutoModelForImageSegmentation.from_pretrained(
        "ZhengPeng7/BiRefNet", trust_remote_code=True, cache_dir="/weights/birefnet")
    _model.to("cuda").eval()
    logger.info("[BiRefNet] 로드 완료")
    return _model

def remove_bg(image_path: str):
    import torch
    from torchvision import transforms
    model = _load_model()
    img = Image.open(image_path).convert("RGB")
    orig_w, orig_h = img.size
    tf = transforms.Compose([transforms.Resize((1024, 1024)), transforms.ToTensor(),
        transforms.Normalize([0.485,0.456,0.406],[0.229,0.224,0.225])])
    inp = tf(img).unsqueeze(0).to("cuda")
    with torch.no_grad():
        preds = model(inp)[-1].sigmoid()
    mask_t = torch.nn.functional.interpolate(preds, size=(orig_h, orig_w), mode="bilinear", align_corners=False).squeeze()
    mask = (mask_t.cpu().numpy() * 255).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=3)
    _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    rgba = img.convert("RGBA")
    r, g, b, _ = rgba.split()
    rgba = Image.merge("RGBA", (r, g, b, Image.fromarray(mask)))
    return mask, rgba

@app.post("/process")
async def process(files: list[UploadFile] = File(...), output_dir: str = Form("/shared/workspace/bg_removal")):
    if not files: raise HTTPException(400, "이미지 없음")
    mask_dir = os.path.join(output_dir, "masks")
    rgba_dir = os.path.join(output_dir, "rgba")
    os.makedirs(mask_dir, exist_ok=True)
    os.makedirs(rgba_dir, exist_ok=True)
    tmp_dir = f"/tmp/bg_{uuid.uuid4().hex}"
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_paths = []
    for f in files:
        tp = os.path.join(tmp_dir, f.filename)
        with open(tp, "wb") as fp: fp.write(await f.read())
        tmp_paths.append((f.filename, tp))
    logger.info(f"[BgRemoval] {len(tmp_paths)}장 처리")
    for i, (fname, tp) in enumerate(tmp_paths):
        stem = Path(fname).stem
        try:
            mask, rgba = remove_bg(tp)
            cv2.imwrite(os.path.join(mask_dir, f"{stem}_mask.png"), mask)
            rgba.save(os.path.join(rgba_dir, f"{stem}_rgba.png"))
            logger.info(f"[BgRemoval] {i+1}/{len(tmp_paths)}: {fname}")
        except Exception as e:
            logger.error(f"[BgRemoval] {fname} 실패: {e}")
    import shutil; shutil.rmtree(tmp_dir, ignore_errors=True)
    return {"mask_dir": mask_dir, "rgba_dir": rgba_dir, "count": len(tmp_paths)}

@app.get("/health")
async def health(): return {"status": "ok", "worker": "bg_removal"}
