"""Projects API"""
import uuid, os, io
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from PIL import Image
from loguru import logger
from app.db.session import get_db
from app.db.models.project import Project, ProjectImage, Asset, JobStatus, AssetFormat
from app.schemas.project import (ProjectCreate, ProjectResponse, ProjectListResponse,
    PipelineStartRequest, PipelineStatusResponse)
from app.services.storage import storage_service
from app.tasks.pipeline import run_pipeline
from app.core.config import settings
import httpx
from app.core.config import settings  # VIDEO_PROCESSOR_URL 사용

router = APIRouter(prefix="/projects", tags=["Projects"])

@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(body: ProjectCreate, db: AsyncSession = Depends(get_db)):
    project = Project(name=body.name, description=body.description, model_type=body.model_type,
        pipeline_config=body.pipeline_config,
        upload_dir=f"{settings.UPLOAD_DIR}/{uuid.uuid4().hex}",
        output_dir=f"{settings.OUTPUT_DIR}/{uuid.uuid4().hex}")
    db.add(project)
    await db.flush()
    os.makedirs(project.upload_dir, exist_ok=True)
    os.makedirs(project.output_dir, exist_ok=True)
    result = await db.execute(select(Project).options(selectinload(Project.assets), selectinload(Project.images)).where(Project.id == project.id))
    return result.scalar_one()

@router.get("", response_model=List[ProjectListResponse])
async def list_projects(skip: int = 0, limit: int = 20, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).order_by(Project.created_at.desc()).offset(skip).limit(limit))
    projects = result.scalars().all()
    response = []
    for p in projects:
        item = ProjectListResponse.model_validate(p)
        img_r = await db.execute(select(ProjectImage).where(ProjectImage.project_id == p.id).limit(1))
        first = img_r.scalar_one_or_none()
        if first and first.thumbnail_key:
            item.thumbnail_url = storage_service.get_presigned_url(first.thumbnail_key)
        response.append(item)
    return response

@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).options(selectinload(Project.assets), selectinload(Project.images)).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project: raise HTTPException(404, "프로젝트 없음")
    response = ProjectResponse.model_validate(project)
    for asset in response.assets:
        db_asset = next((a for a in project.assets if a.id == asset.id), None)
        if db_asset: asset.download_url = storage_service.get_presigned_url(db_asset.storage_key)
    for img in response.images:
        db_img = next((i for i in project.images if i.id == img.id), None)
        if db_img and db_img.thumbnail_key: img.thumbnail_url = storage_service.get_presigned_url(db_img.thumbnail_key)
    return response

@router.post("/{project_id}/images", status_code=201)
async def upload_images(project_id: uuid.UUID, files: List[UploadFile] = File(...), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project: raise HTTPException(404, "프로젝트 없음")
    if project.status not in (JobStatus.PENDING, JobStatus.FAILED): raise HTTPException(400, "처리 중인 프로젝트")
    if len(files) > 200: raise HTTPException(400, "최대 200장")
    if len(files) < 3: raise HTTPException(400, "최소 3장 이상 업로드하세요 (권장: 20장 이상)")

    for idx, file in enumerate(files):
        if not file.content_type.startswith("image/"): raise HTTPException(400, f"{file.filename}은 이미지가 아님")
        raw = await file.read()
        try:
            img = Image.open(io.BytesIO(raw)); w, h = img.size
        except Exception:
            raise HTTPException(400, f"{file.filename} 읽기 실패")
        storage_key = storage_service.upload_file(raw, file.filename, file.content_type, prefix=f"projects/{project_id}/images")
        img.thumbnail((400, 400))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=85)
        thumbnail_key = storage_service.upload_file(buf.getvalue(), f"thumb_{file.filename}", "image/jpeg", prefix=f"projects/{project_id}/thumbnails")
        ext = os.path.splitext(file.filename)[1] or ".jpg"
        local = os.path.join(project.upload_dir, f"{idx:04d}{ext}")
        with open(local, "wb") as fp: fp.write(raw)
        db.add(ProjectImage(project_id=project.id, filename=file.filename, storage_key=storage_key,
            thumbnail_key=thumbnail_key, file_size=len(raw), width=w, height=h, order_index=idx))

    project.image_count = len(files)
    await db.flush()
    return {"uploaded": len(files), "message": f"{len(files)}장 업로드 완료"}

