"""Абстракция объектного хранилища.

Прикладной код работает с протоколом `ObjectStorage`, а не с клиентом MinIO.
Причина: S3-совместимых реализаций несколько, и замена MinIO на управляемое
хранилище в production не должна затрагивать бизнес-код (DEPLOYMENT.md).

Назначение бакетов: исходные выгрузки, артефакты моделей, экспорты, отчёты.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from functools import lru_cache
from typing import BinaryIO, Protocol, runtime_checkable

from minio import Minio
from minio.error import S3Error

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class StoredObject:
    """Ссылка на сохранённый объект."""

    bucket: str
    key: str
    size: int
    etag: str


@runtime_checkable
class ObjectStorage(Protocol):
    """Контракт объектного хранилища, используемый прикладным кодом."""

    def ensure_bucket(self, bucket: str) -> None: ...

    def put(
        self, bucket: str, key: str, data: BinaryIO, size: int, content_type: str
    ) -> StoredObject: ...

    def get(self, bucket: str, key: str) -> bytes: ...

    def exists(self, bucket: str, key: str) -> bool: ...

    def remove(self, bucket: str, key: str) -> None: ...

    def check_connection(self, timeout_s: float) -> None: ...


class MinioObjectStorage:
    """Реализация поверх S3-совместимого MinIO."""

    def __init__(self, client: Minio) -> None:
        self._client = client

    def ensure_bucket(self, bucket: str) -> None:
        if not self._client.bucket_exists(bucket):
            self._client.make_bucket(bucket)
            logger.info("Создан бакет", extra={"bucket": bucket})

    def put(
        self, bucket: str, key: str, data: BinaryIO, size: int, content_type: str
    ) -> StoredObject:
        result = self._client.put_object(
            bucket_name=bucket,
            object_name=key,
            data=data,
            length=size,
            content_type=content_type,
        )
        return StoredObject(bucket=bucket, key=key, size=size, etag=result.etag or "")

    def get(self, bucket: str, key: str) -> bytes:
        response = None
        try:
            response = self._client.get_object(bucket, key)
            return response.read()
        finally:
            if response is not None:
                response.close()
                response.release_conn()

    def exists(self, bucket: str, key: str) -> bool:
        try:
            self._client.stat_object(bucket, key)
            return True
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject"}:
                return False
            raise

    def remove(self, bucket: str, key: str) -> None:
        self._client.remove_object(bucket, key)

    def check_connection(self, timeout_s: float) -> None:  # noqa: ARG002
        """Проверка доступности. Бросает исключение при отказе."""
        self._client.list_buckets()


class InMemoryObjectStorage:
    """Реализация в памяти для автоматических тестов."""

    def __init__(self) -> None:
        self._objects: dict[tuple[str, str], bytes] = {}
        self._buckets: set[str] = set()

    def ensure_bucket(self, bucket: str) -> None:
        self._buckets.add(bucket)

    def put(
        self,
        bucket: str,
        key: str,
        data: BinaryIO,
        size: int,  # noqa: ARG002 - часть контракта протокола
        content_type: str,  # noqa: ARG002 - часть контракта протокола
    ) -> StoredObject:
        payload = data.read()
        self._buckets.add(bucket)
        self._objects[(bucket, key)] = payload
        return StoredObject(bucket=bucket, key=key, size=len(payload), etag="in-memory")

    def get(self, bucket: str, key: str) -> bytes:
        return self._objects[(bucket, key)]

    def exists(self, bucket: str, key: str) -> bool:
        return (bucket, key) in self._objects

    def remove(self, bucket: str, key: str) -> None:
        self._objects.pop((bucket, key), None)

    def check_connection(self, timeout_s: float) -> None:  # noqa: ARG002
        return None

    def read_stream(self, bucket: str, key: str) -> BinaryIO:
        return io.BytesIO(self._objects[(bucket, key)])


@lru_cache(maxsize=1)
def get_object_storage() -> ObjectStorage:
    settings = get_settings()
    client = Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    return MinioObjectStorage(client)


def check_connection(timeout_s: float) -> None:
    get_object_storage().check_connection(timeout_s)
