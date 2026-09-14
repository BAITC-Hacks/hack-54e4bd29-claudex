"""Репозитории сопоставления значений источника со справочниками.

Метода «сопоставить автоматически» здесь нет. Репозиторий умеет
зарегистрировать встреченное значение и посчитать, сколько раз оно
встретилось; связать его с организацией справочника может только
официальная выгрузка или человек, и это отдельная операция.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.enums import MappingStatus
from app.models.mapping import OrganizationAlias, ProfileAlias, RegionAlias

type AliasModel = type[OrganizationAlias] | type[RegionAlias] | type[ProfileAlias]


class _AliasRepository:
    """Общее поведение трёх таблиц сопоставления."""

    model: AliasModel

    def __init__(self, session: Session) -> None:
        self._session = session

    def register_many(
        self,
        *,
        source_system: str,
        values: Iterable[tuple[str, str]],
        import_id: uuid.UUID | None,
    ) -> int:
        """Запомнить встреченные значения.

        Вставка выполняется одним запросом с разрешением конфликта:
        значения приходят пакетами по тысячам, и отдельный SELECT на
        каждое превратил бы регистрацию справочника в самую дорогую
        часть импорта. Повторная встреча увеличивает счётчик, а не
        создаёт дубликат.
        """
        rows = [
            {
                "id": uuid.uuid4(),
                "source_system": source_system,
                "source_value": source_value,
                "normalized_value": normalized,
                "mapping_status": MappingStatus.UNMAPPED,
                "first_seen_import_id": import_id,
                "occurrences": 1,
            }
            for source_value, normalized in values
            if normalized
        ]
        if not rows:
            return 0

        statement = insert(self.model).values(rows)
        statement = statement.on_conflict_do_update(
            index_elements=["source_system", "normalized_value"],
            set_={"occurrences": self.model.occurrences + 1},
        )
        self._session.execute(statement)
        return len(rows)

    def count_unmapped(self) -> int:
        statement = (
            select(func.count())
            .select_from(self.model)
            .where(self.model.mapping_status == MappingStatus.UNMAPPED)
        )
        return int(self._session.execute(statement).scalar_one())

    def list_unmapped(self, limit: int = 100) -> Sequence[object]:
        statement = (
            select(self.model)
            .where(self.model.mapping_status == MappingStatus.UNMAPPED)
            .order_by(self.model.occurrences.desc())
            .limit(limit)
        )
        return list(self._session.scalars(statement).all())


class SqlAlchemyOrganizationAliasRepository(_AliasRepository):
    model = OrganizationAlias


class SqlAlchemyRegionAliasRepository(_AliasRepository):
    model = RegionAlias


class SqlAlchemyProfileAliasRepository(_AliasRepository):
    model = ProfileAlias
