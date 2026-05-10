"""
ai_workers/video_processor/main.py
동영상 → 고품질 프레임 추출 Worker

기능:
1. ffmpeg으로 균등 간격 프레임 추출
2. 블러 프레임 자동 제거 (라플라시안 분산)
3. 유사 프레임 중복 제거 (히스토그램 비교)
4. 목표 장수에 맞게 균등 샘플링
"""
import os
import uuid
import subprocess
import shutil
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from loguru import logger

app = FastAPI(title="FigureForge3D - Video Processor")


def extract_frames_ffmpeg(video_path: str, output_dir: str, fps: float = 2.0) -> list[str]:
    """ffmpeg으로 균등 간격 프레임 추출"""
    os.makedirs(output_dir, exist_ok=True)
    out_pattern = os.path.join(output_dir, "frame_%05d.png")

    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"fps={fps}",
        "-q:v", "2",        # 고품질
        "-vsync", "vfr",
        out_pattern,
        "-y", "-loglevel", "error"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 실패: {result.stderr}")

    frames = sorted([str(p) for p in Path(output_dir).glob("frame_*.png")])
    logger.info(f"[VideoProc] ffmpeg 추출: {len(frames)}장")
    return frames


def calc_blur_score(img_gray: np.ndarray) -> float:
    """라플라시안 분산으로 블러 점수 계산 (높을수록 선명)"""
    return cv2.Laplacian(img_gray, cv2.CV_64F).var()


def calc_similarity(img1_gray: np.ndarray, img2_gray: np.ndarray) -> float:
    """히스토그램 상관관계로 유사도 계산 (1.0 = 동일)"""
    h1 = cv2.calcHist([img1_gray], [0], None, [64], [0, 256])
    h2 = cv2.calcHist([img2_gray], [0], None, [64], [0, 256])
    cv2.normalize(h1, h1)
    cv2.normalize(h2, h2)
    return cv2.compareHist(h1, h2, cv2.HISTCMP_CORREL)


def filter_frames(
    frame_paths: list[str],
    blur_threshold: float = 80.0,
    similarity_threshold: float = 0.97,
) -> list[str]:
    """블러 + 중복 프레임 제거"""
    if not frame_paths:
        return []

    logger.info(f"[VideoProc] 필터링 시작: {len(frame_paths)}장")

    # 1. 블러 제거
    sharp_frames = []
    for path in frame_paths:
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        score = calc_blur_score(img)
        if score >= blur_threshold:
            sharp_frames.append((path, img, score))
        else:
            logger.debug(f"[VideoProc] 블러 제거: {Path(path).name} (score={score:.1f})")

    logger.info(f"[VideoProc] 블러 제거 후: {len(sharp_frames)}장")

    if not sharp_frames:
        # 블러 임계값 낮춰서 재시도
        logger.warning(f"[VideoProc] 블러 임계값 완화 (40.0)")
        for path in frame_paths:
            img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                sharp_frames.append((path, img, calc_blur_score(img)))

    # 2. 중복 제거 (유사도 기반)
    unique_frames = [sharp_frames[0]]
    for i in range(1, len(sharp_frames)):
        curr_path, curr_img, _ = sharp_frames[i]
        prev_path, prev_img, _ = unique_frames[-1]
        sim = calc_similarity(curr_img, prev_img)
        if sim < similarity_threshold:
            unique_frames.append(sharp_frames[i])
        else:
            logger.debug(f"[VideoProc] 중복 제거: {Path(curr_path).name} (sim={sim:.3f})")

    logger.info(f"[VideoProc] 중복 제거 후: {len(unique_frames)}장")
    return [p for p, _, _ in unique_frames]


def sample_frames(frame_paths: list[str], target_count: int) -> list[str]:
    """목표 장수로 균등 샘플링"""
    if len(frame_paths) <= target_count:
        return frame_paths
    indices = np.linspace(0, len(frame_paths) - 1, target_count, dtype=int)
    sampled = [frame_paths[i] for i in indices]
    logger.info(f"[VideoProc] 균등 샘플링: {len(frame_paths)} → {len(sampled)}장")
    return sampled


