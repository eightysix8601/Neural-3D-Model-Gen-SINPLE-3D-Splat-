"""TripoSG 워커 (port 8017) — 공식 inference 패턴 기반.

핵심 흐름:
1. 업로드 이미지를 임시파일로 저장 (prepare_image 가 cv2.imread 사용)
2. BriaRMBG 로 배경 자동 제거 (RGBA 입력이면 자동 스킵)
3. prepare_image 로 흰 배경 + 정사각 패딩 PIL 이미지 생성
4. TripoSGPipeline 으로 메쉬 생성: outputs.samples[0] = (vertices, faces)
5. trimesh 로 GLB + OBJ 저장
6. pyrender(osmesa) 로 4면(front/back/left/right) PNG 렌더링 → thumbnail asset 반환

VRAM: TripoSG fp16 ~6GB + BriaRMBG ~150MB.
가중치: 첫 호출 시 HF 자동 다운로드 (/weights/triposg, /weights/rmbg).
헤드리스 렌더: PYOPENGL_PLATFORM=osmesa (Dockerfile 에서 설정).
"""
# pyrender 가 첫 import 시 PYOPENGL_PLATFORM 을 확인하므로, 환경변수 보장
import os as _os
_os.environ.setdefault("PYOPENGL_PLATFORM", "osmesa")
import os
import sys
import gc
import uuid
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from PIL import Image
from loguru import logger

# /opt/TripoSG/scripts 의 briarmbg.py, image_process.py 를 import 가능하게 함
TRIPOSG_REPO_DIR = os.environ.get("TRIPOSG_REPO_DIR", "/opt/TripoSG")
SCRIPTS_DIR = os.path.join(TRIPOSG_REPO_DIR, "scripts")
if os.path.isdir(SCRIPTS_DIR) and SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
# triposg 패키지 자체 (setup.py 가 없어서 symlink 또는 PYTHONPATH 로 추가됨)
if os.path.isdir(TRIPOSG_REPO_DIR) and TRIPOSG_REPO_DIR not in sys.path:
    sys.path.insert(0, TRIPOSG_REPO_DIR)


app = FastAPI(title="TripoSG Worker", version="1.1.0")

_triposg_pipe = None
_rmbg_net = None

WEIGHTS_TRIPOSG = os.environ.get("TRIPOSG_WEIGHTS", "/weights/triposg")
WEIGHTS_RMBG    = os.environ.get("RMBG_WEIGHTS",   "/weights/rmbg")
HF_TRIPOSG = os.environ.get("TRIPOSG_REPO", "VAST-AI/TripoSG")
HF_RMBG    = os.environ.get("RMBG_REPO",    "briaai/RMBG-1.4")


