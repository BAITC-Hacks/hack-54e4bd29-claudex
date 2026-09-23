"""Что бизнес-слой требует от конвейера обработки файлов.

Протокол структурный: реализация живёт в адаптере и этот модуль
не импортирует. Так сохраняется правило «конвейер данных не знает
о приложении» (ADR-0005).
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Protocol

from app.business.ingestion.results import PipelineFileResult
from app.shared.delivery import DeliveryEvidence


class SourceFileRef(Protocol):
    """Файл, найденный в каталоге источника."""

    @property
    def name(self) -> str: ...

    @property
    def path(self) -> Path: ...

    @property
    def size_bytes(self) -> int: ...


class IngestionPipeline(Protocol):
    """Разбор файла и загрузка его в аналитическое хранилище."""

    def delivery_evidence(
        self, dataset_type: str, import_ids: tuple[uuid.UUID, ...]
    ) -> DeliveryEvidence | None: ...

    def discover(self, dataset_type: str) -> list[SourceFileRef]: ...

    def fingerprint(self, file: SourceFileRef) -> str: ...

    def process(
        self,
        *,
        dataset_type: str,
        file: SourceFileRef,
        file_hash: str,
        import_id: uuid.UUID,
        dry_run: bool,
    ) -> PipelineFileResult: ...

    def rollback(self, *, dataset_type: str, import_id: uuid.UUID) -> None: ...

    def source_system(self, dataset_type: str) -> str: ...

    def expected_row_count(self, dataset_type: str) -> int | None: ...


class DeliveryEvidenceReader(Protocol):
    def delivery_evidence(
        self, dataset_type: str, import_ids: tuple[uuid.UUID, ...]
    ) -> DeliveryEvidence | None: ...
