import os, httpx, asyncio
from celery import Celery
from celery.utils.log import get_task_logger
from app.core.config import settings

celery_app = Celery("figureforge3d", broker=settings.CELERY_BROKER_URL, backend=settings.CELERY_RESULT_BACKEND)
celery_app.conf.update(task_serializer="json", accept_content=["json"], result_serializer="json",
    timezone="Asia/Seoul", enable_utc=True,
    task_routes={"app.tasks.pipeline.run_pipeline": {"queue": "pipeline"}},
    # ★ 무한 재실행(57%→5%)의 진짜 원인 해결:
    # Redis 브로커는 visibility_timeout(기본 3600초) 안에 작업이 안 끝나면
    # 메시지를 '유실'로 보고 재전송한다. 우리 파이프라인은 1~6시간이라
    # 매 1시간마다 중복 실행됐다. 작업 최대시간(6h)보다 훨씬 큰 24h 로 설정.
    broker_transport_options={"visibility_timeout": 86400},
    result_backend_transport_options={"visibility_timeout": 86400},
    # acks_late=False: 강제종료된 작업이 재전송돼 처음부터 또 도는 것 차단
    task_acks_late=False, worker_prefetch_multiplier=1)
logger = get_task_logger(__name__)
# 워커(특히 SuGaR long) 단일 호출이 6시간 예산 안에서 안 끊기도록 상향
TIMEOUT = httpx.Timeout(21600.0)


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
    max_retries=0, soft_time_limit=21600, time_limit=22200)
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

    # ── 스마트 메시(TRIPO): 단일 이미지 → TripoSG ──────────────────────
    # TripoSG 워커는 자체적으로 BriaRMBG 로 배경 제거하므로 BiRefNet 단계는 생략.
    # (이중 배경 제거 시 알파 경계가 깎여 메쉬 디테일이 손상되는 문제 회피)
    if model_type == "tripo":
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            _upd(project_id, 10, "스마트 메시 준비 중...", task)
            img_files = sorted([
                p for p in Path(upload_dir).iterdir()
                if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
            ])
            if not img_files:
                raise RuntimeError("업로드된 이미지가 없습니다")
            input_for_tripo = str(img_files[0])

            # 텍스쳐는 tripo_worker 가 자체 처리 (정면 투영 vertex color).
            # 외부 paint 모델 의존성 제거 — 안정성 우선.
            use_texture = config.get("use_texture", True)
            step_label = (
                "TripoSG 추론 + 텍스쳐 적용 중... (1~3분)"
                if use_texture else "TripoSG 추론 중... (1~3분, 텍스쳐 OFF)"
            )
            _upd(project_id, 30, step_label, task)
            tripo_out = os.path.join(output_dir, "tripo")
            os.makedirs(tripo_out, exist_ok=True)
            with open(input_for_tripo, "rb") as fp:
                resp = await client.post(
                    f"{settings.TRIPO_URL}/generate",
                    files={"image": (Path(input_for_tripo).name, fp.read(), "image/png")},
                    data={
                        "output_dir": tripo_out,
                        "num_inference_steps": str(config.get("num_inference_steps", 50)),
                        "guidance_scale": str(config.get("guidance_scale", 7.0)),
                        "use_sparseflex": str(config.get("use_sparseflex", False)).lower(),
                        "use_texture": str(use_texture).lower(),
                    },
                )
            resp.raise_for_status()
            tripo_result = resp.json()
            assets = tripo_result.get("assets", [])
            if not any(a.get("format") in ("glb", "obj") for a in assets):
                raise RuntimeError("TripoSG 워커가 GLB/OBJ를 만들지 않았습니다")

            _upd(project_id, 90, "메쉬 생성 완료, 업로드 중...", task)
            await _finalize(project_id, assets)
            _set_status(project_id, "SUCCESS")
            return tripo_result

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
            # 4070 Ti 12GB 기준 안전한 고품질 디폴트:
            #   high_poly(g=6) + refinement_time=medium(10k iters).
            # long(15k) 은 VRAM 한계라 OOM 위험 → 사용자가 명시할 때만 허용.
            resp = await client.post(
                f"{settings.SUGAR_URL}/process",
                json={
                    "dataset_dir": dataset_dir,
                    "output_dir": recon_dir,
                    "gs_iterations": config.get("gs_iterations", 30000),
                    "refinement_time": config.get("refinement_time", "medium"),
                    "high_poly": config.get("high_poly", True),
                    "eval": len(img_files) < 10,
                },
            )
        elif model_type == "gof":
            _upd(project_id, 57, "GOF 학습 중... (약 20~30분)", task)
            resp = await client.post(
                f"{settings.GOF_URL}/process",
                json={
                    "dataset_dir": dataset_dir,
                    "output_dir": recon_dir,
                    "iterations": config.get("gs_iterations", config.get("iterations", 30000)),
                    "eval": len(img_files) < 10,
                },
            )
        elif model_type == "twodgs":
            _upd(project_id, 57, "2DGS 학습 중... (약 20~30분)", task)
            resp = await client.post(
                f"{settings.TWODGS_URL}/process",
                json={
                    "dataset_dir": dataset_dir,
                    "output_dir": recon_dir,
                    "iterations": config.get("gs_iterations", config.get("iterations", 30000)),
                    "eval": len(img_files) < 10,
                    # 피규어/오브젝트는 bounded TSDF 가 적합.
                    # 야외씬일 때만 config 에서 unbounded=True 로 덮어쓴다.
                    "unbounded": bool(config.get("unbounded", False)),
                    "mesh_res": int(config.get("mesh_res", 1024)),
                    # bounded TSDF 의 RAM 폭주 방지 캡 (피규어 친화 기본값).
                    "voxel_size": float(config.get("voxel_size", 0.004)),
                    "depth_trunc": float(config.get("depth_trunc", 3.0)),
                    # 피규어 한 덩어리 = 1개 클러스터만 유지 (2DGS num_cluster=50 IndexError 회피).
                    "num_cluster": int(config.get("num_cluster", 1)),
                    # depth_ratio=1(median) 이 오브젝트 케이스에서 잡음 ↓.
                    # lambda_normal=0.1 로 표면 매끈함 ↑.
                    "depth_ratio": float(config.get("depth_ratio", 1.0)),
                    "lambda_normal": float(config.get("lambda_normal", 0.1)),
                },
            )
        elif model_type == "nerf":
            _upd(project_id, 57, "NeRF(nerfacto) 학습 중... (약 15~30분)", task)
            resp = await client.post(
                f"{settings.NERF_URL}/process",
                json={
                    "dataset_dir": dataset_dir,
                    "output_dir": recon_dir,
                    "iterations": min(max(config.get("gs_iterations", 20000), 5000), 30000),
                    "eval": len(img_files) < 10,
                },
            )
        else:
            raise RuntimeError(
                f"알 수 없는 model_type='{model_type}' (지원: sugar, gof, twodgs, nerf, tripo)"
            )

        resp.raise_for_status()
        recon_result = resp.json()
        assets = recon_result.get("assets", [])

        # SuGaR/GOF가 OBJ 또는 GLB를 생성했는지 검증 (silent fail 방지)
        has_mesh = any(
            a.get("format") in ("obj", "glb") or
            a.get("path", "").endswith((".obj", ".glb"))
            for a in assets
        )
        if not has_mesh:
            raise RuntimeError(
                f"메쉬 생성 실패: {model_type} 워커가 OBJ/GLB를 만들지 않았습니다. "
                f"받은 에셋: {[a.get('format') for a in assets]}"
            )

        _upd(project_id, 95, "파일 정리 중...", task)
        await _finalize(project_id, assets)
        _set_status(project_id, "SUCCESS")
        return recon_result

