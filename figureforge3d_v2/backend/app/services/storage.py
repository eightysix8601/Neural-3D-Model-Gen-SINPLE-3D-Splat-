import uuid
from pathlib import Path
from typing import BinaryIO
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from loguru import logger
from app.core.config import settings

class StorageService:
    def __init__(self):
        self._client = None
        self.bucket = settings.MINIO_BUCKET_NAME

    @property
    def client(self):
        if self._client is None:
            self._client = boto3.client("s3",
                endpoint_url=f"http://{settings.MINIO_ENDPOINT}",
                aws_access_key_id=settings.MINIO_ACCESS_KEY,
                aws_secret_access_key=settings.MINIO_SECRET_KEY,
                config=Config(signature_version="s3v4"),
                region_name="us-east-1",
            )
            try:
                self._client.head_bucket(Bucket=self.bucket)
            except ClientError:
                self._client.create_bucket(Bucket=self.bucket)
                logger.info(f"버킷 생성: {self.bucket}")
        return self._client

    def upload_file(self, data, filename: str, content_type: str, prefix: str = "uploads") -> str:
        ext = Path(filename).suffix
        key = f"{prefix}/{uuid.uuid4().hex}{ext}"
        if isinstance(data, bytes):
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        else:
            self.client.upload_fileobj(data, self.bucket, key, ExtraArgs={"ContentType": content_type})
        return key

    def upload_from_path(self, local_path: str, prefix: str = "outputs") -> str:
        path = Path(local_path)
        mime = {".glb":"model/gltf-binary",".obj":"text/plain",".ply":"application/octet-stream",
                ".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg"}
        ct = mime.get(path.suffix.lower(), "application/octet-stream")
        key = f"{prefix}/{uuid.uuid4().hex}{path.suffix}"
        self.client.upload_file(str(local_path), self.bucket, key, ExtraArgs={"ContentType": ct})
        return key

    def get_presigned_url(self, key: str, expires: int = 3600) -> str:
        url = self.client.generate_presigned_url("get_object",
            Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires)
        # 컨테이너 내부 주소 → 브라우저 접근 가능 주소로 변환
        url = url.replace("http://minio:9000", "http://localhost:9000")
        return url

    def delete_file(self, key: str):
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except ClientError as e:
            logger.warning(f"삭제 실패: {key} - {e}")

storage_service = StorageService()
