"""Explicit local command for training the Phase 5A referral forecast."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from app.adapters.forecasting import build_forecast_training_service
from app.core.config import load_settings_or_exit
from app.core.logging import configure_logging


def main(argv: Sequence[str] | None = None) -> int:
    settings = load_settings_or_exit()
    configure_logging(
        level=settings.log_level,
        fmt=settings.log_format,
        service=f"{settings.app_name}-ml",
        environment=settings.app_env.value,
    )
    parser = argparse.ArgumentParser(prog="app.cli.ml")
    parser.add_argument("command", choices=("train-referrals",))
    parser.parse_args(argv)
    forecast_id = build_forecast_training_service().run_referral_forecast()
    print(f"[medsignal] referral forecast persisted: {forecast_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
