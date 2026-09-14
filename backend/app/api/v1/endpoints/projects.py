"""Projects API.

owner_id 가 있는 프로젝트는 본인만 수정/삭제. 비공개 프로젝트는 본인만 GET.
공개 프로젝트는 비로그인도 GET (조회수 증가). 좋아요는 로그인 필수.
스마트 메시(TRIPO) 모드는 이미지 1장만 받아 별도 워커로 라우팅한다.
"""
import uuid, os, io
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from sqlalchemy.orm import selectinload
from PIL import Image
from loguru import logger
from app.db.session import get_db
from app.db.models.project import (
    Project, ProjectImage, Asset, JobStatus, AssetFormat, ModelType, Category,
)
from app.db.models.user import User, Like
from app.schemas.project import (
    ProjectCreate, ProjectUpdate, ProjectResponse, ProjectListResponse,
    PipelineStartRequest, PipelineStatusResponse,
)
from app.services.storage import storage_service
from app.tasks.pipeline import run_pipeline
from app.core.config import settings
from app.api.deps import get_current_user, get_current_user_optional
import httpx

router = APIRouter(prefix="/projects", tags=["Projects"])


def _ensure_can_view(project: Project, user: Optional[User]):
    if project.is_public:
        return
    if not user or (project.owner_id and project.owner_id != user.id and not user.is_admin):
        raise HTTPException(403, "접근 권한이 없습니다")


def _ensure_can_modify(project: Project, user: User):
    if project.owner_id and project.owner_id != user.id and not user.is_admin:
        raise HTTPException(403, "본인 프로젝트가 아닙니다")


async def _build_response(project: Project, user: Optional[User], db: AsyncSession) -> ProjectResponse:
    response = ProjectResponse.model_validate(project)
    for asset in response.assets:
        db_asset = next((a for a in project.assets if a.id == asset.id), None)
        if db_asset:
            asset.download_url = storage_service.get_presigned_url(db_asset.storage_key)
    for img in response.images:
        db_img = next((i for i in project.images if i.id == img.id), None)
        if db_img and db_img.thumbnail_key:
            img.thumbnail_url = storage_service.get_presigned_url(db_img.thumbnail_key)
    if user:
        r = await db.execute(select(Like.id).where(Like.user_id == user.id, Like.project_id == project.id))
        response.liked_by_me = r.scalar_one_or_none() is not None
    return response


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(body: ProjectCreate,
                         user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    project = Project(
        owner_id=user.id,
        name=body.name, description=body.description,
        model_type=body.model_type,
        category=body.category,
        prompt=body.prompt,
        pipeline_config=body.pipeline_config,
        upload_dir=f"{settings.UPLOAD_DIR}/{uuid.uuid4().hex}",
        output_dir=f"{settings.OUTPUT_DIR}/{uuid.uuid4().hex}",
    )
    db.add(project)
    await db.flush()
    os.makedirs(project.upload_dir, exist_ok=True)
    os.makedirs(project.output_dir, exist_ok=True)
    result = await db.execute(
        select(Project).options(
            selectinload(Project.assets), selectinload(Project.images),
            selectinload(Project.owner),
        ).where(Project.id == project.id)
    )
    p = result.scalar_one()
    return await _build_response(p, user, db)


@router.get("", response_model=List[ProjectListResponse])
async def list_my_projects(skip: int = 0, limit: int = 50,
                           user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    """현재 로그인한 사용자의 프로젝트 목록 (모든 상태 포함)."""
    result = await db.execute(
        select(Project).options(selectinload(Project.owner))
        .where(Project.owner_id == user.id)
        .order_by(Project.created_at.desc()).offset(skip).limit(limit)
    )
    projects = result.scalars().all()
    response = []
    for p in projects:
        item = ProjectListResponse.model_validate(p)
        # 우선순위: cover_image_key (워커가 만든 4면 정면 PNG) > 첫 입력 이미지 썸네일
        if p.cover_image_key:
            item.thumbnail_url = storage_service.get_presigned_url(p.cover_image_key)
        else:
            img_r = await db.execute(
                select(ProjectImage).where(ProjectImage.project_id == p.id)
                .order_by(ProjectImage.order_index).limit(1)
            )
            first = img_r.scalar_one_or_none()
            if first and first.thumbnail_key:
                item.thumbnail_url = storage_service.get_presigned_url(first.thumbnail_key)
        response.append(item)
    return response


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: uuid.UUID,
                      user: Optional[User] = Depends(get_current_user_optional),
                      db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Project).options(
            selectinload(Project.assets), selectinload(Project.images),
            selectinload(Project.owner),
        ).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "프로젝트 없음")
    _ensure_can_view(project, user)
    # 공개 프로젝트면서 본인 아닐 때만 조회수 증가
    if project.is_public and (not user or user.id != project.owner_id):
        await db.execute(update(Project).where(Project.id == project.id).values(view_count=Project.view_count + 1))
        project.view_count = (project.view_count or 0) + 1
    return await _build_response(project, user, db)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: uuid.UUID, body: ProjectUpdate,
                         user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    # 1) 권한 체크 & PATCH 적용은 가벼운 select 로
    r = await db.execute(select(Project).where(Project.id == project_id))
    project = r.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "프로젝트 없음")
    _ensure_can_modify(project, user)

    publishing = body.is_public is True and not project.is_public
    if publishing and project.status != JobStatus.SUCCESS:
        raise HTTPException(400, "완료된 프로젝트만 공개할 수 있습니다")

    patch = body.model_dump(exclude_unset=True)
    for k, v in patch.items():
        setattr(project, k, v)
    await db.flush()

    # 2) 응답용으로 관계 포함해서 다시 fresh 로드 (stale relationship 회피)
    result = await db.execute(
        select(Project).options(
            selectinload(Project.assets), selectinload(Project.images),
            selectinload(Project.owner),
        ).where(Project.id == project_id)
    )
    project = result.scalar_one()
    return await _build_response(project, user, db)


