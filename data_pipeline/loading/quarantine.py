"""Карантин отклонённых строк.

Отклонённая строка не исчезает. Она сохраняется в отдельном хранилище
с указанием причины, чтобы владелец данных мог посмотреть, что именно
конвейер отказался принять, и решить, дефект это или новое состояние
записи.

Карантин лежит в зоне ограниченного доступа. Причина прямая: отклонённые
строки — это те же исходные данные, включая код случая и наименование
диагноза. Аналитический API их не видит и видеть не должен; доступ
получают только технические роли.

Формат — Parquet: он сохраняет типы, сжимается и читается по столбцам,
поэтому разбор карантина не требует загрузки его целиком.
"""

from __future__ import annotations

import io
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, BinaryIO, Protocol

import polars as pl

QUARANTINE_BUCKET = "medsignal-quarantine"


class ObjectStore(Protocol):
    """То, что карантину нужно от объектного хранилища."""

    def ensure_bucket(self, bucket: str) -> None: ...

    def put(
        self, bucket: str, key: str, data: BinaryIO, size: int, content_type: str
    ) -> Any: ...


@dataclass(frozen=True, slots=True)
class QuarantineRecord:
    """Метаданные отложенной партии."""

    data_import_id: uuid.UUID
    dataset_type: str
    object_key: str
    rows: int
    reason_codes: tuple[str, ...]
    ingested_at: datetime


def object_key(
    dataset_type: str, data_import_id: uuid.UUID, part: int, ingested_at: datetime
) -> str:
    """Путь в карантине.

    Дата в пути нужна политике хранения: удаление по возрасту выполняется
    правилом жизненного цикла бакета, а не обходом объектов.
    """
    day = ingested_at.strftime("%Y/%m/%d")
    return f"{dataset_type}/{day}/{data_import_id}/part-{part:05d}.parquet"


class QuarantineWriter:
    """Запись отклонённых строк в объектное хранилище."""

    def __init__(
        self,
        store: ObjectStore,
        *,
        bucket: str = QUARANTINE_BUCKET,
        dataset_type: str,
        data_import_id: uuid.UUID,
    ) -> None:
        self._store = store
        self._bucket = bucket
        self._dataset_type = dataset_type
        self._import_id = data_import_id
        self._part = 0
        self._rows = 0
        self._reasons: set[str] = set()
        self._records: list[QuarantineRecord] = []
        self._bucket_ready = False

    @property
    def rows(self) -> int:
        return self._rows

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(sorted(self._reasons))

    @property
    def records(self) -> tuple[QuarantineRecord, ...]:
        return tuple(self._records)

    def write(self, frame: pl.DataFrame, reason_column: str, now: datetime) -> None:
        if frame.height == 0:
            return
        if not self._bucket_ready:
            self._store.ensure_bucket(self._bucket)
            self._bucket_ready = True

        for value in frame[reason_column].to_list():
            for code in str(value or "").split(","):
                if code:
                    self._reasons.add(code)

        buffer = io.BytesIO()
        frame.write_parquet(buffer, compression="zstd")
        payload = buffer.getvalue()

        key = object_key(self._dataset_type, self._import_id, self._part, now)
        self._store.put(
            self._bucket,
            key,
            io.BytesIO(payload),
            len(payload),
            "application/vnd.apache.parquet",
        )
        self._records.append(
            QuarantineRecord(
                data_import_id=self._import_id,
                dataset_type=self._dataset_type,
                object_key=key,
                rows=frame.height,
                reason_codes=tuple(sorted(self._reasons)),
                ingested_at=now,
            )
        )
        self._part += 1
        self._rows += frame.height


class NullQuarantineWriter:
    """Карантин холостого прогона: считает строки, ничего не пишет."""

    def __init__(self) -> None:
        self._rows = 0
        self._reasons: set[str] = set()

    @property
    def rows(self) -> int:
        return self._rows

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(sorted(self._reasons))

    @property
    def records(self) -> tuple[QuarantineRecord, ...]:
        return ()

    def write(self, frame: pl.DataFrame, reason_column: str, now: datetime) -> None:  # noqa: ARG002
        for value in frame[reason_column].to_list():
            for code in str(value or "").split(","):
                if code:
                    self._reasons.add(code)
        self._rows += frame.height
