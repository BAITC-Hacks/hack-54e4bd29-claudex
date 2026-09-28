"""Extend an isolated synthetic referral delivery with enough days for validation.

Never accepts a real-data directory. Generated CSV and manifest are written only
under an explicitly selected, disposable phase8 acceptance project.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from datetime import date, timedelta
from pathlib import Path

from data_pipeline.contracts import get_contract
from scripts.acceptance.synthetic_dataset import _row

FIRST_DAY = date(2025, 1, 3)
LAST_DAY = date(2025, 3, 31)
SEED = 20250927
MANIFEST_NAME = "manifest-REFERRALS-forecast-demo.json"
FILE_NAME = "synthetic-forecast-referrals.csv"


def generate(root: Path) -> tuple[Path, Path]:
    """Write a fixed-seed, contract-exact DELTA without modifying prior files."""
    contract = get_contract("REFERRALS")
    directory = root / contract.source_directory
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / FILE_NAME
    manifest_path = root / MANIFEST_NAME
    if source.exists() or manifest_path.exists():
        raise FileExistsError("Synthetic forecast fixture already exists")
    rng = random.Random(SEED)  # noqa: S311 - invented demo counts, never security material
    row_number = 0
    with source.open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(contract.column_names))
        writer.writeheader()
        day = FIRST_DAY
        while day <= LAST_DAY:
            # Invented weekday pattern and mild drift; no patient observations.
            count = (
                18
                + (4 if day.weekday() < 5 else 0)
                + ((day - FIRST_DAY).days // 21)
                + rng.randint(-2, 2)
            )
            for _ in range(count):
                row = _row("REFERRALS", row_number)
                row["hospitalization_code"] = f"SYNTHETIC-FORECAST-{row_number:07d}"
                row["registration_dt"] = f"{day.isoformat()} 09:00:00"
                row["planned_dt"] = f"{(day + timedelta(days=3)).isoformat()} 09:00:00"
                row["polyclinic_dt"] = row["registration_dt"]
                row["hospitalization_dt"] = ""
                row["sdu_load_date"] = "2025-04-01 03:00:00"
                writer.writerow(
                    {column: row.get(column, "") for column in contract.column_names}
                )
                row_number += 1
            day += timedelta(days=1)
    manifest = {
        "delivery_id": "phase8-synthetic-forecast-referrals-v1",
        "dataset_type": "REFERRALS",
        "source_system": contract.source_system,
        "schema_version": "phase8-synthetic-forecast-v1",
        "mode": "DELTA",
        "period_start": FIRST_DAY.isoformat(),
        "period_end": LAST_DAY.isoformat(),
        "snapshot_date": None,
        "file_hashes": [hashlib.sha256(source.read_bytes()).hexdigest()],
        "expected_rows": row_number,
        "contract_version": "phase8-synthetic-contract-v1",
        "confirmed_complete_through": LAST_DAY.isoformat(),
    }
    with manifest_path.open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    return source, manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, required=True)
    args = parser.parse_args()
    project_dir = args.project_dir.resolve()
    metadata = json.loads((project_dir / "manifest.json").read_text(encoding="utf-8"))
    if (
        not project_dir.name.startswith("phase8-")
        or metadata.get("project") != project_dir.name
        or metadata.get("dataset") != "synthetic-only"
        or metadata.get("status") != "READY"
    ):
        raise ValueError("Only a READY synthetic phase8 project is supported")
    # Separate source mount: the import contract compares exactly the files in
    # one discovered dataset directory with one reviewed delivery manifest.
    source = project_dir / "source-forecast"
    source.mkdir(exist_ok=False)
    _, manifest = generate(source)
    print(f"Generated fixed-seed synthetic referral manifest: {manifest.name}")


if __name__ == "__main__":
    main()
