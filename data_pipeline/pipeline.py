"""Конвейер обработки одного файла.

Модуль отвечает за путь «файл → аналитические записи» и ни за что больше.
Он не знает о PostgreSQL, о сущности DataImport и о правах доступа: этим
управляет бизнес-слой, который вызывает конвейер и получает результат.
Разделение нужно, чтобы конвейер можно было прогнать в тесте без базы
и без приложения.

Память под контролем: файл читается пакетами, каждый пакет проходит весь
путь до записи и освобождается. Расход не зависит от размера файла.
"""

from __future__ import annotations

import datetime as dt
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import polars as pl

from data_pipeline.contracts import DatasetContract
from data_pipeline.ingestion.reader import (
    DEFAULT_BATCH_SIZE,
    SchemaMismatchError,
    count_rows,
    ensure_schema,
    read_batches,
)
from data_pipeline.loading.clickhouse_writer import LoadResult
from data_pipeline.privacy.pseudonymization import Pseudonymizer
from data_pipeline.transformation.canonical import to_canonical
from data_pipeline.transformation.normalization import drop_raw_columns, normalized_frame
from data_pipeline.validation.engine import (
    REASON_COLUMN,
    REJECT_COLUMN,
    WARN_COLUMN,
    validate_batch,
)
from data_pipeline.validation.rules import (
    Finding,
    FindingCollector,
    RuleCode,
    Severity,
    ValidationLevel,
)


class RowAccountingError(Exception):
    """Сумма принятых и отклонённых строк не сошлась с прочитанными.

    Означает, что строка исчезла из учёта. Продолжать нельзя: витрина
    окажется неполной, а расхождение обнаружится не скоро и без объяснения.
    """


class Loader(Protocol):
    def stage(self, frame: pl.DataFrame) -> int: ...
    def staged_row_count(self) -> int: ...
    def verify_staged(self, expected: int) -> None: ...
    def publish(self) -> LoadResult: ...
    def drop_staging(self) -> None: ...
    def rollback(self) -> None: ...


class Quarantine(Protocol):
    @property
    def rows(self) -> int: ...
    @property
    def reason_codes(self) -> tuple[str, ...]: ...
    def write(
        self, frame: pl.DataFrame, reason_column: str, now: dt.datetime
    ) -> None: ...


@dataclass(slots=True)
class FileResult:
    """Итог обработки одного файла."""

    file_name: str
    file_hash: str
    rows_read: int = 0
    rows_valid: int = 0
    rows_with_warning: int = 0
    rows_rejected: int = 0
    rows_loaded: int = 0
    duration_seconds: float = 0.0
    findings: list[Finding] = field(default_factory=list)
    unmapped_organizations: set[str] = field(default_factory=set)
    unmapped_regions: set[str] = field(default_factory=set)
    unmapped_profiles: set[str] = field(default_factory=set)
    quarantine_reason_codes: tuple[str, ...] = ()

    @property
    def rows_per_second(self) -> float:
        if self.duration_seconds <= 0:
            return 0.0
        return self.rows_read / self.duration_seconds


@dataclass(slots=True)
class PipelineConfig:
    batch_size: int = DEFAULT_BATCH_SIZE
    dry_run: bool = False


ProgressCallback = Callable[[str], None]


