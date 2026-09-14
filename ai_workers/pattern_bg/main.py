"""패턴 배경 합성 Worker - CPU only"""
import os
import numpy as np
from pathlib import Path
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from PIL import Image
from loguru import logger

app = FastAPI(title="Pattern BG Worker")

class ProcessRequest(BaseModel):
    rgba_dir: str; output_dir: str; tile_size: int = 60

def synthesize_checker(rgba: Image.Image, tile_size=60):
    img_np = np.array(rgba.convert("RGBA"))
    H, W = img_np.shape[:2]
    checker = np.zeros((H, W, 3), dtype=np.uint8)
    for y in range(0, H, tile_size):
        for x in range(0, W, tile_size):
            color = (220,220,220) if ((x//tile_size + y//tile_size) % 2 == 0) else (30,30,30)
            checker[y:y+tile_size, x:x+tile_size] = color
    alpha = img_np[:,:,3:4].astype(np.float32) / 255.0
    rgb = img_np[:,:,:3].astype(np.float32)
    result = (rgb * alpha + checker.astype(np.float32) * (1 - alpha)).astype(np.uint8)
    return Image.fromarray(result)

@app.post("/process")
async def process(req: ProcessRequest):
    os.makedirs(req.output_dir, exist_ok=True)
    images = sorted([p for p in Path(req.rgba_dir).iterdir() if p.suffix.lower() in {".png",".jpg",".jpeg"}])
    if not images: raise HTTPException(400, f"RGBA 이미지 없음: {req.rgba_dir}")
    logger.info(f"[PatternBg] {len(images)}장 처리")
    for img_path in images:
        stem = img_path.stem.replace("_rgba", "")
        result = synthesize_checker(Image.open(str(img_path)), req.tile_size)
        result.save(os.path.join(req.output_dir, f"{stem}.png"))
    return {"output_dir": req.output_dir, "count": len(images)}

@app.get("/health")
async def health(): return {"status": "ok", "worker": "pattern_bg"}
