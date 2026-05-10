import os, httpx, asyncio
from celery import Celery
from celery.utils.log import get_task_logger
from app.core.config import settings

celery_app = Celery("figureforge3d", broker=settings.CELERY_BROKER_URL, backend=settings.CELERY_RESULT_BACKEND)
celery_app.conf.update(task_serializer="json", accept_content=["json"], result_serializer="json",
    timezone="Asia/Seoul", enable_utc=True,
    task_routes={"app.tasks.pipeline.run_pipeline": {"queue": "pipeline"}},
    task_acks_late=True, worker_prefetch_multiplier=1)
logger = get_task_logger(__name__)
TIMEOUT = httpx.Timeout(10800.0)


def _db_update(sql, params):
    import psycopg2
    from urllib.parse import urlparse
    url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    p = urlparse(url)
    conn = psycopg2.connect(
        host=p.hostname, port=p.port or 5432,
        dbname=p.path.lstrip("/"),
        user=p.username, password=p.password
    )
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _upd(project_id, progress, step, task):
    task.update_state(state="PROGRESS", meta={"progress": progress, "step": step})
    try:
        _db_update(
            "UPDATE projects SET progress=%s, current_step=%s, status='RUNNING' WHERE id=%s::uuid",
            (progress, step, str(project_id))
        )
    except Exception as e:
        logger.warning(f"진행률 업데이트 실패 (무시): {e}")


def _set_status(project_id, status, error=None):
    from datetime import datetime
    try:
        if status == "SUCCESS":
            _db_update(
                "UPDATE projects SET status=%s, progress=100, current_step='완료!', completed_at=%s WHERE id=%s::uuid",
                (status, datetime.utcnow(), str(project_id))
            )
        elif error:
            _db_update(
                "UPDATE projects SET status=%s, error_message=%s WHERE id=%s::uuid",
                (status, error[:2000], str(project_id))
            )
        else:
            _db_update(
                "UPDATE projects SET status=%s WHERE id=%s::uuid",
                (status, str(project_id))
            )
    except Exception as e:
        logger.warning(f"상태 업데이트 실패 (무시): {e}")


@celery_app.task(bind=True, name="app.tasks.pipeline.run_pipeline",
    max_retries=0, soft_time_limit=10800, time_limit=11000)
def run_pipeline(self, project_id: str, config: dict) -> dict:
    logger.info(f"[Pipeline] 시작: {project_id}")
    try:
        result = asyncio.run(_run(project_id, config, self))
        logger.info(f"[Pipeline] 완료: {project_id}")
        return result
    except Exception as e:
        logger.error(f"[Pipeline] 실패: {e}")
        _set_status(project_id, "FAILED", str(e))
        raise


async def _run(project_id: str, config: dict, task) -> dict:
    from pathlib import Path
    upload_dir = config["upload_dir"]
    output_dir = config["output_dir"]
    model_type = config["model_type"]
    ws = os.path.join(output_dir, "workspace")
    os.makedirs(ws, exist_ok=True)

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:

        # Step 1: 배경 분리
        _upd(project_id, 5, "배경 분리 중... (BiRefNet)", task)
        img_files = sorted([
            p for p in Path(upload_dir).iterdir()
            if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        ])
        if not img_files:
            raise RuntimeError("업로드된 이미지 없음")

        files = [("files", (p.name, open(p, "rb"), "image/jpeg")) for p in img_files]
        resp = await client.post(
            f"{settings.BG_REMOVAL_URL}/process",
            files=files,
            data={"output_dir": os.path.join(ws, "bg_removal")},
        )
        resp.raise_for_status()
        bg_result = resp.json()
        _upd(project_id, 18, f"배경 분리 완료 ({bg_result['count']}장)", task)

        # Step 2: 패턴 합성
        # _upd(project_id, 20, "패턴 배경 합성 중...", task)
        # pattern_dir = os.path.join(ws, "pattern")
        # resp = await client.post(
        #     f"{settings.PATTERN_BG_URL}/process",
        #     json={"rgba_dir": bg_result["rgba_dir"], "output_dir": pattern_dir, "tile_size": 60},
        # )
        # resp.raise_for_status()
        # _upd(project_id, 30, "패턴 합성 완료", task)

        # Step 2: 패턴 합성 스킵 (원본으로 COLMAP 돌리므로 불필요)
        _upd(project_id, 30, "COLMAP 준비 완료", task)

        # Step 3: COLMAP
        # _upd(project_id, 32, "COLMAP 포즈 추정 중... (약 5~15분)", task)
        # colmap_ws = os.path.join(ws, "colmap")
        # # resp = await client.post(
        # #     f"{settings.COLMAP_URL}/process",
        # #     json={"pattern_dir": pattern_dir, "rgba_dir": bg_result["rgba_dir"], "workspace": colmap_ws},
        # # )
        # resp = await client.post(
        #     f"{settings.COLMAP_URL}/process",
        #     json={
        #         "pattern_dir": pattern_dir,
        #         "rgba_dir": bg_result["rgba_dir"],
        #         "workspace": colmap_ws,
        #         "upload_dir": upload_dir,
        #     },
        # )
        _upd(project_id, 32, "COLMAP 포즈 추정 중... (약 5~15분)", task)
        colmap_ws = os.path.join(ws, "colmap")
        resp = await client.post(
            f"{settings.COLMAP_URL}/process",
            json={
                "pattern_dir": upload_dir,   # 원본 폴더
                "rgba_dir": bg_result["rgba_dir"],
                "workspace": colmap_ws,
                "upload_dir": upload_dir,    # 원본 폴더
            },
        )
        resp.raise_for_status()
        dataset_dir = resp.json()["dataset_dir"]
        _upd(project_id, 55, "COLMAP 완료", task)

        # Step 4: 3D 재구성
        recon_dir = os.path.join(output_dir, "reconstruction")
        os.makedirs(recon_dir, exist_ok=True)

        if model_type == "sugar":
            _upd(project_id, 57, "SuGaR 학습 중... (약 20~40분)", task)
            resp = await client.post(
                f"{settings.SUGAR_URL}/process",
                json={
                    "dataset_dir": dataset_dir,
                    "output_dir": recon_dir,
                    "gs_iterations": config.get("gs_iterations", 30000),
                    "refinement_time": config.get("refinement_time", "short"),
                    "high_poly": config.get("high_poly", False),
                    "eval": len(img_files) < 10,
                },
            )
        else:
            _upd(project_id, 57, "GOF 학습 중... (약 20~30분)", task)
            resp = await client.post(
                f"{settings.GOF_URL}/process",
                json={
                    "dataset_dir": dataset_dir,
                    "output_dir": recon_dir,
                    "iterations": config.get("iterations", 30000),
                    "eval": len(img_files) < 10,
                },
            )

        resp.raise_for_status()
        recon_result = resp.json()
        _upd(project_id, 95, "파일 정리 중...", task)
        await _finalize(project_id, recon_result.get("assets", []))
        _set_status(project_id, "SUCCESS")
        return recon_result

