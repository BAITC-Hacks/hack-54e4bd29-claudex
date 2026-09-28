"""Метрики конвейера загрузки.

Определены здесь, а не в бизнес-слое: метрика — это наблюдаемость,
а не правило предметной области. Сервис вызывает функции этого модуля,
не зная, чем именно они реализованы.

Правило по меткам простое и жёсткое: в метку не попадает ничего, кроме
типа набора, системы-источника и исхода. Ни идентификатора пациента,
ни кода случая, ни наименования организации. Метка с высокой мощностью
превращает хранилище метрик в базу данных, а метка с идентификатором —
в утечку.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

# Метки: тип набора и система-источник. Обе имеют не более десятка
# значений и известны заранее.
_DATASET_LABELS = ("dataset_type", "source_system")

data_import_started_total = Counter(
    "medsignal_data_import_started_total",
    "Начатые импорты",
    _DATASET_LABELS,
)
data_import_completed_total = Counter(
    "medsignal_data_import_completed_total",
    "Успешно завершённые импорты",
    _DATASET_LABELS,
)
data_import_failed_total = Counter(
    "medsignal_data_import_failed_total",
    "Неуспешные импорты",
    _DATASET_LABELS,
)
data_import_skipped_total = Counter(
    "medsignal_data_import_skipped_total",
    "Импорты, пропущенные как уже выполненные",
    _DATASET_LABELS,
)

data_rows_read_total = Counter(
    "medsignal_data_rows_read_total",
    "Прочитано строк источника",
    _DATASET_LABELS,
)
data_rows_loaded_total = Counter(
    "medsignal_data_rows_loaded_total",
    "Загружено строк в аналитическое хранилище",
    _DATASET_LABELS,
)
data_rows_rejected_total = Counter(
    "medsignal_data_rows_rejected_total",
    "Отклонено строк",
    _DATASET_LABELS,
)
data_validation_warnings_total = Counter(
    "medsignal_data_validation_warnings_total",
    "Строк с предупреждением проверки",
    _DATASET_LABELS,
)

# Несопоставленные значения справочников. Метка — вид справочника,
# а не само значение: значений тысячи, и они относятся к организациям.
data_unmapped_total = Counter(
    "medsignal_data_unmapped_total",
    "Различных значений без сопоставления со справочником",
    ("dataset_type", "reference"),
)

# Границы подобраны под наблюдаемые времена: часть файла обрабатывается
# доли секунды, полный набор — десятки секунд.
data_import_duration_seconds = Histogram(
    "medsignal_data_import_duration_seconds",
    "Длительность обработки одного файла",
    _DATASET_LABELS,
    buckets=(0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600),
)


def record_started(dataset_type: str, source_system: str) -> None:
    data_import_started_total.labels(dataset_type, source_system).inc()


def record_skipped(dataset_type: str, source_system: str) -> None:
    data_import_skipped_total.labels(dataset_type, source_system).inc()


def record_failed(dataset_type: str, source_system: str) -> None:
    data_import_failed_total.labels(dataset_type, source_system).inc()


def record_completed(
    dataset_type: str,
    source_system: str,
    *,
    rows_read: int,
    rows_loaded: int,
    rows_rejected: int,
    warnings: int,
    duration_seconds: float,
) -> None:
    labels = (dataset_type, source_system)
    data_import_completed_total.labels(*labels).inc()
    data_rows_read_total.labels(*labels).inc(rows_read)
    data_rows_loaded_total.labels(*labels).inc(rows_loaded)
    data_rows_rejected_total.labels(*labels).inc(rows_rejected)
    data_validation_warnings_total.labels(*labels).inc(warnings)
    data_import_duration_seconds.labels(*labels).observe(duration_seconds)


def record_unmapped(
    dataset_type: str, *, organizations: int, regions: int, profiles: int
) -> None:
    data_unmapped_total.labels(dataset_type, "organization").inc(organizations)
    data_unmapped_total.labels(dataset_type, "region").inc(regions)
    data_unmapped_total.labels(dataset_type, "profile").inc(profiles)
