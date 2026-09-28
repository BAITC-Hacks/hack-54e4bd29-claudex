"""Точка входа Data Audit.

Запуск:
    python -m data_pipeline.audit.cli --source <каталог> --output ./data/audit

Каталог источника открывается только на чтение. Все результаты пишутся
в каталог вывода и в docs/data. Путь к данным нигде не зашит в код:
аудит должен запускаться на другой машине и на другой выгрузке.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from data_pipeline.audit import AUDIT_VERSION, report
from data_pipeline.audit.excel_profiler import WorkbookProfile, profile_workbook
from data_pipeline.audit.fingerprint import (
    duplicate_groups,
    fingerprint_files,
)
from data_pipeline.audit.fingerprint import (
    to_dict as fingerprints_to_dict,
)
from data_pipeline.audit.inventory import PART_PATTERN, Inventory, build_inventory
from data_pipeline.audit.joinability import (
    JoinRole,
    assess,
    build_matrix,
    collect_key_values,
    detect_roles,
)
from data_pipeline.audit.privacy import classify
from data_pipeline.audit.profiler import TableProfile, profile_table
from data_pipeline.audit.quality import check_table
from data_pipeline.audit.sources import classify_dataset
from data_pipeline.audit.target_analysis import (
    TableEvidence,
    assess_candidates,
    recommend,
)
from data_pipeline.audit.temporal import LOAD_TIMESTAMP_COLUMNS, analyze_table

# Столбцы, по которым проверяется уникальность ключа.
KEY_COLUMN_HINTS = ("id", "hospitalization_code")


def _log(message: str) -> None:
    print(f"[audit] {message}", file=sys.stderr, flush=True)


def _table_name(file_name: str) -> str:
    """Имя логической таблицы, общее для всех частей одной выгрузки."""
    stem = Path(file_name).stem.strip()
    stem = stem.split(" (")[0]
    match = PART_PATTERN.match(stem)
    return match.group("stem") if match else stem


def _group_tables(inventory: Inventory, root: Path) -> dict[tuple[str, str], list[Path]]:
    grouped: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for entry in inventory.files:
        if entry.kind != "tabular":
            continue
        grouped[(entry.dataset, _table_name(entry.file_name))].append(
            root / entry.relative_path
        )
    return {key: sorted(paths) for key, paths in sorted(grouped.items())}


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    _log(f"записано: {path}")


def _write_inventory_csv(path: Path, inventory: Inventory) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "relative_path",
                "dataset",
                "file_name",
                "extension",
                "kind",
                "size_bytes",
                "part_index",
                "part_total",
            ]
        )
        for entry in inventory.files:
            writer.writerow(
                [
                    entry.relative_path,
                    entry.dataset,
                    entry.file_name,
                    entry.extension,
                    entry.kind,
                    entry.size_bytes,
                    entry.part_index or "",
                    entry.part_total or "",
                ]
            )
    _log(f"записано: {path}")


def _months_covered(temporal_result: object) -> int:
    """Глубина истории по основной оси времени таблицы.

    Считать по максимуму среди всех столбцов с датой нельзя. Плановая дата
    госпитализации уходит на год вперёд от даты регистрации, и такой
    максимум показал бы историю, которой в данных нет.
    """
    primary = getattr(temporal_result, "primary_date_column", None)
    for column in getattr(temporal_result, "columns", []):
        if column.column_name == primary and column.column_name not in (
            LOAD_TIMESTAMP_COLUMNS
        ):
            return column.distinct_months or 0
    return 0


def _granularity(temporal_result: object) -> str:
    primary = getattr(temporal_result, "primary_date_column", None)
    for column in getattr(temporal_result, "columns", []):
        if column.column_name == primary:
            return column.granularity
    return "unknown"


def run(source: Path, output: Path, docs: Path, skip_fingerprints: bool) -> int:
    started = time.monotonic()
    root = source.expanduser().resolve()

    _log(f"источник: {root} (только чтение)")
    inventory = build_inventory(root)
    _log(
        f"файлов: {inventory.total_files}, "
        f"объём: {inventory.total_size_bytes / 1e9:.2f} ГБ"
    )

    _write_json(output / "inventory.json", inventory.to_dict())
    _write_inventory_csv(output / "inventory.csv", inventory)

    # --- Отпечатки ----------------------------------------------------------
    fingerprints = []
    duplicates: dict[str, list[str]] = {}
    if skip_fingerprints:
        _log("отпечатки пропущены по флагу --skip-fingerprints")
    else:
        _log("подсчёт SHA-256 (потоком)")
        fingerprints = fingerprint_files(
            root,
            [f.relative_path for f in inventory.files],
            progress=lambda p: _log(f"  hash: {p}"),
        )
        duplicates = duplicate_groups(fingerprints)
        _write_json(
            output / "file_fingerprints.json",
            {
                "audit_version": AUDIT_VERSION,
                "source_root": str(root),
                "files": fingerprints_to_dict(fingerprints),
                "identical_content_groups": duplicates,
            },
        )

    # --- Профилирование таблиц ---------------------------------------------
    tables = _group_tables(inventory, root)
    profiles: list[TableProfile] = []
    temporal_results = []
    quality_results = []

    for (dataset, table), paths in tables.items():
        size = sum(p.stat().st_size for p in paths)
        _log(f"профилирование {dataset} / {table} ({size / 1e6:.0f} МБ)")
        profile = profile_table(dataset, table, paths, size, progress=_log)
        profiles.append(profile)

        date_columns = {
            c.column_name: c.datetime_format
            for c in profile.columns
            if c.inferred_type in {"datetime", "date"} and c.datetime_format
        }
        _log(f"  временное покрытие: {len(date_columns)} столбц(ев) с датой")
        temporal_results.append(analyze_table(dataset, table, paths, date_columns))

        keys = [
            c.column_name
            for c in profile.columns
            if c.column_name.lower() in KEY_COLUMN_HINTS
        ]
        _log("  проверки качества")
        quality_results.append(check_table(profile, paths, keys))

    # --- Excel --------------------------------------------------------------
    workbooks: list[WorkbookProfile] = []
    for entry in inventory.files:
        if entry.kind != "excel":
            continue
        _log(f"разбор книги {entry.relative_path}")
        workbooks.append(profile_workbook(entry.dataset, root / entry.relative_path))

    # --- Источники и приватность -------------------------------------------
    descriptions = {d.name: d.description for d in inventory.datasets}
    columns_by_dataset: dict[str, list[str]] = defaultdict(list)
    for profile in profiles:
        columns_by_dataset[profile.dataset].extend(c.column_name for c in profile.columns)
    for book in workbooks:
        for sheet in book.sheets:
            columns_by_dataset[book.dataset].extend(sheet.headers)

    classifications = [
        classify_dataset(name, tuple(dict.fromkeys(columns)), descriptions.get(name))
        for name, columns in sorted(columns_by_dataset.items())
    ]

    privacy_rows = []
    for profile in profiles:
        for column in profile.columns:
            item = classify(
                column.column_name,
                non_null_count=profile.row_count - column.null_count,
                unique_count=column.unique_count,
                unique_is_approximate=column.unique_is_approximate,
            )
            privacy_rows.append(
                {"dataset": profile.dataset, "table": profile.table, **item.to_dict()}
            )

    # Книги Excel обязаны проходить ту же классификацию. Пропустить их
    # значит объявить выгрузку свободной от персональных данных только
    # потому, что она хранится в другом формате.
    for book in workbooks:
        for sheet in book.sheets:
            for header in sheet.headers:
                if not header:
                    continue
                item = classify(header)
                privacy_rows.append(
                    {
                        "dataset": book.dataset,
                        "table": f"{book.file} / {sheet.sheet_name}",
                        **item.to_dict(),
                    }
                )

    # --- Связуемость --------------------------------------------------------
    _log("проверка связуемости выгрузок")
    key_values = []
    for profile in profiles:
        roles = detect_roles([c.column_name for c in profile.columns])
        paths = tables[(profile.dataset, profile.table)]
        for role, names in roles.items():
            if role is JoinRole.DATE:
                continue
            for name in names:
                _log(f"  ключи {profile.dataset}.{name} ({role.value})")
                key_values.append(collect_key_values(profile.dataset, paths, name, role))

    assessments = []
    for index, left in enumerate(key_values):
        for right in key_values[index + 1 :]:
            if left.dataset == right.dataset or left.role != right.role:
                continue
            assessments.append(assess(left, right))

    matrix = build_matrix(assessments)

    # --- Цели ---------------------------------------------------------------
    evidence: list[TableEvidence] = []
    for profile, temporal_result in zip(profiles, temporal_results, strict=True):
        evidence.append(
            TableEvidence(
                dataset=profile.dataset,
                table=profile.table,
                columns=tuple(c.column_name for c in profile.columns),
                row_count=profile.row_count,
                months_covered=_months_covered(temporal_result),
                granularity=_granularity(temporal_result),
                time_series_possible=temporal_result.time_series_possible,
            )
        )

    candidates = assess_candidates(evidence)
    recommended, recommendation_reason = recommend(candidates)

    # --- Артефакты ----------------------------------------------------------
    _write_json(
        output / "schema_catalog.json",
        {
            "audit_version": AUDIT_VERSION,
            "tables": [p.to_dict() for p in profiles],
            "workbooks": [w.to_dict() for w in workbooks],
        },
    )
    _write_json(
        output / "quality_summary.json",
        {
            "audit_version": AUDIT_VERSION,
            "tables": [q.to_dict() for q in quality_results],
        },
    )
    _write_json(
        output / "temporal_coverage.json",
        {
            "audit_version": AUDIT_VERSION,
            "tables": [t.to_dict() for t in temporal_results],
        },
    )
    _write_json(
        output / "joinability.json",
        {
            "audit_version": AUDIT_VERSION,
            "matrix": matrix,
            "assessments": [a.to_dict() for a in assessments],
        },
    )
    _write_json(
        output / "privacy_audit.json",
        {"audit_version": AUDIT_VERSION, "columns": privacy_rows},
    )

    context = report.AuditContext(
        audit_version=AUDIT_VERSION,
        source_root=str(root),
        inventory=inventory,
        profiles=profiles,
        workbooks=workbooks,
        temporal=temporal_results,
        quality=quality_results,
        privacy=privacy_rows,
        classifications=classifications,
        key_values=key_values,
        join_assessments=assessments,
        join_matrix=matrix,
        candidates=candidates,
        recommended_target=recommended,
        recommendation_reason=recommendation_reason,
        duplicate_content_groups=duplicates,
        elapsed_seconds=round(time.monotonic() - started, 1),
    )

    _write_json(output / "medsignal_audit_summary.json", report.build_summary(context))
    report.write_documents(context, docs)

    _log(f"готово за {context.elapsed_seconds:.0f} с")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="data_pipeline.audit.cli",
        description="Разведочный аудит исходных выгрузок MedSignal (только чтение)",
    )
    parser.add_argument(
        "--source",
        required=True,
        type=Path,
        help="каталог с исходными выгрузками; открывается только на чтение",
    )
    parser.add_argument(
        "--output",
        default=Path("data/audit"),
        type=Path,
        help="каталог для машиночитаемых результатов",
    )
    parser.add_argument(
        "--docs",
        default=Path("docs/data"),
        type=Path,
        help="каталог для отчётов в Markdown",
    )
    parser.add_argument(
        "--skip-fingerprints",
        action="store_true",
        help="не считать SHA-256 (ускоряет повторный прогон)",
    )
    args = parser.parse_args(argv)

    return run(args.source, args.output, args.docs, args.skip_fingerprints)


if __name__ == "__main__":
    raise SystemExit(main())
