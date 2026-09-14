"""기존 학습 결과 폴더 → DB Project + Asset 시드.

backend 컨테이너 안에서 실행. 사용 예 (PowerShell):

    docker exec ff3d_backend python /app/scripts/seed_project.py \
        --input-dir /tmp/seed/gundam \
        --name "Gundam Model" \
        --owner-email eightysix8601@gmail.com \
        --model-type twodgs \
        --category character \
        --public

`/tmp/seed/gundam` 안의 예상 파일들 (없는 건 그냥 스킵):
  - `*.glb`                                                       (필수: 최종 GLB)
  - `*.zip`                                                       (선택: OBJ+MTL+텍스처 묶음)
  - `gundam model 3d model/*.obj` + `*.mtl` + `*.jpg`             (zip 없으면 폴더 통째로)
  - `3dgs_pointcloud/reconstruction/point_cloud/iteration_*/point_cloud.ply`
  - `colmap/sparse/0/points3D_preview.ply`
  - `video_frames/frames/*.jpg`                                   (썸네일 + 이미지 카운트)
"""
import argparse, asyncio, os, shutil, uuid, sys
from datetime import datetime
from pathlib import Path

# /app 이 sys.path 에 잡혀 있어야 backend 모듈 import 가능 (CMD uvicorn 과 동일)
if "/app" not in sys.path:
    sys.path.insert(0, "/app")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.core.config import settings
from app.db.models.project import (
    Project, Asset, ProjectImage, JobStatus, ModelType, AssetFormat, Category,
)
from app.db.models.user import User
from app.services.storage import storage_service


def _find_one(root: Path, patterns):
    """root 아래에서 glob 매칭되는 가장 큰 파일 1개 반환 (없으면 None)."""
    for pat in patterns:
        cands = sorted(root.rglob(pat), key=lambda p: p.stat().st_size, reverse=True)
        for p in cands:
            if p.is_file() and p.stat().st_size > 0:
                return p
    return None


def _find_first_frame(root: Path):
    for sub in ("video_frames/frames", "frames", "images", "."):
        d = root / sub
        if d.is_dir():
            for ext in (".jpg", ".jpeg", ".png"):
                cands = sorted(d.glob(f"*{ext}"))
                if cands:
                    return cands[0]
    return None


def _count_frames(root: Path) -> int:
    for sub in ("video_frames/frames", "frames", "images"):
        d = root / sub
        if d.is_dir():
            n = sum(1 for p in d.iterdir()
                    if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})
            if n > 0:
                return n
    return 0


def _make_obj_zip(input_dir: Path, project_uuid: uuid.UUID) -> Path | None:
    """입력에 OBJ+MTL+텍스처 폴더가 있으면 zip 으로 새로 묶는다.
    이미 zip 이 있으면 그걸 우선 사용."""
    existing_zip = _find_one(input_dir, ("*.zip",))
    if existing_zip:
        return existing_zip
    obj = _find_one(input_dir, ("*.obj",))
    if not obj:
        return None
    obj_dir = obj.parent
    import zipfile
    zip_out = Path(f"/tmp/seed_obj_{project_uuid.hex}.zip")
    with zipfile.ZipFile(zip_out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in obj_dir.iterdir():
            if p.is_file() and p.suffix.lower() in {".obj", ".mtl", ".png", ".jpg", ".jpeg"}:
                zf.write(p, p.name)
    return zip_out if zip_out.stat().st_size > 0 else None


def _make_thumbnail(src_image: Path, project_uuid: uuid.UUID) -> Path:
    """첫 프레임을 1024 정사각 썸네일로."""
    from PIL import Image
    img = Image.open(src_image).convert("RGB")
    # 정사각 크롭 (가운데)
    w, h = img.size
    s = min(w, h)
    img = img.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2))
    img.thumbnail((1024, 1024), Image.LANCZOS)
    out = Path(f"/tmp/seed_thumb_{project_uuid.hex}.jpg")
    img.save(out, "JPEG", quality=88)
    return out