def _free_vram():
    try:
        import torch
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def _front_project_vertex_color(mesh, input_image_path: str, fallback_rgb=(180, 180, 180)):
    """입력 이미지를 메쉬에 정면 방향으로 투영해 vertex color 부착.

    원리:
    - GLB/Three.js Y-up 기준. 정면 = +Z 방향에서 보는 화면.
    - 메쉬를 -1..1 정규화 후, (x, y) 가 화면 좌표.
    - 각 vertex 의 (x, y) 를 입력 이미지 픽셀로 매핑 → RGB 추출.
    - 노멀의 z 성분 < 0 (뒷면 vertex) 은 fallback 색 (회색) 으로.

    Tripo 사이트 수준 PBR 은 아니지만, 외부 모델 의존 없이 정면 또렷한 GLB 를
    안정적으로 만들어준다. 8회 디버그 끝에 결정한 안정성 우선 솔루션.
    """
    try:
        import numpy as np
        from PIL import Image
    except Exception as e:
        logger.warning(f"[Texture] PIL/numpy 불러오기 실패: {e}")
        return mesh

    try:
        img = Image.open(input_image_path).convert("RGBA")
        img_w, img_h = img.size
        pix = np.array(img)  # (H, W, 4)
        # 알파 채널이 있으면 알파<10 픽셀은 배경으로 간주
        has_alpha = pix.shape[2] == 4

        # 메쉬를 [-1, 1] 박스로 정규화
        bounds = mesh.bounds
        center = (bounds[0] + bounds[1]) / 2.0
        scale = float(np.max(bounds[1] - bounds[0])) / 2.0
        if scale <= 0:
            return mesh
        verts = (np.asarray(mesh.vertices) - center) / scale  # (N, 3) in [-1, 1]

        # 화면 좌표 매핑.
        # X축 180° 회전 후의 메쉬에서:
        #   - 머리가 +Y (정자세)지만 카메라 시점에선 -Y 쪽으로 매핑돼야 image top 과 일치.
        #     → v = (y+1)/2 * H  (Y 반전 X)
        #   - 정면은 -Z 쪽이므로 normal 의 Z 가 음수인 vertex 가 정면. → back_mask = z > 0
        u = ((verts[:, 0] + 1.0) / 2.0 * (img_w - 1)).astype(np.int32)
        v = ((verts[:, 1] + 1.0) / 2.0 * (img_h - 1)).astype(np.int32)
        u = np.clip(u, 0, img_w - 1)
        v = np.clip(v, 0, img_h - 1)

        sampled = pix[v, u]  # (N, 4)
        if not has_alpha:
            sampled = np.concatenate(
                [sampled, np.full((sampled.shape[0], 1), 255, dtype=sampled.dtype)], axis=1,
            )

        # 뒷면 vertex 판단 — normal 의 Z 가 + 인 vertex 가 뒷면 (카메라 반대 방향 향함)
        try:
            vnormals = np.asarray(mesh.vertex_normals)
            back_mask = vnormals[:, 2] > 0.1
        except Exception:
            back_mask = np.zeros(len(verts), dtype=bool)

        # 알파 < 10 인 픽셀 (이미지에서 배경 부분) 도 fallback 으로 처리
        if has_alpha:
            bg_mask = sampled[:, 3] < 10
            replace_mask = back_mask | bg_mask
        else:
            replace_mask = back_mask

        # fallback 색
        fb = np.array([*fallback_rgb, 255], dtype=sampled.dtype)
        if replace_mask.any():
            sampled[replace_mask] = fb

        # 알파는 항상 255 로 (반투명 메쉬 방지)
        sampled[:, 3] = 255

        # mesh.visual 에 vertex color 부착
        import trimesh
        mesh.visual = trimesh.visual.ColorVisuals(mesh=mesh, vertex_colors=sampled)
        logger.info(f"[Texture] 정면 투영 vertex color 부착: V={len(verts)} 뒷면={int(back_mask.sum())} bg={int((replace_mask & ~back_mask).sum()) if has_alpha else 0}")
        return mesh
    except Exception as e:
        logger.warning(f"[Texture] 정면 투영 실패(무시): {e}")
        return mesh


