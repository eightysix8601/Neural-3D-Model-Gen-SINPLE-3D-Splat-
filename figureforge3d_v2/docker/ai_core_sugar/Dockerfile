FROM nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 TORCH_CUDA_ARCH_LIST="8.9" CUDA_HOME=/usr/local/cuda
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3.10-dev python3-pip git wget curl cmake build-essential ninja-build \
    libgl1-mesa-glx libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.10 /usr/bin/python \
    && ln -sf /usr/bin/python3.10 /usr/bin/python3
RUN pip install --no-cache-dir "numpy==1.24.4"
RUN pip install --no-cache-dir torch==2.0.1+cu118 torchvision==0.15.2+cu118 torchaudio==2.0.2+cu118 \
    --index-url https://download.pytorch.org/whl/cu118
RUN pip install --no-cache-dir fastapi==0.111.0 uvicorn[standard]==0.29.0 \
    python-multipart==0.0.9 pillow==10.3.0 loguru==0.7.2 aiofiles==23.2.1 \
    trimesh==4.3.2 scipy==1.11.4 plyfile open3d==0.18.0 pydantic==2.7.1
RUN git clone https://github.com/Anttwo/SuGaR /opt/SuGaR
RUN cd /opt/SuGaR/gaussian_splatting/submodules/diff-gaussian-rasterization && \
    TORCH_CUDA_ARCH_LIST="8.9" pip install . --no-build-isolation
RUN cd /opt/SuGaR/gaussian_splatting/submodules/simple-knn && \
    TORCH_CUDA_ARCH_LIST="8.9" pip install . --no-build-isolation
RUN pip install --no-cache-dir fvcore iopath && \
    pip install --no-cache-dir "git+https://github.com/facebookresearch/pytorch3d.git@v0.7.5" \
    || echo "pytorch3d 설치 실패 (계속)"
RUN pip install --force-reinstall --no-cache-dir "numpy==1.24.4" "torch==2.0.1+cu118" \
    --index-url https://download.pytorch.org/whl/cu118
RUN mkdir -p /weights
COPY . .
EXPOSE 8013
CMD ["uvicorn", "sugar_worker.main:app", "--host", "0.0.0.0", "--port", "8013"]
