"""Жизненный цикл импорта.

Проверяется поведение сервиса, а не разбор файлов: идемпотентность,
состояние операции, отчёт о качестве и поведение при сбое. Конвейер
подменён — его собственные проверки живут в tests/pipeline.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from app.business.ingestion.query import DataImportQueryService
from app.business.ingestion.results import (
    ImportOutcome,
    PipelineFileResult,
    QualityFinding,
    QuarantineReference,
)
from app.business.ingestion.service import ImportService
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.models.enums import DataImportStatus, DatasetType
from app.security.authorization import AuthorizationService
from app.security.context import DataScope, Role
from app.shared.pagination import PageRequest
from tests.fakes import FakeStore, make_context, unit_of_work_factory


@dataclass
class FakeSourceFile:
    name: str
    path: Path
    size_bytes: int = 1024


@dataclass
class FakePipeline:
    """Подставной конвейер с управляемым поведением."""

    files: list[FakeSourceFile]
    hashes: dict[str, str] = field(default_factory=dict)
    fail_on: set[str] = field(default_factory=set)
    rows: int = 10
    rejected: int = 2
    rollbacks: list[uuid.UUID] = field(default_factory=list)
    processed: list[uuid.UUID] = field(default_factory=list)
    findings: tuple[QualityFinding, ...] = ()
    quarantine: tuple[QuarantineReference, ...] = ()
    organizations: tuple[str, ...] = ()

    expected_rows: int | None = None

    def source_system(self, dataset_type: str) -> str:  # noqa: ARG002
        return "ИС БГ"

    def expected_row_count(self, dataset_type: str) -> int | None:  # noqa: ARG002
        return self.expected_rows

    def discover(self, dataset_type: str) -> list[FakeSourceFile]:  # noqa: ARG002
        return self.files

    def fingerprint(self, file: FakeSourceFile) -> str:
        return self.hashes.get(file.name, f"hash-{file.name}")

    def process(
        self,
        *,
        dataset_type: str,  # noqa: ARG002
        file: FakeSourceFile,
        file_hash: str,
        import_id: uuid.UUID,
        dry_run: bool,
    ) -> PipelineFileResult:
        if file.name in self.fail_on:
            raise RuntimeError("разбор не удался")
        self.processed.append(import_id)
        loaded = 0 if dry_run else self.rows - self.rejected
        return PipelineFileResult(
            file_name=file.name,
            file_hash=file_hash,
            size_bytes=file.size_bytes,
            rows_read=self.rows,
            rows_valid=self.rows - self.rejected,
            rows_with_warning=1,
            rows_rejected=self.rejected,
            rows_loaded=loaded,
            duration_seconds=0.5,
            findings=self.findings,
            quarantine=self.quarantine,
            unmapped_organizations=self.organizations,
        )

    def rollback(self, *, dataset_type: str, import_id: uuid.UUID) -> None:  # noqa: ARG002
        self.rollbacks.append(import_id)


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


def build_service(store: FakeStore, pipeline: FakePipeline) -> ImportService:
    return ImportService(unit_of_work_factory(store), AuthorizationService(), pipeline)


def admin_context():
    return make_context(roles={Role.ADMIN}, scope=DataScope.global_scope())


@pytest.fixture
def pipeline(tmp_path: Path) -> FakePipeline:
    return FakePipeline(files=[FakeSourceFile("part_1.csv", tmp_path / "part_1.csv")])


# --- Идемпотентность --------------------------------------------------------


def test_second_import_of_the_same_file_is_skipped(
    store: FakeStore, pipeline: FakePipeline
) -> None:
    service = build_service(store, pipeline)
    context = admin_context()

    first = service.import_dataset(context, DatasetType.REFERRALS)
    second = service.import_dataset(context, DatasetType.REFERRALS)

    assert first.files[0].outcome is ImportOutcome.COMPLETED
    assert second.files[0].outcome is ImportOutcome.SKIPPED_IDEMPOTENT
    # Второй прогон не дошёл до разбора: файл не читался повторно.
    assert len(pipeline.processed) == 1
    assert len(store.data_imports) == 1


def test_skipped_import_reports_previously_loaded_rows(
    store: FakeStore, pipeline: FakePipeline
) -> None:
    service = build_service(store, pipeline)
    context = admin_context()
    service.import_dataset(context, DatasetType.REFERRALS)

    again = service.import_dataset(context, DatasetType.REFERRALS)
    assert again.files[0].rows_loaded == pipeline.rows - pipeline.rejected


def test_same_name_different_content_is_a_new_import(
    store: FakeStore, tmp_path: Path
) -> None:
    """Имя файла не является его личностью: ключ — содержимое."""
    pipeline = FakePipeline(
        files=[FakeSourceFile("part.csv", tmp_path / "part.csv")],
        hashes={"part.csv": "hash-v1"},
    )
    service = build_service(store, pipeline)
    context = admin_context()
    service.import_dataset(context, DatasetType.REFERRALS)

    pipeline.hashes["part.csv"] = "hash-v2"
    second = service.import_dataset(context, DatasetType.REFERRALS)

    assert second.files[0].outcome is ImportOutcome.COMPLETED
    assert len(store.data_imports) == 2


def test_same_hash_in_another_dataset_is_a_separate_import(
    store: FakeStore, pipeline: FakePipeline
) -> None:
    """Ключ идемпотентности включает тип набора, а не только контрольную сумму."""
    service = build_service(store, pipeline)
    context = admin_context()

    service.import_dataset(context, DatasetType.REFERRALS)
    other = service.import_dataset(context, DatasetType.REFUSALS)

    assert other.files[0].outcome is ImportOutcome.COMPLETED
    assert len(store.data_imports) == 2


# --- Состояние и статистика -------------------------------------------------


def test_completed_import_stores_statistics(
    store: FakeStore, pipeline: FakePipeline
) -> None:
    service = build_service(store, pipeline)
    service.import_dataset(admin_context(), DatasetType.REFERRALS)

    record = next(iter(store.data_imports.values()))
    assert record.status is DataImportStatus.COMPLETED
    assert record.rows_read == pipeline.rows
    assert record.rows_rejected == pipeline.rejected
    assert record.rows_loaded == pipeline.rows - pipeline.rejected
    assert record.completed_at is not None


def test_import_is_written_to_the_audit_log(
    store: FakeStore, pipeline: FakePipeline
) -> None:
    service = build_service(store, pipeline)
    service.import_dataset(admin_context(), DatasetType.REFERRALS)

    actions = [event.action.value for event in store.audit]
    assert "DATA_IMPORT_REGISTERED" in actions


def test_quality_findings_are_persisted(store: FakeStore, tmp_path: Path) -> None:
    pipeline = FakePipeline(
        files=[FakeSourceFile("part.csv", tmp_path / "part.csv")],
        findings=(
            QualityFinding(
                validation_level="BUSINESS",
                rule_code="INVALID_REGISTRATION_DATE",
                severity="ERROR",
                column_name="registration_dt",
                affected_rows=17,
                message="17 строк содержат неразобранную дату регистрации",
            ),
        ),
    )
    service = build_service(store, pipeline)
    service.import_dataset(admin_context(), DatasetType.REFERRALS)

    assert len(store.quality) == 1
    assert store.quality[0].affected_rows == 17


def test_quality_message_carries_no_source_values(
    store: FakeStore, tmp_path: Path
) -> None:
    """Отчёт о качестве не должен становиться каналом утечки."""
    pipeline = FakePipeline(
        files=[FakeSourceFile("part.csv", tmp_path / "part.csv")],
        findings=(
            QualityFinding(
                validation_level="BUSINESS",
                rule_code="INVALID_REGISTRATION_DATE",
                severity="ERROR",
                column_name="registration_dt",
                affected_rows=17,
                message="17 строк содержат неразобранную дату регистрации",
            ),
        ),
    )
    service = build_service(store, pipeline)
    service.import_dataset(admin_context(), DatasetType.REFERRALS)

    message = store.quality[0].message
    assert "61.01" not in message
    assert message.startswith("17 строк")


def test_quarantine_references_are_persisted(store: FakeStore, tmp_path: Path) -> None:
    pipeline = FakePipeline(
        files=[FakeSourceFile("part.csv", tmp_path / "part.csv")],
        quarantine=(
            QuarantineReference(
                bucket="medsignal-quarantine",
                object_key="REFERRALS/2026/05/01/x/part-00000.parquet",
                rows=2,
                reason_codes=("INVALID_REGISTRATION_DATE",),
            ),
        ),
    )
    service = build_service(store, pipeline)
    service.import_dataset(admin_context(), DatasetType.REFERRALS)

    assert len(store.quarantine) == 1
    assert store.quarantine[0].bucket == "medsignal-quarantine"


def test_unmapped_organizations_are_registered(store: FakeStore, tmp_path: Path) -> None:
    """Несопоставленная организация накапливается, а не отбрасывается."""
    pipeline = FakePipeline(
        files=[FakeSourceFile("part.csv", tmp_path / "part.csv")],
        organizations=("больница а", "клиника б"),
    )
    service = build_service(store, pipeline)
    report = service.import_dataset(admin_context(), DatasetType.REFERRALS)

    assert report.unmapped_organizations == 2
    assert len(store.organization_aliases) == 2


# --- Сбой и восстановление --------------------------------------------------


def test_failed_import_is_rolled_back(store: FakeStore, tmp_path: Path) -> None:
    pipeline = FakePipeline(
        files=[FakeSourceFile("part.csv", tmp_path / "part.csv")],
        fail_on={"part.csv"},
    )
    service = build_service(store, pipeline)
    report = service.import_dataset(admin_context(), DatasetType.REFERRALS)

    assert report.files[0].outcome is ImportOutcome.FAILED
    assert report.failed
    record = next(iter(store.data_imports.values()))
    assert record.status is DataImportStatus.FAILED
    assert record.error_summary
    assert pipeline.rollbacks == [record.id]


def test_one_bad_file_does_not_cancel_the_good_one(
    store: FakeStore, tmp_path: Path
) -> None:
    """Набор поставляется частями: одна испорченная часть не отменяет все."""
    pipeline = FakePipeline(
        files=[
            FakeSourceFile("part_1.csv", tmp_path / "part_1.csv"),
            FakeSourceFile("part_2.csv", tmp_path / "part_2.csv"),
        ],
        fail_on={"part_2.csv"},
    )
    service = build_service(store, pipeline)
    report = service.import_dataset(admin_context(), DatasetType.REFERRALS)

    outcomes = [f.outcome for f in report.files]
    assert outcomes == [ImportOutcome.COMPLETED, ImportOutcome.FAILED]
    assert report.rows_loaded == pipeline.rows - pipeline.rejected


def test_failed_import_can_be_retried(store: FakeStore, tmp_path: Path) -> None:
    """Неуспешная попытка не блокирует повтор ключом идемпотентности."""
    pipeline = FakePipeline(
        files=[FakeSourceFile("part.csv", tmp_path / "part.csv")],
        fail_on={"part.csv"},
    )
    service = build_service(store, pipeline)
    context = admin_context()
    service.import_dataset(context, DatasetType.REFERRALS)

    pipeline.fail_on.clear()
    retry = service.import_dataset(context, DatasetType.REFERRALS)

    assert retry.files[0].outcome is ImportOutcome.COMPLETED
    assert len(store.data_imports) == 1


def test_recover_marks_the_import_failed(store: FakeStore, tmp_path: Path) -> None:
    pipeline = FakePipeline(
        files=[FakeSourceFile("part.csv", tmp_path / "part.csv")],
        fail_on={"part.csv"},
    )
    service = build_service(store, pipeline)
    context = admin_context()
    report = service.import_dataset(context, DatasetType.REFERRALS)
    import_id = report.files[0].data_import_id
    assert import_id is not None

    service.recover(context, import_id)

    assert store.data_imports[import_id].status is DataImportStatus.FAILED
    assert pipeline.rollbacks.count(import_id) == 2


def test_recover_refuses_a_completed_import(
    store: FakeStore, pipeline: FakePipeline
) -> None:
    """Удаление успешно загруженных данных — не процедура восстановления."""
    service = build_service(store, pipeline)
    context = admin_context()
    report = service.import_dataset(context, DatasetType.REFERRALS)
    import_id = report.files[0].data_import_id
    assert import_id is not None

    with pytest.raises(ValidationError):
        service.recover(context, import_id)


def test_recover_requires_an_existing_import(
    store: FakeStore, pipeline: FakePipeline
) -> None:
    service = build_service(store, pipeline)
    with pytest.raises(NotFoundError):
        service.recover(admin_context(), uuid.uuid4())


# --- Холостой прогон --------------------------------------------------------


def test_dry_run_writes_nothing(store: FakeStore, pipeline: FakePipeline) -> None:
    service = build_service(store, pipeline)
    report = service.import_dataset(admin_context(), DatasetType.REFERRALS, dry_run=True)

    assert report.files[0].outcome is ImportOutcome.DRY_RUN
    assert report.files[0].rows_loaded == 0
    assert store.data_imports == {}
    assert store.quality == []


def test_dry_run_still_parses_and_validates(
    store: FakeStore, pipeline: FakePipeline
) -> None:
    """Холостой прогон обязан выполнить именно те шаги, что могут отказать."""
    service = build_service(store, pipeline)
    report = service.import_dataset(admin_context(), DatasetType.REFERRALS, dry_run=True)

    assert report.files[0].rows_read == pipeline.rows
    assert report.files[0].rows_rejected == pipeline.rejected
    assert len(pipeline.processed) == 1


# --- Права ------------------------------------------------------------------


@pytest.mark.parametrize(
    "role",
    [Role.REGIONAL_ANALYST, Role.HOSPITAL_MANAGER, Role.HOSPITAL_ANALYST],
)
def test_ordinary_user_cannot_start_an_import(
    store: FakeStore, pipeline: FakePipeline, role: Role
) -> None:
    service = build_service(store, pipeline)
    context = make_context(roles={role}, scope=DataScope.global_scope())
    with pytest.raises(ForbiddenError):
        service.import_dataset(context, DatasetType.REFERRALS)


@pytest.mark.parametrize(
    "role",
    [Role.REGIONAL_ANALYST, Role.HOSPITAL_MANAGER, Role.HOSPITAL_ANALYST],
)
def test_ordinary_user_cannot_read_import_history(
    store: FakeStore, pipeline: FakePipeline, role: Role
) -> None:
    context = make_context(roles={role}, scope=DataScope.global_scope())
    reader = DataImportQueryService(unit_of_work_factory(store), AuthorizationService())
    page = PageRequest(page=1, page_size=20, sort_by="created_at", sort_desc=True)
    with pytest.raises(ForbiddenError):
        reader.list_imports(context, page)


def test_ordinary_user_cannot_recover(store: FakeStore, pipeline: FakePipeline) -> None:
    """Восстановление удаляет данные и требует права администратора."""
    service = build_service(store, pipeline)
    context = make_context(roles={Role.HEALTH_AUTHORITY}, scope=DataScope.global_scope())
    with pytest.raises(ForbiddenError):
        service.recover(context, uuid.uuid4())


def test_health_authority_may_import(store: FakeStore, pipeline: FakePipeline) -> None:
    service = build_service(store, pipeline)
    context = make_context(roles={Role.HEALTH_AUTHORITY}, scope=DataScope.global_scope())
    report = service.import_dataset(context, DatasetType.REFERRALS)
    assert report.files[0].outcome is ImportOutcome.COMPLETED


def test_missing_files_are_reported(store: FakeStore) -> None:
    service = build_service(store, FakePipeline(files=[]))
    with pytest.raises(NotFoundError):
        service.import_dataset(admin_context(), DatasetType.REFERRALS)


# --- Состояние, прочитанное из базы -----------------------------------------


def test_status_stored_as_text_is_still_recognised(
    store: FakeStore, pipeline: FakePipeline
) -> None:
    """Состояние может прийти строкой, а не членом перечисления.

    Столбец объявлен строковым, и объект, прочитанный из PostgreSQL,
    несёт обычную строку. Проверка на тождественность в этом случае
    всегда ложна, и повторный импорт того же файла не распознавался бы
    как повторный — с удалением уже загруженных данных при откате.
    """
    service = build_service(store, pipeline)
    context = admin_context()
    service.import_dataset(context, DatasetType.REFERRALS)

    record = next(iter(store.data_imports.values()))
    record.status = "COMPLETED"  # так выглядит значение после чтения из базы

    again = service.import_dataset(context, DatasetType.REFERRALS)
    assert again.files[0].outcome is ImportOutcome.SKIPPED_IDEMPOTENT
    assert len(pipeline.processed) == 1


def test_completed_import_is_never_re_registered(
    store: FakeStore, pipeline: FakePipeline
) -> None:
    """Переиспользование записи завершённого импорта удалило бы его данные."""
    service = build_service(store, pipeline)
    context = admin_context()
    service.import_dataset(context, DatasetType.REFERRALS)

    record = next(iter(store.data_imports.values()))
    record.status = "COMPLETED"

    with pytest.raises(ValidationError):
        service._register_import(
            context, DatasetType.REFERRALS, pipeline.files[0], record.file_hash
        )


# --- Сверка с отчётом аудита ------------------------------------------------


def test_row_count_drift_is_measured_across_the_whole_dataset(
    store: FakeStore, tmp_path: Path
) -> None:
    """Ожидаемое число строк относится к набору, а не к одной его части.

    Набор поставляется частями. Сравнение числа строк одного файла
    с числом строк всего набора давало бы расхождение при каждой
    нормальной поставке.
    """
    pipeline = FakePipeline(
        files=[
            FakeSourceFile("part_1.csv", tmp_path / "part_1.csv"),
            FakeSourceFile("part_2.csv", tmp_path / "part_2.csv"),
        ],
        rows=100,
        rejected=0,
        expected_rows=200,
    )
    service = build_service(store, pipeline)
    report = service.import_dataset(admin_context(), DatasetType.REFERRALS)

    assert report.rows_read == 200
    assert report.row_count_drift is None


def test_real_drift_is_reported(store: FakeStore, tmp_path: Path) -> None:
    pipeline = FakePipeline(
        files=[FakeSourceFile("part.csv", tmp_path / "part.csv")],
        rows=100,
        rejected=0,
        expected_rows=500,
    )
    service = build_service(store, pipeline)
    report = service.import_dataset(admin_context(), DatasetType.REFERRALS)

    assert report.row_count_drift == 400


# --- Метрики ----------------------------------------------------------------


def _metric_value(counter, *labels) -> float:
    return counter.labels(*labels)._value.get()


def test_metric_labels_contain_no_identifiers() -> None:
    """Метка не должна нести значений из выгрузки.

    Метка с высокой мощностью превращает хранилище метрик в базу данных,
    а метка с идентификатором — в утечку.
    """
    from app.core import metrics

    allowed = {"dataset_type", "source_system", "reference"}
    for counter in (
        metrics.data_import_started_total,
        metrics.data_import_completed_total,
        metrics.data_import_failed_total,
        metrics.data_rows_read_total,
        metrics.data_rows_loaded_total,
        metrics.data_rows_rejected_total,
        metrics.data_unmapped_total,
        metrics.data_import_duration_seconds,
    ):
        assert set(counter._labelnames) <= allowed


def test_completed_import_is_counted(store: FakeStore, pipeline: FakePipeline) -> None:
    from app.core import metrics

    before = _metric_value(metrics.data_rows_loaded_total, "REFERRALS", "ИС БГ")
    service = build_service(store, pipeline)
    service.import_dataset(admin_context(), DatasetType.REFERRALS)
    after = _metric_value(metrics.data_rows_loaded_total, "REFERRALS", "ИС БГ")

    assert after - before == pipeline.rows - pipeline.rejected


def test_failed_import_is_counted(store: FakeStore, tmp_path: Path) -> None:
    from app.core import metrics

    pipeline = FakePipeline(
        files=[FakeSourceFile("bad.csv", tmp_path / "bad.csv")],
        fail_on={"bad.csv"},
    )
    before = _metric_value(metrics.data_import_failed_total, "REFERRALS", "ИС БГ")
    service = build_service(store, pipeline)
    service.import_dataset(admin_context(), DatasetType.REFERRALS)
    after = _metric_value(metrics.data_import_failed_total, "REFERRALS", "ИС БГ")

    assert after - before == 1
