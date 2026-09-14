"""공용 메쉬/텍스처 베이커.

세 곳에서 재사용한다:
  - SuGaR refine 가 죽었을 때의 자동 폴백 (3DGS point_cloud.ply → 메쉬)
  - GOF extract_mesh 가 죽었을 때의 자동 폴백 (GOF point_cloud.ply → 메쉬)
  - NeRF(nerfstudio) 워커가 뽑은 정점색 메쉬(ply) → 텍스처드 OBJ

핵심 계약:
  * 입력이 무엇이든 **항상** OBJ + GLB 는 만들어낸다 (정점색 폴백 포함).
  * 가능하면 OBJ + MTL + PNG(텍스처) + GLB 풀세트를 만든다.
  * 어떤 단계가 실패해도 예외를 위로 던지지 않고, 만들 수 있는 만큼만 만들어
    에셋 리스트를 돌려준다. (파이프라인이 절대 빈손으로 끝나지 않게)

반환 형식은 SuGaR `_collect_assets` 와 동일:
    [{"format": "obj"|"mtl"|"texture"|"glb", "path": str, "size": int}, ...]
"""
import os
import math
import numpy as np
from loguru import logger

# SH0 계수 (3DGS f_dc → RGB 변환)
_SH_C0 = 0.28209479177387814


# ──────────────────────────────────────────────────────────────────────────
# 1. 포인트클라우드 / 메쉬 PLY 읽기
# ──────────────────────────────────────────────────────────────────────────
def _read_pointcloud_ply(path: str):
    """3DGS / 일반 PLY 를 (xyz[N,3] float64, rgb[N,3] float64 0~1) 로 읽는다."""
    from plyfile import PlyData

    ply = PlyData.read(path)
    v = ply["vertex"]
    names = set(v.data.dtype.names or [])

    xyz = np.stack([np.asarray(v["x"]), np.asarray(v["y"]), np.asarray(v["z"])], axis=1).astype(np.float64)

    if {"f_dc_0", "f_dc_1", "f_dc_2"} <= names:
        # 3DGS: SH DC 계수 → 색
        f_dc = np.stack(
            [np.asarray(v["f_dc_0"]), np.asarray(v["f_dc_1"]), np.asarray(v["f_dc_2"])], axis=1
        ).astype(np.float64)
        rgb = np.clip(0.5 + _SH_C0 * f_dc, 0.0, 1.0)
    elif {"red", "green", "blue"} <= names:
        rgb = np.stack(
            [np.asarray(v["red"]), np.asarray(v["green"]), np.asarray(v["blue"])], axis=1
        ).astype(np.float64) / 255.0
    else:
        rgb = np.full((xyz.shape[0], 3), 0.72, dtype=np.float64)

    # 3DGS 면 opacity 로 떠다니는 노이즈 제거
    if "opacity" in names:
        op = 1.0 / (1.0 + np.exp(-np.asarray(v["opacity"]).astype(np.float64)))
        keep = op > 0.05
        if keep.sum() > 1000:  # 너무 많이 날아가면 필터 포기
            xyz, rgb = xyz[keep], rgb[keep]

    # NaN/inf 제거
    good = np.isfinite(xyz).all(axis=1) & np.isfinite(rgb).all(axis=1)
    return xyz[good], rgb[good]


def _largest_cluster(mesh):
    import open3d as o3d  # noqa

    try:
        tri_idx, _, _ = mesh.cluster_connected_triangles()
        tri_idx = np.asarray(tri_idx)
        if tri_idx.size == 0:
            return mesh
        # 가장 큰 연결요소만 유지 (떠다니는 파편 제거)
        biggest = np.bincount(tri_idx).argmax()
        rm = np.where(tri_idx != biggest)[0]
        mesh.remove_triangles_by_index(rm.tolist())
        mesh.remove_unreferenced_vertices()
    except Exception as e:
        logger.warning(f"[meshbake] 클러스터 정리 건너뜀: {e}")
    return mesh


