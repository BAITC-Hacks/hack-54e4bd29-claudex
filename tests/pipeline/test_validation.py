"""Проверки качества и разбора.

Главная проверяемая мысль: отклонение строки — крайняя мера. Отсутствие
необязательного поля не должно стоить строки, а отсутствие даты, по
которой строится ряд, — должно.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from data_pipeline.contracts import get_contract
from data_pipeline.ingestion.reader import (
    SchemaMismatchError,
    ensure_schema,
    inspect_schema,
    read_batches,
)
from data_pipeline.transformation.normalization import (
    normalize_icd10,
    normalize_organization,
    normalize_text,
    normalized_frame,
    parse_datetime,
)
from data_pipeline.validation.engine import REJECT_COLUMN, validate_batch
from data_pipeline.validation.rules import FindingCollector, RuleCode, Severity
from tests.pipeline.conftest import (
    dataset_file,
    referral_row,
    refusal_row,
    treated_row,
    waiting_row,
    write_csv,
)


def _validate(rows, dataset_key: str):
    contract = get_contract(dataset_key)
    frame = pl.DataFrame(
        [{name: row.get(name) or None for name in contract.column_names} for row in rows],
        schema={name: pl.String for name in contract.column_names},
    )
    collector = FindingCollector()
    result = validate_batch(normalized_frame(frame, contract), contract, collector)
    return result, collector


def _codes(collector: FindingCollector) -> dict[str, int]:
    return {f.rule_code.value: f.affected_rows for f in collector.findings()}


# --- Нормализация -----------------------------------------------------------


def test_empty_string_becomes_missing_value() -> None:
    frame = pl.DataFrame({"value": ["  ", "текст", ""]})
    result = frame.select(normalize_text(pl.col("value")).alias("value"))
    assert result["value"].to_list() == [None, "текст", None]


def test_organization_key_collapses_case_and_spacing() -> None:
    frame = pl.DataFrame({"org": ['  ТОО   "Клиника"  ', 'тоо "клиника"']})
    result = frame.select(normalize_organization(pl.col("org")).alias("org"))
    assert result["org"][0] == result["org"][1]


def test_organization_key_keeps_the_number() -> None:
    """«Поликлиника №1» и «Поликлиника №11» — разные организации."""
    frame = pl.DataFrame({"org": ["Поликлиника №1", "Поликлиника №11"]})
    result = frame.select(normalize_organization(pl.col("org")).alias("org"))
    assert result["org"][0] != result["org"][1]


def test_icd_code_keeps_ranges_and_dots() -> None:
    """Справочник МКБ-10 содержит и диапазоны, и коды с точкой."""
    frame = pl.DataFrame({"icd": [" j41.0 ", "c01-02"]})
    result = frame.select(normalize_icd10(pl.col("icd")).alias("icd"))
    assert result["icd"].to_list() == ["J41.0", "C01-02"]


def test_datetime_parsed_with_and_without_fraction() -> None:
    frame = pl.DataFrame(
        {"dt": ["2025-01-16 16:01:14.463000", "2025-01-16 16:01:14", "мусор"]}
    )
    result = frame.select(parse_datetime(pl.col("dt")).alias("dt"))
    assert result["dt"][0] is not None
    assert result["dt"][1] is not None
    assert result["dt"][2] is None


# --- Схема ------------------------------------------------------------------


def test_missing_column_is_rejected(tmp_path: Path) -> None:
    contract = get_contract("REFERRALS")
    columns = [c for c in contract.column_names if c != "bed_profile"]
    path = write_csv(tmp_path / "broken.csv", [referral_row()], columns)
    with pytest.raises(SchemaMismatchError) as error:
        ensure_schema(path, contract)
    assert "bed_profile" in str(error.value)


def test_unexpected_column_is_rejected(tmp_path: Path) -> None:
    """Лишний столбец означает, что источник изменился, и это не мелочь."""
    contract = get_contract("REFERRALS")
    columns = [*contract.column_names, "новый_столбец"]
    path = write_csv(tmp_path / "extra.csv", [referral_row()], columns)
    schema = inspect_schema(path, contract)
    assert schema.unexpected == ("новый_столбец",)
    assert not schema.matches_contract


def test_valid_file_matches_contract(source_root: Path) -> None:
    contract = get_contract("REFERRALS")
    path = source_root / contract.source_directory / f"{contract.source_directory}.csv"
    assert ensure_schema(path, contract).matches_contract


# --- Направления ------------------------------------------------------------


def test_valid_referral_is_accepted() -> None:
    result, collector = _validate([referral_row()], "REFERRALS")
    assert result.valid.height == 1
    assert result.rejected.height == 0
    assert RuleCode.MISSING_REQUIRED_VALUE.value not in _codes(collector)


def test_missing_optional_bed_profile_does_not_reject() -> None:
    """Профиль койки пуст почти в половине строк. Терять их нельзя."""
    result, collector = _validate([referral_row(bed_profile="")], "REFERRALS")
    assert result.valid.height == 1
    assert RuleCode.MISSING_REQUIRED_VALUE.value not in _codes(collector)


def test_empty_refusal_date_is_expected_not_a_defect() -> None:
    """Отсутствие даты отказа означает, что отказа не было."""
    result, collector = _validate([referral_row(refusal_dt="")], "REFERRALS")
    assert result.valid.height == 1
    findings = {f.rule_code: f for f in collector.findings()}
    conditional = findings[RuleCode.CONDITIONAL_NULL_EXPECTED]
    assert conditional.severity is Severity.INFO
    assert conditional.affected_rows >= 1


def test_invalid_registration_date_rejects_the_row() -> None:
    result, collector = _validate([referral_row(registration_dt="не дата")], "REFERRALS")
    assert result.rejected.height == 1
    assert _codes(collector)[RuleCode.INVALID_REGISTRATION_DATE.value] == 1


def test_registration_date_out_of_range_rejects_the_row() -> None:
    result, collector = _validate(
        [referral_row(registration_dt="0001-05-31 07:57:27")], "REFERRALS"
    )
    assert result.rejected.height == 1
    assert RuleCode.DATE_OUT_OF_RANGE.value in _codes(collector)


def test_hospitalization_before_registration_warns_but_keeps_the_row() -> None:
    """Порядок дат подозрителен, но строка всё ещё описывает направление."""
    result, collector = _validate(
        [
            referral_row(
                registration_dt="2025-02-01 10:00:00",
                hospitalization_dt="2025-01-01 10:00:00",
            )
        ],
        "REFERRALS",
    )
    assert result.valid.height == 1
    assert result.rejected.height == 0
    assert _codes(collector)[RuleCode.HOSPITALIZATION_BEFORE_REGISTRATION.value] == 1


def test_duplicate_source_key_is_not_a_rejection() -> None:
    """Код случая повторяется в реальной выгрузке и ключом не является."""
    rows = [referral_row(), referral_row()]
    result, _ = _validate(rows, "REFERRALS")
    assert result.valid.height == 2


# --- Очередь ----------------------------------------------------------------


def test_missing_operation_does_not_reject_waiting_row() -> None:
    """Операция отсутствует у трёх четвертей записей очереди."""
    result, collector = _validate(
        [waiting_row(operation_code="", operation_name="")], "WAITING"
    )
    assert result.valid.height == 1
    assert RuleCode.MISSING_REQUIRED_VALUE.value not in _codes(collector)


def test_unknown_hospital_code_is_still_ingested() -> None:
    """Неизвестная организация не отменяет запись: справочника ещё нет."""
    result, _ = _validate([waiting_row(mo_destination_code="ZZZZ")], "WAITING")
    assert result.valid.height == 1


def test_missing_patient_number_rejects_the_row() -> None:
    """Без номера запись очереди не отличима от другой такой же."""
    result, collector = _validate([waiting_row(patient_seq_no="")], "WAITING")
    assert result.rejected.height == 1
    assert _codes(collector)[RuleCode.MISSING_REQUIRED_VALUE.value] == 1


# --- Отказы -----------------------------------------------------------------


def test_valid_refusal_is_accepted() -> None:
    result, _ = _validate([refusal_row()], "REFUSALS")
    assert result.valid.height == 1


def test_unknown_region_is_ingested_with_a_warning() -> None:
    result, _ = _validate([refusal_row(region_in="Регион Неизвестный")], "REFUSALS")
    assert result.valid.height == 1


def test_missing_benefit_category_is_expected() -> None:
    result, collector = _validate([refusal_row(benefit_cat="")], "REFUSALS")
    assert result.valid.height == 1
    assert RuleCode.CONDITIONAL_NULL_EXPECTED.value in _codes(collector)


def test_missing_refusal_date_rejects_the_row() -> None:
    result, collector = _validate([refusal_row(refuse_dt="")], "REFUSALS")
    assert result.rejected.height == 1
    assert RuleCode.INVALID_REFUSAL_DATE.value in _codes(collector)


# --- Пролеченные случаи -----------------------------------------------------


def test_negative_aggregate_rejects_the_row() -> None:
    """Отрицательное число выбывших невозможно по смыслу поля."""
    result, collector = _validate([treated_row(discharged_total="-5")], "TREATED")
    assert result.rejected.height == 1
    assert _codes(collector)[RuleCode.NEGATIVE_AGGREGATE.value] == 1


def test_missing_organization_rejects_the_row() -> None:
    """Показатели без организации нельзя отнести ни к кому."""
    result, collector = _validate([treated_row(medicine_organization="")], "TREATED")
    assert result.rejected.height == 1
    assert _codes(collector)[RuleCode.MISSING_REQUIRED_VALUE.value] == 1


def test_snapshot_date_is_the_only_time_axis_of_treated() -> None:
    """Отчётного периода в наборе нет, и осью служит отметка выгрузки."""
    from data_pipeline.validation.engine import DATE_AXES

    assert DATE_AXES["TREATED"].column == "sdu_load_date"


# --- Чтение пакетами --------------------------------------------------------


def test_batches_cover_every_row(tmp_path: Path) -> None:
    contract = get_contract("REFERRALS")
    rows = [referral_row(hospitalization_code=f"61.01W9.321.{i}") for i in range(250)]
    path = dataset_file(tmp_path, contract, rows)
    total = sum(batch.height for batch in read_batches(path, contract, batch_size=64))
    assert total == 250


def test_batch_size_limits_frame_height(tmp_path: Path) -> None:
    """Расход памяти определяется размером пакета, а не размером файла."""
    contract = get_contract("REFERRALS")
    rows = [referral_row(hospitalization_code=f"61.01W9.321.{i}") for i in range(300)]
    path = dataset_file(tmp_path, contract, rows)
    heights = [batch.height for batch in read_batches(path, contract, batch_size=50)]
    assert max(heights) <= 50
    assert sum(heights) == 300


def test_reject_column_marks_only_bad_rows() -> None:
    rows = [referral_row(), referral_row(registration_dt="")]
    result, _ = _validate(rows, "REFERRALS")
    assert result.frame[REJECT_COLUMN].to_list() == [False, True]


# --- Учёт строк -------------------------------------------------------------


def test_rows_with_missing_numeric_value_are_not_lost() -> None:
    """Строка с пустой суммой обязана остаться в учёте.

    Сравнение отсутствующего числа с нулём даёт пустое значение, а не
    «ложь». Если пустое значение попадает в маску отклонения, строка
    исчезает и из принятых, и из отклонённых. На реальной выгрузке
    отказов так терялась четверть записей.
    """
    rows = [refusal_row(amount=""), refusal_row()]
    result, _ = _validate(rows, "REFUSALS")

    assert result.valid.height + result.rejected.height == 2
    assert result.valid.height == 2


def test_every_row_lands_in_exactly_one_bucket() -> None:
    rows = [
        referral_row(),
        referral_row(registration_dt=""),
        referral_row(bed_profile=""),
        referral_row(planned_dt=""),
    ]
    result, _ = _validate(rows, "REFERRALS")

    assert result.valid.height + result.rejected.height == len(rows)
    assert result.frame[REJECT_COLUMN].null_count() == 0


def test_optional_numeric_absence_is_not_a_negative_value() -> None:
    """Пустая сумма не должна выглядеть отрицательной."""
    result, collector = _validate([treated_row(amount_to_pay="")], "TREATED")
    assert RuleCode.NEGATIVE_AGGREGATE.value not in _codes(collector)
