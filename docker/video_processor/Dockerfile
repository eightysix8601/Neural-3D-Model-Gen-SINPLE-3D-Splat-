FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# ffmpeg + opencv 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    fastapi==0.111.0 \
    uvicorn[standard]==0.29.0 \
    python-multipart==0.0.9 \
    numpy==1.24.4 \
    opencv-python-headless==4.8.1.78 \
    loguru==0.7.2 \
    aiofiles==23.2.1 \
    pydantic==2.7.1

COPY . .

EXPOSE 8015
CMD ["uvicorn", "video_processor.main:app", "--host", "0.0.0.0", "--port", "8015"]