def _poisson_mesh(xyz: np.ndarray, rgb: np.ndarray, target_tris: int = 120_000):
    """포인트클라우드 → 워터타이트 메쉬 (정점색 포함)."""
    import open3d as o3d

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(xyz)
    pcd.colors = o3d.utility.Vector3dVector(rgb)

    # 통계적 이상치 제거 (점이 충분할 때만)
    if len(pcd.points) > 5000:
        pcd, _ = pcd.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.5)

    pcd.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamKNN(knn=30))
    try:
        pcd.orient_normals_consistent_tangent_plane(30)
    except Exception:
        pcd.orient_normals_towards_camera_location(pcd.get_center())

    mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        pcd, depth=9, scale=1.1, linear_fit=False
    )
    densities = np.asarray(densities)
    if densities.size:
        thr = np.quantile(densities, 0.04)
        mesh.remove_vertices_by_mask(densities < thr)

    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_triangles()
    mesh.remove_duplicated_vertices()
    mesh.remove_unreferenced_vertices()
    mesh = _largest_cluster(mesh)

    n_tri = len(mesh.triangles)
    if n_tri > target_tris:
        mesh = mesh.simplify_quadric_decimation(target_number_of_triangles=target_tris)
        mesh.remove_unreferenced_vertices()

    mesh.compute_vertex_normals()
    if not mesh.has_vertex_colors() or len(mesh.vertex_colors) != len(mesh.vertices):
        # 데시메이션 후 색이 날아가면 원본 점에서 최근접 색을 전사
        _transfer_colors(mesh, xyz, rgb)
    return mesh


def _load_mesh_ply(path: str):
    """정점색 메쉬 PLY 로드 + 정리.

    각 단계마다 로그를 찍어 메쉬가 클 때 어디서 시간이 걸리는지 보이게 한다.
    입력이 매우 크면(>2M tris) quadric_decimation 만으로는 30~60분이 걸리므로,
    vertex_clustering 으로 빠른 1차 감축(수초~수십초) 후 정밀 데시메이션을 한다.
    """
    import open3d as o3d

    logger.info(f"[meshbake] Open3D 로드 시작")
    mesh = o3d.io.read_triangle_mesh(path)
    logger.info(f"[meshbake] 로드 완료: V={len(mesh.vertices):,}, F={len(mesh.triangles):,}")

    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_triangles()
    mesh.remove_duplicated_vertices()
    mesh.remove_unreferenced_vertices()
    logger.info(f"[meshbake] 중복/디제너레이트 제거 후: V={len(mesh.vertices):,}, F={len(mesh.triangles):,}")

    logger.info(f"[meshbake] 최대 연결요소 추출 중...")
    mesh = _largest_cluster(mesh)
    logger.info(f"[meshbake] 최대 연결요소만 유지: F={len(mesh.triangles):,}")

    n_tri = len(mesh.triangles)
    if n_tri > 200_000:
        # 초대형 입력 (>2M tris) 은 quadric_decimation 단독으론 너무 느림.
        # vertex_clustering 으로 빠르게 1차 감축 후 정밀 데시메이션.
        if n_tri > 2_000_000:
            bbox = mesh.get_axis_aligned_bounding_box()
            voxel = max(bbox.get_extent()) / 256.0
            logger.info(
                f"[meshbake] 초대형 입력 → vertex_clustering 1차 감축 "
                f"(voxel_size={voxel:.5f})"
            )
            mesh = mesh.simplify_vertex_clustering(
                voxel_size=voxel,
                contraction=o3d.geometry.SimplificationContraction.Average,
            )
            logger.info(f"[meshbake] vertex_clustering 완료: F={len(mesh.triangles):,}")

        logger.info(f"[meshbake] quadric_decimation 시작 → 200k tris")
        mesh = mesh.simplify_quadric_decimation(target_number_of_triangles=200_000)
        mesh.remove_unreferenced_vertices()
        logger.info(f"[meshbake] 데시메이션 완료: F={len(mesh.triangles):,}")

    logger.info(f"[meshbake] 정점 노멀 계산")
    mesh.compute_vertex_normals()
    return mesh


def _transfer_colors(mesh, src_xyz: np.ndarray, src_rgb: np.ndarray):
    """원본 점군에서 메쉬 정점으로 최근접 색 전사."""
    from scipy.spatial import cKDTree

    verts = np.asarray(mesh.vertices)
    if verts.size == 0 or src_xyz.size == 0:
        return
    tree = cKDTree(src_xyz)
    _, idx = tree.query(verts, k=1)
    import open3d as o3d

    mesh.vertex_colors = o3d.utility.Vector3dVector(np.clip(src_rgb[idx], 0.0, 1.0))


