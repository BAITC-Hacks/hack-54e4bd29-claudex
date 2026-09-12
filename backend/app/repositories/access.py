"""Репозиторий пользователей и разрешение области данных.

Область данных берётся из таблицы MedSignal, а не из токена: изменение,
внесённое администратором, должно действовать немедленно (ADR-0009).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.access import User, UserDataScope
from app.models.enums import DataScopeType
from app.security.context import DataScope


class SqlAlchemyUserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: uuid.UUID) -> User | None:
        return self._session.get(User, user_id)

    def get_by_subject(self, external_subject: str) -> User | None:
        statement = select(User).where(User.external_subject == external_subject)
        return self._session.scalars(statement).first()

    def ensure(
        self, *, external_subject: str, display_name: str | None, email: str | None
    ) -> User:
        """Создать проекцию пользователя, если её ещё нет.

        Проекция нужна внешним ключам назначения и авторства. Прав она
        не выдаёт: область данных назначается администратором отдельно,
        и до этого пользователь не видит ничего.
        """
        user = self.get_by_subject(external_subject)
        if user is not None:
            changed = False
            if display_name and user.display_name != display_name:
                user.display_name = display_name
                changed = True
            if email and user.email != email:
                user.email = email
                changed = True
            if changed:
                self._session.flush()
            return user

        user = User(
            external_subject=external_subject,
            display_name=display_name,
            email=email,
        )
        self._session.add(user)
        self._session.flush()
        return user

    def resolve_scope(self, user: User) -> DataScope:
        """Собрать область данных из строк таблицы областей.

        Отсутствие строк означает неразрешённую область, то есть запрет.
        Пустая область и «область не настроена» различаются признаком
        `resolved`, иначе дефект настройки выглядел бы как корректная
        работа системы.
        """
        statement = select(UserDataScope).where(UserDataScope.user_id == user.id)
        rows = list(self._session.scalars(statement).all())

        if any(row.scope_type == DataScopeType.GLOBAL for row in rows):
            return DataScope.global_scope()

        region_ids = frozenset(
            str(row.region_id)
            for row in rows
            if row.scope_type == DataScopeType.REGION and row.region_id is not None
        )
        hospital_ids = frozenset(
            str(row.hospital_id)
            for row in rows
            if row.scope_type == DataScopeType.HOSPITAL and row.hospital_id is not None
        )

        if not rows:
            return DataScope.unresolved()

        return DataScope(
            region_ids=region_ids,
            hospital_ids=hospital_ids,
            is_global=False,
            resolved=True,
        )
