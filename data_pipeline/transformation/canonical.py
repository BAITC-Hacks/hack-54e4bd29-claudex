"""Превращение исходной строки в аналитическую запись.

Здесь проходит граница приватности. Слева от неё — данные как в файле,
включая код случая и номер пациента; справа — то, что попадёт в ClickHouse.
Столбцы, перечисленные в контракте как запрещённые к переносу, физически
не могут оказаться справа: набор выходных столбцов задан явно, и запись
собирается по нему, а не копированием входного пакета.

Псевдонимизация выполняется здесь же, а не после загрузки. Загрузить
сырой идентификатор и обезличить его потом означает, что он какое-то
время лежал в аналитическом хранилище, а «какое-то время» в реальности
превращается в «навсегда» при первом же сбое.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import polars as pl

from data_pipeline.contracts import DatasetContract
from data_pipeline.contracts.datasets import REFERRALS, REFUSALS, TREATED, WAITING
from data_pipeline.privacy.pseudonymization import Pseudonymizer
from data_pipeline.transformation.normalization import (
    normalize_category,
    normalize_icd10,
    normalize_organization,
)

# Пустая строка вместо NULL в столбцах, входящих в ключ сортировки
# ClickHouse. Nullable в ORDER BY допустим, но делает пропуск участником
# упорядочения и портит сжатие; пустая строка честнее и дешевле.
EMPTY = ""


class ForbiddenColumnError(Exception):
    """Попытка перенести запрещённый столбец в аналитическое хранилище."""


def _text(column: str) -> pl.Expr:
    return pl.col(column).fill_null(EMPTY)


def _org(column: str) -> pl.Expr:
    return normalize_organization(pl.col(column)).fill_null(EMPTY)


def _icd(column: str) -> pl.Expr:
    return normalize_icd10(pl.col(column)).fill_null(EMPTY)


def _category(column: str) -> pl.Expr:
    return normalize_category(pl.col(column)).fill_null(EMPTY)


def _pseudonym_series(
    frame: pl.DataFrame, pseudonymizer: Pseudonymizer, columns: list[str]
) -> pl.Series:
    """Псевдонимы для пакета.

    HMAC считается на Python: векторизованной реализации в polars нет.
    Стоимость приемлема — порядка микросекунды на строку, что на пакете
    в пятьдесят тысяч строк даёт доли секунды.
    """
    parts = [frame[column].to_list() for column in columns]
    values = [
        pseudonymizer.pseudonymize_parts(
            *(str(part[index]) if part[index] is not None else None for part in parts)
        )
        for index in range(frame.height)
    ]
    return pl.Series("__pseudonym__", values, dtype=pl.String)


def _common(
    import_id: uuid.UUID,
    contract: DatasetContract,
    file_hash: str,
    now: dt.datetime,
) -> list[pl.Expr]:
    return [
        pl.lit(str(import_id)).alias("import_id"),
        pl.lit(contract.source_system).alias("source_system"),
        pl.lit(file_hash).alias("source_file_hash"),
        pl.lit(now).alias("ingested_at"),
    ]


def _referrals(
    frame: pl.DataFrame,
    contract: DatasetContract,
    pseudonymizer: Pseudonymizer,
    import_id: uuid.UUID,
    file_hash: str,
    now: dt.datetime,
) -> pl.DataFrame:
    keys = _pseudonym_series(frame, pseudonymizer, ["hospitalization_code"])
    return frame.with_columns(keys.alias("event_key")).select(
        pl.col("event_key"),
        pl.col("registration_dt"),
        pl.col("planned_dt"),
        pl.col("polyclinic_dt"),
        pl.col("hospitalization_dt"),
        pl.col("refusal_dt"),
        _org("referring_mo").alias("referring_org_key"),
        _org("hospital_mo").alias("receiving_org_key"),
        pl.lit(None, dtype=pl.String).alias("referring_hospital_id"),
        pl.lit(None, dtype=pl.String).alias("receiving_hospital_id"),
        _category("bed_profile").alias("profile_source"),
        pl.lit(None, dtype=pl.String).alias("canonical_profile_id"),
        _icd("icd10_ref_diag_code").alias("icd10_code"),
        _category("territorial_type").alias("territorial_type"),
        _category("referral_purpose").alias("referral_purpose"),
        _category("finance_source").alias("finance_source"),
        *_common(import_id, contract, file_hash, now),
    )


def _waiting(
    frame: pl.DataFrame,
    contract: DatasetContract,
    pseudonymizer: Pseudonymizer,
    import_id: uuid.UUID,
    file_hash: str,
    now: dt.datetime,
) -> pl.DataFrame:
    # Номер пациента сам по себе не уникален: восемь тысяч различных
    # значений на семьсот тысяч строк. Псевдоним строится по составному
    # идентификатору, иначе он склеил бы разных людей в одного.
    keys = _pseudonym_series(
        frame,
        pseudonymizer,
        ["region_origin_code", "mo_destination_code", "profile_code", "patient_seq_no"],
    )
    return frame.with_columns(keys.alias("patient_key")).select(
        pl.col("patient_key"),
        pl.col("registration_dt"),
        pl.col("planned_dt"),
        pl.col("sdu_load_date").alias("snapshot_dt"),
        _text("region_origin_code").alias("region_source"),
        pl.lit(None, dtype=pl.String).alias("region_id"),
        _text("mo_destination_code").alias("hospital_source"),
        pl.lit(None, dtype=pl.String).alias("hospital_id"),
        _text("profile_code").alias("profile_source"),
        pl.lit(None, dtype=pl.String).alias("profile_id"),
        _icd("icd10_ref_diag_code").alias("icd10_code"),
        pl.col("operation_code").is_not_null().cast(pl.UInt8).alias("has_operation"),
        *_common(import_id, contract, file_hash, now),
    )


def _refusals(
    frame: pl.DataFrame,
    contract: DatasetContract,
    pseudonymizer: Pseudonymizer,  # noqa: ARG001 — идентификаторов в наборе нет
    import_id: uuid.UUID,
    file_hash: str,
    now: dt.datetime,
) -> pl.DataFrame:
    return frame.select(
        pl.col("refuse_dt"),
        _category("region_in").alias("region_source"),
        pl.lit(None, dtype=pl.String).alias("region_id"),
        _org("org_in").alias("hospital_source"),
        pl.lit(None, dtype=pl.String).alias("hospital_id"),
        _category("attach_region").alias("attachment_region_source"),
        pl.lit(None, dtype=pl.String).alias("attachment_region_id"),
        _org("attach_org").alias("attachment_hospital_source"),
        pl.lit(None, dtype=pl.String).alias("attachment_hospital_id"),
        _category("resident").alias("resident"),
        _category("insured").alias("insured"),
        _category("benefit_cat").alias("benefit_category"),
        _icd("icd10").alias("icd10_code"),
        _category("finance_src").alias("finance_source"),
        pl.col("amount"),
        *_common(import_id, contract, file_hash, now),
    )


def _treated(
    frame: pl.DataFrame,
    contract: DatasetContract,
    pseudonymizer: Pseudonymizer,  # noqa: ARG001 — идентификаторов в наборе нет
    import_id: uuid.UUID,
    file_hash: str,
    now: dt.datetime,
) -> pl.DataFrame:
    return frame.select(
        _org("medicine_organization").alias("hospital_source"),
        pl.lit(None, dtype=pl.String).alias("hospital_id"),
        pl.col("discharged_total").cast(pl.UInt32),
        pl.col("discharged_children").cast(pl.UInt32),
        pl.col("treated_budget").cast(pl.UInt32),
        pl.col("treated_paid").cast(pl.UInt32),
        pl.col("discharged_within_day").cast(pl.UInt32),
        pl.col("deaths_total").cast(pl.UInt32),
        pl.col("bed_days").cast(pl.UInt64),
        pl.col("amount_to_pay"),
        # Имя столбца выбрано так, чтобы принять его за отчётный период
        # было трудно. Отчётного периода в источнике нет.
        pl.col("sdu_load_date").alias("snapshot_load_dt"),
        *_common(import_id, contract, file_hash, now),
    )


_BUILDERS: dict[
    str,
    Callable[
        [pl.DataFrame, DatasetContract, Pseudonymizer, uuid.UUID, str, dt.datetime],
        pl.DataFrame,
    ],
] = {
    REFERRALS: _referrals,
    WAITING: _waiting,
    REFUSALS: _refusals,
    TREATED: _treated,
}


def to_canonical(
    frame: pl.DataFrame,
    contract: DatasetContract,
    pseudonymizer: Pseudonymizer,
    import_id: uuid.UUID,
    file_hash: str,
    now: dt.datetime,
) -> pl.DataFrame:
    """Собрать аналитические записи из проверенного пакета."""
    builder = _BUILDERS.get(contract.key)
    if builder is None:  # pragma: no cover — реестр закрыт разрешающим списком
        raise KeyError(f"Нет канонизации для набора {contract.key}")

    result = builder(frame, contract, pseudonymizer, import_id, file_hash, now)
    assert_no_forbidden_columns(result, contract)
    return result


def assert_no_forbidden_columns(frame: pl.DataFrame, contract: DatasetContract) -> None:
    """Проверить, что запрещённый столбец не просочился в результат.

    Проверка избыточна по построению: набор выходных столбцов задан
    явно. Она существует именно поэтому — чтобы будущая правка, добавившая
    столбец «просто чтобы было», упала здесь, а не обнаружилась в
    аналитическом хранилище через полгода.
    """
    leaked = sorted(set(frame.columns) & contract.forbidden_in_analytics)
    if leaked:
        raise ForbiddenColumnError(
            f"Набор {contract.key}: столбцы {', '.join(leaked)} запрещены "
            "к переносу в аналитическое хранилище"
        )
