# 공식 nerfstudio 이미지 사용 (tinycudann/nerfacto/ns-* CLI 사전 빌드됨).
# 태그가 없을 경우 :latest 로 교체 가능.
FROM ghcr.io/nerfstudio-project/nerfstudio:1.1.5

USER root
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 \
    TORCH_CUDA_ARCH_LIST="8.9" \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

# 워커 + meshbake 의존성 (open3d/numpy/pillow/scipy 는 nerfstudio 가 이미 포함)
RUN python -m pip install --no-cache-dir \
        fastapi==0.111.0 "uvicorn[standard]==0.29.0" python-multipart==0.0.9 \
        loguru==0.7.2 aiofiles==23.2.1 plyfile xatlas \
    && (python -m pip install --no-cache-dir "trimesh==4.3.2" || python -m pip install --no-cache-dir trimesh) \
    && (python -c "import scipy" || python -m pip install --no-cache-dir scipy)

COPY . .
EXPOSE 8016
CMD ["uvicorn", "nerf_worker.main:app", "--host", "0.0.0.0", "--port", "8016"]
