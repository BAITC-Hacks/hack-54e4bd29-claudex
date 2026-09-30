"""Generate immutable, contract-valid invented data for the local demo stack."""

from __future__ import annotations

import csv
import hashlib
import json
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from data_pipeline.contracts import get_contract
from scripts.acceptance.synthetic_dataset import _row

ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = ROOT / "backend" / "seeds" / "local_demo_profile.json"
FIRST_DAY = date(2025, 1, 1)
LAST_DAY = date(2025, 3, 31)
LOAD_DATE = "2025-04-01 03:00:00"
DATASETS = ("REFERRALS", "WAITING", "REFUSALS")
DELIVERY_IDS = tuple(
    f"phase8-synthetic-local-demo-{dataset.lower()}-v1" for dataset in DATASETS
)


def load_profile() -> tuple[dict[str, str], ...]:
    """Read the one reviewed list of fictional canonical identities."""
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    if not isinstance(profile, list) or len(profile) != 12:
        raise ValueError("Local demo profile must contain exactly 12 regions")
    codes: set[str] = set()
    result: list[dict[str, str]] = []
    for item in profile:
        if (
            not isinstance(item, dict)
            or set(item) != {"code", "name"}
            or not isinstance(item["code"], str)
            or not isinstance(item["name"], str)
            or not item["code"].startswith("KZ-")
            or not item["name"].strip()
            or item["code"] in codes
        ):
            raise ValueError("Local demo profile contains an invalid or duplicate region")
        codes.add(item["code"])
        result.append({"code": item["code"], "name": item["name"]})
    return tuple(result)


def _referrals(profile: tuple[dict[str, str], ...]) -> list[dict[str, str]]:
    rng = random.Random(20250927)  # noqa: S311 — only invented demo counts
    rows: list[dict[str, str]] = []
    for day_index in range((LAST_DAY - FIRST_DAY).days + 1):
        day = FIRST_DAY + timedelta(days=day_index)
        daily_count = (
            18
            + (4 if day.weekday() < 5 else 0)
            + day_index // 21
            + rng.randint(-2, 2)
        )
        for offset in range(daily_count):
            region = profile[(day_index + offset) % len(profile)]
            referring = profile[(day_index + offset + 1) % len(profile)]
            index = day_index * 100 + offset
            row = _row("REFERRALS", index)
            row.update(
                hospitalization_code=f"SYNTHETIC-LOCAL-CASE-{index:07d}",
                hospital_mo=f"SYN-ORG-{region['code']}",
                referring_mo=f"SYN-ORG-{referring['code']}",
                registration_dt=f"{day.isoformat()} 09:00:00",
                polyclinic_dt=f"{day.isoformat()} 09:00:00",
                planned_dt=f"{(day + timedelta(days=3)).isoformat()} 09:00:00",
                hospitalization_dt="",
                refusal_dt="",
                sdu_load_date=LOAD_DATE,
            )
            rows.append(row)
    return rows


def _waiting(profile: tuple[dict[str, str], ...]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for region_index, region in enumerate(profile):
        for offset in range(4 + region_index % 3):
            index = region_index * 10 + offset
            row = _row("WAITING", index)
            row.update(
                region_origin_code=f"SYN-REG-{region['code']}",
                mo_destination_code=f"SYN-WAIT-{region['code']}",
                patient_seq_no=f"SYNTHETIC-LOCAL-PATIENT-{index:05d}",
                registration_dt="2025-03-27 09:00:00",
                planned_dt="2025-03-31 09:00:00",
                sdu_load_date="2025-03-31 03:00:00",
            )
            rows.append(row)
    return rows


def _refusals(profile: tuple[dict[str, str], ...]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for day_index in range(0, (LAST_DAY - FIRST_DAY).days + 1, 7):
        day = FIRST_DAY + timedelta(days=day_index)
        for region_index, region in enumerate(profile):
            index = day_index * 100 + region_index
            row = _row("REFUSALS", index)
            row.update(
                region_in=f"SYN-REF-REG-{region['code']}",
                org_in=f"SYN-ORG-{region['code']}",
                refuse_dt=f"{day.isoformat()} 10:00:00",
                sdu_load_date=LOAD_DATE,
            )
            rows.append(row)
    return rows


def generate(root: Path) -> dict[str, int]:
    """Write three deliveries to a completely empty target; never overwrite data."""
    if root.exists() and any(root.iterdir()):
        raise FileExistsError("Local demo source directory must be empty")
    root.mkdir(parents=True, exist_ok=True)
    profile = load_profile()
    rows_by_dataset = {
        "REFERRALS": _referrals(profile),
        "WAITING": _waiting(profile),
        "REFUSALS": _refusals(profile),
    }
    counts: dict[str, int] = {}
    for dataset in DATASETS:
        contract = get_contract(dataset)
        source_dir = root / contract.source_directory
        source_dir.mkdir(exist_ok=True)
        source = source_dir / "synthetic-local-demo.csv"
        rows = rows_by_dataset[dataset]
        with source.open("x", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(contract.column_names))
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {column: row.get(column, "") for column in contract.column_names}
                )
        snapshot = dataset == "WAITING"
        last_refusal = FIRST_DAY + timedelta(days=84)
        manifest: dict[str, Any] = {
            "delivery_id": DELIVERY_IDS[DATASETS.index(dataset)],
            "dataset_type": dataset,
            "source_system": contract.source_system,
            "schema_version": "phase8-synthetic-local-demo-v1",
            "mode": "SNAPSHOT" if snapshot else "DELTA",
            "period_start": None if snapshot else FIRST_DAY.isoformat(),
            "period_end": None
            if snapshot
            else (LAST_DAY if dataset == "REFERRALS" else last_refusal).isoformat(),
            "snapshot_date": LAST_DAY.isoformat() if snapshot else None,
            "file_hashes": [hashlib.sha256(source.read_bytes()).hexdigest()],
            "expected_rows": len(rows),
            "contract_version": "phase8-synthetic-contract-v1",
            "confirmed_complete_through": LAST_DAY.isoformat()
            if dataset != "REFUSALS"
            else last_refusal.isoformat(),
        }
        manifest_path = root / f"manifest-{dataset}.json"
        with manifest_path.open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
            handle.write("\n")
        counts[dataset] = len(rows)
    return counts
