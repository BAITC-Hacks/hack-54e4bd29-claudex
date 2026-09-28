"""Загрузка канонических записей в ClickHouse.

ClickHouse и PostgreSQL не образуют одной транзакции, поэтому граница
«загружено» и граница «опубликовано» разведены явно:

    пакеты → промежуточная таблица (разбита по import_id)
           → сверка числа строк
           → публикация в таблицу фактов
           → сверка числа строк
           → очистка промежуточной таблицы

Импорт помечается завершённым только после второй сверки. При сбое
на любом шаге вызывающий код обязан вызвать `rollback`: он удаляет
и промежуточные, и опубликованные строки этого импорта. Так частично
загруженные данные не выдают себя за успешную поставку.

Разбиение промежуточной таблицы по import_id выбрано ради этого:
DROP PARTITION удаляет ровно свой импорт мгновенно и не трогает чужие,
тогда как DELETE был бы отложенной мутацией.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Protocol

import polars as pl

DEFAULT_BATCH_SIZE = 50_000

# Имя таблицы приходит из контракта набора, а не из запроса пользователя,
# но подстановка имени в текст запроса всё равно проверяется: параметром
# идентификатор передать нельзя, и единственная защита — убедиться, что
# это действительно идентификатор. Значения при этом всегда идут
# параметрами, а не склейкой.
TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


class UnsafeTableNameError(Exception):
    """Имя таблицы не является простым идентификатором."""


def _checked_table(name: str) -> str:
    if not TABLE_NAME.match(name):
        raise UnsafeTableNameError(f"Недопустимое имя таблицы: {name!r}")
    return name


class ClickHouseClient(Protocol):
    """То, что писателю нужно от клиента ClickHouse."""

    def command(self, cmd: str, parameters: Any = None) -> Any: ...

    def query(self, query: str, parameters: Any = None) -> Any: ...

    def insert(
        self,
        table: str,
        data: Sequence[Sequence[Any]],
        column_names: str | Iterable[str],
    ) -> Any: ...


@dataclass(frozen=True, slots=True)
class LoadResult:
    staged_rows: int
    published_rows: int


class RowCountMismatchError(Exception):
    """Число строк после шага не совпало с ожидаемым.

    Расхождение означает потерю или задвоение данных. Импорт в таком
    состоянии завершённым не признаётся.
    """


class ClickHouseLoader:
    """Загрузчик одного импорта в одну пару таблиц."""

    def __init__(
        self,
        client: ClickHouseClient,
        *,
        target_table: str,
        staging_table: str,
        import_id: uuid.UUID,
    ) -> None:
        self._client = client
        self._target = _checked_table(target_table)
        self._staging = _checked_table(staging_table)
        self._import_id = import_id
        self._staged = 0

    # ------------------------------------------------------------------
    # Запись
    # ------------------------------------------------------------------

    def stage(self, frame: pl.DataFrame) -> int:
        """Записать пакет в промежуточную таблицу."""
        if frame.height == 0:
            return 0
        self._client.insert(
            self._staging,
            frame.rows(),
            column_names=list(frame.columns),
        )
        self._staged += frame.height
        return frame.height

    def staged_row_count(self) -> int:
        return self._count(self._staging)

    def published_row_count(self) -> int:
        return self._count(self._target)

    def _count(self, table: str) -> int:
        result = self._client.query(
            # Имя таблицы проверено при создании загрузчика; значение
            # идентификатора импорта передаётся параметром.
            f"SELECT count() FROM {table} WHERE import_id = {{import_id:UUID}}",  # noqa: S608
            parameters={"import_id": str(self._import_id)},
        )
        return int(result.result_rows[0][0])

    # ------------------------------------------------------------------
    # Публикация
    # ------------------------------------------------------------------

    def verify_staged(self, expected: int) -> None:
        actual = self.staged_row_count()
        if actual != expected:
            raise RowCountMismatchError(
                f"В промежуточной таблице {self._staging} строк {actual}, "
                f"ожидалось {expected}"
            )

    def publish(self) -> LoadResult:
        """Перенести строки импорта из промежуточной таблицы в фактовую."""
        staged = self.staged_row_count()
        self._client.command(
            f"INSERT INTO {self._target} SELECT * FROM {self._staging} "  # noqa: S608
            "WHERE import_id = {import_id:UUID}",
            parameters={"import_id": str(self._import_id)},
        )
        published = self.published_row_count()
        if published != staged:
            raise RowCountMismatchError(
                f"В таблице {self._target} строк {published}, "
                f"в промежуточной {staged}"
            )
        return LoadResult(staged_rows=staged, published_rows=published)

    def drop_staging(self) -> None:
        """Убрать промежуточные строки импорта."""
        self._client.command(
            f"ALTER TABLE {self._staging} DROP PARTITION {{import_id:String}}",
            parameters={"import_id": str(self._import_id)},
        )

    def rollback(self) -> None:
        """Удалить всё, что импорт успел записать.

        Вызывается при сбое. Промежуточная часть удаляется мгновенно
        сбросом раздела; опубликованная — мутацией, потому что раздел
        фактовой таблицы содержит данные и других импортов.
        """
        self.drop_staging()
        self._client.command(
            f"ALTER TABLE {self._target} DELETE WHERE import_id = {{import_id:UUID}}",
            parameters={"import_id": str(self._import_id)},
        )


def batched(
    frame: pl.DataFrame, size: int = DEFAULT_BATCH_SIZE
) -> Iterator[pl.DataFrame]:
    """Разбить пакет на части заданного размера."""
    for offset in range(0, frame.height, size):
        yield frame.slice(offset, size)


class NullLoader:
    """Загрузчик, который ничего не пишет.

    Используется при холостом прогоне: проверить разбор, правила и
    псевдонимизацию нужно, а трогать аналитическое хранилище — нет.
    """

    def __init__(self) -> None:
        self._staged = 0

    def stage(self, frame: pl.DataFrame) -> int:
        self._staged += frame.height
        return frame.height

    def staged_row_count(self) -> int:
        return self._staged

    def published_row_count(self) -> int:
        return 0

    def verify_staged(self, expected: int) -> None:
        if self._staged != expected:  # pragma: no cover — счётчик локальный
            raise RowCountMismatchError("Расхождение счётчика холостого прогона")

    def publish(self) -> LoadResult:
        return LoadResult(staged_rows=self._staged, published_rows=0)

    def drop_staging(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def __enter__(self) -> NullLoader:  # pragma: no cover
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:  # pragma: no cover
        return None