async def _finalize(project_id, assets):
    import zipfile
    from app.services.storage import storage_service
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
    from app.db.models.project import Project, Asset, AssetFormat
    from sqlalchemy import update
    from pathlib import Path

    engine = create_async_engine(settings.DATABASE_URL)
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    # 워커가 만든 4면 썸네일 (TripoSG 워커에서 추가됨)
    thumbnail_assets = [a for a in assets if a.get("format") == "thumbnail"]

    # OBJ 관련 파일들 zip으로 묶기 (단, 워커가 만든 thumbnail PNG 는 텍스처가 아니라 제외)
    obj_files = [a for a in assets if a.get("format") in ("obj", "mtl") or
                 a.get("path", "").endswith(".obj") or a.get("path", "").endswith(".mtl")]
    png_files = [a for a in assets if a.get("format") == "texture" or
                 (a.get("path", "").endswith(".png") and a.get("format") != "thumbnail")]
    other_assets = [a for a in assets if a.get("format") in ("glb", "ply")]

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

        # ── 4면 썸네일 업로드 + cover_image_key 설정 (front 우선) ───────────
        cover_key = None
        if thumbnail_assets:
            uploaded = {}
            for a in thumbnail_assets:
                path = a.get("path"); view = a.get("view", "front")
                if not path or not os.path.exists(path):
                    continue
                try:
                    key = storage_service.upload_from_path(
                        path, prefix=f"projects/{project_id}/thumbnails"
                    )
                    uploaded[view] = key
                    logger.info(f"[Finalize] 썸네일 {view} 업로드 완료")
                except Exception as e:
                    logger.warning(f"썸네일 업로드 실패({view}): {e}")
            # 정면이 있으면 정면을 cover, 없으면 아무거나
            cover_key = uploaded.get("front") or next(iter(uploaded.values()), None)
            if cover_key:
                await s.execute(
                    update(Project).where(Project.id == project_id)
                    .values(cover_image_key=cover_key)
                )
                logger.info(f"[Finalize] cover_image_key 설정 = {cover_key}")

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