# ──────────────────────────────────────────────────────────────────────────
# 2. UV 언랩 + 텍스처 베이크
# ──────────────────────────────────────────────────────────────────────────
# Numba 가 설치돼 있으면 베이크 커널을 JIT 컴파일 + 멀티스레드로 돌려
# 200k 삼각형 베이크가 70분 → 2~5분으로 단축된다. 미설치면 NumPy 폴백.
try:
    import numba as _numba

    @_numba.njit(parallel=True, fastmath=True, cache=True)
    def _bake_kernel(px, py, col_u, faces_u, S, img, filled):
        for fi in _numba.prange(faces_u.shape[0]):
            i0 = faces_u[fi, 0]
            i1 = faces_u[fi, 1]
            i2 = faces_u[fi, 2]
            x0 = px[i0]; y0 = py[i0]
            x1 = px[i1]; y1 = py[i1]
            x2 = px[i2]; y2 = py[i2]
            c0r = col_u[i0, 0]; c0g = col_u[i0, 1]; c0b = col_u[i0, 2]
            c1r = col_u[i1, 0]; c1g = col_u[i1, 1]; c1b = col_u[i1, 2]
            c2r = col_u[i2, 0]; c2g = col_u[i2, 1]; c2b = col_u[i2, 2]

            minx = int(min(x0, x1, x2))
            maxx = int(max(x0, x1, x2)) + 1
            miny = int(min(y0, y1, y2))
            maxy = int(max(y0, y1, y2)) + 1
            if minx < 0: minx = 0
            if miny < 0: miny = 0
            if maxx > S - 1: maxx = S - 1
            if maxy > S - 1: maxy = S - 1
            if maxx < minx or maxy < miny:
                continue

            denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            if abs(denom) < 1e-9:
                continue
            inv = 1.0 / denom

            for yi in range(miny, maxy + 1):
                fy = float(yi)
                for xi in range(minx, maxx + 1):
                    fx = float(xi)
                    a = ((y1 - y2) * (fx - x2) + (x2 - x1) * (fy - y2)) * inv
                    b = ((y2 - y0) * (fx - x2) + (x0 - x2) * (fy - y2)) * inv
                    c = 1.0 - a - b
                    if a >= -1e-3 and b >= -1e-3 and c >= -1e-3:
                        r = a * c0r + b * c1r + c * c2r
                        g = a * c0g + b * c1g + c * c2g
                        bl = a * c0b + b * c1b + c * c2b
                        if r < 0.0: r = 0.0
                        elif r > 1.0: r = 1.0
                        if g < 0.0: g = 0.0
                        elif g > 1.0: g = 1.0
                        if bl < 0.0: bl = 0.0
                        elif bl > 1.0: bl = 1.0
                        img[yi, xi, 0] = r
                        img[yi, xi, 1] = g
                        img[yi, xi, 2] = bl
                        filled[yi, xi] = True

    _HAS_NUMBA = True
except Exception as _e:  # numba 미설치 또는 import 실패
    _HAS_NUMBA = False


