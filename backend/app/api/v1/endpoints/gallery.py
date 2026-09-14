"""Gallery API: 공개 프로젝트 목록 / 인기 / 카테고리 필터.

비로그인도 조회 가능. 좋아요는 /projects/{id}/like 사용 (로그인 필수).
"""
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload
from app.db.session import get_db
from app.db.models.project import Project, ProjectImage, Asset, JobStatus, AssetFormat, Category
from app.db.models.user import User, Like
from app.schemas.project import GalleryItem, OwnerMini
from app.services.storage import storage_service
from app.api.deps import get_current_user_optional


router = APIRouter(prefix="/gallery", tags=["Gallery"])


SortType = str  # "recent" | "popular"


@router.get("", response_model=List[GalleryItem])
async def list_gallery(
    category: Optional[Category] = Query(None),
    sort: SortType = Query("recent", regex="^(recent|popular)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(24, ge=1, le=100),
    user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    q = select(Project).options(selectinload(Project.owner)).where(
        Project.is_public == True,
        Project.status == JobStatus.SUCCESS,
    )
    if category:
        q = q.where(Project.category == category)
    if sort == "popular":
        q = q.order_by(desc(Project.like_count), desc(Project.created_at))
    else:
        q = q.order_by(desc(Project.created_at))
    q = q.offset(skip).limit(limit)
    res = await db.execute(q)
    projects = res.scalars().all()

    liked_ids: set = set()
    if user and projects:
        lr = await db.execute(select(Like.project_id).where(
            Like.user_id == user.id,
            Like.project_id.in_([p.id for p in projects]),
        ))
        liked_ids = {row[0] for row in lr.all()}

    items: list[GalleryItem] = []
    for p in projects:
        item = GalleryItem.model_validate(p)
        # cover thumbnail
        if p.cover_image_key:
            item.thumbnail_url = storage_service.get_presigned_url(p.cover_image_key)
        else:
            ir = await db.execute(
                select(ProjectImage).where(ProjectImage.project_id == p.id)
                .order_by(ProjectImage.order_index).limit(1)
            )
            first = ir.scalar_one_or_none()
            if first and first.thumbnail_key:
                item.thumbnail_url = storage_service.get_presigned_url(first.thumbnail_key)
        # GLB preview for hover
        ar = await db.execute(
            select(Asset).where(Asset.project_id == p.id, Asset.format == AssetFormat.GLB).limit(1)
        )
        glb = ar.scalar_one_or_none()
        if glb:
            item.preview_url = f"/api/v1/projects/{p.id}/assets/{glb.id}/file"
        item.liked_by_me = p.id in liked_ids
        items.append(item)
    return items


@router.get("/categories")
async def list_categories(db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(Project.category, func.count(Project.id))
        .where(Project.is_public == True, Project.status == JobStatus.SUCCESS)
        .group_by(Project.category)
    )
    counts = {row[0].value if hasattr(row[0], "value") else str(row[0]): row[1] for row in res.all()}
    out = []
    for c in Category:
        out.append({"key": c.value, "count": counts.get(c.value, 0)})
    return out
