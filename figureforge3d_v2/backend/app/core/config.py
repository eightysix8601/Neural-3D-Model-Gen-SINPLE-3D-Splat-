from functools import lru_cache
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_ENV: str = "development"
    SECRET_KEY: str = "figureforge3d-change-in-production"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"
    DATABASE_URL: str = "postgresql+asyncpg://ff3d:ff3d_secret@postgres:5432/figureforge3d"
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "ff3d_admin"
    MINIO_SECRET_KEY: str = "ff3d_minio_secret"
    MINIO_BUCKET_NAME: str = "figureforge3d"
    MINIO_USE_SSL: bool = False
    BG_REMOVAL_URL: str = "http://ff3d_bg_removal:8010"
    PATTERN_BG_URL: str = "http://ff3d_pattern_bg:8011"
    COLMAP_URL: str = "http://ff3d_colmap:8012"
    SUGAR_URL: str = "http://ff3d_sugar:8013"
    GOF_URL: str = "http://ff3d_gof:8014"
    VIDEO_PROCESSOR_URL: str = "http://ff3d_video:8015"
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:80"
    SHARED_DATA_DIR: str = "/shared"
    UPLOAD_DIR: str = "/shared/uploads"
    OUTPUT_DIR: str = "/shared/outputs"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    class Config:
        env_file = ".env"

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
