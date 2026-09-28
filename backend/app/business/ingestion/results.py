"""Значения, которыми бизнес-слой описывает результат загрузки.

Типы объявлены здесь, а не взяты из библиотеки конвейера, намеренно.
Бизнес-слой не должен зависеть от того, чем именно разобран файл;
перевод из представления конвейера в это выполняет адаптер, и он —
единственное место, знающее обе стороны.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum


class ImportOutcome(StrEnum):
    """Чем закончилась попытка импорта файла."""

    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    # Файл с таким же содержимым уже загружен. Это не ошибка: повторный
    # запуск команды импорта — обычное дело, и он обязан быть безопасным.
    SKIPPED_IDEMPOTENT = "SKIP_IDEMPOTENT"
    # Холостой прогон: разбор и проверки выполнены, хранилище не тронуто.
    DRY_RUN = "DRY_RUN"


@dataclass(frozen=True, slots=True)
class QualityFinding:
    validation_level: str
    rule_code: str
    severity: str
    column_name: str | None
    affected_rows: int
    message: str


@dataclass(frozen=True, slots=True)
class QuarantineReference:
    bucket: str
    object_key: str
    rows: int
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PipelineFileResult:
    """Итог работы конвейера над одним файлом."""

    file_name: str
    file_hash: str
    size_bytes: int
    rows_read: int
    rows_valid: int
    rows_with_warning: int
    rows_rejected: int
    rows_loaded: int
    duration_seconds: float
    findings: tuple[QualityFinding, ...] = ()
    quarantine: tuple[QuarantineReference, ...] = ()
    unmapped_organizations: tuple[str, ...] = ()
    unmapped_regions: tuple[str, ...] = ()
    unmapped_profiles: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FileImportReport:
    """Что произошло с одним файлом, с точки зрения приложения."""

    file_name: str
    file_hash: str
    outcome: ImportOutcome
    data_import_id: uuid.UUID | None
    rows_read: int = 0
    rows_valid: int = 0
    rows_rejected: int = 0
    rows_loaded: int = 0
    warnings_count: int = 0
    duration_seconds: float = 0.0
    error_summary: str | None = None
    findings: tuple[QualityFinding, ...] = ()


@dataclass(slots=True)
class DatasetImportReport:
    """Итог по набору данных: все его файлы вместе."""

    dataset_type: str
    source_system: str
    dry_run: bool
    files: list[FileImportReport] = field(default_factory=list)
    unmapped_organizations: int = 0
    unmapped_regions: int = 0
    unmapped_profiles: int = 0
    # Расхождение с числом строк из отчёта Data Audit, если оно заметно.
    # Не ошибка: поставка могла обновиться. Но оператор должен это увидеть.
    row_count_drift: int | None = None

    @property
    def rows_read(self) -> int:
        return sum(f.rows_read for f in self.files)

    @property
    def rows_valid(self) -> int:
        return sum(f.rows_valid for f in self.files)

    @property
    def rows_rejected(self) -> int:
        return sum(f.rows_rejected for f in self.files)

    @property
    def rows_loaded(self) -> int:
        return sum(f.rows_loaded for f in self.files)

    @property
    def warnings_count(self) -> int:
        return sum(f.warnings_count for f in self.files)

    @property
    def duration_seconds(self) -> float:
        return round(sum(f.duration_seconds for f in self.files), 3)

    @property
    def failed(self) -> bool:
        return any(f.outcome is ImportOutcome.FAILED for f in self.files)

    @property
    def skipped(self) -> int:
        return sum(1 for f in self.files if f.outcome is ImportOutcome.SKIPPED_IDEMPOTENT)