def get_video_info(video_path: str) -> dict:
    """동영상 메타데이터 추출"""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams",
        "-select_streams", "v:0", video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return {"duration": 0, "fps": 30, "width": 0, "height": 0}
    import json
    data = json.loads(result.stdout)
    stream = data.get("streams", [{}])[0]
    fps_str = stream.get("r_frame_rate", "30/1")
    try:
        num, den = fps_str.split("/")
        fps = float(num) / float(den)
    except Exception:
        fps = 30.0
    duration = float(stream.get("duration", 0))
    return {
        "duration": round(duration, 2),
        "fps": round(fps, 2),
        "width": stream.get("width", 0),
        "height": stream.get("height", 0),
    }


@app.post("/process")
async def process_video(
    file: UploadFile = File(...),
    output_dir: str = Form("/shared/workspace/video"),
    target_frames: int = Form(60),       # 목표 프레임 수
    extraction_fps: float = Form(3.0),   # 초당 추출 프레임 수
    blur_threshold: float = Form(80.0),
    similarity_threshold: float = Form(0.97),
):
    """
    동영상 → 고품질 프레임 추출

    Returns:
        frames_dir: 추출된 프레임 폴더 경로
        frame_count: 최종 프레임 수
        video_info: 동영상 메타데이터
    """
    # 형식 확인
    allowed = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed:
        raise HTTPException(400, f"지원하지 않는 형식: {ext}. 지원: {', '.join(allowed)}")

    # 임시 저장
    tmp_dir = f"/tmp/video_{uuid.uuid4().hex}"
    os.makedirs(tmp_dir, exist_ok=True)
    video_path = os.path.join(tmp_dir, file.filename)

    logger.info(f"[VideoProc] 동영상 저장: {file.filename}")
    content = await file.read()
    with open(video_path, "wb") as f:
        f.write(content)

    # 동영상 정보
    video_info = get_video_info(video_path)
    logger.info(f"[VideoProc] 동영상 정보: {video_info}")

    # 출력 폴더
    frames_dir = os.path.join(output_dir, "frames")
    raw_dir = os.path.join(tmp_dir, "raw_frames")

    try:
        # 1. ffmpeg 프레임 추출
        raw_frames = extract_frames_ffmpeg(video_path, raw_dir, fps=extraction_fps)

        if not raw_frames:
            raise HTTPException(500, "프레임 추출 실패: 동영상에서 프레임을 읽을 수 없습니다")

        # 2. 블러 + 중복 제거
        filtered = filter_frames(raw_frames, blur_threshold, similarity_threshold)

        if len(filtered) < 5:
            logger.warning("[VideoProc] 필터링 후 프레임이 너무 적음 - 임계값 완화")
            filtered = filter_frames(raw_frames, blur_threshold * 0.5, 0.99)

        # 3. 목표 장수로 샘플링
        final_frames = sample_frames(filtered, target_frames)

        # 4. 최종 폴더에 저장 (0000.jpg 형식으로 리네이밍)
        os.makedirs(frames_dir, exist_ok=True)
        for i, src in enumerate(final_frames):
            dst = os.path.join(frames_dir, f"{i:04d}.jpg")
            img = cv2.imread(src)
            cv2.imwrite(dst, img, [cv2.IMWRITE_JPEG_QUALITY, 95])

        final_count = len(list(Path(frames_dir).glob("*.jpg")))
        logger.info(f"[VideoProc] 완료: {final_count}장 → {frames_dir}")

        return {
            "frames_dir": frames_dir,
            "frame_count": final_count,
            "video_info": video_info,
            "status": "success",
        }

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@app.post("/analyze")
async def analyze_video(file: UploadFile = File(...)):
    """동영상 정보만 빠르게 확인 (업로드 전 미리보기용)"""
    tmp_path = f"/tmp/analyze_{uuid.uuid4().hex}{Path(file.filename).suffix}"
    content = await file.read()
    with open(tmp_path, "wb") as f:
        f.write(content)
    try:
        info = get_video_info(tmp_path)
        estimated_frames_3fps = int(info["duration"] * 3)
        return {
            **info,
            "estimated_frames_3fps": estimated_frames_3fps,
            "recommended_target": min(60, max(20, estimated_frames_3fps)),
        }
    finally:
        os.remove(tmp_path)


@app.get("/health")
async def health():
    # ffmpeg 설치 확인
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
    has_ffmpeg = result.returncode == 0
    return {"status": "ok", "worker": "video_processor", "ffmpeg": has_ffmpeg}