def process_file(
    *,
    path: Path,
    file_hash: str,
    contract: DatasetContract,
    import_id: uuid.UUID,
    pseudonymizer: Pseudonymizer,
    loader: Loader,
    quarantine: Quarantine,
    config: PipelineConfig | None = None,
    progress: ProgressCallback | None = None,
    now: dt.datetime | None = None,
) -> FileResult:
    """Пропустить файл через конвейер и вернуть итог."""
    settings = config or PipelineConfig()
    started = time.monotonic()
    moment = now or dt.datetime.now(tz=dt.UTC).replace(tzinfo=None)
    collector = FindingCollector()
    result = FileResult(file_name=path.name, file_hash=file_hash)

    # --- Уровень 1: файл ----------------------------------------------------
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.stat().st_size == 0:
        collector.add(
            ValidationLevel.FILE,
            RuleCode.FILE_EMPTY,
            Severity.ERROR,
            None,
            1,
            "Файл пуст",
        )
        result.findings = collector.findings()
        return result

    # --- Уровень 2: схема ---------------------------------------------------
    # Расхождение со схемой останавливает файл целиком. Подогнать данные
    # под контракт молча означало бы загрузить неизвестно что.
    try:
        ensure_schema(path, contract)
    except SchemaMismatchError as error:
        for column in error.missing:
            collector.add(
                ValidationLevel.SCHEMA,
                RuleCode.SCHEMA_MISSING_COLUMN,
                Severity.ERROR,
                column,
                1,
                "Столбец контракта отсутствует в файле",
            )
        for column in error.unexpected:
            collector.add(
                ValidationLevel.SCHEMA,
                RuleCode.SCHEMA_UNEXPECTED_COLUMN,
                Severity.ERROR,
                column,
                1,
                "В файле есть столбец, которого нет в контракте",
            )
        result.findings = collector.findings()
        raise

    for index, raw_batch in enumerate(read_batches(path, contract, settings.batch_size)):
        parsed = normalized_frame(raw_batch, contract)
        validation = validate_batch(parsed, contract, collector)

        rejected = validation.rejected
        if rejected.height:
            quarantine.write(rejected, REASON_COLUMN, moment)

        accepted = validation.valid
        result.rows_read += validation.rows_read
        result.rows_rejected += rejected.height
        result.rows_valid += accepted.height

        # Инвариант учёта проверяется на каждом пакете, а не в конце:
        # так видно, какой именно пакет потерял строки.
        if accepted.height + rejected.height != validation.rows_read:
            raise RowAccountingError(
                f"Пакет {index}: прочитано {validation.rows_read}, "
                f"принято {accepted.height}, отклонено {rejected.height}"
            )
        result.rows_with_warning += int(accepted.select(pl.col(WARN_COLUMN).sum()).item())

        if accepted.height:
            payload = drop_raw_columns(
                accepted.drop([REJECT_COLUMN, WARN_COLUMN, REASON_COLUMN])
            )
            canonical = to_canonical(
                payload, contract, pseudonymizer, import_id, file_hash, moment
            )
            _collect_unmapped(canonical, result)
            loader.stage(canonical)

        if progress is not None and index % 10 == 0:
            progress(f"{contract.key} / {path.name}: прочитано {result.rows_read} строк")

    # --- Уровень 3: справочники --------------------------------------------
    # Несопоставленная организация не является дефектом строки. Официального
    # справочника пока нет, и отклонение таких строк оставило бы систему
    # без данных вовсе.
    collector.add(
        ValidationLevel.REFERENCE,
        RuleCode.UNMAPPED_ORGANIZATION,
        Severity.WARNING,
        None,
        len(result.unmapped_organizations),
        f"{len(result.unmapped_organizations)} различных организаций "
        "не сопоставлены со справочником",
    )
    collector.add(
        ValidationLevel.REFERENCE,
        RuleCode.UNMAPPED_REGION,
        Severity.WARNING,
        None,
        len(result.unmapped_regions),
        f"{len(result.unmapped_regions)} различных регионов "
        "не сопоставлены со справочником",
    )
    collector.add(
        ValidationLevel.REFERENCE,
        RuleCode.UNMAPPED_PROFILE,
        Severity.WARNING,
        None,
        len(result.unmapped_profiles),
        f"{len(result.unmapped_profiles)} различных профилей койки "
        "не сопоставлены со справочником",
    )

    result.rows_loaded = loader.staged_row_count()
    result.quarantine_reason_codes = quarantine.reason_codes
    result.findings = collector.findings()
    result.duration_seconds = round(time.monotonic() - started, 3)
    return result


def _collect_unmapped(frame: pl.DataFrame, result: FileResult) -> None:
    """Запомнить различные несопоставленные значения.

    Собираются именно различные значения, а не строки: интересен размер
    незакрытого справочника, а не то, сколько раз встретилась каждая
    организация. Множество ограничено сверху числом организаций в стране
    и памяти не съедает.
    """
    for column in ("receiving_org_key", "referring_org_key", "hospital_source"):
        if column in frame.columns:
            result.unmapped_organizations.update(
                value for value in frame[column].unique().to_list() if value
            )
    for column in ("region_source", "attachment_region_source"):
        if column in frame.columns:
            result.unmapped_regions.update(
                value for value in frame[column].unique().to_list() if value
            )
    # Профиль койки собирается так же. Официального справочника профилей
    # нет: Data Audit показал, что наименования профилей в направлениях
    # и коды профилей в очереди не пересекаются ни одним значением.
    # Накопленные значения — это материал для будущего сопоставления.
    for column in ("profile_source",):
        if column in frame.columns:
            result.unmapped_profiles.update(
                value for value in frame[column].unique().to_list() if value
            )


def count_source_rows(path: Path) -> int:
    """Число строк в исходном файле для сверки."""
    return count_rows(path)
