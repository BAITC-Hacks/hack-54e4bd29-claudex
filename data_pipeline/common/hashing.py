"""Потоковое вычисление SHA-256.

Один файл может занимать сотни мегабайт, поэтому содержимое читается
кусками, а не целиком. Отпечаток служит ключом идемпотентности импорта:
переименованный файл — тот же файл, а файл с тем же именем и другим
содержимым — другой файл.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

CHUNK_SIZE = 8 * 1024 * 1024


def sha256_file(path: Path, chunk_size: int = CHUNK_SIZE) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