def _bake_texture(verts, faces, vcolors, tex_size=2048):
    """xatlas 로 UV 를 풀고 정점색을 텍스처에 베이크.

    반환: (verts_u[Vu,3], uvs[Vu,2], faces_u[F,3], image[H,W,3] uint8)  또는 None
    """
    try:
        import xatlas
    except Exception as e:
        logger.warning(f"[meshbake] xatlas 없음, 텍스처 베이크 생략: {e}")
        return None

    try:
        vmapping, indices, uvs = xatlas.parametrize(
            verts.astype(np.float32), faces.astype(np.uint32)
        )
        vmapping = np.asarray(vmapping).astype(np.int64)
        faces_u = np.asarray(indices).astype(np.int64).reshape(-1, 3)
        uvs = np.asarray(uvs).astype(np.float64)
        verts_u = verts[vmapping]
        col_u = np.clip(vcolors[vmapping], 0.0, 1.0)

        S = int(tex_size)
        img = np.zeros((S, S, 3), dtype=np.float64)
        filled = np.zeros((S, S), dtype=np.bool_)

        # UV(0~1) → 픽셀. v 축은 뒤집어 이미지 좌표계로.
        px = uvs[:, 0] * (S - 1)
        py = (1.0 - uvs[:, 1]) * (S - 1)

        if _HAS_NUMBA:
            # 컴파일된 멀티스레드 베이크 (200k tris 케이스 70분 → 2~5분).
            logger.info(f"[meshbake] Numba JIT 베이크 실행")
            _bake_kernel(
                px.astype(np.float64), py.astype(np.float64),
                col_u.astype(np.float64),
                faces_u.astype(np.int64),
                S, img, filled,
            )
        else:
            # NumPy 폴백 (Numba 없을 때) — 느리지만 동작은 함
            logger.info(f"[meshbake] NumPy 폴백 베이크 (numba 미설치)")
            for f in faces_u:
                i0, i1, i2 = f
                x0, y0 = px[i0], py[i0]
                x1, y1 = px[i1], py[i1]
                x2, y2 = px[i2], py[i2]
                c0, c1, c2 = col_u[i0], col_u[i1], col_u[i2]

                minx = max(int(math.floor(min(x0, x1, x2))), 0)
                maxx = min(int(math.ceil(max(x0, x1, x2))), S - 1)
                miny = max(int(math.floor(min(y0, y1, y2))), 0)
                maxy = min(int(math.ceil(max(y0, y1, y2))), S - 1)
                if maxx < minx or maxy < miny:
                    continue

                xs = np.arange(minx, maxx + 1)
                ys = np.arange(miny, maxy + 1)
                gx, gy = np.meshgrid(xs.astype(np.float64), ys.astype(np.float64))

                denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
                if abs(denom) < 1e-9:
                    continue
                a = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) / denom
                b = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) / denom
                c = 1.0 - a - b
                inside = (a >= -1e-3) & (b >= -1e-3) & (c >= -1e-3)
                if not inside.any():
                    continue

                col = (
                    a[..., None] * c0[None, None, :]
                    + b[..., None] * c1[None, None, :]
                    + c[..., None] * c2[None, None, :]
                )
                yy = gy.astype(np.int64)[inside]
                xx = gx.astype(np.int64)[inside]
                img[yy, xx] = np.clip(col[inside], 0.0, 1.0)
                filled[yy, xx] = True

        # 빈 텍셀을 최근접 색으로 채워 UV 솔기/검은 줄 제거
        if filled.any() and not filled.all():
            try:
                from scipy.ndimage import distance_transform_edt

                _, (iy, ix) = distance_transform_edt(
                    ~filled, return_distances=True, return_indices=True
                )
                img = img[iy, ix]
            except Exception:
                pass

        image = (np.clip(img, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
        return verts_u, uvs.astype(np.float64), faces_u, image
    except Exception as e:
        logger.warning(f"[meshbake] 텍스처 베이크 실패, 정점색 폴백: {e}")
        return None


# ──────────────────────────────────────────────────────────────────────────
# 3. 디스크 기록 (OBJ / MTL / PNG / GLB)
# ──────────────────────────────────────────────────────────────────────────
def _asset(fmt, path):
    return {"format": fmt, "path": str(path), "size": os.path.getsize(path)}


def _write_textured_obj(out_dir, name, verts, uvs, faces, image):
    """OBJ + MTL + PNG 풀세트 기록. 에셋 리스트 반환."""
    from PIL import Image

    obj_p = os.path.join(out_dir, f"{name}.obj")
    mtl_p = os.path.join(out_dir, f"{name}.mtl")
    png_p = os.path.join(out_dir, f"{name}.png")

    Image.fromarray(image, "RGB").save(png_p)

    with open(mtl_p, "w") as f:
        f.write(f"newmtl material0\nKa 1 1 1\nKd 1 1 1\nKs 0 0 0\nd 1\nillum 1\nmap_Kd {name}.png\n")

    lines = [f"mtllib {name}.mtl", "usemtl material0"]
    for p in verts:
        lines.append(f"v {p[0]:.6f} {p[1]:.6f} {p[2]:.6f}")
    for uv in uvs:
        lines.append(f"vt {uv[0]:.6f} {uv[1]:.6f}")
    for tri in faces:
        a, b, c = tri[0] + 1, tri[1] + 1, tri[2] + 1
        lines.append(f"f {a}/{a} {b}/{b} {c}/{c}")
    with open(obj_p, "w") as f:
        f.write("\n".join(lines) + "\n")

    assets = [_asset("obj", obj_p), _asset("mtl", mtl_p), _asset("texture", png_p)]

    # GLB (텍스처 포함)
    try:
        import trimesh

        tm = trimesh.Trimesh(
            vertices=np.asarray(verts),
            faces=np.asarray(faces),
            visual=trimesh.visual.TextureVisuals(
                uv=np.asarray(uvs), image=Image.fromarray(image, "RGB")
            ),
            process=False,
        )
        glb_p = os.path.join(out_dir, f"{name}.glb")
        tm.export(glb_p)
        if os.path.exists(glb_p) and os.path.getsize(glb_p) > 0:
            assets.append(_asset("glb", glb_p))
    except Exception as e:
        logger.warning(f"[meshbake] 텍스처드 GLB 실패: {e}")
    return assets


def _write_vertexcolor_obj(out_dir, name, mesh):
    """텍스처 베이크 불가 시: 정점색 OBJ + GLB (블렌더에서 정상 오픈)."""
    verts = np.asarray(mesh.vertices)
    faces = np.asarray(mesh.triangles)
    cols = (
        np.asarray(mesh.vertex_colors)
        if mesh.has_vertex_colors()
        else np.full((len(verts), 3), 0.72)
    )
    obj_p = os.path.join(out_dir, f"{name}.obj")
    lines = []
    for p, col in zip(verts, cols):
        lines.append(
            f"v {p[0]:.6f} {p[1]:.6f} {p[2]:.6f} {col[0]:.4f} {col[1]:.4f} {col[2]:.4f}"
        )
    for tri in faces:
        lines.append(f"f {tri[0]+1} {tri[1]+1} {tri[2]+1}")
    with open(obj_p, "w") as f:
        f.write("\n".join(lines) + "\n")
    assets = [_asset("obj", obj_p)]
    try:
        import trimesh

        tm = trimesh.Trimesh(
            vertices=verts,
            faces=faces,
            vertex_colors=(np.clip(cols, 0, 1) * 255).astype(np.uint8),
            process=False,
        )
        glb_p = os.path.join(out_dir, f"{name}.glb")
        tm.export(glb_p)
        if os.path.exists(glb_p) and os.path.getsize(glb_p) > 0:
            assets.append(_asset("glb", glb_p))
    except Exception as e:
        logger.warning(f"[meshbake] 정점색 GLB 실패: {e}")
    return assets


def _mesh_to_assets(mesh, out_dir, name):
    os.makedirs(out_dir, exist_ok=True)
    verts = np.asarray(mesh.vertices)
    faces = np.asarray(mesh.triangles)
    if verts.size == 0 or faces.size == 0:
        raise RuntimeError("빈 메쉬 - 폴백 불가")
    vcolors = (
        np.asarray(mesh.vertex_colors)
        if mesh.has_vertex_colors()
        else np.full((len(verts), 3), 0.72)
    )

    logger.info(f"[meshbake] 텍스처 베이크 시작 (V={len(verts):,}, F={len(faces):,})")
    baked = _bake_texture(verts, faces, vcolors)
    if baked is not None:
        verts_u, uvs, faces_u, image = baked
        logger.info(
            f"[meshbake] 베이크 완료: V_uv={len(verts_u):,}, F_uv={len(faces_u):,}, "
            f"tex={image.shape[1]}x{image.shape[0]}"
        )
        try:
            assets = _write_textured_obj(out_dir, name, verts_u, uvs, faces_u, image)
            logger.info(f"[meshbake] 텍스처드 OBJ/MTL/PNG/GLB 기록 완료")
            return assets
        except Exception as e:
            logger.warning(f"[meshbake] 텍스처드 OBJ 기록 실패, 정점색 폴백: {e}")
    logger.info(f"[meshbake] 정점색 OBJ/GLB 폴백 기록")
    return _write_vertexcolor_obj(out_dir, name, mesh)


# ──────────────────────────────────────────────────────────────────────────
# 4. 공개 진입점
# ──────────────────────────────────────────────────────────────────────────
def gs_ply_to_assets(gs_ply: str, out_dir: str, name: str = "fallback_mesh") -> list:
    """3DGS point_cloud.ply → Poisson 메쉬 → 텍스처드 OBJ/MTL/PNG/GLB.

    절대 예외를 던지지 않는다. 실패하면 [] 반환 (호출부가 판단).
    """
    try:
        logger.info(f"[meshbake] 3DGS 폴백 시작: {gs_ply}")
        xyz, rgb = _read_pointcloud_ply(gs_ply)
        if xyz.shape[0] < 100:
            logger.error(f"[meshbake] 점이 너무 적음({xyz.shape[0]})")
            return []
        mesh = _poisson_mesh(xyz, rgb)
        assets = _mesh_to_assets(mesh, out_dir, name)
        logger.info(f"[meshbake] 폴백 완료: {[a['format'] for a in assets]}")
        return assets
    except Exception as e:
        logger.error(f"[meshbake] 3DGS 폴백 실패: {e}")
        return []


def mesh_ply_to_assets(mesh_ply: str, out_dir: str, name: str = "model") -> list:
    """정점색 메쉬 PLY(예: nerfstudio poisson) → 텍스처드 OBJ/MTL/PNG/GLB."""
    try:
        logger.info(f"[meshbake] 메쉬 텍스처링 시작: {mesh_ply}")
        mesh = _load_mesh_ply(mesh_ply)
        assets = _mesh_to_assets(mesh, out_dir, name)
        logger.info(f"[meshbake] 메쉬 텍스처링 완료: {[a['format'] for a in assets]}")
        return assets
    except Exception as e:
        logger.error(f"[meshbake] 메쉬 텍스처링 실패: {e}")
        return []
