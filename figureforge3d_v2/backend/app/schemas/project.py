from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field, ConfigDict
from app.db.models.project import JobStatus, ModelType, AssetFormat

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    model_type: ModelType = ModelType.SUGAR
    pipeline_config: dict[str, Any] = Field(default_factory=dict)

class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID; format: AssetFormat; file_size: Optional[int] = None
    has_texture: bool = False; download_url: Optional[str] = None; created_at: datetime

class ProjectImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID; filename: str; width: Optional[int] = None; height: Optional[int] = None
    thumbnail_url: Optional[str] = None; order_index: int

class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID; name: str; description: Optional[str] = None
    status: JobStatus; progress: int; current_step: Optional[str] = None
    model_type: ModelType; pipeline_config: dict; error_message: Optional[str] = None
    image_count: int = 0; created_at: datetime; updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    assets: list[AssetResponse] = []; images: list[ProjectImageResponse] = []

class ProjectListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID; name: str; status: JobStatus; progress: int
    model_type: ModelType; image_count: int = 0; created_at: datetime
    thumbnail_url: Optional[str] = None

class PipelineStartRequest(BaseModel):
    gs_iterations: int = Field(default=30000, ge=10000, le=60000)
    refinement_time: str = "short"
    high_poly: bool = False

class PipelineStatusResponse(BaseModel):
    job_id: str; status: JobStatus; progress: int
    current_step: Optional[str] = None; error_message: Optional[str] = None
