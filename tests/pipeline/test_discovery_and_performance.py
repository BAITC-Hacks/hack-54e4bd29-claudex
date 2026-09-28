"""Поиск файлов, защита каталога источника и потоковая обработка."""

from __future__ import annotations

import gc
import tracemalloc
import uuid
from pathlib import Path

import pytest

from data_pipeline.common.hashing import sha256_file
from data_pipeline.contracts import ALLOWED_DATASETS, get_contract
from data_pipeline.ingestion.discovery import (
    SourceNotFoundError,
    discover,
    fingerprint,
    resolve_within,
)
from data_pipeline.loading.clickhouse_writer import NullLoader
from data_pipeline.loading.quarantine import NullQuarantineWriter
from data_pipeline.pipeline import PipelineConfig, process_file
from tests.pipeline.conftest import dataset_file, referral_row

# --- Разрешающий список -----------------------------------------------------


def test_only_case_datasets_are_allowed() -> None:
    """Вакцинации и онкология в конвейер не входят и войти не могут."""
    assert {"REFERRALS", "WAITING", "REFUSALS", "TREATED"} == ALLOWED_DATASETS


def test_unknown_dataset_is_refused() -> None:
    with pytest.raises(KeyError) as error:
        get_contract("VACCINATIONS")
    assert "разрешающий список" in str(error.value)


def test_vaccination_directory_is_ignored(tmp_path: Path) -> None:
    """Каталог с чужой выгрузкой рядом не превращает её в источник."""
    (tmp_path / "Факты проведённых вакцинаций").mkdir(parents=True)
    (tmp_path / "Факты проведённых вакцинаций" / "part.csv").write_text(
        "id\n1\n", encoding="utf-8"
    )
    contract = get_contract("REFERRALS")
    dataset_file(tmp_path, contract, [referral_row()])

    files = discover(tmp_path, contract)
    assert [f.name for f in files] == [f"{contract.source_directory}.csv"]


# --- Поиск ------------------------------------------------------------------


def test_discovery_is_deterministic(tmp_path: Path) -> None:
    contract = get_contract("REFERRALS")
    for index in (3, 1, 2):
        dataset_file(tmp_path, contract, [referral_row()], name=f"part_{index}.csv")
    names = [f.name for f in discover(tmp_path, contract)]
    assert names == ["part_1.csv", "part_2.csv", "part_3.csv"]


def test_missing_source_is_reported(tmp_path: Path) -> None:
    with pytest.raises(SourceNotFoundError):
        discover(tmp_path / "нет", get_contract("REFERRALS"))


def test_fingerprint_matches_file_content(tmp_path: Path) -> None:
    contract = get_contract("REFERRALS")
    path = dataset_file(tmp_path, contract, [referral_row()])
    file = discover(tmp_path, contract)[0]
    assert fingerprint(file).sha256 == sha256_file(path)


def test_same_name_different_content_gives_different_hash(tmp_path: Path) -> None:
    """Имя файла не является его личностью."""
    contract = get_contract("REFERRALS")
    dataset_file(tmp_path, contract, [referral_row()], name="part.csv")
    first = fingerprint(discover(tmp_path, contract)[0]).sha256

    dataset_file(tmp_path, contract, [referral_row(), referral_row()], name="part.csv")
    second = fingerprint(discover(tmp_path, contract)[0]).sha256

    assert first != second


# --- Защита каталога --------------------------------------------------------


@pytest.mark.parametrize(
    "candidate",
    ["../../../etc/passwd", "../secrets.env", "../../"],
)
def test_path_traversal_is_refused(tmp_path: Path, candidate: str) -> None:
    root = tmp_path / "source"
    root.mkdir()
    with pytest.raises(SourceNotFoundError):
        resolve_within(root, Path(candidate))


def test_path_inside_source_is_allowed(tmp_path: Path) -> None:
    root = tmp_path / "source"
    (root / "Набор").mkdir(parents=True)
    assert resolve_within(root, Path("Набор")).is_relative_to(root.resolve())


def test_processing_does_not_modify_the_source(
    tmp_path: Path, pseudonymizer, import_id: uuid.UUID
) -> None:
    """Главное правило конвейера проверяется, а не декларируется."""
    contract = get_contract("REFERRALS")
    path = dataset_file(tmp_path, contract, [referral_row() for _ in range(20)])
    before = (path.stat().st_size, sha256_file(path))

    process_file(
        path=path,
        file_hash="hash",
        contract=contract,
        import_id=import_id,
        pseudonymizer=pseudonymizer,
        loader=NullLoader(),
        quarantine=NullQuarantineWriter(),
    )

    assert (path.stat().st_size, sha256_file(path)) == before


# --- Потоковая обработка ----------------------------------------------------


def test_memory_does_not_scale_with_file_size(
    tmp_path: Path, pseudonymizer, import_id: uuid.UUID
) -> None:
    """Расход памяти определяется размером пакета, а не размером файла.

    Файл генерируется в тесте и в репозиторий не попадает. Сравниваются
    два прогона: на малом и на большом файле при одном размере пакета.
    Если бы файл читался целиком, пик памяти вырос бы примерно во столько
    же раз, во сколько вырос файл.

    Размер пакета задан заведомо меньше обоих файлов. С размером пакета
    по умолчанию оба файла уместились бы в один пакет, и тест перестал бы
    проверять то, ради чего написан.
    """
    contract = get_contract("REFERRALS")
    config = PipelineConfig(batch_size=1_000)

    def peak_for(rows: int) -> tuple[int, float]:
        directory = tmp_path / f"run_{rows}"
        path = dataset_file(
            directory,
            contract,
            [referral_row(hospitalization_code=f"61.01W9.321.{i}") for i in range(rows)],
        )
        gc.collect()
        tracemalloc.start()
        result = process_file(
            path=path,
            file_hash="hash",
            contract=contract,
            import_id=import_id,
            pseudonymizer=pseudonymizer,
            loader=NullLoader(),
            quarantine=NullQuarantineWriter(),
            config=config,
        )
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert result.rows_read == rows
        return peak, path.stat().st_size

    small_peak, small_size = peak_for(2_000)
    large_peak, large_size = peak_for(40_000)

    size_growth = large_size / small_size
    memory_growth = large_peak / max(small_peak, 1)

    # Файл вырос примерно в двадцать раз. Пик памяти обязан вырасти
    # существенно слабее: порог выбран с запасом, чтобы тест не зависел
    # от шума сборщика мусора, но ловил чтение файла целиком.
    assert size_growth > 10
    assert memory_growth < size_growth / 4


def test_throughput_is_recorded(
    tmp_path: Path, pseudonymizer, import_id: uuid.UUID
) -> None:
    contract = get_contract("REFERRALS")
    path = dataset_file(
        tmp_path,
        contract,
        [referral_row(hospitalization_code=f"61.01W9.321.{i}") for i in range(5_000)],
    )
    result = process_file(
        path=path,
        file_hash="hash",
        contract=contract,
        import_id=import_id,
        pseudonymizer=pseudonymizer,
        loader=NullLoader(),
        quarantine=NullQuarantineWriter(),
    )
    assert result.duration_seconds > 0
    assert result.rows_per_second > 0