async def _finalize(project_id, assets):
    import zipfile
    from app.services.storage import storage_service
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
    from app.db.models.project import Asset, AssetFormat
    from pathlib import Path

    engine = create_async_engine(settings.DATABASE_URL)
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    # OBJ 관련 파일들 zip으로 묶기
    obj_files = [a for a in assets if a.get("path", "").endswith(".obj") or 
                 a.get("path", "").endswith(".mtl")]
    png_files = [a for a in assets if a.get("path", "").endswith(".png")]
    other_assets = [a for a in assets if a.get("format") in ("glb", "ply") and 
                    not a.get("path", "").endswith(".png")]

    async with Session() as s:
        # OBJ + MTL + PNG → zip으로 묶기
        if obj_files:
            try:
                obj_path = next((a["path"] for a in obj_files if a["path"].endswith(".obj")), None)
                if obj_path:
                    zip_path = obj_path.replace(".obj", "_with_texture.zip")
                    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                        for a in obj_files + png_files:
                            p = a.get("path")
                            if p and os.path.exists(p):
                                zf.write(p, Path(p).name)
                    key = storage_service.upload_from_path(zip_path, prefix=f"projects/{project_id}/assets")
                    s.add(Asset(project_id=project_id, format=AssetFormat.OBJ,
                        storage_key=key, file_size=os.path.getsize(zip_path), has_texture=True))
                    logger.info(f"[Finalize] OBJ+텍스처 zip 업로드 완료")
            except Exception as e:
                logger.warning(f"zip 생성 실패: {e}")

        # GLB, PLY 개별 업로드
        for a in other_assets:
            fmt, path = a.get("format"), a.get("path")
            if not path or not os.path.exists(path):
                continue
            try:
                key = storage_service.upload_from_path(path, prefix=f"projects/{project_id}/assets")
                s.add(Asset(project_id=project_id, format=AssetFormat(fmt),
                    storage_key=key, file_size=a.get("size"), has_texture=fmt=="glb"))
            except Exception as e:
                logger.warning(f"에셋 업로드 실패: {e}")
        await s.commit()
    await engine.dispose()

# async def _finalize(project_id, assets):
#     from app.services.storage import storage_service
#     from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
#     from app.db.models.project import Asset, AssetFormat

#     engine = create_async_engine(settings.DATABASE_URL)
#     Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

#     async with Session() as s:
#         for a in assets:
#             fmt, path = a.get("format"), a.get("path")
#             if not path or not os.path.exists(path):
#                 continue
#             try:
#                 key = storage_service.upload_from_path(path, prefix=f"projects/{project_id}/assets")
#                 s.add(Asset(project_id=project_id, format=AssetFormat(fmt),
#                     storage_key=key, file_size=a.get("size")))
#             except Exception as e:
#                 logger.warning(f"에셋 업로드 실패: {e}")
#         await s.commit()
#     await engine.dispose()