@router.post("/{project_id}/images", status_code=201)
async def upload_images(project_id: uuid.UUID,
                        files: List[UploadFile] = File(...),
                        user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project: raise HTTPException(404, "프로젝트 없음")
    _ensure_can_modify(project, user)
    if project.status not in (JobStatus.PENDING, JobStatus.FAILED):
        raise HTTPException(400, "처리 중인 프로젝트")
    if len(files) > 200: raise HTTPException(400, "최대 200장")

    # TRIPO 모드는 단일 이미지로 충분, 그 외는 최소 3장 권장
    min_required = 1 if project.model_type == ModelType.TRIPO else 3
    if len(files) < min_required:
        raise HTTPException(400, f"최소 {min_required}장 이상 업로드하세요")

    for idx, file in enumerate(files):
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(400, f"{file.filename}은 이미지가 아님")
        raw = await file.read()
        try:
            img = Image.open(io.BytesIO(raw)); w, h = img.size
        except Exception:
            raise HTTPException(400, f"{file.filename} 읽기 실패")
        storage_key = storage_service.upload_file(
            raw, file.filename, file.content_type,
            prefix=f"projects/{project_id}/images",
        )
        img.thumbnail((400, 400))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=85)
        thumbnail_key = storage_service.upload_file(
            buf.getvalue(), f"thumb_{file.filename}", "image/jpeg",
            prefix=f"projects/{project_id}/thumbnails",
        )
        ext = os.path.splitext(file.filename or "")[1] or ".jpg"
        local = os.path.join(project.upload_dir, f"{idx:04d}{ext}")
        with open(local, "wb") as fp: fp.write(raw)
        db.add(ProjectImage(
            project_id=project.id, filename=file.filename or f"img_{idx}{ext}",
            storage_key=storage_key, thumbnail_key=thumbnail_key,
            file_size=len(raw), width=w, height=h, order_index=idx,
        ))

    project.image_count = len(files)
    if not project.cover_image_key:
        # 첫 이미지의 storage_key 를 cover 로
        first_img_r = await db.execute(
            select(ProjectImage).where(ProjectImage.project_id == project.id)
            .order_by(ProjectImage.order_index).limit(1)
        )
        first_img = first_img_r.scalar_one_or_none()
        if first_img:
            project.cover_image_key = first_img.thumbnail_key or first_img.storage_key
    await db.flush()
    return {"uploaded": len(files), "message": f"{len(files)}장 업로드 완료"}


