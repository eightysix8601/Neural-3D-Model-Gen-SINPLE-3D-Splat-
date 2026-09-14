# TripoSG / TripoSF worker (port 8017)
# 베이스: cu121 — 최신 diffusers/torch 호환.
# 추가: pyrender + libosmesa6 로 헤드리스 4면 PNG 렌더링 지원.
FROM nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/weights/hf \
    HUGGINGFACE_HUB_CACHE=/weights/hf \
    TORCH_CUDA_ARCH_LIST="7.5;8.0;8.6;8.9" \
    PYOPENGL_PLATFORM=osmesa \
    TRIPOSG_REPO_DIR=/opt/TripoSG

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 python3.10-dev python3-pip \
        git wget curl ca-certificates \
        libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender1 \
        libosmesa6 libosmesa6-dev \
        freeglut3-dev \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.10 /usr/bin/python \
    && ln -sf /usr/bin/python3.10 /usr/bin/python3 \
    && python -m pip install --upgrade pip setuptools wheel

# torch (cu121)
RUN pip install --no-cache-dir torch==2.4.0 torchvision==0.19.0 \
        --index-url https://download.pytorch.org/whl/cu121

# 1차: 핵심 의존성 (FastAPI / torch 외 기본). numpy 는 일단 1.x.
RUN pip install --no-cache-dir \
        "numpy<2.0" \
        "fastapi==0.111.0" "uvicorn[standard]==0.29.0" "python-multipart==0.0.9" \
        "pillow==10.3.0" "loguru==0.7.2" "aiofiles==23.2.1" \
        "pyfqmr>=0.2.0" \
        "huggingface-hub>=0.24,<1.0" \
        "transformers==4.44.2" \
        "diffusers>=0.30.0,<0.32.0" \
        "accelerate>=0.30,<1.1" \
        "safetensors>=0.4.3" \
        "einops" "omegaconf" "trimesh>=4.0" "pyglet<2" "scikit-image" \
        "opencv-python-headless==4.8.1.78"

# TripoSG 공식 repo 를 /opt 에 clone 하고 triposg 패키지를 site-packages 로 symlink.
# (공식 repo 에 setup.py 가 없어 pip install git+ 가 안 된다)
RUN git clone --depth=1 https://github.com/VAST-AI-Research/TripoSG.git /opt/TripoSG \
    && ln -sf /opt/TripoSG/triposg /usr/local/lib/python3.10/dist-packages/triposg

# 2차: TripoSG requirements (numpy 핀 제외). peft / jaxtyping / typeguard / pymeshlab.
RUN grep -v '^numpy' /opt/TripoSG/requirements.txt > /tmp/triposg_reqs.txt \
    && grep -v '^diso' /tmp/triposg_reqs.txt > /tmp/triposg_reqs_nodiso.txt \
    && pip install --no-cache-dir -r /tmp/triposg_reqs_nodiso.txt

# diso (CUDA 확장) — build isolation 끄고 시스템 torch 사용
RUN pip install --no-cache-dir --no-build-isolation diso

# 3차: 헤드리스 렌더링 의존성 (4면 캡처용)
RUN pip install --no-cache-dir "pyrender==0.1.45" "PyOpenGL==3.1.0" "PyOpenGL-accelerate==3.1.7"

# TripoSF (선택). 실패해도 워커는 동작.
RUN pip install --no-cache-dir "git+https://github.com/VAST-AI-Research/TripoSF.git" \
    || echo "[WARN] TripoSF pip install 실패 → SparseFlex 미사용"

RUN mkdir -p /weights/triposg /weights/triposf /weights/rmbg /weights/hf

COPY . .

EXPOSE 8017

CMD ["uvicorn", "tripo_worker.main:app", "--host", "0.0.0.0", "--port", "8017"]
