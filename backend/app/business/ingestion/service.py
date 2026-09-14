"""Управление жизненным циклом импорта.

Сервис отвечает за то, что нельзя доверить библиотеке разбора файлов:
идемпотентность, состояние операции, отчёт о качестве, запись в аудит
и поведение при сбое.

Ключевое свойство — импорт объявляется завершённым только после того,
как строки посчитаны в аналитическом хранилище. ClickHouse и PostgreSQL
не образуют одной транзакции, поэтому «загружено» и «опубликовано»
разведены явно, а не подразумеваются. Импорт, упавший посередине,
откатывается по идентификатору и остаётся в состоянии FAILED — данные
такого импорта не выдают себя за успешную поставку.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.business.ingestion.ports import IngestionPipeline, SourceFileRef
from app.business.ingestion.results import (
    DatasetImportReport,
    FileImportReport,
    ImportOutcome,
    PipelineFileResult,
)
from app.business.ports import UnitOfWorkFactory
from app.core import metrics
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger, get_request_id
from app.models.data_import import DataImport
from app.models.enums import (
    AuditAction,
    AuditEntityType,
    DataImportStatus,
    DatasetType,
    QualitySeverity,
)
from app.models.quality import DataQualityResult, QuarantineBatch
from app.security.authorization import AuthorizationService
from app.security.context import SecurityContext
from app.security.permissions import Permission

logger = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(tz=UTC)


class ImportService:
    """Импорт выгрузок и чтение их истории."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        authorization: AuthorizationService,
        pipeline: IngestionPipeline,
    ) -> None:
        self._uow_factory = uow_factory
        self._authz = authorization
        self._pipeline = pipeline

    # ------------------------------------------------------------------
    # Импорт
    # ------------------------------------------------------------------

    def import_dataset(
        self,
        context: SecurityContext,
        dataset_type: DatasetType,
        *,
        dry_run: bool = False,
    ) -> DatasetImportReport:
        """Загрузить все файлы набора.

        Файлы обрабатываются по одному и независимо: один испорченный
        файл не отменяет уже загруженные. Это осознанный выбор — набор
        поставляется частями, и отказ от всей поставки из-за одной части
        означал бы отсутствие данных вместо неполных данных.
        """
        self._authz.require_permission(context, Permission.DATA_IMPORT_CREATE)

        report = DatasetImportReport(
            dataset_type=dataset_type.value,
            source_system=self._pipeline.source_system(dataset_type.value),
            dry_run=dry_run,
        )

        files = self._pipeline.discover(dataset_type.value)
        if not files:
            raise NotFoundError(
                f"В каталоге источника нет файлов набора {dataset_type.value}"
            )

        for file in files:
            report.files.append(
                self._import_file(context, dataset_type, file, dry_run=dry_run)
            )

        # Сверка с отчётом аудита выполняется по набору целиком, а не
        # по файлу: набор поставляется частями, и ожидаемое число строк
        # относится ко всем частям вместе.
        expected = self._pipeline.expected_row_count(dataset_type.value)
        if expected is not None and report.rows_read:
            drift = abs(report.rows_read - expected)
            if drift > max(1, expected // 100):
                report.row_count_drift = drift
                logger.warning(
                    "Число строк набора расходится с отчётом аудита",
                    extra={
                        "dataset_type": dataset_type.value,
                        "rows_read": report.rows_read,
                        "audit_rows": expected,
                    },
                )

        with self._uow_factory() as uow:
            report.unmapped_organizations = uow.organization_aliases.count_unmapped()
            report.unmapped_regions = uow.region_aliases.count_unmapped()
            report.unmapped_profiles = uow.profile_aliases.count_unmapped()

        return report

    def discover(
        self, context: SecurityContext, dataset_type: DatasetType
    ) -> list[SourceFileRef]:
        """Файлы набора, найденные в каталоге источника."""
        self._authz.require_permission(context, Permission.DATA_IMPORT_READ)
        return self._pipeline.discover(dataset_type.value)

    def _import_file(
        self,
        context: SecurityContext,
        dataset_type: DatasetType,
        file: SourceFileRef,
        *,
        dry_run: bool,
    ) -> FileImportReport:
        file_hash = self._pipeline.fingerprint(file)
        source_system = self._pipeline.source_system(dataset_type.value)

        # --- Идемпотентность ------------------------------------------------
        # Ключ — тип набора и контрольная сумма содержимого. Имя файла
        # в ключ не входит: переименование не делает файл новым, а тот же
        # файл с изменённым содержимым — новый, даже под старым именем.
        with self._uow_factory() as uow:
            existing = uow.data_imports.find_by_hash(dataset_type.value, file_hash)
            if existing is not None and _is_completed(existing):
                metrics.record_skipped(dataset_type.value, source_system)
                return FileImportReport(
                    file_name=file.name,
                    file_hash=file_hash,
                    outcome=ImportOutcome.SKIPPED_IDEMPOTENT,
                    data_import_id=existing.id,
                    rows_loaded=existing.rows_loaded,
                )

        if dry_run:
            return self._dry_run_file(dataset_type, file, file_hash)

        import_id = self._register_import(context, dataset_type, file, file_hash)
        metrics.record_started(dataset_type.value, source_system)

        try:
            result = self._pipeline.process(
                dataset_type=dataset_type.value,
                file=file,
                file_hash=file_hash,
                import_id=import_id,
                dry_run=False,
            )
        except Exception as error:  # сбой любого рода фиксируется и откатывается
            self._fail(dataset_type, import_id, error)
            metrics.record_failed(dataset_type.value, source_system)
            return FileImportReport(
                file_name=file.name,
                file_hash=file_hash,
                outcome=ImportOutcome.FAILED,
                data_import_id=import_id,
                error_summary=_summarize(error),
            )

        self._complete(dataset_type, import_id, file, result)
        metrics.record_completed(
            dataset_type.value,
            source_system,
            rows_read=result.rows_read,
            rows_loaded=result.rows_loaded,
            rows_rejected=result.rows_rejected,
            warnings=result.rows_with_warning,
            duration_seconds=result.duration_seconds,
        )
        metrics.record_unmapped(
            dataset_type.value,
            organizations=len(result.unmapped_organizations),
            regions=len(result.unmapped_regions),
            profiles=len(result.unmapped_profiles),
        )
        return FileImportReport(
            file_name=file.name,
            file_hash=file_hash,
            outcome=ImportOutcome.COMPLETED,
            data_import_id=import_id,
            rows_read=result.rows_read,
            rows_valid=result.rows_valid,
            rows_rejected=result.rows_rejected,
            rows_loaded=result.rows_loaded,
            warnings_count=result.rows_with_warning,
            duration_seconds=result.duration_seconds,
            findings=result.findings,
        )

    def _dry_run_file(
        self, dataset_type: DatasetType, file: SourceFileRef, file_hash: str
    ) -> FileImportReport:
        """Проверить файл, не трогая хранилище.

        Холостой прогон выполняет разбор, все четыре уровня проверок
        и псевдонимизацию: именно эти шаги и могут отказать на реальных
        данных. Запись в ClickHouse и в PostgreSQL не выполняется, запись
        об импорте не создаётся.
        """
        placeholder = uuid.uuid4()
        result = self._pipeline.process(
            dataset_type=dataset_type.value,
            file=file,
            file_hash=file_hash,
            import_id=placeholder,
            dry_run=True,
        )
        return FileImportReport(
            file_name=file.name,
            file_hash=file_hash,
            outcome=ImportOutcome.DRY_RUN,
            data_import_id=None,
            rows_read=result.rows_read,
            rows_valid=result.rows_valid,
            rows_rejected=result.rows_rejected,
            rows_loaded=0,
            warnings_count=result.rows_with_warning,
            duration_seconds=result.duration_seconds,
            findings=result.findings,
        )

    # ------------------------------------------------------------------
    # Состояние импорта
    # ------------------------------------------------------------------

    def _register_import(
        self,
        context: SecurityContext,
        dataset_type: DatasetType,
        file: SourceFileRef,
        file_hash: str,
    ) -> uuid.UUID:
        """Создать запись об импорте и перевести её в работу.

        Запись фиксируется отдельной транзакцией до начала разбора.
        Иначе упавший процесс не оставил бы следа, и отличить «импорт
        не запускался» от «импорт упал» было бы невозможно.
        """
        now = _now()
        with self._uow_factory() as uow:
            existing = uow.data_imports.find_by_hash(dataset_type.value, file_hash)
            if existing is not None and _is_completed(existing):
                # Сюда попасть нельзя: завершённый импорт отсеивается раньше.
                # Проверка оставлена потому, что цена ошибки — удаление
                # успешно загруженных данных откатом при следующем сбое.
                raise ValidationError("Импорт с таким содержимым уже завершён успешно")
            if existing is not None:
                # Прошлая попытка не дошла до конца. Переиспользуем запись,
                # чтобы ключ идемпотентности не был нарушен.
                import_id = existing.id
                uow.data_imports.update_status(
                    import_id,
                    status=DataImportStatus.RUNNING,
                    error_summary=None,
                    now=now,
                )
            else:
                created = uow.data_imports.add(
                    DataImport(
                        id=uuid.uuid4(),
                        dataset_type=dataset_type.value,
                        source=self._pipeline.source_system(dataset_type.value),
                        file_name=file.name,
                        file_hash=file_hash,
                        status=DataImportStatus.RUNNING,
                        created_by=context.internal_user_id,
                        request_id=get_request_id(),
                        started_at=now,
                        source_size_bytes=file.size_bytes,
                    )
                )
                import_id = created.id

            uow.audit.append(
                # Загрузку запускает и оператор командной строки, у которого
                # проекции пользователя нет. Пустой автор здесь допустим:
                # запись всё равно фиксирует, что и когда было загружено.
                actor_user_id=context.internal_user_id,
                action=AuditAction.DATA_IMPORT_REGISTERED,
                entity_type=AuditEntityType.DATA_IMPORT,
                entity_id=import_id,
                metadata={
                    "dataset_type": dataset_type.value,
                    "file_name": file.name,
                    "file_hash": file_hash,
                },
                request_id=get_request_id(),
            )
            uow.commit()

        logger.info(
            "Импорт начат",
            extra={
                "import_id": str(import_id),
                "dataset_type": dataset_type.value,
                "file_hash": file_hash,
            },
        )
        return import_id

    def _complete(
        self,
        dataset_type: DatasetType,
        import_id: uuid.UUID,
        file: SourceFileRef,
        result: PipelineFileResult,
    ) -> None:
        """Зафиксировать успешную загрузку одной транзакцией."""
        now = _now()
        with self._uow_factory() as uow:
            uow.data_imports.update_statistics(
                import_id,
                rows_read=result.rows_read,
                rows_valid=result.rows_valid,
                rows_rejected=result.rows_rejected,
                rows_loaded=result.rows_loaded,
                warnings_count=result.rows_with_warning,
                source_size_bytes=file.size_bytes,
                duration_seconds=result.duration_seconds,
            )
            uow.data_quality.add_many(
                [
                    DataQualityResult(
                        id=uuid.uuid4(),
                        data_import_id=import_id,
                        validation_level=finding.validation_level,
                        rule_code=finding.rule_code,
                        severity=QualitySeverity(finding.severity),
                        column_name=finding.column_name,
                        affected_rows=finding.affected_rows,
                        message=finding.message,
                    )
                    for finding in result.findings
                ]
            )
            uow.quarantine.add_many(
                [
                    QuarantineBatch(
                        id=uuid.uuid4(),
                        data_import_id=import_id,
                        dataset_type=dataset_type.value,
                        bucket=reference.bucket,
                        object_key=reference.object_key,
                        rows=reference.rows,
                        reason_codes=",".join(reference.reason_codes),
                    )
                    for reference in result.quarantine
                ]
            )

            source_system = self._pipeline.source_system(dataset_type.value)
            uow.organization_aliases.register_many(
                source_system=source_system,
                values=[(value, value) for value in result.unmapped_organizations],
                import_id=import_id,
            )
            uow.region_aliases.register_many(
                source_system=source_system,
                values=[(value, value) for value in result.unmapped_regions],
                import_id=import_id,
            )
            uow.profile_aliases.register_many(
                source_system=source_system,
                values=[(value, value) for value in result.unmapped_profiles],
                import_id=import_id,
            )

            uow.data_imports.update_status(
                import_id,
                status=DataImportStatus.COMPLETED,
                error_summary=None,
                now=now,
            )
            uow.commit()

        logger.info(
            "Импорт завершён",
            extra={
                "import_id": str(import_id),
                "rows_read": result.rows_read,
                "rows_loaded": result.rows_loaded,
                "rows_rejected": result.rows_rejected,
            },
        )

    def _fail(
        self, dataset_type: DatasetType, import_id: uuid.UUID, error: Exception
    ) -> None:
        """Пометить импорт неуспешным и убрать его следы из хранилища."""
        summary = _summarize(error)
        try:
            self._pipeline.rollback(dataset_type=dataset_type.value, import_id=import_id)
        except Exception:  # откат не должен скрывать исходную ошибку
            logger.exception(
                "Откат импорта не выполнен",
                extra={"import_id": str(import_id)},
            )
            summary = (
                f"{summary}. Откат аналитического хранилища не выполнен; "
                "требуется ручное восстановление"
            )

        with self._uow_factory() as uow:
            uow.data_imports.update_status(
                import_id,
                status=DataImportStatus.FAILED,
                error_summary=summary,
                now=_now(),
            )
            uow.commit()

        logger.error(
            "Импорт не выполнен",
            extra={"import_id": str(import_id), "error_summary": summary},
        )

    def recover(self, context: SecurityContext, import_id: uuid.UUID) -> None:
        """Убрать следы незавершённого импорта.

        Применяется, когда процесс прервался и запись осталась в состоянии
        RUNNING. Завершённый импорт этой командой не трогается: удалять
        опубликованные данные нужно осознанно, а не в порядке
        восстановления.
        """
        self._authz.require_permission(context, Permission.ADMIN_MANAGE)

        with self._uow_factory() as uow:
            data_import = uow.data_imports.get(import_id)
            if data_import is None:
                raise NotFoundError("Импорт не найден")
            if _is_completed(data_import):
                raise ValidationError(
                    "Импорт завершён успешно и восстановлению не подлежит"
                )
            dataset_type = data_import.dataset_type

        self._pipeline.rollback(dataset_type=dataset_type, import_id=import_id)

        with self._uow_factory() as uow:
            uow.data_imports.update_status(
                import_id,
                status=DataImportStatus.FAILED,
                error_summary="Импорт отменён процедурой восстановления",
                now=_now(),
            )
            uow.commit()


def _is_completed(data_import: DataImport) -> bool:
    """Завершён ли импорт успешно.

    Сравнение через приведение к перечислению, а не через `is`. Столбец
    состояния объявлен строковым, и объект, прочитанный из PostgreSQL,
    несёт обычную строку, а не член перечисления. Проверка на
    тождественность в этом случае всегда ложна, и повторный импорт того
    же файла не был бы распознан.
    """
    return DataImportStatus(data_import.status) is DataImportStatus.COMPLETED


def _summarize(error: Exception) -> str:
    """Краткая причина отказа для человека.

    В сообщение попадает тип ошибки и её текст, но не трассировка и не
    содержимое строк: сообщение об ошибке — не место для медицинских
    данных. Полная картина остаётся в журнале, связанном по request_id.
    """
    text = str(error).strip() or error.__class__.__name__
    return text[:500]
