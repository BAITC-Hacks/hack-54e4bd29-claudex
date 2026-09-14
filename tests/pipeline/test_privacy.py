"""Проверки границы приватности.

Здесь проверяется главное свойство конвейера: идентификатор из выгрузки
не может оказаться в аналитическом хранилище. Проверка выполняется
не на намерении, а на составе столбцов и на содержимом подставного
ClickHouse.
"""

from __future__ import annotations

import logging
import uuid

import polars as pl
import pytest

from data_pipeline.contracts import get_contract
from data_pipeline.privacy.pseudonymization import (
    InsecurePseudonymizationKeyError,
    Pseudonymizer,
    normalize_identifier,
)
from data_pipeline.transformation.canonical import (
    ForbiddenColumnError,
    assert_no_forbidden_columns,
    to_canonical,
)
from data_pipeline.transformation.normalization import (
    drop_raw_columns,
    normalized_frame,
)
from tests.pipeline.conftest import SECOND_KEY, TEST_KEY, referral_row, waiting_row

RAW_CODE = "61.01W9.321.72S"
RAW_PATIENT_NO = "172"


def _canonical(rows, dataset_key, pseudonymizer, import_id, now) -> pl.DataFrame:
    contract = get_contract(dataset_key)
    frame = pl.DataFrame(
        [{name: row.get(name) or None for name in contract.column_names} for row in rows],
        schema={name: pl.String for name in contract.column_names},
    )
    parsed = drop_raw_columns(normalized_frame(frame, contract))
    return to_canonical(parsed, contract, pseudonymizer, import_id, "hash", now)


# --- Псевдонимизация --------------------------------------------------------


def test_pseudonym_is_deterministic() -> None:
    first = Pseudonymizer.from_secret(TEST_KEY)
    second = Pseudonymizer.from_secret(TEST_KEY)
    assert first.pseudonymize(RAW_CODE) == second.pseudonymize(RAW_CODE)


def test_different_secret_gives_different_pseudonym() -> None:
    """Смена ключа обрывает связуемость. Так и задумано."""
    first = Pseudonymizer.from_secret(TEST_KEY)
    second = Pseudonymizer.from_secret(SECOND_KEY)
    assert first.pseudonymize(RAW_CODE) != second.pseudonymize(RAW_CODE)


def test_pseudonym_does_not_contain_source_value() -> None:
    pseudonymizer = Pseudonymizer.from_secret(TEST_KEY)
    value = pseudonymizer.pseudonymize(RAW_CODE)
    assert RAW_CODE not in value
    assert "01W9" not in value


def test_identifier_is_normalized_before_hashing() -> None:
    """Регистр и пробелы не должны порождать двух псевдонимов у одного случая."""
    pseudonymizer = Pseudonymizer.from_secret(TEST_KEY)
    assert pseudonymizer.pseudonymize(" 61.01w9.321.72s ") == pseudonymizer.pseudonymize(
        RAW_CODE
    )
    assert normalize_identifier(" abc ") == "ABC"


def test_composite_parts_do_not_collide() -> None:
    """Разные наборы частей обязаны давать разные псевдонимы.

    Простая склейка сделала бы («11», «01») и («110», «1») одной строкой,
    то есть одним человеком.
    """
    pseudonymizer = Pseudonymizer.from_secret(TEST_KEY)
    first = pseudonymizer.pseudonymize_parts("11", "01")
    second = pseudonymizer.pseudonymize_parts("110", "1")
    assert first != second


@pytest.mark.parametrize("key", ["", "change_me", "secret", "short"])
def test_insecure_key_is_rejected(key: str) -> None:
    with pytest.raises(InsecurePseudonymizationKeyError):
        Pseudonymizer.from_secret(key)


def test_error_message_never_contains_the_key() -> None:
    try:
        Pseudonymizer.from_secret("too-short-secret")
    except InsecurePseudonymizationKeyError as error:
        assert "too-short-secret" not in str(error)
    else:  # pragma: no cover
        pytest.fail("Короткий ключ должен быть отклонён")


def test_repr_hides_the_secret(caplog: pytest.LogCaptureFixture) -> None:
    """Ключ не должен попасть в журнал через случайный вывод объекта."""
    pseudonymizer = Pseudonymizer.from_secret(TEST_KEY)
    assert TEST_KEY not in repr(pseudonymizer)
    assert TEST_KEY not in str(pseudonymizer)

    with caplog.at_level(logging.INFO):
        logging.getLogger("test").info("объект: %s", pseudonymizer)
    assert TEST_KEY not in caplog.text


# --- Состав аналитических записей -------------------------------------------


def test_hospitalization_code_never_reaches_analytics(
    pseudonymizer: Pseudonymizer, import_id: uuid.UUID, now
) -> None:
    canonical = _canonical([referral_row()], "REFERRALS", pseudonymizer, import_id, now)

    assert "hospitalization_code" not in canonical.columns
    assert "diagnosis_name" not in canonical.columns
    serialised = str(canonical.to_dicts())
    assert RAW_CODE not in serialised
    assert "Простой хронический бронхит" not in serialised


def test_patient_seq_no_never_reaches_analytics(
    pseudonymizer: Pseudonymizer, import_id: uuid.UUID, now
) -> None:
    canonical = _canonical([waiting_row()], "WAITING", pseudonymizer, import_id, now)

    forbidden_columns = (
        "patient_seq_no",
        "diagnosis_name",
        "operation_code",
        "operation_name",
    )
    for forbidden in forbidden_columns:
        assert forbidden not in canonical.columns

    serialised = str(canonical.to_dicts())
    assert "Врожденный ихтиоз простой" not in serialised
    assert "Условная операция" not in serialised
    # Сам номер короткий и может случайно встретиться внутри псевдонима,
    # поэтому проверяется именно отсутствие столбца, а не подстроки.
    assert canonical["patient_key"][0] != RAW_PATIENT_NO


def test_waiting_keeps_only_operation_presence(
    pseudonymizer: Pseudonymizer, import_id: uuid.UUID, now
) -> None:
    with_operation = _canonical([waiting_row()], "WAITING", pseudonymizer, import_id, now)
    without_operation = _canonical(
        [waiting_row(operation_code="", operation_name="")],
        "WAITING",
        pseudonymizer,
        import_id,
        now,
    )
    assert with_operation["has_operation"][0] == 1
    assert without_operation["has_operation"][0] == 0


def test_refusals_carry_no_patient_identifier(
    pseudonymizer: Pseudonymizer, import_id: uuid.UUID, now
) -> None:
    from tests.pipeline.conftest import refusal_row

    canonical = _canonical([refusal_row()], "REFUSALS", pseudonymizer, import_id, now)
    assert not {"patient_key", "event_key", "icd_name"} & set(canonical.columns)


def test_forbidden_column_check_catches_a_leak() -> None:
    """Страховка срабатывает, если будущая правка добавит лишний столбец."""
    contract = get_contract("REFERRALS")
    leaked = pl.DataFrame({"hospitalization_code": ["61.01"], "event_key": ["abc"]})
    with pytest.raises(ForbiddenColumnError) as error:
        assert_no_forbidden_columns(leaked, contract)
    assert "hospitalization_code" in str(error.value)
