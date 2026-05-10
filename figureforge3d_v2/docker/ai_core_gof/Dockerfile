FROM nvidia/cuda:11.3.1-cudnn8-devel-ubuntu20.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 TORCH_CUDA_ARCH_LIST="8.9" CUDA_HOME=/usr/local/cuda
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.8 python3.8-dev python3-pip git wget curl cmake build-essential ninja-build \
    libgl1-mesa-glx libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.8 /usr/bin/python \
    && ln -sf /usr/bin/python3.8 /usr/bin/python3
RUN pip install --no-cache-dir torch==1.12.1+cu113 torchvision==0.13.1+cu113 \
    -f https://download.pytorch.org/whl/torch_stable.html
RUN pip install --no-cache-dir fastapi==0.111.0 uvicorn[standard]==0.29.0 \
    python-multipart==0.0.9 pillow==9.5.0 loguru==0.7.2 aiofiles==23.2.1 \
    trimesh==4.0.0 scipy==1.10.1 plyfile open3d==0.16.0 pydantic==1.10.13
RUN git clone https://github.com/autonomousvision/gaussian-opacity-fields /opt/GOF
RUN cd /opt/GOF/submodules/diff-gaussian-rasterization && \
    TORCH_CUDA_ARCH_LIST="8.9" pip install . --no-build-isolation
RUN cd /opt/GOF/submodules/simple-knn && \
    TORCH_CUDA_ARCH_LIST="8.9" pip install . --no-build-isolation
RUN pip install --force-reinstall --no-cache-dir "numpy==1.23.5"
RUN mkdir -p /weights
COPY . .
EXPOSE 8014
CMD ["uvicorn", "gof_worker.main:app", "--host", "0.0.0.0", "--port", "8014"]
