"""Поиск файлов набора данных в исходном каталоге.

Каталог источника открывается только на чтение. Модуль не создаёт, не
переименовывает, не перемещает и не удаляет в нём ничего; единственные
вызовы файловой системы здесь — перечисление и чтение метаданных.

Набор определяется каталогом из контракта, а не догадкой по содержимому.
Угадывание набора по столбцам однажды загрузит отказы в таблицу
направлений, и заметить это будет некому.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from data_pipeline.common.hashing import sha256_file
from data_pipeline.contracts import DatasetContract


class SourceNotFoundError(Exception):
    """Каталог источника или каталог набора отсутствует."""


@dataclass(frozen=True, slots=True)
class SourceFile:
    dataset_key: str
    path: Path
    relative_path: str
    size_bytes: int

    @property
    def name(self) -> str:
        return self.path.name


@dataclass(frozen=True, slots=True)
class FingerprintedFile:
    source: SourceFile
    sha256: str


def dataset_directory(source_root: Path, contract: DatasetContract) -> Path:
    return source_root / contract.source_directory


def discover(source_root: Path, contract: DatasetContract) -> list[SourceFile]:
    """Файлы набора, отсортированные по имени.

    Порядок детерминирован: части одной выгрузки должны загружаться
    в одном и том же порядке при каждом прогоне, иначе воспроизвести
    результат невозможно.
    """
    root = source_root.expanduser().resolve()
    if not root.is_dir():
        raise SourceNotFoundError(f"Каталог источника не найден: {root}")

    directory = dataset_directory(root, contract)
    if not directory.is_dir():
        raise SourceNotFoundError(f"Каталог набора {contract.key} не найден: {directory}")

    files = [
        SourceFile(
            dataset_key=contract.key,
            path=path,
            relative_path=path.relative_to(root).as_posix(),
            size_bytes=path.stat().st_size,
        )
        for path in sorted(directory.glob(contract.file_glob))
        if path.is_file()
    ]
    return files


def fingerprint(file: SourceFile) -> FingerprintedFile:
    return FingerprintedFile(source=file, sha256=sha256_file(file.path))


def resolve_within(source_root: Path, candidate: Path) -> Path:
    """Проверить, что путь не выходит за пределы каталога источника.

    Защита от обхода каталога. Путь приходит из аргумента командной строки
    или из запроса администратора, и без этой проверки `../../etc/passwd`
    оказался бы допустимым именем файла выгрузки.
    """
    root = source_root.expanduser().resolve()
    target = (
        candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    )
    if root != target and root not in target.parents:
        raise SourceNotFoundError("Путь выходит за пределы каталога источника и отклонён")
    return target
