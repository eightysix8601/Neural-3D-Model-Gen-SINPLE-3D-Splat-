from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field, ConfigDict
from app.db.models.project import JobStatus, ModelType, AssetFormat, Category


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    model_type: ModelType = ModelType.SUGAR
    category: Category = Category.OTHER
    prompt: Optional[str] = Field(None, max_length=2000)
    pipeline_config: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    category: Optional[Category] = None
    is_public: Optional[bool] = None
    prompt: Optional[str] = Field(None, max_length=2000)


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    format: AssetFormat
    file_size: Optional[int] = None
    has_texture: bool = False
    download_url: Optional[str] = None
    created_at: datetime


class ProjectImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    filename: str
    width: Optional[int] = None
    height: Optional[int] = None
    thumbnail_url: Optional[str] = None
    order_index: int


class OwnerMini(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    username: str


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    status: JobStatus
    progress: int
    current_step: Optional[str] = None
    model_type: ModelType
    category: Category = Category.OTHER
    is_public: bool = False
    like_count: int = 0
    view_count: int = 0
    pipeline_config: dict
    prompt: Optional[str] = None
    error_message: Optional[str] = None
    image_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    assets: list[AssetResponse] = []
    images: list[ProjectImageResponse] = []
    owner: Optional[OwnerMini] = None
    liked_by_me: bool = False


class ProjectListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    status: JobStatus
    progress: int
    model_type: ModelType
    category: Category = Category.OTHER
    is_public: bool = False
    like_count: int = 0
    image_count: int = 0
    created_at: datetime
    thumbnail_url: Optional[str] = None
    owner: Optional[OwnerMini] = None


class GalleryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    category: Category
    like_count: int = 0
    view_count: int = 0
    created_at: datetime
    thumbnail_url: Optional[str] = None
    preview_url: Optional[str] = None  # GLB url for hover preview
    owner: Optional[OwnerMini] = None
    liked_by_me: bool = False


class PipelineStartRequest(BaseModel):
    gs_iterations: int = Field(default=30000, ge=10000, le=60000)
    refinement_time: str = "short"
    high_poly: bool = False


class PipelineStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: int
    current_step: Optional[str] = None
    error_message: Optional[str] = None
