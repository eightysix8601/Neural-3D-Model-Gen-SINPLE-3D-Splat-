FROM nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 TORCH_CUDA_ARCH_LIST="8.9" CUDA_HOME=/usr/local/cuda
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3.10-dev python3-pip git wget curl cmake build-essential ninja-build \
    libgl1-mesa-glx libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.10 /usr/bin/python \
    && ln -sf /usr/bin/python3.10 /usr/bin/python3

# numpy 먼저 (open3d / torch 와의 ABI 충돌 방지)
RUN pip install --no-cache-dir "numpy==1.24.4"

# torch 2.0.1 + cu118 — SuGaR 워커와 동일 베이스 (단일 GPU 공유 시 충돌 없음)
RUN pip install --no-cache-dir torch==2.0.1+cu118 torchvision==0.15.2+cu118 torchaudio==2.0.2+cu118 \
    --index-url https://download.pytorch.org/whl/cu118

# FastAPI + 메쉬/이미지 처리 + 2DGS train/render.py 의존성.
# numba: meshbake 텍스처 베이크 JIT 가속 (200k tris 70분 → 2~5분).
RUN pip install --no-cache-dir fastapi==0.111.0 "uvicorn[standard]==0.29.0" \
    python-multipart==0.0.9 pillow==10.3.0 loguru==0.7.2 aiofiles==23.2.1 \
    trimesh==4.3.2 scipy==1.11.4 plyfile open3d==0.18.0 pydantic==2.7.1 xatlas \
    opencv-python==4.9.0.80 scikit-image==0.21.0 lpips==0.1.4 tqdm==4.66.2 mediapy==1.1.2 \
    "numba==0.59.1" "llvmlite==0.42.0"

# 2DGS 본체 — 서브모듈(diff-surfel-rasterization, simple-knn) 포함 클론
# NOTE: 동작 검증 후 커밋 핀 추가 권장. 일단 main 추적.
RUN git clone --recurse-submodules https://github.com/hbb1/2d-gaussian-splatting /opt/2d-gaussian-splatting

# 커스텀 CUDA 익스텐션 빌드 (RTX 4090=8.9; SuGaR/GOF 와 동일 정책)
RUN cd /opt/2d-gaussian-splatting/submodules/diff-surfel-rasterization && \
    TORCH_CUDA_ARCH_LIST="8.9" pip install . --no-build-isolation
RUN cd /opt/2d-gaussian-splatting/submodules/simple-knn && \
    TORCH_CUDA_ARCH_LIST="8.9" pip install . --no-build-isolation

# extension 빌드 후 numpy/torch 가 깨지는 케이스 대비해 강제 재설치 (SuGaR 와 동일)
RUN pip install --force-reinstall --no-cache-dir "numpy==1.24.4" "torch==2.0.1+cu118" \
    --index-url https://download.pytorch.org/whl/cu118

RUN mkdir -p /weights
COPY . .
EXPOSE 8018
CMD ["uvicorn", "twodgs_worker.main:app", "--host", "0.0.0.0", "--port", "8018"]
