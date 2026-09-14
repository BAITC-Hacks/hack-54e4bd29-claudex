"""Командная строка конвейера загрузки.

Запуск:
    python -m app.cli.data discover  --source <каталог>
    python -m app.cli.data import    --source <каталог> --dataset REFERRALS
    python -m app.cli.data import    --source <каталог> --dataset REFERRALS --dry-run
    python -m app.cli.data recover   --import-id <uuid>

Командная строка — основной способ загрузки в разработке. Это осознанно:
загрузка читает файлы с диска сервера, и открывать такую операцию через
HTTP означало бы дать возможность прочитать произвольный файл. Через API
доступен просмотр импортов, но не запуск импорта из произвольного пути.

Команда работает от имени служебного контекста с правом импорта. Контекст
собирается здесь, а не приходит извне: у процесса командной строки нет
токена, и подделать его нечем.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from collections.abc import Sequence
from pathlib import Path

from data_pipeline.contracts import ALLOWED_DATASETS

from app.adapters.composition import build_import_service
from app.business.ingestion.results import DatasetImportReport
from app.core.config import load_settings_or_exit
from app.core.logging import configure_logging
from app.models.enums import DatasetType
from app.security.context import DataScope, Role, SecurityContext

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_CONFIG = 78


def _operator_context() -> SecurityContext:
    """Служебный контекст оператора загрузки.

    Роль администратора, потому что импорт — операция уровня системы.
    Область данных глобальная: файл содержит записи всех регионов,
    и ограничивать его территорией бессмысленно.
    """
    return SecurityContext(
        user_id="cli:data-import",
        roles=frozenset({Role.ADMIN}),
        scope=DataScope.global_scope(),
        username="data-import",
    )


def _print_report(report: DatasetImportReport) -> None:
    mode = "ХОЛОСТОЙ ПРОГОН" if report.dry_run else "ИМПОРТ"
    print(f"\n{mode}: {report.dataset_type} ({report.source_system})")
    print(
        f"{'файл':<58} {'итог':<18} {'прочитано':>10} "
        f"{'принято':>9} {'отклонено':>10} {'загружено':>10}"
    )
    for file in report.files:
        print(
            f"{file.file_name[:57]:<58} {file.outcome.value:<18} "
            f"{file.rows_read:>10} {file.rows_valid:>9} "
            f"{file.rows_rejected:>10} {file.rows_loaded:>10}"
        )
        if file.error_summary:
            print(f"    причина: {file.error_summary}")

    print(
        f"\nвсего: прочитано {report.rows_read}, принято {report.rows_valid}, "
        f"отклонено {report.rows_rejected}, загружено {report.rows_loaded}, "
        f"предупреждений {report.warnings_count}"
    )
    print(
        f"не сопоставлено: организаций {report.unmapped_organizations}, "
        f"регионов {report.unmapped_regions}, профилей {report.unmapped_profiles}"
    )
    print(f"длительность: {report.duration_seconds} с")
    if report.row_count_drift is not None:
        print(
            f"внимание: число строк расходится с отчётом Data Audit "
            f"на {report.row_count_drift}. Это не ошибка, но поставка "
            "изменилась и это стоит подтвердить у владельца данных"
        )

    findings = [
        finding
        for file in report.files
        for finding in file.findings
        if finding.severity in ("ERROR", "WARNING")
    ]
    if findings:
        print("\nзамечания:")
        for finding in findings:
            column = f" [{finding.column_name}]" if finding.column_name else ""
            print(
                f"  {finding.severity:<8} {finding.rule_code:<38}{column} "
                f"строк {finding.affected_rows}"
            )


def _command_discover(source: Path) -> int:
    service = build_import_service(source)
    context = _operator_context()
    print(f"Каталог источника: {source} (только чтение)")
    for dataset in sorted(ALLOWED_DATASETS):
        try:
            files = service.discover(context, DatasetType(dataset))
        except Exception as error:  # отсутствие каталога набора не фатально
            print(f"{dataset:<12} — {error}")
            continue
        total = sum(f.size_bytes for f in files)
        print(f"{dataset:<12} файлов {len(files):>3}, объём {total / 1e6:>10.1f} МБ")
        for file in files:
            print(f"    {file.name}")
    return EXIT_OK


def _command_import(source: Path, datasets: list[str], dry_run: bool) -> int:
    service = build_import_service(source)
    context = _operator_context()
    failed = False

    for name in datasets:
        report = service.import_dataset(context, DatasetType(name), dry_run=dry_run)
        _print_report(report)
        if report.failed:
            failed = True

    return EXIT_FAILED if failed else EXIT_OK


def _command_recover(source: Path, import_id: uuid.UUID) -> int:
    service = build_import_service(source)
    service.recover(_operator_context(), import_id)
    print(f"Импорт {import_id} отменён, аналитические данные удалены")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="app.cli.data",
        description="Загрузка выгрузок MedSignal. Источник только читается",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="каталог с выгрузками; по умолчанию DATA_SOURCE_DIR",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("discover", help="показать найденные файлы наборов")

    importer = commands.add_parser("import", help="загрузить наборы")
    importer.add_argument(
        "--dataset",
        action="append",
        choices=sorted(ALLOWED_DATASETS),
        help="набор данных; можно указать несколько раз",
    )
    importer.add_argument(
        "--all-core",
        action="store_true",
        help="все наборы MedSignal Case 1",
    )
    importer.add_argument(
        "--dry-run",
        action="store_true",
        help="проверить файлы, не записывая в хранилище",
    )

    recovery = commands.add_parser("recover", help="отменить незавершённый импорт")
    recovery.add_argument("--import-id", required=True, type=uuid.UUID)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    settings = load_settings_or_exit()
    configure_logging(
        level=settings.log_level,
        fmt=settings.log_format,
        service=settings.app_name,
        environment=settings.app_env.value,
    )

    args = build_parser().parse_args(argv)
    source = args.source or Path(settings.data_source_dir)

    if not source.is_dir():
        print(f"[medsignal] Каталог источника не найден: {source}", file=sys.stderr)
        return EXIT_CONFIG

    if args.command == "discover":
        return _command_discover(source)

    if args.command == "recover":
        return _command_recover(source, args.import_id)

    datasets = sorted(ALLOWED_DATASETS) if args.all_core else (args.dataset or [])
    if not datasets:
        print(
            "[medsignal] Укажите --dataset или --all-core. "
            "Загрузка всего каталога подряд не предусмотрена намеренно",
            file=sys.stderr,
        )
        return EXIT_CONFIG

    return _command_import(source, datasets, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
