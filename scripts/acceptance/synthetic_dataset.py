"""Generate small, fully invented source files matching the audited contracts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from data_pipeline.contracts import get_contract

LOAD_DATE = "2025-01-03 03:00:00"
COUNTS = {"REFERRALS": 30, "WAITING": 22, "REFUSALS": 24, "TREATED": 2}
ORG_A = "SYNTHETIC-ORGANIZATION-A"
ORG_B = "SYNTHETIC-ORGANIZATION-B"


def _row(dataset: str, index: int) -> dict[str, str]:
    day = "01" if index % 2 == 0 else "02"
    organization = ORG_A if index % 2 == 0 else ORG_B
    if dataset == "REFERRALS":
        return {
            "hospitalization_code": f"SYNTHETIC-CASE-{index:05d}",
            "referring_mo": ORG_B if organization == ORG_A else ORG_A,
            "hospital_mo": organization,
            "icd10_ref_diag_code": "Z00.0",
            "diagnosis_name": "",
            "bed_profile": "SYNTHETIC-PROFILE",
            "registration_dt": f"2025-01-{day} 09:00:00",
            "planned_dt": "2025-01-04 09:00:00",
            "polyclinic_dt": f"2025-01-{day} 09:00:00",
            "hospitalization_dt": "2025-01-04 09:00:00" if index % 3 else "",
            "refusal_dt": "",
            "territorial_type": "SYNTHETIC",
            "referral_purpose": "SYNTHETIC",
            "finance_source": "SYNTHETIC",
            "sdu_load_date": LOAD_DATE,
        }
    if dataset == "WAITING":
        return {
            "region_origin_code": "01" if index % 2 == 0 else "02",
            "mo_destination_code": "SYN-A" if index % 2 == 0 else "SYN-B",
            "profile_code": "SYN-PROFILE",
            "patient_seq_no": f"SYNTHETIC-PATIENT-{index:05d}",
            "icd10_ref_diag_code": "Z00.0",
            "diagnosis_name": "",
            "operation_code": "",
            "operation_name": "",
            "registration_dt": f"2025-01-{day} 09:00:00",
            "planned_dt": "2025-01-04 09:00:00",
            "sdu_load_date": LOAD_DATE,
        }
    if dataset == "REFUSALS":
        return {
            "region_in": "SYNTHETIC-REGION-A" if index % 2 == 0 else "SYNTHETIC-REGION-B",
            "org_in": organization,
            "resident": "",
            "insured": "",
            "benefit_cat": "",
            "refuse_dt": f"2025-01-{day} 10:00:00",
            "attach_region": "",
            "attach_org": "",
            "icd10": "Z00.0",
            "icd_name": "",
            "amount": "",
            "finance_src": "SYNTHETIC",
            "sdu_load_date": LOAD_DATE,
        }
    return {
        "medicine_organization": organization,
        "discharged_total": "12",
        "discharged_children": "0",
        "treated_budget": "12",
        "treated_paid": "0",
        "discharged_within_day": "1",
        "deaths_total": "0",
        "bed_days": "12",
        "amount_to_pay": "0",
        "sdu_load_date": LOAD_DATE,
    }


def generate(root: Path) -> dict[str, int]:
    """Write contract-exact synthetic CSVs and owner-reviewable manifests.

    Existing files are never overwritten; the caller owns the destination.
    """
    root.mkdir(parents=True, exist_ok=True)
    for dataset, count in COUNTS.items():
        contract = get_contract(dataset)
        directory = root / contract.source_directory
        directory.mkdir(exist_ok=True)
        source = directory / "synthetic.csv"
        with source.open("x", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(contract.column_names))
            writer.writeheader()
            for index in range(count):
                row = _row(dataset, index)
                writer.writerow(
                    {column: row.get(column, "") for column in contract.column_names}
                )
        snapshot = dataset in {"WAITING", "TREATED"}
        manifest: dict[str, Any] = {
            "delivery_id": f"phase8-synthetic-{dataset.lower()}-v1",
            "dataset_type": dataset,
            "source_system": contract.source_system,
            "schema_version": "phase8-synthetic-v1",
            "mode": "SNAPSHOT" if snapshot else "DELTA",
            "period_start": None if snapshot else "2025-01-01",
            "period_end": None if snapshot else "2025-01-02",
            "snapshot_date": "2025-01-03" if snapshot else None,
            "file_hashes": [hashlib.sha256(source.read_bytes()).hexdigest()],
            "expected_rows": count,
            "contract_version": "phase8-synthetic-contract-v1",
            "confirmed_complete_through": "2025-01-03" if snapshot else "2025-01-02",
        }
        manifest_path = root / f"manifest-{dataset}.json"
        with manifest_path.open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
            handle.write("\n")
    return dict(COUNTS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    counts = generate(args.output)
    print(
        "Synthetic acceptance records: "
        + ", ".join(f"{k}={v}" for k, v in counts.items())
    )


if __name__ == "__main__":
    main()
