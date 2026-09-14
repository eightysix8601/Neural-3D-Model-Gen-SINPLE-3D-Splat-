# Hunyuan3D-Paint worker (port 8018)
# Tencent Hunyuan3D-2 의 텍스쳐 베이크 파이프라인을 단독 호출하는 워커.
# License: Tencent Hunyuan Community License — attribution 필요 (사이트 footer 에 표기).
FROM nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/weights/hf \
    HUGGINGFACE_HUB_CACHE=/weights/hf \
    TORCH_CUDA_ARCH_LIST="7.5;8.0;8.6;8.9" \
    PYOPENGL_PLATFORM=egl \
    HUNYUAN_REPO_DIR=/opt/Hunyuan3D-2 \
    HUNYUAN_PAINT_SUBFOLDER=hunyuan3d-paint-v2-0-turbo

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 python3.10-dev python3-pip \
        git wget curl ca-certificates build-essential cmake \
        libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender1 \
        libegl1 libgles2-mesa-dev libosmesa6 libosmesa6-dev freeglut3-dev \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.10 /usr/bin/python \
    && ln -sf /usr/bin/python3.10 /usr/bin/python3 \
    && python -m pip install --upgrade pip setuptools wheel

# torch (cu121)
RUN pip install --no-cache-dir torch==2.4.0 torchvision==0.19.0 \
        --index-url https://download.pytorch.org/whl/cu121

# 기본 의존성
RUN pip install --no-cache-dir \
        "numpy<2.0" \
        "fastapi==0.111.0" "uvicorn[standard]==0.29.0" "python-multipart==0.0.9" \
        "pillow==10.3.0" "loguru==0.7.2" "aiofiles==23.2.1" \
        "huggingface-hub>=0.24,<1.0" \
        "transformers==4.44.2" \
        "diffusers>=0.27.0,<0.30.0" \
        "accelerate>=0.30,<1.1" \
        "safetensors>=0.4.3" \
        "einops" "omegaconf" "trimesh>=4.0" "scikit-image" \
        "opencv-python-headless==4.8.1.78" \
        "xatlas" "ninja" "pymeshlab" "imageio" "imageio-ffmpeg" \
        "configargparse" "rembg" "onnxruntime"

# Hunyuan3D-2 repo clone (가장 깊지 않은 history 만)
RUN git clone --depth=1 https://github.com/Tencent/Hunyuan3D-2.git /opt/Hunyuan3D-2

# hy3dgen 패키지 설치. setup.py 가 있으면 pip -e .  없으면 PYTHONPATH 폴백.
RUN cd /opt/Hunyuan3D-2 && \
    (pip install --no-cache-dir --no-build-isolation -e . \
        || echo "[WARN] hy3dgen pip install -e 실패, PYTHONPATH 폴백 사용") && \
    ln -sf /opt/Hunyuan3D-2/hy3dgen /usr/local/lib/python3.10/dist-packages/hy3dgen || true

# Hunyuan3D-2 의 texgen 안에 있는 CUDA 확장 (custom_rasterizer, differentiable_renderer)
# 둘 다 설치되면 품질 향상, 실패해도 polyfill 동작. PR/버전에 따라 디렉토리가 다름.
RUN for d in \
        /opt/Hunyuan3D-2/hy3dgen/texgen/custom_rasterizer \
        /opt/Hunyuan3D-2/hy3dgen/texgen/differentiable_renderer \
        /opt/Hunyuan3D-2/hy3dgen/texgen/sub_modules/custom_rasterizer \
        /opt/Hunyuan3D-2/hy3dgen/texgen/sub_modules/differentiable_renderer ; do \
        if [ -d "$d" ]; then \
            echo "[Build] CUDA 확장 빌드: $d" && \
            (cd "$d" && pip install --no-cache-dir --no-build-isolation -e . \
                || echo "[WARN] $d 빌드 실패"); \
        fi; \
    done

# 추가 의존성 (Hunyuan3D-2 requirements.txt 가 있다면 같이)
RUN if [ -f /opt/Hunyuan3D-2/requirements.txt ]; then \
        grep -v '^numpy' /opt/Hunyuan3D-2/requirements.txt > /tmp/hy_reqs.txt && \
        grep -v '^torch' /tmp/hy_reqs.txt > /tmp/hy_reqs2.txt && \
        pip install --no-cache-dir --no-build-isolation -r /tmp/hy_reqs2.txt \
            || echo "[WARN] hy requirements 일부 실패 (무시)"; \
    fi

RUN mkdir -p /weights/hunyuan3d /weights/hf

COPY . .

EXPOSE 8018

CMD ["uvicorn", "hunyuan_paint_worker.main:app", "--host", "0.0.0.0", "--port", "8018"]
