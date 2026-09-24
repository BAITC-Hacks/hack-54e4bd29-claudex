"""Адаптер между приложением и конвейером обработки файлов.

Это единственное место, знающее обе стороны сразу: типы `data_pipeline`
и типы бизнес-слоя. Благодаря ему конвейер остаётся библиотекой без
знания о приложении, а бизнес-слой — без знания о polars и ClickHouse.

Адаптер живёт вне слоёв, рядом с композиционным корнем: он собирает
систему, а не выражает предметную область.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path

from app.business.ingestion.ports import SourceFileRef
from app.business.ingestion.results import (
    PipelineFileResult,
    QualityFinding,
    QuarantineReference,
)
from app.core.config import Settings
from app.core.logging import get_logger
from app.shared.delivery import DeliveryEvidence
from data_pipeline.common.hashing import sha256_file
from data_pipeline.contracts import get_contract
from data_pipeline.ingestion.discovery import discover
from data_pipeline.loading.clickhouse_writer import (
    ClickHouseClient,
    ClickHouseLoader,
    NullLoader,
)
from data_pipeline.loading.quarantine import (
    NullQuarantineWriter,
    ObjectStore,
    QuarantineWriter,
)
from data_pipeline.pipeline import (
    FileResult,
    Loader,
    PipelineConfig,
    Quarantine,
    process_file,
)
from data_pipeline.privacy.pseudonymization import Pseudonymizer

logger = get_logger(__name__)


class PipelineAdapter:
    """Реализация порта `IngestionPipeline` поверх `data_pipeline`."""

    def __init__(
        self,
        *,
        settings: Settings,
        source_root: Path,
        clickhouse_client_factory: Callable[[], ClickHouseClient],
        object_storage: ObjectStore,
    ) -> None:
        self._settings = settings
        self._source_root = source_root
        self._client_factory = clickhouse_client_factory
        self._object_storage = object_storage
        # Ключ проверяется при создании адаптера, а не при первой записи.
        # Импорт, упавший на середине файла из-за непригодного секрета,
        # оставил бы половину данных загруженной.
        self._pseudonymizer = Pseudonymizer.from_secret(
            settings.data_pseudonymization_key
        )

    # ------------------------------------------------------------------

    def source_system(self, dataset_type: str) -> str:
        return get_contract(dataset_type).source_system

    def expected_row_count(self, dataset_type: str) -> int | None:
        """Число строк набора по отчёту Data Audit, если оно известно."""
        return get_contract(dataset_type).audit_row_count

    def discover(self, dataset_type: str) -> list[SourceFileRef]:
        return discover(self._source_root, get_contract(dataset_type))

    def fingerprint(self, file: SourceFileRef) -> str:
        return sha256_file(file.path)

    # ------------------------------------------------------------------

    def process(
        self,
        *,
        dataset_type: str,
        file: SourceFileRef,
        file_hash: str,
        import_id: uuid.UUID,
        dry_run: bool,
    ) -> PipelineFileResult:
        contract = get_contract(dataset_type)
        bucket = self._settings.minio_bucket_quarantine

        loader: Loader
        quarantine: Quarantine
        if dry_run:
            loader = NullLoader()
            quarantine = NullQuarantineWriter()
        else:
            loader = ClickHouseLoader(
                self._client_factory(),
                target_table=contract.target_table,
                staging_table=contract.staging_table,
                import_id=import_id,
            )
            quarantine = QuarantineWriter(
                self._object_storage,
                bucket=bucket,
                dataset_type=dataset_type,
                data_import_id=import_id,
            )

        result = process_file(
            path=file.path,
            file_hash=file_hash,
            contract=contract,
            import_id=import_id,
            pseudonymizer=self._pseudonymizer,
            loader=loader,
            quarantine=quarantine,
            config=PipelineConfig(
                batch_size=self._settings.data_batch_size, dry_run=dry_run
            ),
            progress=logger.info,
        )

        if dry_run:
            result.rows_loaded = 0
        else:
            # Публикация выполняется только после сверки числа строк
            # в промежуточной таблице. Расхождение означает потерю или
            # задвоение и обязано прервать импорт, а не обнаружиться
            # позже по странным цифрам в витрине.
            loader.verify_staged(result.rows_valid)
            published = loader.publish()
            loader.drop_staging()
            result.rows_loaded = published.published_rows

        return _to_business(result, quarantine, bucket)

    def delivery_evidence(
        self, dataset_type: str, import_ids: tuple[uuid.UUID, ...]
    ) -> DeliveryEvidence | None:
        from app.shared.delivery import DeliveryEvidence

        specs = {
            "REFERRALS": ("fact_referral_events", "registration_dt", None),
            "REFUSALS": ("fact_refusal_events", "refuse_dt", None),
            "WAITING": ("fact_waiting_events", "registration_dt", "snapshot_dt"),
        }
        # TREATED has only a source load date, not an independently observed
        # reporting period. Do not silently reinterpret it as event evidence.
        if dataset_type not in specs or not import_ids:
            return None
        table, event, snapshot = specs[dataset_type]
        snapshot_sql = (
            f"if(uniqExact({snapshot}) = 1, min({snapshot}), NULL)"
            if snapshot
            else "NULL"
        )
        result = self._client_factory().query(
            f"SELECT count(), min({event}), max({event}), {snapshot_sql} "  # noqa: S608
            f"FROM {table} WHERE import_id IN {{ids:Array(UUID)}}",
            parameters={"ids": [str(i) for i in import_ids]},
        )
        rows, start, end, snapshot_at = result.result_rows[0]
        return DeliveryEvidence(
            int(rows),
            start.date() if rows and start else None,
            end.date() if rows and end else None,
            snapshot_at.date() if snapshot_at else None,
        )

    def rollback(self, *, dataset_type: str, import_id: uuid.UUID) -> None:
        contract = get_contract(dataset_type)
        ClickHouseLoader(
            self._client_factory(),
            target_table=contract.target_table,
            staging_table=contract.staging_table,
            import_id=import_id,
        ).rollback()


def _to_business(
    result: FileResult, quarantine: Quarantine, bucket: str
) -> PipelineFileResult:
    """Перевести результат конвейера в термины бизнес-слоя."""
    findings = tuple(
        QualityFinding(
            validation_level=finding.level.value,
            rule_code=finding.rule_code.value,
            severity=finding.severity.value,
            column_name=finding.column_name,
            affected_rows=finding.affected_rows,
            message=finding.message,
        )
        for finding in result.findings
    )
    references = tuple(
        QuarantineReference(
            bucket=bucket,
            object_key=record.object_key,
            rows=record.rows,
            reason_codes=record.reason_codes,
        )
        for record in getattr(quarantine, "records", ())
    )
    return PipelineFileResult(
        file_name=result.file_name,
        file_hash=result.file_hash,
        size_bytes=0,
        rows_read=result.rows_read,
        rows_valid=result.rows_valid,
        rows_with_warning=result.rows_with_warning,
        rows_rejected=result.rows_rejected,
        rows_loaded=result.rows_loaded,
        duration_seconds=result.duration_seconds,
        findings=findings,
        quarantine=references,
        unmapped_organizations=tuple(sorted(result.unmapped_organizations)),
        unmapped_regions=tuple(sorted(result.unmapped_regions)),
        unmapped_profiles=tuple(sorted(result.unmapped_profiles)),
    )
