FROM nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 TORCH_CUDA_ARCH_LIST="8.9"
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3.10-dev python3-pip git libgl1-mesa-glx libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.10 /usr/bin/python \
    && ln -sf /usr/bin/python3.10 /usr/bin/python3
RUN pip install --no-cache-dir "numpy==1.24.4"
RUN pip install --no-cache-dir torch==2.0.1+cu118 torchvision==0.15.2+cu118 \
    --index-url https://download.pytorch.org/whl/cu118
RUN pip install --no-cache-dir fastapi==0.111.0 uvicorn[standard]==0.29.0 \
    python-multipart==0.0.9 pillow==10.3.0 loguru==0.7.2 aiofiles==23.2.1 \
    "transformers==4.38.2" "huggingface-hub>=0.20.2,<0.22" timm kornia einops
RUN pip install --force-reinstall --no-cache-dir "numpy==1.24.4" "opencv-python-headless==4.8.1.78"
RUN mkdir -p /weights/birefnet
COPY . .
EXPOSE 8010
CMD ["uvicorn", "bg_removal.main:app", "--host", "0.0.0.0", "--port", "8010"]
