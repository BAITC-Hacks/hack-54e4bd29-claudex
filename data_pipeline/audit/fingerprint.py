"""Отпечатки исходных файлов.

SHA-256 считается потоком: файлы измеряются гигабайтами, целиком в память
они не помещаются. Отпечаток нужен дважды — чтобы аудит был воспроизводим
на том же наборе файлов и чтобы будущий DataImport мог отклонить повторную
загрузку той же выгрузки (ADR по идемпотентности импорта).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

CHUNK_SIZE = 8 * 1024 * 1024


@dataclass(slots=True)
class Fingerprint:
    relative_path: str
    size_bytes: int
    sha256: str


def hash_file(path: Path, chunk_size: int = CHUNK_SIZE) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint_files(
    root: Path,
    relative_paths: Iterable[str],
    progress: Callable[[str], None] | None = None,
) -> list[Fingerprint]:
    result: list[Fingerprint] = []
    for relative in relative_paths:
        path = root / relative
        if progress is not None:
            progress(relative)
        result.append(
            Fingerprint(
                relative_path=relative,
                size_bytes=path.stat().st_size,
                sha256=hash_file(path),
            )
        )
    return result


def duplicate_groups(fingerprints: Iterable[Fingerprint]) -> dict[str, list[str]]:
    """Файлы с одинаковым содержимым. Разные имена этому не мешают."""
    by_hash: dict[str, list[str]] = {}
    for item in fingerprints:
        by_hash.setdefault(item.sha256, []).append(item.relative_path)
    return {h: sorted(paths) for h, paths in by_hash.items() if len(paths) > 1}


def to_dict(fingerprints: Iterable[Fingerprint]) -> list[dict[str, object]]:
    return [asdict(f) for f in fingerprints]
