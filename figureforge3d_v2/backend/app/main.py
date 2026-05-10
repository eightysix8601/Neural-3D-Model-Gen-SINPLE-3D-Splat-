import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from app.core.config import settings
from app.db.session import engine, Base
from app.api.v1.endpoints import projects, ws

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"🚀 FigureForge3D Backend 시작 (ENV={settings.APP_ENV})")
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
    if settings.APP_ENV == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("DB 테이블 초기화 완료")
    yield
    await engine.dispose()

app = FastAPI(title="FigureForge3D API", description="다각도 사진 → 3D 모델 자동 생성",
    version="2.0.0", lifespan=lifespan, docs_url="/api/docs", redoc_url="/api/redoc")

app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins_list,
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(projects.router, prefix=settings.API_V1_STR)
app.include_router(ws.router)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "figureforge3d-backend", "version": "2.0.0"}