@router.post("/{project_id}/video", status_code=201)
async def upload_video(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    target_frames: int = Form(60),
    extraction_fps: float = Form(3.0),
    blur_threshold: float = Form(80.0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project: raise HTTPException(404, "프로젝트 없음")
    _ensure_can_modify(project, user)
    if project.status not in (JobStatus.PENDING, JobStatus.FAILED):
        raise HTTPException(400, "처리 중인 프로젝트에는 업로드 불가")

    allowed_exts = {".mp4", ".mov", ".avi", ".webm", ".mkv", ".m4v"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed_exts:
        raise HTTPException(400, f"지원하지 않는 형식: {ext}")

    logger.info(f"[API] 동영상 업로드: {file.filename} → project {project_id}")
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

    from pathlib import Path
    import shutil
    frame_files = sorted(Path(frames_dir).glob("*.jpg"))
    for idx, frame_path in enumerate(frame_files):
        dst = os.path.join(project.upload_dir, f"{idx:04d}.jpg")
        shutil.copy(str(frame_path), dst)
        with open(dst, "rb") as fp: raw = fp.read()
        storage_key = storage_service.upload_file(
            raw, frame_path.name, "image/jpeg",
            prefix=f"projects/{project_id}/images",
        )
        img = Image.open(dst)
        img.thumbnail((400, 400))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=85)
        thumbnail_key = storage_service.upload_file(
            buf.getvalue(), f"thumb_{frame_path.name}", "image/jpeg",
            prefix=f"projects/{project_id}/thumbnails",
        )
        w, h = img.size
        db.add(ProjectImage(
            project_id=project.id, filename=frame_path.name,
            storage_key=storage_key, thumbnail_key=thumbnail_key,
            file_size=len(raw), width=w, height=h, order_index=idx,
        ))

    project.image_count = frame_count
    await db.flush()
    logger.info(f"[API] 동영상 처리 완료: {frame_count}장 프레임 추출")
    return {"frame_count": frame_count, "video_info": video_info,
            "message": f"동영상에서 {frame_count}장 프레임 추출 완료"}


@router.post("/{project_id}/analyze-video")
async def analyze_video(project_id: uuid.UUID, file: UploadFile = File(...),
                        user: User = Depends(get_current_user)):
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
async def run_reconstruction(project_id: uuid.UUID, body: PipelineStartRequest,
                             user: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project: raise HTTPException(404, "프로젝트 없음")
    _ensure_can_modify(project, user)
    if project.status == JobStatus.RUNNING: raise HTTPException(400, "이미 실행 중")
    img_r = await db.execute(select(ProjectImage).where(ProjectImage.project_id == project.id).limit(1))
    if not img_r.scalar_one_or_none():
        raise HTTPException(400, "이미지를 먼저 업로드하세요")

    task = run_pipeline.apply_async(kwargs={"project_id": str(project.id), "config": {
        "model_type": project.model_type.value if hasattr(project.model_type, "value") else str(project.model_type),
        "upload_dir": project.upload_dir,
        "output_dir": project.output_dir,
        "gs_iterations": body.gs_iterations,
        "refinement_time": body.refinement_time,
        "high_poly": body.high_poly,
        **project.pipeline_config,
    }}, queue="pipeline")

    project.status = JobStatus.RUNNING
    project.celery_job_id = task.id
    project.progress = 0
    project.current_step = "파이프라인 시작 중..."
    project.error_message = None
    return {"job_id": task.id, "message": "파이프라인 시작"}


@router.get("/{project_id}/status", response_model=PipelineStatusResponse)
async def get_status(project_id: uuid.UUID,
                     user: Optional[User] = Depends(get_current_user_optional),
                     db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project: raise HTTPException(404, "프로젝트 없음")
    _ensure_can_view(project, user)
    return PipelineStatusResponse(
        job_id=project.celery_job_id or "",
        status=project.status, progress=project.progress,
        current_step=project.current_step, error_message=project.error_message,
    )


@router.get("/{project_id}/assets/{asset_id}/download")
async def get_download_url(project_id: uuid.UUID, asset_id: uuid.UUID,
                           user: Optional[User] = Depends(get_current_user_optional),
                           db: AsyncSession = Depends(get_db)):
    pr = await db.execute(select(Project).where(Project.id == project_id))
    project = pr.scalar_one_or_none()
    if not project: raise HTTPException(404, "프로젝트 없음")
    _ensure_can_view(project, user)
    result = await db.execute(select(Asset).where(Asset.id == asset_id, Asset.project_id == project_id))
    asset = result.scalar_one_or_none()
    if not asset: raise HTTPException(404, "에셋 없음")
    asset.download_count += 1
    return {"download_url": storage_service.get_presigned_url(asset.storage_key),
            "format": asset.format}


def _asset_filename_ct(asset):
    fmt = asset.format.value if hasattr(asset.format, "value") else str(asset.format)
    if fmt == "obj" and asset.has_texture:
        return "model_with_texture.zip", "application/zip"
    if fmt == "obj":
        return "model.obj", "text/plain"
    if fmt == "glb":
        return "model.glb", "model/gltf-binary"
    if fmt == "ply":
        return "model.ply", "application/octet-stream"
    return f"model.{fmt}", "application/octet-stream"


@router.get("/{project_id}/assets/{asset_id}/file")
async def stream_asset_file(
    project_id: uuid.UUID, asset_id: uuid.UUID,
    dl: int = 0,
    user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import StreamingResponse
    pr = await db.execute(select(Project).where(Project.id == project_id))
    project = pr.scalar_one_or_none()
    if not project: raise HTTPException(404, "프로젝트 없음")
    _ensure_can_view(project, user)
    result = await db.execute(select(Asset).where(Asset.id == asset_id, Asset.project_id == project_id))
    asset = result.scalar_one_or_none()
    if not asset: raise HTTPException(404, "에셋 없음")
    fname, ct = _asset_filename_ct(asset)
    try:
        obj = storage_service.client.get_object(Bucket=storage_service.bucket, Key=asset.storage_key)
    except Exception as e:
        raise HTTPException(404, f"파일을 찾을 수 없습니다: {e}")
    body = obj["Body"]
    def gen():
        try:
            while True:
                chunk = body.read(262144)
                if not chunk: break
                yield chunk
        finally:
            try: body.close()
            except Exception: pass
    disp = f'{"attachment" if dl else "inline"}; filename="{fname}"'
    return StreamingResponse(gen(), media_type=ct, headers={
        "Content-Disposition": disp,
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "no-store",
    })


def _resolve_preview_path(project: Project):
    """프로젝트 진행 상태에 따라 가장 적합한 PLY 파일 경로 + 메타데이터 반환.

    `/preview` (JSON 메타) 와 `/preview/file` (실제 PLY 스트림) 가 같은 로직을
    공유해야 화면에 표시한 단계와 다운로드한 파일이 어긋나지 않는다.
    반환: (path, meta_dict) 또는 (None, None).
    """
    output_dir = project.output_dir or ""
    progress = project.progress or 0
    if not output_dir or progress < 30:
        return None, None
    ws = os.path.join(output_dir, "workspace")
    # COLMAP 워커가 미리보기용 PLY 를 `points3D_preview.ply` 로 별도 저장한다.
    # 절대 `points3D.ply` 를 쓰면 안 됨 — 3DGS dataset_readers.py 가
    # 자기네 포맷으로 오인해 train.py 가 `'NoneType' object has no attribute
    # 'points'` 로 죽는다.
    colmap_ply = os.path.join(ws, "colmap", "sparse", "0", "points3D_preview.ply")

    def _intermediate(it):
        return (
            os.path.join(output_dir, "reconstruction", "gs_pretrain",
                         "point_cloud", f"iteration_{it}", "point_cloud.ply"),  # SuGaR
            os.path.join(output_dir, "reconstruction",
                         "point_cloud", f"iteration_{it}", "point_cloud.ply"),  # 2DGS/GOF
        )

    # 우선순위: 진행률에 맞춰 더 후기 단계의 PLY 가 있으면 그것을 우선.
    candidates = []
    if progress < 55:
        candidates.append((colmap_ply,
            {"stage": "colmap", "label": "COLMAP 포즈 추정 결과",
             "point_size": 3, "color": "#4ade80"}))
    if progress < 75:
        for p in _intermediate(7000):
            candidates.append((p,
                {"stage": "gs7k", "label": "3DGS 중간 결과 (7k 스텝)",
                 "point_size": 1.2, "color": "#c084fc"}))
    for p in _intermediate(30000):
        candidates.append((p,
            {"stage": "gs30k", "label": "3DGS 완료 (30k 스텝)",
             "point_size": 1, "color": "#60a5fa"}))
    # 최후 폴백: COLMAP PLY (학습 단계 PLY 가 아직 없으면)
    candidates.append((colmap_ply,
        {"stage": "colmap",
         "label": f"COLMAP 포인트클라우드 ({progress}% 진행 중)",
         "point_size": 3, "color": "#4ade80"}))

    for path, meta in candidates:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path, meta
    return None, None


@router.get("/{project_id}/preview")
async def get_preview(project_id: uuid.UUID,
                      user: Optional[User] = Depends(get_current_user_optional),
                      db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(Project).where(Project.id == project_id))
    project = r.scalar_one_or_none()
    if not project: raise HTTPException(404, "프로젝트 없음")
    _ensure_can_view(project, user)
    progress = project.progress or 0

    if project.status == JobStatus.SUCCESS:
        r2 = await db.execute(
            select(Asset).where(Asset.project_id == project_id,
                                Asset.format == AssetFormat.GLB).limit(1)
        )
        asset = r2.scalar_one_or_none()
        if asset:
            return {"type": "glb",
                    "url": storage_service.get_presigned_url(asset.storage_key),
                    "progress": 100, "label": "완성된 3D 메쉬", "stage": "mesh"}

    if not project.output_dir or progress < 30:
        return {"type": None, "url": None, "progress": progress, "label": "처리 준비 중..."}

    path, meta = _resolve_preview_path(project)
    if path is None:
        return {"type": None, "url": None, "progress": progress, "label": "결과 준비 중..."}

    # 프론트는 url 에서 projectId 만 뽑아 `/preview/file` 로 다시 부른다 (PointCloudViewer.tsx).
    # 따라서 url 은 "정확한 PLY 위치" 가 아니라 "이 프로젝트의 미리보기" 라는 키 역할만 하면 된다.
    placeholder = f"/api/v1/projects/{project_id}/preview/{meta['stage']}.ply"
    return {"type": "pointcloud", "url": placeholder, "progress": progress, **meta}


@router.get("/{project_id}/preview/file")
async def get_preview_file(project_id: uuid.UUID,
                           user: Optional[User] = Depends(get_current_user_optional),
                           db: AsyncSession = Depends(get_db)):
    """PointCloudViewer 가 호출하는 실제 PLY 바이너리 엔드포인트.

    `_resolve_preview_path` 로 현재 단계의 PLY 경로를 찾아 /shared 볼륨에서
    직접 스트리밍한다. MinIO 업로드 왕복을 생략해 HDD 압박 상황에서도
    빠르게 응답한다. 단계가 바뀌어도 같은 URL 로 다음 PLY 가 자동 노출된다.
    """
    from fastapi.responses import FileResponse
    r = await db.execute(select(Project).where(Project.id == project_id))
    project = r.scalar_one_or_none()
    if not project: raise HTTPException(404, "프로젝트 없음")
    _ensure_can_view(project, user)
    path, meta = _resolve_preview_path(project)
    if path is None:
        raise HTTPException(404, "미리보기 PLY 가 아직 준비되지 않았습니다")
    return FileResponse(
        path,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'inline; filename="{meta["stage"]}.ply"',
            "Cache-Control": "no-store",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: uuid.UUID,
                         user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Project).options(
            selectinload(Project.assets), selectinload(Project.images),
        ).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project: raise HTTPException(404, "프로젝트 없음")
    _ensure_can_modify(project, user)
    for img in project.images:
        if img.storage_key: storage_service.delete_file(img.storage_key)
        if img.thumbnail_key: storage_service.delete_file(img.thumbnail_key)
    for asset in project.assets:
        if asset.storage_key: storage_service.delete_file(asset.storage_key)
    import shutil
    for d in (project.upload_dir, project.output_dir):
        if d and os.path.isdir(d) and (
            d.startswith(settings.UPLOAD_DIR) or d.startswith(settings.OUTPUT_DIR)
        ):
            shutil.rmtree(d, ignore_errors=True)
    await db.delete(project)


# ── 좋아요 토글 (로그인 필수) ──────────────────────────────────────────
@router.post("/{project_id}/like")
async def toggle_like(project_id: uuid.UUID,
                      user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    pr = await db.execute(select(Project).where(Project.id == project_id))
    project = pr.scalar_one_or_none()
    if not project: raise HTTPException(404, "프로젝트 없음")
    if not project.is_public:
        raise HTTPException(400, "공개되지 않은 프로젝트입니다")
    lr = await db.execute(select(Like).where(Like.user_id == user.id, Like.project_id == project.id))
    existing = lr.scalar_one_or_none()
    if existing:
        await db.delete(existing)
        await db.execute(update(Project).where(Project.id == project.id)
                         .values(like_count=func.greatest(Project.like_count - 1, 0)))
        liked = False
    else:
        db.add(Like(user_id=user.id, project_id=project.id))
        await db.execute(update(Project).where(Project.id == project.id)
                         .values(like_count=Project.like_count + 1))
        liked = True
    await db.flush()
    await db.refresh(project)
    return {"liked": liked, "like_count": project.like_count}
