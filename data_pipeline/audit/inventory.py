"""Обход исходного каталога и построение описи файлов.

Опись строится до любого разбора содержимого. Сначала нужно знать, что
вообще лежит в источнике и какого объёма, и только потом решать, какой
файл можно прочитать целиком, а какой — только потоком.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Расширения, которые аудит разбирает своими силами.
TABULAR_EXTENSIONS = frozenset({".csv", ".tsv", ".parquet", ".json", ".jsonl", ".ndjson"})
EXCEL_EXTENSIONS = frozenset({".xlsx", ".xlsm", ".xls"})
TEXT_EXTENSIONS = frozenset({".txt", ".md", ".sql"})
# Архивы фиксируются, но не распаковываются автоматически: распаковка
# внутри источника изменила бы источник.
ARCHIVE_EXTENSIONS = frozenset({".zip", ".7z", ".rar", ".gz", ".tar", ".bz2", ".xz"})

# Имя вида «<dataset>_part_003_of_105.csv». Части одной выгрузки должны
# профилироваться как одна таблица, иначе строки будут посчитаны отдельно.
PART_PATTERN = re.compile(r"^(?P<stem>.+?)_part_(?P<index>\d+)_of_(?P<total>\d+)$")
# Браузер добавляет «(1)» к повторно скачанному файлу. Такой файл может
# оказаться как дубликатом, так и единственной копией части.
BROWSER_COPY_PATTERN = re.compile(r"\s\((?P<copy>\d+)\)$")


def classify_extension(suffix: str) -> str:
    lowered = suffix.lower()
    if lowered in TABULAR_EXTENSIONS:
        return "tabular"
    if lowered in EXCEL_EXTENSIONS:
        return "excel"
    if lowered in TEXT_EXTENSIONS:
        return "text"
    if lowered in ARCHIVE_EXTENSIONS:
        return "archive"
    return "unknown"


@dataclass(slots=True)
class FileEntry:
    """Один файл источника. Содержимое здесь ещё не читалось."""

    relative_path: str
    dataset: str
    file_name: str
    extension: str
    kind: str
    size_bytes: int
    part_index: int | None = None
    part_total: int | None = None
    browser_copy_suffix: bool = False


@dataclass(slots=True)
class DatasetEntry:
    """Каталог источника, принимаемый за одну выгрузку."""

    name: str
    file_count: int
    size_bytes: int
    kinds: dict[str, int]
    description: str | None = None
    tabular_files: list[str] = field(default_factory=list)
    excel_files: list[str] = field(default_factory=list)
    other_files: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Inventory:
    source_root: str
    total_files: int
    total_size_bytes: int
    extensions: dict[str, int]
    files: list[FileEntry]
    datasets: list[DatasetEntry]

    def to_dict(self) -> dict[str, object]:
        return {
            "source_root": self.source_root,
            "total_files": self.total_files,
            "total_size_bytes": self.total_size_bytes,
            "extensions": self.extensions,
            "datasets": [asdict(d) for d in self.datasets],
            "files": [asdict(f) for f in self.files],
        }


def _read_description(directory: Path) -> str | None:
    """desc.txt рядом с выгрузкой — описание от поставщика данных."""
    candidate = directory / "desc.txt"
    if not candidate.is_file():
        return None
    try:
        return candidate.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None


def _dataset_notes(files: list[FileEntry]) -> list[str]:
    """Замечания о комплектности выгрузки, видимые уже по именам файлов."""
    notes: list[str] = []
    by_stem: dict[str, list[FileEntry]] = defaultdict(list)
    for entry in files:
        if entry.part_total is not None:
            match = PART_PATTERN.match(Path(entry.file_name).stem.strip())
            key = match.group("stem") if match else entry.file_name
            by_stem[key].append(entry)

    for stem, parts in by_stem.items():
        declared = parts[0].part_total or 0
        # part_index заполнен у каждой части: она попала сюда только потому,
        # что имя файла разобралось шаблоном. Отбор нужен ради проверки типов.
        present = {p.part_index for p in parts if p.part_index is not None}
        missing = sorted(set(range(1, declared + 1)) - present)
        if missing:
            notes.append(
                f"{stem}: объявлено частей {declared}, отсутствуют номера "
                f"{', '.join(str(m) for m in missing)}"
            )
        duplicated = [
            i for i in present if sum(1 for p in parts if p.part_index == i) > 1
        ]
        if duplicated:
            notes.append(
                f"{stem}: номера частей встречаются более одного раза: "
                f"{', '.join(str(d) for d in sorted(duplicated))}"
            )

    renamed = [f.file_name for f in files if f.browser_copy_suffix]
    if renamed:
        notes.append(
            "Имена содержат суффикс копии браузера «(N)»: "
            + ", ".join(sorted(renamed))
            + ". Это след повторной загрузки, а не признак другого содержимого."
        )
    return notes


def _build_file_entry(path: Path, root: Path) -> FileEntry:
    relative = path.relative_to(root).as_posix()
    dataset = relative.split("/")[0] if "/" in relative else "."
    stem = path.stem.strip()

    browser_copy = False
    copy_match = BROWSER_COPY_PATTERN.search(stem)
    if copy_match:
        browser_copy = True
        stem = stem[: copy_match.start()]

    part_index: int | None = None
    part_total: int | None = None
    part_match = PART_PATTERN.match(stem)
    if part_match:
        part_index = int(part_match.group("index"))
        part_total = int(part_match.group("total"))

    return FileEntry(
        relative_path=relative,
        dataset=dataset,
        file_name=path.name,
        extension=path.suffix.lower(),
        kind=classify_extension(path.suffix),
        size_bytes=path.stat().st_size,
        part_index=part_index,
        part_total=part_total,
        browser_copy_suffix=browser_copy,
    )


def build_inventory(source_root: Path) -> Inventory:
    """Обойти источник и описать каждый файл. Источник только читается."""
    root = source_root.resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Источник не является каталогом: {root}")

    files: list[FileEntry] = []
    for current, _dirs, names in os.walk(root):
        for name in sorted(names):
            path = Path(current) / name
            if not path.is_file():
                continue
            files.append(_build_file_entry(path, root))

    files.sort(key=lambda f: f.relative_path)

    extensions: dict[str, int] = defaultdict(int)
    for entry in files:
        extensions[entry.extension or "<нет расширения>"] += 1

    grouped: dict[str, list[FileEntry]] = defaultdict(list)
    for entry in files:
        grouped[entry.dataset].append(entry)

    datasets: list[DatasetEntry] = []
    for name, entries in sorted(grouped.items()):
        kinds: dict[str, int] = defaultdict(int)
        for entry in entries:
            kinds[entry.kind] += 1
        datasets.append(
            DatasetEntry(
                name=name,
                file_count=len(entries),
                size_bytes=sum(e.size_bytes for e in entries),
                kinds=dict(sorted(kinds.items())),
                description=_read_description(root / name),
                tabular_files=[e.relative_path for e in entries if e.kind == "tabular"],
                excel_files=[e.relative_path for e in entries if e.kind == "excel"],
                other_files=[
                    e.relative_path for e in entries if e.kind not in {"tabular", "excel"}
                ],
                notes=_dataset_notes(entries),
            )
        )

    return Inventory(
        source_root=str(root),
        total_files=len(files),
        total_size_bytes=sum(f.size_bytes for f in files),
        extensions=dict(sorted(extensions.items())),
        files=files,
        datasets=datasets,
    )