# ── 추가할 라우터 1: 동영상 업로드 ───────────────────────────────────────────
@router.post("/{project_id}/video", status_code=201)
async def upload_video(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    target_frames: int = 60,
    extraction_fps: float = 3.0,
    blur_threshold: float = 80.0,
    db: AsyncSession = Depends(get_db),
):
    """
    동영상 업로드 → 프레임 추출 → 이미지로 저장
    
    - target_frames: 최종 추출할 프레임 수 (기본 60장)
    - extraction_fps: 초당 추출 FPS (기본 3.0)
    - blur_threshold: 블러 제거 임계값 (높을수록 엄격, 기본 80.0)
    """
    from sqlalchemy import select
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "프로젝트 없음")
    if project.status not in (JobStatus.PENDING, JobStatus.FAILED):
        raise HTTPException(400, "처리 중인 프로젝트에는 업로드 불가")

    # 형식 확인
    allowed_types = {"video/mp4", "video/quicktime", "video/x-msvideo", "video/webm", "video/x-matroska"}
    allowed_exts  = {".mp4", ".mov", ".avi", ".webm", ".mkv", ".m4v"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_exts:
        raise HTTPException(400, f"지원하지 않는 형식: {ext}")

    logger.info(f"[API] 동영상 업로드: {file.filename} → project {project_id}")

    # video_processor Worker로 전달
    video_output_dir = os.path.join(project.output_dir, "video_frames")
    os.makedirs(video_output_dir, exist_ok=True)

    content = await file.read()

    async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client:
        resp = await client.post(
            f"{settings.VIDEO_PROCESSOR_URL}/process",
            files={"file": (file.filename, content, file.content_type or "video/mp4")},
            data={
                "output_dir": video_output_dir,
                "target_frames": str(target_frames),
                "extraction_fps": str(extraction_fps),
                "blur_threshold": str(blur_threshold),
            },
        )
        if resp.status_code != 200:
            raise HTTPException(500, f"프레임 추출 실패: {resp.text}")
        result_data = resp.json()

    frames_dir = result_data["frames_dir"]
    frame_count = result_data["frame_count"]
    video_info  = result_data["video_info"]

    if frame_count < 3:
        raise HTTPException(500, f"추출된 프레임이 너무 적습니다: {frame_count}장")

    # 추출된 프레임을 upload_dir로 복사 + DB 저장
    from pathlib import Path
    import shutil
    frame_files = sorted(Path(frames_dir).glob("*.jpg"))

    for idx, frame_path in enumerate(frame_files):
        # upload_dir로 복사
        dst = os.path.join(project.upload_dir, f"{idx:04d}.jpg")
        shutil.copy(str(frame_path), dst)

        # MinIO 업로드
        with open(dst, "rb") as fp:
            raw = fp.read()
        storage_key = storage_service.upload_file(
            raw, frame_path.name, "image/jpeg",
            prefix=f"projects/{project_id}/images"
        )

        # 썸네일
        from PIL import Image as PILImage
        img = PILImage.open(dst)
        img.thumbnail((400, 400))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=85)
        thumbnail_key = storage_service.upload_file(
            buf.getvalue(), f"thumb_{frame_path.name}", "image/jpeg",
            prefix=f"projects/{project_id}/thumbnails"
        )

        w, h = img.size
        db.add(ProjectImage(
            project_id=project.id,
            filename=frame_path.name,
            storage_key=storage_key,
            thumbnail_key=thumbnail_key,
            file_size=len(raw),
            width=w, height=h,
            order_index=idx,
        ))

    project.image_count = frame_count
    await db.flush()

    logger.info(f"[API] 동영상 처리 완료: {frame_count}장 프레임 추출")
    return {
        "frame_count": frame_count,
        "video_info": video_info,
        "message": f"동영상에서 {frame_count}장 프레임 추출 완료",
    }


