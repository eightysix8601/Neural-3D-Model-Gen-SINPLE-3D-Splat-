import uuid, enum
from sqlalchemy import Column, String, Integer, DateTime, Enum, ForeignKey, JSON, Text, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base

class JobStatus(str, enum.Enum):
    PENDING = "PENDING"; RUNNING = "RUNNING"; SUCCESS = "SUCCESS"; FAILED = "FAILED"

class ModelType(str, enum.Enum):
    SUGAR = "sugar"; GOF = "gof"; NERF = "nerf"; TRIPO = "tripo"; TWODGS = "twodgs"

class AssetFormat(str, enum.Enum):
    GLB = "glb"; OBJ = "obj"; PLY = "ply"

class Category(str, enum.Enum):
    OTHER = "other"
    CHARACTER = "character"
    VEHICLE = "vehicle"
    FURNITURE = "furniture"
    ANIMAL = "animal"
    FOOD = "food"
    PROP = "prop"
    BUILDING = "building"

class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_public_created", "is_public", "created_at"),
        Index("ix_projects_owner", "owner_id"),
        Index("ix_projects_category", "category"),
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Enum(JobStatus), default=JobStatus.PENDING, nullable=False)
    celery_job_id = Column(String(255), nullable=True)
    progress = Column(Integer, default=0)
    current_step = Column(String(255), nullable=True)
    model_type = Column(Enum(ModelType), default=ModelType.SUGAR, nullable=False)
    category = Column(Enum(Category), default=Category.OTHER, nullable=False)
    is_public = Column(Boolean, default=False, nullable=False, index=True)
    like_count = Column(Integer, default=0, nullable=False)
    view_count = Column(Integer, default=0, nullable=False)
    pipeline_config = Column(JSON, default={})
    prompt = Column(Text, nullable=True)  # 메타데이터/메모용 (TripoSG 표준은 image-only 라 generation 영향 X)
    upload_dir = Column(String(512), nullable=True)
    output_dir = Column(String(512), nullable=True)
    error_message = Column(Text, nullable=True)
    image_count = Column(Integer, default=0)
    cover_image_key = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    assets = relationship("Asset", back_populates="project", cascade="all, delete-orphan")
    images = relationship("ProjectImage", back_populates="project", cascade="all, delete-orphan")
    owner = relationship("User", back_populates="projects")
    likes = relationship("Like", back_populates="project", cascade="all, delete-orphan")

class ProjectImage(Base):
    __tablename__ = "project_images"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    storage_key = Column(String(512), nullable=False)
    thumbnail_key = Column(String(512), nullable=True)
    file_size = Column(Integer, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    order_index = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    project = relationship("Project", back_populates="images")

class Asset(Base):
    __tablename__ = "assets"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    format = Column(Enum(AssetFormat), nullable=False)
    storage_key = Column(String(512), nullable=False)
    file_size = Column(Integer, nullable=True)
    has_texture = Column(Boolean, default=False)
    download_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    project = relationship("Project", back_populates="assets")
