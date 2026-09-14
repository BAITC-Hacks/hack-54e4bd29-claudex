"""Контракты наборов данных MedSignal.

Контракт описывает, что pipeline ожидает от файла. Реестр контрактов
является разрешающим списком: набор, которого в нём нет, загрузить нельзя.
"""

from data_pipeline.contracts.base import (
    ColumnKind,
    ColumnSpec,
    DatasetContract,
    Nullability,
    require_columns,
)
from data_pipeline.contracts.datasets import (
    ALLOWED_DATASETS,
    CONTRACTS,
    REFERRALS,
    REFUSALS,
    TREATED,
    WAITING,
    get_contract,
)

__all__ = [
    "ALLOWED_DATASETS",
    "CONTRACTS",
    "REFERRALS",
    "REFUSALS",
    "TREATED",
    "WAITING",
    "ColumnKind",
    "ColumnSpec",
    "DatasetContract",
    "Nullability",
    "get_contract",
    "require_columns",
]