# ── 추가할 라우터 2: 동영상 분석 미리보기 ────────────────────────────────────
@router.post("/{project_id}/analyze-video")
async def analyze_video(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
):
    """
    동영상 업로드 없이 정보만 미리 확인
    (파일 크기, 길이, 예상 프레임 수 등)
    """
    content = await file.read()
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        resp = await client.post(
            f"{settings.VIDEO_PROCESSOR_URL}/analyze",
            files={"file": (file.filename, content, file.content_type or "video/mp4")},
        )
        if resp.status_code != 200:
            raise HTTPException(500, f"분석 실패: {resp.text}")
        return resp.json()



@router.post("/{project_id}/run")
async def run_reconstruction(project_id: uuid.UUID, body: PipelineStartRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project: raise HTTPException(404, "프로젝트 없음")
    if project.status == JobStatus.RUNNING: raise HTTPException(400, "이미 실행 중")
    img_r = await db.execute(select(ProjectImage).where(ProjectImage.project_id == project.id).limit(1))
    if not img_r.scalar_one_or_none(): raise HTTPException(400, "이미지를 먼저 업로드하세요")

    task = run_pipeline.apply_async(kwargs={"project_id": str(project.id), "config": {
        "model_type": project.model_type, "upload_dir": project.upload_dir,
        "output_dir": project.output_dir, "gs_iterations": body.gs_iterations,
        "refinement_time": body.refinement_time, "high_poly": body.high_poly,
        **project.pipeline_config}}, queue="pipeline")

    project.status = JobStatus.RUNNING; project.celery_job_id = task.id
    project.progress = 0; project.current_step = "파이프라인 시작 중..."; project.error_message = None
    return {"job_id": task.id, "message": "파이프라인 시작"}

@router.get("/{project_id}/status", response_model=PipelineStatusResponse)
async def get_status(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project: raise HTTPException(404, "프로젝트 없음")
    return PipelineStatusResponse(job_id=project.celery_job_id or "", status=project.status,
        progress=project.progress, current_step=project.current_step, error_message=project.error_message)

@router.get("/{project_id}/assets/{asset_id}/download")
async def get_download_url(project_id: uuid.UUID, asset_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Asset).where(Asset.id == asset_id, Asset.project_id == project_id))
    asset = result.scalar_one_or_none()
    if not asset: raise HTTPException(404, "에셋 없음")
    asset.download_count += 1
    return {"download_url": storage_service.get_presigned_url(asset.storage_key), "format": asset.format}

@router.get("/{project_id}/preview")
async def get_preview(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    현재 진행 단계에 맞는 미리보기 파일 URL 반환
    progress < 30%  → None
    progress 30~54% → COLMAP sparse pointcloud
    progress 55~91% → 3DGS iteration_7000
    progress >= 92% → 3DGS iteration_30000
    status SUCCESS  → GLB
    """
    from pathlib import Path
    from sqlalchemy import select

    r = await db.execute(select(Project).where(Project.id == project_id))
    project = r.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "프로젝트 없음")

    progress = project.progress or 0
    output_dir = project.output_dir or ""

    # 완료 → GLB
    if project.status == "SUCCESS":
        r2 = await db.execute(
            select(Asset).where(
                Asset.project_id == project_id,
                Asset.format == AssetFormat.GLB
            ).limit(1)
        )
        asset = r2.scalar_one_or_none()
        if asset:
            return {
                "type": "glb",
                "url": storage_service.get_presigned_url(asset.storage_key),
                "progress": 100,
                "label": "완성된 3D 메쉬",
                "stage": "mesh",
            }

    if not output_dir or progress < 30:
        return {"type": None, "url": None, "progress": progress, "label": "처리 준비 중..."}

    ws = os.path.join(output_dir, "workspace")

    def _upload_and_url(ply_path: str) -> str | None:
        if not os.path.exists(ply_path):
            return None
        try:
            key = storage_service.upload_from_path(
                ply_path, prefix=f"projects/{project_id}/preview"
            )
            url = storage_service.get_presigned_url(key)
            url = url.replace("http://minio:9000", "http://localhost:9000")
            return url
        except Exception:
            return None

    # COLMAP sparse (30~54%)
    if progress < 55:
        url = _upload_and_url(os.path.join(ws, "colmap", "sparse", "0", "points3D.ply"))
        if url:
            return {
                "type": "pointcloud", "url": url,
                "progress": progress, "label": "COLMAP 포즈 추정 결과",
                "stage": "colmap", "point_size": 3, "color": "#4ade80",
            }

    # 3DGS 7k (55~74%)
    if progress < 75:
        url = _upload_and_url(os.path.join(
            output_dir, "reconstruction", "gs_pretrain",
            "point_cloud", "iteration_7000", "point_cloud.ply"
        ))
        if url:
            return {
                "type": "pointcloud", "url": url,
                "progress": progress, "label": "3DGS 중간 결과 (7k 스텝)",
                "stage": "gs7k", "point_size": 1.2, "color": "#c084fc",
            }

    # 3DGS 30k (75%+)
    url = _upload_and_url(os.path.join(
        output_dir, "reconstruction", "gs_pretrain",
        "point_cloud", "iteration_30000", "point_cloud.ply"
    ))
    if url:
        return {
            "type": "pointcloud", "url": url,
            "progress": progress, "label": "3DGS 완료 (30k 스텝)",
            "stage": "gs30k", "point_size": 1, "color": "#60a5fa",
        }

    # 폴백 → COLMAP sparse (어떤 단계든 있으면 표시)
    url = _upload_and_url(os.path.join(ws, "colmap", "sparse", "0", "points3D.ply"))
    if url:
        return {
            "type": "pointcloud", "url": url,
            "progress": progress, "label": f"COLMAP 포인트클라우드 ({progress}% 진행 중)",
            "stage": "colmap", "point_size": 3, "color": "#4ade80",
        }

    return {"type": None, "url": None, "progress": progress, "label": "결과 준비 중..."}


@router.get("/{project_id}/preview/file")
async def get_preview_file(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """PLY 파일을 백엔드가 직접 스트리밍 (CORS 우회)"""
    from fastapi.responses import StreamingResponse
    from sqlalchemy import select

    r = await db.execute(select(Project).where(Project.id == project_id))
    project = r.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "없음")

    output_dir = project.output_dir or ""
    ws = os.path.join(output_dir, "workspace")

    candidates = [
        os.path.join(output_dir, "reconstruction", "gs_pretrain", "point_cloud", "iteration_30000", "point_cloud.ply"),
        os.path.join(output_dir, "reconstruction", "gs_pretrain", "point_cloud", "iteration_10000", "point_cloud.ply"),
        os.path.join(output_dir, "reconstruction", "gs_pretrain", "point_cloud", "iteration_7000", "point_cloud.ply"),
        os.path.join(ws, "colmap", "sparse", "0", "points3D.ply"),
    ]

    ply_path = None
    for c in candidates:
        if os.path.exists(c):
            ply_path = c
            break

    if not ply_path:
        raise HTTPException(404, "PLY 없음")

    def iter_file():
        with open(ply_path, "rb") as f:
            while chunk := f.read(65536):
                yield chunk

    return StreamingResponse(
        iter_file(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename=preview.ply",
            "Access-Control-Allow-Origin": "*",
        }
    )


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).options(selectinload(Project.assets), selectinload(Project.images)).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project: raise HTTPException(404, "프로젝트 없음")
    for img in project.images:
        if img.storage_key: storage_service.delete_file(img.storage_key)
        if img.thumbnail_key: storage_service.delete_file(img.thumbnail_key)
    for asset in project.assets:
        if asset.storage_key: storage_service.delete_file(asset.storage_key)
    await db.delete(project)
