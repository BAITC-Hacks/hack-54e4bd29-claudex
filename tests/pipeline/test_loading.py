"""Загрузка, публикация, откат и карантин.

Проверяется семантика, ради которой промежуточная таблица вообще
существует: данные попадают в таблицу фактов только после сверки, а
прерванный импорт не оставляет следов, выдающих себя за поставку.
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path

import polars as pl
import pytest

from data_pipeline.contracts import get_contract
from data_pipeline.loading.clickhouse_writer import (
    ClickHouseLoader,
    RowCountMismatchError,
    batched,
)
from data_pipeline.loading.quarantine import QuarantineWriter, object_key
from data_pipeline.pipeline import process_file
from data_pipeline.privacy.pseudonymization import Pseudonymizer
from tests.pipeline.conftest import (
    FakeClickHouse,
    FakeObjectStore,
    dataset_file,
    referral_row,
    refusal_row,
    treated_row,
    waiting_row,
)

QUARANTINE_BUCKET = "medsignal-quarantine"


def _run(
    root: Path,
    dataset_key: str,
    rows: list[dict],
    clickhouse: FakeClickHouse,
    object_store: FakeObjectStore,
    pseudonymizer: Pseudonymizer,
    import_id: uuid.UUID,
):
    contract = get_contract(dataset_key)
    path = dataset_file(root, contract, rows)
    file_hash = "a" * 64
    loader = ClickHouseLoader(
        clickhouse,
        target_table=contract.target_table,
        staging_table=contract.staging_table,
        import_id=import_id,
    )
    quarantine = QuarantineWriter(
        object_store,
        bucket=QUARANTINE_BUCKET,
        dataset_type=dataset_key,
        data_import_id=import_id,
    )
    result = process_file(
        path=path,
        file_hash=file_hash,
        contract=contract,
        import_id=import_id,
        pseudonymizer=pseudonymizer,
        loader=loader,
        quarantine=quarantine,
    )
    return result, loader, quarantine, contract


# --- Публикация -------------------------------------------------------------


def test_rows_reach_facts_only_after_publish(
    tmp_path, clickhouse, object_store, pseudonymizer, import_id
) -> None:
    result, loader, _, contract = _run(
        tmp_path,
        "REFERRALS",
        [referral_row()],
        clickhouse,
        object_store,
        pseudonymizer,
        import_id,
    )

    assert clickhouse.rows(contract.staging_table)
    assert clickhouse.rows(contract.target_table) == []

    loader.verify_staged(result.rows_valid)
    published = loader.publish()
    loader.drop_staging()

    assert published.published_rows == 1
    assert len(clickhouse.rows(contract.target_table)) == 1
    assert clickhouse.rows(contract.staging_table) == []


def test_count_mismatch_stops_the_import(
    tmp_path, clickhouse, object_store, pseudonymizer, import_id
) -> None:
    """Расхождение числа строк означает потерю или задвоение."""
    _, loader, _, _ = _run(
        tmp_path,
        "REFERRALS",
        [referral_row()],
        clickhouse,
        object_store,
        pseudonymizer,
        import_id,
    )
    with pytest.raises(RowCountMismatchError):
        loader.verify_staged(expected=999)


def test_rollback_removes_staged_and_published_rows(
    tmp_path, clickhouse, object_store, pseudonymizer, import_id
) -> None:
    result, loader, _, contract = _run(
        tmp_path,
        "REFERRALS",
        [referral_row()],
        clickhouse,
        object_store,
        pseudonymizer,
        import_id,
    )
    loader.verify_staged(result.rows_valid)
    loader.publish()

    loader.rollback()

    assert clickhouse.rows(contract.staging_table) == []
    assert clickhouse.rows(contract.target_table) == []


def test_rollback_keeps_other_imports(
    tmp_path, clickhouse, object_store, pseudonymizer
) -> None:
    """Откат одного импорта не трогает соседний."""
    first = uuid.uuid4()
    second = uuid.uuid4()
    contract = get_contract("REFERRALS")

    result_a, loader_a, _, _ = _run(
        tmp_path / "a",
        "REFERRALS",
        [referral_row()],
        clickhouse,
        object_store,
        pseudonymizer,
        first,
    )
    loader_a.verify_staged(result_a.rows_valid)
    loader_a.publish()
    loader_a.drop_staging()

    result_b, loader_b, _, _ = _run(
        tmp_path / "b",
        "REFERRALS",
        [referral_row()],
        clickhouse,
        object_store,
        pseudonymizer,
        second,
    )
    loader_b.verify_staged(result_b.rows_valid)
    loader_b.publish()
    loader_b.rollback()

    remaining = clickhouse.rows(contract.target_table)
    assert len(remaining) == 1
    assert remaining[0]["import_id"] == str(first)


def test_every_row_carries_lineage(
    tmp_path, clickhouse, object_store, pseudonymizer, import_id
) -> None:
    """Строку витрины должно быть можно связать с файлом и импортом."""
    result, loader, _, contract = _run(
        tmp_path,
        "REFERRALS",
        [referral_row()],
        clickhouse,
        object_store,
        pseudonymizer,
        import_id,
    )
    loader.verify_staged(result.rows_valid)
    loader.publish()

    row = clickhouse.rows(contract.target_table)[0]
    assert row["import_id"] == str(import_id)
    assert row["source_file_hash"] == "a" * 64
    assert row["source_system"] == contract.source_system
    assert row["ingested_at"] is not None


# --- Карантин ---------------------------------------------------------------


def test_rejected_rows_go_to_quarantine(
    tmp_path, clickhouse, object_store, pseudonymizer, import_id
) -> None:
    rows = [referral_row(), referral_row(registration_dt="")]
    result, _, quarantine, contract = _run(
        tmp_path, "REFERRALS", rows, clickhouse, object_store, pseudonymizer, import_id
    )

    assert result.rows_read == 2
    assert result.rows_valid == 1
    assert result.rows_rejected == 1
    assert quarantine.rows == 1
    assert "INVALID_REGISTRATION_DATE" in quarantine.reason_codes
    assert QUARANTINE_BUCKET in object_store.buckets
    assert len(clickhouse.rows(contract.staging_table)) == 1


def test_quarantine_keeps_the_original_values(
    tmp_path, clickhouse, object_store, pseudonymizer, import_id
) -> None:
    """Карантин существует, чтобы владелец данных увидел отклонённое.

    Поэтому там лежат исходные значения — и поэтому он в зоне
    ограниченного доступа, а не в аналитическом API.
    """
    rows = [referral_row(registration_dt="не дата")]
    _, _, quarantine, _ = _run(
        tmp_path, "REFERRALS", rows, clickhouse, object_store, pseudonymizer, import_id
    )

    record = quarantine.records[0]
    payload = object_store.get(QUARANTINE_BUCKET, record.object_key)
    frame = pl.read_parquet(io.BytesIO(payload))
    assert frame.height == 1
    assert "__reject_reasons__" in frame.columns


def test_quarantine_key_carries_date_for_retention() -> None:
    import datetime as dt

    key = object_key("REFERRALS", uuid.UUID(int=1), 0, dt.datetime(2026, 5, 1))
    assert key.startswith("REFERRALS/2026/05/01/")
    assert key.endswith("part-00000.parquet")


# --- Наборы -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("dataset", "rows", "table"),
    [
        ("REFERRALS", [referral_row()], "fact_referral_events"),
        ("WAITING", [waiting_row()], "fact_waiting_events"),
        ("REFUSALS", [refusal_row()], "fact_refusal_events"),
        ("TREATED", [treated_row()], "fact_treated_snapshot"),
    ],
)
def test_each_dataset_loads(
    tmp_path, clickhouse, object_store, pseudonymizer, import_id, dataset, rows, table
) -> None:
    result, loader, _, _ = _run(
        tmp_path, dataset, rows, clickhouse, object_store, pseudonymizer, import_id
    )
    loader.verify_staged(result.rows_valid)
    loader.publish()
    assert len(clickhouse.rows(table)) == 1


def test_treated_snapshot_names_the_column_honestly(
    tmp_path, clickhouse, object_store, pseudonymizer, import_id
) -> None:
    """Отметка выгрузки не должна выглядеть отчётным периодом."""
    result, loader, _, _ = _run(
        tmp_path,
        "TREATED",
        [treated_row()],
        clickhouse,
        object_store,
        pseudonymizer,
        import_id,
    )
    loader.verify_staged(result.rows_valid)
    loader.publish()

    row = clickhouse.rows("fact_treated_snapshot")[0]
    assert "snapshot_load_dt" in row
    assert "reporting_period" not in row
    assert "sdu_load_date" not in row


def test_batched_splits_by_size() -> None:
    frame = pl.DataFrame({"x": list(range(250))})
    sizes = [part.height for part in batched(frame, size=100)]
    assert sizes == [100, 100, 50]


# --- Справочники ------------------------------------------------------------


def test_profiles_are_collected_for_mapping(
    tmp_path, clickhouse, object_store, pseudonymizer, import_id
) -> None:
    """Профиль койки накапливается так же, как организация и регион.

    Официального справочника профилей нет: наименования из направлений
    и коды из очереди не пересекаются ни одним значением. Накопленные
    значения — это материал для будущего сопоставления, и терять их
    нельзя.
    """
    rows = [
        referral_row(bed_profile="Неврологические для взрослых"),
        referral_row(bed_profile="Хирургические для взрослых"),
    ]
    result, _, _, _ = _run(
        tmp_path, "REFERRALS", rows, clickhouse, object_store, pseudonymizer, import_id
    )
    assert len(result.unmapped_profiles) == 2


def test_unmapped_sets_hold_distinct_values_not_rows(
    tmp_path, clickhouse, object_store, pseudonymizer, import_id
) -> None:
    """Интересен размер незакрытого справочника, а не число упоминаний."""
    rows = [referral_row() for _ in range(50)]
    result, _, _, _ = _run(
        tmp_path, "REFERRALS", rows, clickhouse, object_store, pseudonymizer, import_id
    )
    assert result.rows_read == 50
    assert len(result.unmapped_organizations) == 2
    assert len(result.unmapped_profiles) == 1
