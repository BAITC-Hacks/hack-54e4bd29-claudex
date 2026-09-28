"""Применение версионированных схем ClickHouse.

Alembic для ClickHouse не используется: он рассчитан на транзакционный
DDL, которого здесь нет. Вместо этого — пронумерованные файлы и таблица
применённых версий, то есть тот же принцип в минимальном виде.

Удаляющих команд не выполняется. Файл, содержащий DROP или TRUNCATE,
отклоняется до отправки в базу: потеря аналитических данных должна быть
осознанным действием человека, а не следствием запуска миграции.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

MIGRATIONS_TABLE = "schema_migrations"

NEWLINE = chr(10)

# Команды, которые миграция выполнять не вправе. Проверка текстовая
# и потому грубая, но её задача — не пропустить очевидно разрушительное,
# а не разобрать SQL.
FORBIDDEN_STATEMENTS = re.compile(
    r"\b(DROP\s+(TABLE|DATABASE|VIEW)|TRUNCATE|DELETE\s+FROM)\b", re.IGNORECASE
)

# Комментарии вырезаются до проверки: слово DROP в объяснении, почему
# его здесь нет, не должно ломать миграцию.
_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


class DestructiveMigrationError(Exception):
    """Миграция содержит удаляющую команду."""


class ClickHouseCommandClient(Protocol):
    def command(self, cmd: str, parameters: Any = None) -> Any: ...

    def query(self, query: str, parameters: Any = None) -> Any: ...


@dataclass(frozen=True, slots=True)
class Migration:
    version: str
    name: str
    path: Path
    sql: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class MigrationOutcome:
    version: str
    name: str
    applied: bool
    statements: int


def _scan(sql: str) -> tuple[str, list[str]]:
    """Один проход по тексту: убрать комментарии и разделить команды.

    Разбор посимвольный, а не регулярным выражением, по конкретной
    причине: строковый литерал может содержать и точку с запятой, и два
    дефиса. Например, COMMENT 'псевдоним; исходный код не хранится'.
    Наивное разбиение по точке с запятой рвёт такую команду пополам,
    и ошибка обнаруживается только на живой базе.

    Возвращается пара «текст без комментариев, список команд».
    """
    cleaned: list[str] = []
    statements: list[str] = []
    current: list[str] = []

    index = 0
    length = len(sql)
    in_string = False

    while index < length:
        char = sql[index]
        pair = sql[index : index + 2]

        if in_string:
            current.append(char)
            cleaned.append(char)
            # Удвоенная кавычка внутри литерала — это экранированная
            # кавычка, а не его конец.
            if char == "'" and sql[index + 1 : index + 2] == "'":
                current.append("'")
                cleaned.append("'")
                index += 2
                continue
            if char == "'":
                in_string = False
            index += 1
            continue

        if pair == "--":
            end = sql.find(NEWLINE, index)
            index = length if end == -1 else end
            continue

        if pair == "/*":
            end = sql.find("*/", index + 2)
            index = length if end == -1 else end + 2
            continue

        if char == "'":
            in_string = True
            current.append(char)
            cleaned.append(char)
            index += 1
            continue

        if char == ";":
            statements.append("".join(current).strip())
            current = []
            cleaned.append(char)
            index += 1
            continue

        current.append(char)
        cleaned.append(char)
        index += 1

    statements.append("".join(current).strip())
    return "".join(cleaned), [item for item in statements if item]


def _strip_comments(sql: str) -> str:
    return _scan(sql)[0]


def split_statements(sql: str) -> list[str]:
    """Разбить файл на команды, не разрывая строковые литералы."""
    return _scan(sql)[1]


def load_migrations(directory: Path) -> list[Migration]:
    """Прочитать миграции в порядке версий.

    Версией служит полное имя файла без расширения, а не числовой
    префикс. Префикс задаёт лишь порядок; полное имя делает запись
    в таблице версий однозначной и не сталкивается с записями,
    оставленными более ранними скриптами инициализации.
    """
    migrations: list[Migration] = []
    for path in sorted(directory.glob("*.sql")):
        version = path.stem
        _, _, name = path.stem.partition("_")
        sql = path.read_text(encoding="utf-8")
        if FORBIDDEN_STATEMENTS.search(_strip_comments(sql)):
            raise DestructiveMigrationError(
                f"Миграция {path.name} содержит удаляющую команду. "
                "Удаление аналитических данных выполняется человеком, "
                "а не запуском миграций"
            )
        migrations.append(
            Migration(version=version, name=name or path.stem, path=path, sql=sql)
        )
    return migrations


def ensure_migrations_table(client: ClickHouseCommandClient) -> None:
    """Создать таблицу версий или дополнить существующую.

    Таблица могла быть создана скриптом инициализации более ранней фазы
    без столбцов имени и контрольной суммы. Она дополняется, а не
    пересоздаётся: уже записанные версии должны сохраниться, иначе
    применённые схемы будут применены повторно.
    """
    client.command(
        f"""
        CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE}
        (
            version   String,
            name      String,
            checksum  String,
            applied_at DateTime DEFAULT now()
        )
        ENGINE = MergeTree
        ORDER BY version
        """
    )
    for column in ("name String DEFAULT ''", "checksum String DEFAULT ''"):
        client.command(
            f"ALTER TABLE {MIGRATIONS_TABLE} ADD COLUMN IF NOT EXISTS {column}"
        )


def applied_versions(client: ClickHouseCommandClient) -> dict[str, str]:
    # MIGRATIONS_TABLE — константа модуля, а не значение извне.
    result = client.query(f"SELECT version, checksum FROM {MIGRATIONS_TABLE}")  # noqa: S608
    return {row[0]: row[1] for row in result.result_rows}


def apply(
    client: ClickHouseCommandClient,
    directory: Path,
) -> Iterator[MigrationOutcome]:
    """Применить непримененные миграции по порядку."""
    ensure_migrations_table(client)
    known = applied_versions(client)

    for migration in load_migrations(directory):
        if migration.version in known:
            # Пустая контрольная сумма означает запись, оставленную до
            # того, как сумма начала сохраняться. Такую запись
            # перепроверить нечем, и она принимается как есть.
            if known[migration.version] not in ("", migration.checksum):
                raise DestructiveMigrationError(
                    f"Миграция {migration.version} изменена после применения. "
                    "Принятую миграцию правят новой, а не на месте"
                )
            yield MigrationOutcome(
                version=migration.version,
                name=migration.name,
                applied=False,
                statements=0,
            )
            continue

        statements = split_statements(migration.sql)
        for statement in statements:
            client.command(statement)

        client.command(
            f"INSERT INTO {MIGRATIONS_TABLE} (version, name, checksum) "  # noqa: S608
            "VALUES ({version:String}, {name:String}, {checksum:String})",
            parameters={
                "version": migration.version,
                "name": migration.name,
                "checksum": migration.checksum,
            },
        )
        yield MigrationOutcome(
            version=migration.version,
            name=migration.name,
            applied=True,
            statements=len(statements),
        )


def apply_all(
    client: ClickHouseCommandClient, directory: Path
) -> Sequence[MigrationOutcome]:
    return list(apply(client, directory))
