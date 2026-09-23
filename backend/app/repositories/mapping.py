"""Репозитории сопоставления значений источника со справочниками.

Метода «сопоставить автоматически» здесь нет. Репозиторий умеет
зарегистрировать встреченное значение и посчитать, сколько раз оно
встретилось; связать его с организацией справочника может только
официальная выгрузка или человек, и это отдельная операция.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.enums import MappingStatus
from app.models.mapping import MappingState, OrganizationAlias, ProfileAlias, RegionAlias
from app.shared.mapping import MappingReadiness, MappingSnapshot

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
        identity_space: str = "LEGACY_UNRESOLVED",
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

        if self.model is not ProfileAlias:
            for row in rows:
                row["identity_space"] = identity_space
        statement = insert(self.model).values(rows)
        statement = statement.on_conflict_do_update(
            index_elements=["source_system", "normalized_value"]
            if self.model is ProfileAlias
            else ["source_system", "identity_space", "normalized_value"],
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


class SqlAlchemyMappingRepository:
    """All writers and transactional scoped consumers acquire lock 64730102 first."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def lock(self) -> None:
        from sqlalchemy import text

        self._session.execute(text("SELECT pg_advisory_xact_lock(64730102)"))

    def _state(self) -> MappingState | None:
        from app.models.mapping import MappingState

        return self._session.get(MappingState, 1, populate_existing=True)

    def readiness(self) -> MappingReadiness:
        from app.shared.mapping import MappingReadiness

        state = self._state()
        if state is None:
            return MappingReadiness()
        verified = bool(
            state.active_version and state.generation == state.active_generation
        )
        return MappingReadiness(
            state.active_version if verified else None, state.generation, verified
        )

    def get_alias(
        self, alias_id: uuid.UUID, kind: str = "ORGANIZATION"
    ) -> OrganizationAlias | RegionAlias | None:
        model = OrganizationAlias if kind == "ORGANIZATION" else RegionAlias
        return cast(
            OrganizationAlias | RegionAlias | None,
            self._session.get(model, alias_id, populate_existing=True),
        )

    def target_exists(self, target_id: uuid.UUID, kind: str) -> bool:
        from app.models.directory import Hospital, Region

        model = Hospital if kind == "ORGANIZATION" else Region
        return (
            self._session.scalar(
                select(model.id).where(model.id == target_id, model.is_active.is_(True))
            )
            is not None
        )

    def register(
        self, *, kind: str, source_system: str, identity_space: str, source_key: str
    ) -> OrganizationAlias | RegionAlias:
        model = OrganizationAlias if kind == "ORGANIZATION" else RegionAlias
        row = self._session.scalar(
            select(model).where(
                model.source_system == source_system,
                model.identity_space == identity_space,
                model.normalized_value == source_key,
            )
        )
        if row is None:
            row = model(
                source_system=source_system,
                identity_space=identity_space,
                source_value=source_key,
                normalized_value=source_key,
                version=0,
                mapping_status="UNMAPPED",
            )
            self._session.add(row)
            self._session.flush()
        return cast(OrganizationAlias | RegionAlias, row)

    def record_decision(self, *, actor: str, evidence_ref: str) -> str:
        from app.models.mapping import MappingRevision, MappingState
        from app.shared.mapping import ORGANIZATION_SPACES, REGION_SPACES, MappingSnapshot

        state = self._state()
        if state is None:
            state = MappingState(id=1, generation=0)
            self._session.add(state)
        state.generation += 1
        self._session.flush()
        rows = []
        for kind, model, target, spaces in (
            ("ORGANIZATION", OrganizationAlias, "hospital_id", ORGANIZATION_SPACES),
            ("REGION", RegionAlias, "region_id", REGION_SPACES),
        ):
            aliases = self._session.scalars(
                select(model).where(
                    model.mapping_status == "MAPPED",
                    model.mapping_method.in_(["MANUAL_APPROVED", "OFFICIAL_REFERENCE"]),
                    model.identity_space.in_(spaces),
                )
            )
            for raw_alias in aliases:
                alias = cast(OrganizationAlias | RegionAlias, raw_alias)
                if getattr(alias, target) is not None:
                    rows.append(
                        (
                            kind,
                            alias.identity_space,
                            alias.normalized_value,
                            str(getattr(alias, target)),
                        )
                    )
        version = f"mapping-{state.generation}"
        snapshot = MappingSnapshot.from_rows(version, rows)
        self._session.add(
            MappingRevision(
                version=version,
                generation=state.generation,
                digest=snapshot.digest,
                rows=list(snapshot.rows()),
                actor=actor,
                evidence_ref=evidence_ref,
            )
        )
        return version

    def candidate(self, version: str) -> MappingSnapshot:
        from app.core.exceptions import ConflictError
        from app.models.mapping import MappingRevision
        from app.shared.mapping import MappingSnapshot

        row = self._session.get(MappingRevision, version)
        state = self._state()
        if row is None or state is None or row.generation != state.generation:
            raise ConflictError("STALE_MAPPING_CANDIDATE")
        snapshot = MappingSnapshot.from_rows(version, row.rows)
        if snapshot.digest != row.digest:
            raise ConflictError("MAPPING_DIGEST_MISMATCH")
        return snapshot

    def activate(self, version: str) -> None:
        from datetime import UTC, datetime

        from app.models.mapping import MappingRevision

        self.candidate(version)
        state = self._state()
        if state is None:
            raise RuntimeError("Mapping state disappeared under publication lock")
        state.active_version = version
        state.active_generation = state.generation
        revision = self._session.get(MappingRevision, version)
        if revision is None:
            raise RuntimeError("Mapping revision disappeared under publication lock")
        revision.published_at = datetime.now(UTC)
