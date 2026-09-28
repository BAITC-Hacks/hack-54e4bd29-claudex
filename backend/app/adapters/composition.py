"""Сборка сервиса импорта.

Вынесено из основного композиционного корня, потому что здесь появляется
зависимость от библиотеки разбора файлов. Образ API её не содержит и
не должен: сервис, смотрящий наружу, не обязан уметь читать гигабайтные
выгрузки, а лишняя библиотека — это лишняя поверхность атаки.

Этот модуль импортируется только исполнителем загрузки.
"""

from __future__ import annotations

from pathlib import Path

from app.adapters.ingestion import PipelineAdapter
from app.business.ingestion.service import ImportService
from app.composition import get_unit_of_work_factory
from app.core.config import get_settings
from app.database.clickhouse import get_client as get_clickhouse_client
from app.database.object_storage import get_object_storage
from app.security.authorization import get_authorization_service
from data_pipeline.loading.clickhouse_writer import ClickHouseClient


def _clickhouse_writer_client() -> ClickHouseClient:
    """Adapt the cached driver client to the import writer's narrow contract."""
    return get_clickhouse_client()


def build_import_service(source_root: Path | None = None) -> ImportService:
    """Сервис импорта вместе с конвейером обработки файлов.

    Каталог источника берётся из настроек и может быть переопределён
    вызывающим. Путь из запроса пользователя сюда не попадает: приём
    произвольного пути означал бы чтение любого файла от имени
    приложения.
    """
    settings = get_settings()
    adapter = PipelineAdapter(
        settings=settings,
        source_root=source_root or Path(settings.data_source_dir),
        clickhouse_client_factory=_clickhouse_writer_client,
        object_storage=get_object_storage(),
    )
    return ImportService(get_unit_of_work_factory(), get_authorization_service(), adapter)
