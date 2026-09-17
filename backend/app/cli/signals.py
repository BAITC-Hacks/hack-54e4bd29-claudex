"""Manual Signal Engine evaluation using the production composition root."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from app.business.system.operations import OperationService
from app.composition import build_signal_evaluation_service, get_unit_of_work_factory
from app.core.config import load_settings_or_exit
from app.core.logging import configure_logging
from app.core.request_context import get_request_id


def main(argv: Sequence[str] | None = None) -> int:
    settings = load_settings_or_exit()
    configure_logging(
        level=settings.log_level,
        fmt=settings.log_format,
        service=f"{settings.app_name}-signal-engine",
        environment=settings.app_env.value,
    )
    parser = argparse.ArgumentParser(prog="app.cli.signals")
    parser.add_argument("command", choices=("evaluate",))
    parser.parse_args(argv)

    operations = OperationService(get_unit_of_work_factory())
    operation_id = operations.register(
        operation_type="signals.evaluate", request_id=get_request_id()
    )
    operations.mark_running(operation_id)
    try:
        report = build_signal_evaluation_service().evaluate_all().as_dict()
        operations.mark_completed(operation_id, result=report)
    except Exception:
        operations.mark_failed(operation_id, reason="Signal Engine не завершил оценку")
        raise
    print(
        json.dumps(
            {"operation_id": str(operation_id), "report": report},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
