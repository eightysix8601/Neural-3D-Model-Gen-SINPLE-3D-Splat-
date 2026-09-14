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
        self._presign_client = None
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

    @property
    def presign_client(self):
        """presigned URL 전용 클라이언트.

        브라우저가 접근하는 공개 호스트(localhost:9000)로 *서명*해야 한다.
        내부 호스트(minio:9000)로 서명 후 문자열만 바꾸면 S3 v4 서명에 포함된
        Host 헤더가 어긋나 SignatureDoesNotMatch 가 난다. presign 은 네트워크
        호출이 없으므로 이 클라이언트는 minio 에 접속하지 않는다(head_bucket 안 함).
        """
        if self._presign_client is None:
            self._presign_client = boto3.client("s3",
                endpoint_url=f"http://{settings.MINIO_PUBLIC_ENDPOINT}",
                aws_access_key_id=settings.MINIO_ACCESS_KEY,
                aws_secret_access_key=settings.MINIO_SECRET_KEY,
                config=Config(signature_version="s3v4"),
                region_name="us-east-1",
            )
        return self._presign_client

    def get_presigned_url(self, key: str, expires: int = 3600) -> str:
        return self.presign_client.generate_presigned_url("get_object",
            Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires)

    def delete_file(self, key: str):
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except ClientError as e:
            logger.warning(f"삭제 실패: {key} - {e}")

storage_service = StorageService()