def _render_four_views(mesh, out_dir: str, base: str, size: int = 768) -> list[dict]:
    """trimesh.Mesh → 앞/뒤/좌/우 4면 PNG 렌더링.

    pyrender + osmesa 헤드리스 렌더링. 실패 시 빈 리스트 반환 (생성 자체는 성공).
    카메라는 메쉬 bounding sphere 기준으로 자동 배치. 흰 배경.
    """
    try:
        import numpy as np
        import pyrender
        import trimesh
        from PIL import Image
    except Exception as e:
        logger.warning(f"[Render] pyrender import 실패, 렌더 건너뜀: {e}")
        return []

    try:
        # 메쉬 복사 (원본 손상 방지) + 컬러 정보 없으면 회색 머티리얼
        mesh_for_render = mesh.copy()
        if mesh_for_render.visual is None or not hasattr(mesh_for_render.visual, "kind") \
                or mesh_for_render.visual.kind not in ("vertex", "face", "texture"):
            mesh_for_render.visual = trimesh.visual.ColorVisuals(
                mesh=mesh_for_render,
                vertex_colors=np.tile([200, 200, 200, 255], (len(mesh_for_render.vertices), 1)),
            )

        scene = pyrender.Scene(bg_color=[1.0, 1.0, 1.0, 0.0], ambient_light=[0.5, 0.5, 0.5])
        mesh_node = pyrender.Mesh.from_trimesh(mesh_for_render, smooth=True)
        scene.add(mesh_node)

        # 메쉬 bounding sphere → 카메라 거리 산정
        bounds = mesh_for_render.bounds  # (2,3) min/max
        center = (bounds[0] + bounds[1]) / 2.0
        extent = float(np.linalg.norm(bounds[1] - bounds[0]))
        cam_dist = extent * 1.2 if extent > 0 else 2.0

        camera = pyrender.PerspectiveCamera(yfov=np.pi / 4.0, aspectRatio=1.0)
        light = pyrender.DirectionalLight(color=[1, 1, 1], intensity=3.0)

        # 4방향 카메라 위치 (Y-up 가정, GLB 정자세)
        # front=+Z, back=-Z, right=+X, left=-X
        views = {
            "front": np.array([0, 0,  cam_dist]),
            "back":  np.array([0, 0, -cam_dist]),
            "right": np.array([cam_dist, 0, 0]),
            "left":  np.array([-cam_dist, 0, 0]),
        }

        renderer = pyrender.OffscreenRenderer(viewport_width=size, viewport_height=size)
        results = []
        for name, eye in views.items():
            eye_world = center + eye
            # 카메라 행렬 (look at center)
            forward = (center - eye_world)
            forward = forward / (np.linalg.norm(forward) + 1e-9)
            up = np.array([0, 1, 0], dtype=float)
            right = np.cross(forward, up)
            right = right / (np.linalg.norm(right) + 1e-9)
            up = np.cross(right, forward)
            cam_pose = np.eye(4)
            cam_pose[:3, 0] = right
            cam_pose[:3, 1] = up
            cam_pose[:3, 2] = -forward  # OpenGL: -Z 방향이 카메라 앞
            cam_pose[:3, 3] = eye_world

            cam_node = scene.add(camera, pose=cam_pose)
            light_node = scene.add(light, pose=cam_pose)
            try:
                color, _ = renderer.render(scene)
            finally:
                scene.remove_node(cam_node)
                scene.remove_node(light_node)

            png_path = os.path.join(out_dir, f"thumb_{base}_{name}.png")
            Image.fromarray(color).save(png_path)
            results.append({
                "format": "thumbnail", "view": name,
                "path": png_path, "size": os.path.getsize(png_path),
            })
            logger.info(f"[Render] {name} → {png_path}")

        renderer.delete()
        return results
    except Exception as e:
        logger.warning(f"[Render] 4면 렌더링 실패(무시): {e}")
        return []


def _ensure_weights(local_dir: str, repo: str) -> str:
    p = Path(local_dir)
    if p.exists() and any(p.iterdir()):
        return str(p)
    p.mkdir(parents=True, exist_ok=True)
    logger.info(f"[Weights] HF 다운로드 시작: {repo} → {p}")
    from huggingface_hub import snapshot_download
    snapshot_download(repo_id=repo, local_dir=str(p), local_dir_use_symlinks=False)
    logger.info(f"[Weights] 다운로드 완료: {p}")
    return str(p)


def _load_rmbg():
    """BriaRMBG (briaai/RMBG-1.4) — prepare_image 가 alpha 없을 때 호출."""
    global _rmbg_net
    if _rmbg_net is not None:
        return _rmbg_net
    import torch
    from briarmbg import BriaRMBG  # /opt/TripoSG/scripts/briarmbg.py
    weights = _ensure_weights(WEIGHTS_RMBG, HF_RMBG)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    net = BriaRMBG.from_pretrained(weights).to(device)
    net.eval()
    _rmbg_net = net
    logger.info("[RMBG] 로드 완료")
    return net


