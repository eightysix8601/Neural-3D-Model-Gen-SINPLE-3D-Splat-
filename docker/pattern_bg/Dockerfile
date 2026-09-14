FROM python:3.10-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir fastapi==0.111.0 uvicorn[standard]==0.29.0 \
    python-multipart==0.0.9 pillow==10.3.0 numpy==1.24.4 \
    opencv-python-headless==4.8.1.78 loguru==0.7.2 aiofiles==23.2.1 pydantic==2.7.1
COPY . .
EXPOSE 8011
CMD ["uvicorn", "pattern_bg.main:app", "--host", "0.0.0.0", "--port", "8011"]
