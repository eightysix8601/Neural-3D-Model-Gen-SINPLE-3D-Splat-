import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from app.core.config import settings
from app.db.session import engine, Base
# 모든 모델을 import 해서 Base.metadata 에 등록되도록 함 (create_all 사용 시 필수)
from app.db.models import project as _project_models  # noqa: F401
from app.db.models import user as _user_models  # noqa: F401
from app.api.v1.endpoints import projects, ws, auth, gallery


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"🚀 SnapAsset3D Backend 시작 (ENV={settings.APP_ENV})")
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
    if settings.APP_ENV == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("DB 테이블 초기화 완료")
    # 기존 DB에서 enum 확장 + 새 컬럼 추가 (안전: 존재할 때만)
    try:
        async with engine.connect() as conn:
            conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
            # ModelType: nerf, tripo 추가
            row = (await conn.exec_driver_sql(
                "SELECT DISTINCT enumtypid::regtype::text FROM pg_enum "
                "WHERE upper(enumlabel) IN ('SUGAR','GOF') LIMIT 1"
            )).first()
            if row:
                for v in ("NERF", "TRIPO", "TWODGS"):
                    await conn.exec_driver_sql(
                        f"ALTER TYPE {row[0]} ADD VALUE IF NOT EXISTS '{v}'"
                    )
                logger.info(f"ModelType enum 확장 확인: {row[0]} += NERF, TRIPO, TWODGS")
            # Project.prompt 컬럼 추가 (기존 DB 호환)
            await conn.exec_driver_sql(
                "ALTER TABLE projects ADD COLUMN IF NOT EXISTS prompt TEXT"
            )
            logger.info("projects.prompt 컬럼 확인/추가 완료")
    except Exception as e:
        logger.warning(f"마이그레이션 경고(무시 가능): {e}")
    yield
    await engine.dispose()


app = FastAPI(
    title="SnapAsset3D API",
    description="다각도 사진 → 3D 모델 자동 생성 + TripoSG 스마트 메시",
    version="2.1.0", lifespan=lifespan,
    docs_url="/api/docs", redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(gallery.router, prefix=settings.API_V1_STR)
app.include_router(projects.router, prefix=settings.API_V1_STR)
app.include_router(ws.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "snapasset3d-backend", "version": "2.1.0"}
