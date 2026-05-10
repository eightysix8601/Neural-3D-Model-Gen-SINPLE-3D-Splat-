FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3.10-dev python3-pip colmap libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.10 /usr/bin/python \
    && ln -sf /usr/bin/python3.10 /usr/bin/python3
RUN pip install --no-cache-dir fastapi==0.111.0 uvicorn[standard]==0.29.0 \
    python-multipart==0.0.9 pillow==10.3.0 numpy==1.24.4 loguru==0.7.2 \
    aiofiles==23.2.1 pydantic==2.7.1
COPY . .
EXPOSE 8012
CMD ["uvicorn", "colmap_worker.main:app", "--host", "0.0.0.0", "--port", "8012"]