async def seed(args):
    input_dir = Path(args.input_dir).resolve()
    if not input_dir.is_dir():
        raise SystemExit(f"입력 폴더 없음: {input_dir}")

    project_uuid = uuid.uuid4()
    print(f"[seed] 프로젝트 ID: {project_uuid}")

    # 1) 파일 탐색 ─────────────────────────────────────────────────
    glb = _find_one(input_dir, ("*.glb",))
    if not glb:
        raise SystemExit("GLB 파일을 찾지 못함 (최종 메쉬 필수)")
    obj_zip = _make_obj_zip(input_dir, project_uuid)
    gauss_ply = _find_one(input_dir, ("point_cloud.ply", "*.ply"))
    colmap_ply = _find_one(input_dir, ("points3D_preview.ply",)) or \
                 _find_one(input_dir, ("points3D.ply",))
    first_frame = _find_first_frame(input_dir)
    n_frames = _count_frames(input_dir)
    print(f"[seed] 탐색 결과:")
    print(f"  GLB         : {glb} ({glb.stat().st_size/1024/1024:.1f}MB)")
    print(f"  OBJ zip     : {obj_zip}")
    print(f"  2DGS PLY    : {gauss_ply}")
    print(f"  COLMAP PLY  : {colmap_ply}")
    print(f"  첫 프레임   : {first_frame} (총 {n_frames}장)")

    # 2) /shared 안에 워크스페이스 구조 만들기 (preview 파일 위치 일치) ─
    output_dir = f"/shared/outputs/{project_uuid.hex}"
    upload_dir = f"/shared/uploads/{project_uuid.hex}"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    Path(upload_dir).mkdir(parents=True, exist_ok=True)

    if colmap_ply:
        dst = Path(output_dir) / "workspace" / "colmap" / "sparse" / "0" / "points3D_preview.ply"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(colmap_ply, dst)
        print(f"[seed] COLMAP PLY → {dst}")
    if gauss_ply:
        dst = Path(output_dir) / "reconstruction" / "point_cloud" / "iteration_7000" / "point_cloud.ply"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(gauss_ply, dst)
        print(f"[seed] 2DGS PLY → {dst}")
    if first_frame:
        shutil.copy2(first_frame, Path(upload_dir) / first_frame.name)

    # 3) MinIO 업로드 ──────────────────────────────────────────────
    prefix = f"projects/{project_uuid}/assets"
    glb_key = storage_service.upload_from_path(str(glb), prefix=prefix)
    print(f"[seed] GLB 업로드: {glb_key}")

    obj_key = None
    obj_size = 0
    if obj_zip:
        obj_key = storage_service.upload_from_path(str(obj_zip), prefix=prefix)
        obj_size = obj_zip.stat().st_size
        print(f"[seed] OBJ zip 업로드: {obj_key}")

    ply_key = None
    ply_size = 0
    if gauss_ply:
        ply_key = storage_service.upload_from_path(str(gauss_ply), prefix=prefix)
        ply_size = gauss_ply.stat().st_size
        print(f"[seed] PLY 업로드: {ply_key}")

    # 썸네일 = 첫 프레임 정사각 크롭 + 1024 리사이즈
    cover_key = None
    if first_frame:
        thumb = _make_thumbnail(first_frame, project_uuid)
        cover_key = storage_service.upload_from_path(
            str(thumb), prefix=f"projects/{project_uuid}/thumbnails"
        )
        thumb.unlink(missing_ok=True)
        print(f"[seed] 썸네일 업로드: {cover_key}")

    # 4) DB 삽입 ─────────────────────────────────────────────────
    engine = create_async_engine(settings.DATABASE_URL)
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with Session() as s:
            owner_id = None
            if args.owner_email:
                r = await s.execute(select(User).where(User.email == args.owner_email))
                u = r.scalar_one_or_none()
                if u is None:
                    print(f"[seed] ⚠️ 소유자 이메일 '{args.owner_email}' 없음 → owner_id=NULL")
                else:
                    owner_id = u.id
            else:
                # 첫 번째 사용자
                r = await s.execute(select(User).limit(1))
                u = r.scalar_one_or_none()
                if u:
                    owner_id = u.id

            category = Category(args.category.lower()) if args.category else Category.OTHER
            model_type = ModelType(args.model_type.lower())

            project = Project(
                id=project_uuid,
                owner_id=owner_id,
                name=args.name,
                description=args.description or "기존 결과물에서 시드된 프로젝트",
                status=JobStatus.SUCCESS,
                progress=100,
                current_step="완료!",
                model_type=model_type,
                category=category,
                is_public=args.public,
                pipeline_config={"seeded": True, "source_dir": str(input_dir)},
                upload_dir=upload_dir,
                output_dir=output_dir,
                image_count=n_frames or 60,
                cover_image_key=cover_key,
                completed_at=datetime.utcnow(),
            )
            s.add(project)
            await s.flush()  # project.id 보장

            s.add(Asset(
                project_id=project_uuid,
                format=AssetFormat.GLB,
                storage_key=glb_key,
                file_size=glb.stat().st_size,
                has_texture=True,
            ))
            if obj_key:
                s.add(Asset(
                    project_id=project_uuid,
                    format=AssetFormat.OBJ,
                    storage_key=obj_key,
                    file_size=obj_size,
                    has_texture=True,
                ))
            if ply_key:
                s.add(Asset(
                    project_id=project_uuid,
                    format=AssetFormat.PLY,
                    storage_key=ply_key,
                    file_size=ply_size,
                    has_texture=False,
                ))

            await s.commit()
    finally:
        await engine.dispose()

    print(f"\n[seed] ✅ 완료. 프로젝트 ID: {project_uuid}")
    print(f"  - http://localhost/projects/{project_uuid}")
    print(f"  - API  : http://localhost:8000/api/v1/projects/{project_uuid}")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", required=True, help="output_gundam 같은 결과물 폴더")
    p.add_argument("--name", required=True)
    p.add_argument("--description", default=None)
    p.add_argument("--owner-email", default=None)
    p.add_argument("--model-type", default="twodgs",
                   choices=["sugar", "gof", "nerf", "tripo", "twodgs"])
    p.add_argument("--category", default="other")
    p.add_argument("--public", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(seed(parse_args()))