def _load_triposg():
    """TripoSG 파이프라인 (fp16)."""
    global _triposg_pipe
    if _triposg_pipe is not None:
        return _triposg_pipe
    import torch
    from triposg.pipelines.pipeline_triposg import TripoSGPipeline  # /opt/TripoSG/triposg
    weights = _ensure_weights(WEIGHTS_TRIPOSG, HF_TRIPOSG)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    pipe = TripoSGPipeline.from_pretrained(weights).to(device, dtype)
    _triposg_pipe = pipe
    logger.info(f"[TripoSG] 로드 완료 (device={device}, dtype={dtype})")
    return pipe


@app.get("/health")
def health():
    import torch
    return {
        "status": "ok",
        "service": "tripo_worker",
        "cuda": torch.cuda.is_available(),
        "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
        "triposg_loaded": _triposg_pipe is not None,
        "rmbg_loaded": _rmbg_net is not None,
    }


@app.post("/generate")
async def generate(
    image: UploadFile = File(...),
    output_dir: str = Form(...),
    num_inference_steps: int = Form(50),
    guidance_scale: float = Form(7.0),
    use_sparseflex: bool = Form(False),  # 호환용 (현재 미사용)
    use_texture: bool = Form(True),  # ON 이면 정면 투영으로 vertex color 부착
    seed: Optional[int] = Form(None),
    faces: int = Form(50000),  # 자동 face 감소 (브라우저 로드 부담↓). 0 이면 비활성.
):
    """이미지 1장 → 3D 메쉬 (GLB + OBJ).

    공식 inference_triposg.py 의 run_triposg 패턴을 그대로 따른다.
    """
    import numpy as np
    import torch
    import trimesh

    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(400, "이미지 파일이어야 합니다")

    raw = await image.read()
    suffix = os.path.splitext(image.filename or "")[1].lower() or ".png"
    if suffix not in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
        suffix = ".png"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)

        # 모델 로드 (lazy)
        pipe = _load_triposg()
        rmbg_net = _load_rmbg()

        # 전처리: 배경 제거 + 흰 배경 + 정사각 패딩
        from image_process import prepare_image
        logger.info(f"[TripoSG] prepare_image: {tmp_path}")
        img_pil = prepare_image(
            tmp_path,
            bg_color=np.array([1.0, 1.0, 1.0]),
            rmbg_net=rmbg_net,
        )
        if not isinstance(img_pil, Image.Image):
            raise HTTPException(500, f"prepare_image 결과 이상: {img_pil!r}")

        seed_val = int(seed) if seed is not None else 42
        generator = torch.Generator(device=pipe.device).manual_seed(seed_val)

        logger.info(f"[TripoSG] 추론 steps={num_inference_steps} cfg={guidance_scale} seed={seed_val}")
        with torch.no_grad():
            out = pipe(
                image=img_pil,
                generator=generator,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
            ).samples[0]  # (vertices_np, faces_np)

        vertices = out[0].astype(np.float32)
        faces_arr = np.ascontiguousarray(out[1])
        mesh = trimesh.Trimesh(vertices, faces_arr, process=False)
        v0, f0 = len(mesh.vertices), len(mesh.faces)
        logger.info(f"[TripoSG] 원본 메쉬: V={v0} F={f0}")

        # ── 메쉬 정리 ──────────────────────────────────────────
        # TripoSG sparse-flex 출력은 voxel corner 가 중복으로 들어있어 V≫F 비정상.
        # 중복 vertex/face 제거 + 노멀 정규화로 깨끗한 GLB 만든다.
        try:
            mesh.merge_vertices()
            mesh.update_faces(mesh.unique_faces())
            mesh.update_faces(mesh.nondegenerate_faces())
            mesh.remove_unreferenced_vertices()
            mesh.fix_normals()
            logger.info(f"[TripoSG] 정리 후: V={len(mesh.vertices)} F={len(mesh.faces)}")
        except Exception as e:
            logger.warning(f"[TripoSG] 메쉬 cleanup 경고(무시): {e}")

        # ── 좌표계 보정 ────────────────────────────────────────
        # TripoSG 출력이 Three.js/GLB(Y-up) 기준 위아래가 뒤집혀 나오는 문제.
        # X축 180° 회전 = (y, z) → (-y, -z). 머리가 위로 가게 정자세.
        try:
            import trimesh.transformations as tf
            mesh.apply_transform(tf.rotation_matrix(np.pi, [1, 0, 0]))
        except Exception as e:
            logger.warning(f"[TripoSG] 좌표 보정 실패(무시): {e}")

        # ── face decimation ────────────────────────────────────
        # 브라우저에서 GLB 가 부드럽게 로드되려면 face/vertex 수가 적당해야 함.
        # 자동으로 50k faces 정도로 줄임. (TripoSG 원본은 1.6M+ faces 라 너무 무거움)
        # vertex color 입히기 전에 decimate 해야 color 가 정확히 매핑됨.
        # pyfqmr (Fast Quadric Mesh Reduction) 사용 — pymeshlab API 변경 회피.
        if faces and int(faces) > 0 and len(mesh.faces) > int(faces):
            decimated = False
            target = int(faces)

            # 1차: pyfqmr (가장 안정적, 빠름)
            try:
                import pyfqmr
                simplifier = pyfqmr.Simplify()
                simplifier.setMesh(np.asarray(mesh.vertices), np.asarray(mesh.faces))
                simplifier.simplify_mesh(
                    target_count=target, aggressiveness=7,
                    preserve_border=True, verbose=False,
                )
                v, f, _ = simplifier.getMesh()
                mesh = trimesh.Trimesh(v, f, process=False)
                logger.info(f"[TripoSG] decimated (pyfqmr) → V={len(mesh.vertices)} F={len(mesh.faces)}")
                decimated = True
            except Exception as e:
                logger.warning(f"[TripoSG] pyfqmr decimation 실패: {e}")

            # 2차 폴백: trimesh built-in (fast-simplification 의존)
            if not decimated:
                try:
                    mesh = mesh.simplify_quadric_decimation(target)
                    logger.info(f"[TripoSG] decimated (trimesh) → V={len(mesh.vertices)} F={len(mesh.faces)}")
                    decimated = True
                except Exception as e:
                    logger.warning(f"[TripoSG] trimesh decimation 실패: {e}")

            if not decimated:
                logger.warning(f"[TripoSG] decimation 모두 실패 — 원본 메쉬 사용 (V={len(mesh.vertices)} F={len(mesh.faces)})")

        # ── 텍스쳐 (정면 투영 vertex color) ─────────────────────
        # use_texture ON 이면 prepare_image 의 결과를 메쉬에 정면 투영.
        # decimation 후에 적용해서 vertex color 가 정확히 매핑되도록.
        if use_texture:
            try:
                proc_img_path = tmp_path + ".processed.png"
                img_pil.save(proc_img_path)
                mesh = _front_project_vertex_color(mesh, proc_img_path)
                try: os.unlink(proc_img_path)
                except Exception: pass
            except Exception as e:
                logger.warning(f"[TripoSG] 텍스쳐 적용 실패(무시): {e}")

        # face decimation 은 위에서 vertex color 전에 이미 처리됨

        os.makedirs(output_dir, exist_ok=True)
        base = uuid.uuid4().hex[:8]
        glb_path = os.path.join(output_dir, f"mesh_{base}.glb")
        obj_path = os.path.join(output_dir, f"mesh_{base}.obj")
        mesh.export(glb_path)
        mesh.export(obj_path)

        # 4면 미리보기 렌더링 (실패해도 메쉬 생성 자체는 성공으로 처리)
        thumbnail_assets = _render_four_views(mesh, output_dir, base, size=768)

        _free_vram()
        return {
            "assets": [
                {"format": "glb", "path": glb_path, "size": os.path.getsize(glb_path)},
                {"format": "obj", "path": obj_path, "size": os.path.getsize(obj_path)},
                *thumbnail_assets,
            ],
            "vertices": int(len(mesh.vertices)),
            "faces": int(len(mesh.faces)),
        }
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
