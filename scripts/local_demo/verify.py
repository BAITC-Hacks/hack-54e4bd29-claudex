"""Reconcile one isolated local demo's hashed CSVs with real scoped APIs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any

from data_pipeline.contracts import get_contract
from scripts.local_demo.dataset import DATASETS, FIRST_DAY, LAST_DAY, load_profile
from scripts.operations.prepare_acceptance import ROOT, _compose_command

PERIOD = ("2025-01-01T00:00:00Z", "2025-03-31T23:59:59Z")


def _rows(source_root: Path, dataset: str) -> list[dict[str, str]]:
    manifest_path = source_root / f"manifest-{dataset}.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("dataset_type") != dataset
        or not str(manifest.get("delivery_id", "")).startswith(
            f"phase8-synthetic-local-demo-{dataset.lower()}-"
        )
    ):
        raise ValueError("Local synthetic manifest identity mismatch")
    source_dir = source_root / get_contract(dataset).source_directory
    files = list(source_dir.glob("*.csv"))
    if len(files) != 1:
        raise ValueError("Local synthetic manifest must identify one source CSV")
    source = files[0]
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if manifest.get("file_hashes") != [digest]:
        raise ValueError("Local synthetic source hash mismatch")
    with source.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if manifest.get("expected_rows") != len(rows):
        raise ValueError("Local synthetic source row count mismatch")
    return rows


def expected_counts(source_root: Path) -> dict[str, int]:
    """Read counts only from one-to-one hash-checked source manifests."""
    return {dataset: len(_rows(source_root, dataset)) for dataset in DATASETS}


def expected_region_counts(source_root: Path) -> dict[str, tuple[int, int, int]]:
    """Derive exact per-region referral, waiting, refusal totals from source IDs."""
    codes = {item["code"] for item in load_profile()}
    keys = {
        "REFERRALS": ("hospital_mo", "SYN-ORG-"),
        "WAITING": ("mo_destination_code", "SYN-WAIT-"),
        "REFUSALS": ("org_in", "SYN-ORG-"),
    }
    grouped: dict[str, Counter[str]] = {}
    for dataset, (column, prefix) in keys.items():
        counter: Counter[str] = Counter()
        for row in _rows(source_root, dataset):
            source_id = row[column]
            if not source_id.startswith(prefix):
                raise ValueError("Local synthetic source alias mismatch")
            code = source_id.removeprefix(prefix)
            if code not in codes:
                raise ValueError("Local synthetic source region mismatch")
            counter[code] += 1
        grouped[dataset] = counter
    return {
        code: tuple(grouped[dataset][code] for dataset in DATASETS)
        for code in codes
    }


def assert_region_coverage(expected_codes: set[str], actual_codes: set[str]) -> None:
    if expected_codes != actual_codes:
        raise AssertionError("Canonical region coverage mismatch")


def assert_forecast_contract(forecast: dict[str, Any]) -> None:
    """Assert the existing global seven-day contract without choosing ML outputs."""
    points = forecast["forecast"]
    if (
        forecast["target"] != "DAILY_REFERRAL_COUNT"
        or forecast["scope_type"] != "GLOBAL"
    ):
        raise AssertionError("Forecast target or scope mismatch")
    if forecast["horizon_days"] != 7 or len(points) != 7:
        raise AssertionError("Forecast horizon mismatch")
    if forecast["input_period_end"][:10] != LAST_DAY.isoformat():
        raise AssertionError("Forecast historical cutoff mismatch")
    expected_days = [
        (LAST_DAY + timedelta(days=offset)).isoformat() for offset in range(1, 8)
    ]
    if (
        forecast["forecast_start"] != expected_days[0]
        or forecast["forecast_end"] != expected_days[-1]
        or [point["date"] for point in points] != expected_days
    ):
        raise AssertionError("Forecast future period mismatch")
    if not (
        forecast.get("validation_period_start")
        and forecast.get("validation_period_end")
        and forecast.get("model_version")
    ):
        raise AssertionError("Forecast validation or model metadata missing")
    for field in ("metrics", "baseline_metrics"):
        mae = forecast[field].get("mae")
        if not isinstance(mae, int | float) or not math.isfinite(mae) or mae < 0:
            raise AssertionError("Forecast MAE missing or invalid")


def _counts(payload: dict[str, Any]) -> tuple[int, int, int]:
    data = payload["data"]
    keys = ("referrals_total", "waiting_records", "refusals_total")
    values = tuple(data[key]["value"] for key in keys)
    if any(not isinstance(value, int) for value in values):
        raise AssertionError("Analytics returned an unavailable or nonnumeric count")
    return values  # type: ignore[return-value]


def _daily_referrals(source_root: Path) -> Counter[str]:
    days: Counter[str] = Counter()
    for row in _rows(source_root, "REFERRALS"):
        day = row["registration_dt"][:10]
        if not FIRST_DAY.isoformat() <= day <= LAST_DAY.isoformat():
            raise ValueError("Referral date outside local synthetic period")
        days[day] += 1
    if len(days) != 90:
        raise AssertionError("Local synthetic referral history is incomplete")
    return days


def verify_published_mappings(project_dir: Path) -> int:
    """Compare the active ClickHouse projection with all 60 expected aliases."""
    command = [
        *_compose_command(project_dir.name, project_dir),
        "exec", "-T", "backend", "python", "-",
    ]
    script = Path(__file__).with_name("verify_mappings_db.py").read_text(
        encoding="utf-8"
    )
    try:
        result = subprocess.run(  # noqa: S603 — fixed validated Compose project
            command,
            input=script,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Published mapping snapshot check unavailable") from exc
    if result.returncode:
        raise AssertionError("Published mapping snapshot check failed")
    try:
        evidence = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError("Published mapping snapshot evidence invalid") from exc
    if evidence != {"mapping": "PASS", "aliases": 60}:
        raise AssertionError("Published mapping snapshot evidence mismatch")
    return 60


def verify(project_dir: Path) -> dict[str, object]:
    """Use actual Keycloak tokens and API responses; return only safe evidence."""
    import httpx

    manifest = json.loads((project_dir / "manifest.json").read_text(encoding="utf-8"))
    origin = manifest.get("origin", "")
    if (
        not project_dir.name.startswith("phase8-local-demo-")
        or manifest.get("project") != project_dir.name
        or manifest.get("dataset") != "synthetic-only"
        or manifest.get("status") != "READY"
        or not isinstance(origin, str)
        or not origin.startswith("http://127.0.0.1:")
    ):
        raise ValueError("Only one READY loopback local synthetic project is supported")
    source = project_dir / "source-empty"
    expected = expected_counts(source)
    by_region = expected_region_counts(source)
    days = _daily_referrals(source)
    mapping_aliases = verify_published_mappings(project_dir)
    realm = json.loads((project_dir / "realm.json").read_text(encoding="utf-8"))
    users = {item["username"]: item for item in realm["users"]}
    params = {"date_from": PERIOD[0], "date_to": PERIOD[1]}
    names = ("admin", "regional-analyst", "hospital-manager")
    with httpx.Client(base_url=origin, timeout=20) as client:
        tokens: dict[str, str] = {}
        for name in names:
            response = client.post(
                "/auth/realms/medsignal/protocol/openid-connect/token",
                data={
                    "grant_type": "password",
                    "client_id": "medsignal-frontend",
                    "username": name,
                    "password": users[name]["credentials"][0]["value"],
                },
            )
            response.raise_for_status()
            tokens[name] = response.json()["access_token"]

        def get(name: str, route: str, extra: dict[str, str] | None = None) -> dict:
            response = client.get(
                route,
                params={**params, **(extra or {})}
                if route.startswith("/api/v1/analytics") else extra,
                headers={"Authorization": f"Bearer {tokens[name]}"},
            )
            response.raise_for_status()
            return response.json()

        regions = get("admin", "/api/v1/regions", {"page_size": "100"})["items"]
        hospitals = get("admin", "/api/v1/hospitals", {"page_size": "100"})["items"]
        region_ids = {item["code"]: str(item["id"]) for item in regions}
        hospital_ids = {item["code"]: str(item["id"]) for item in hospitals}
        assert_region_coverage(set(by_region), set(region_ids))
        if set(hospital_ids) != {f"H-{code}" for code in by_region}:
            raise AssertionError("Canonical hospital coverage mismatch")
        if any(
            "[синтетические данные]" not in item["name"]
            for item in regions + hospitals
        ):
            raise AssertionError("Local synthetic directory provenance missing")
        if any(
            str(item["region_id"]) != region_ids[item["code"].removeprefix("H-")]
            for item in hospitals
        ):
            raise AssertionError("Canonical hospital-region link mismatch")

        global_actual = _counts(get("admin", "/api/v1/analytics/overview"))
        global_expected = tuple(expected[dataset] for dataset in DATASETS)
        if global_actual != global_expected:
            raise AssertionError("Global analytics differs from hashed source counts")
        for code, values in by_region.items():
            regional = _counts(get(
                "admin", "/api/v1/analytics/overview", {"region": region_ids[code]}
            ))
            organization = _counts(get(
                "admin", "/api/v1/analytics/overview",
                {"organization": f"canonical:{hospital_ids[f'H-{code}']}"},
            ))
            if regional != values or organization != values:
                raise AssertionError(
                    f"Mapped analytics mismatch for {code}: "
                    f"source={values}, region={regional}, organization={organization}"
                )

        first_code = load_profile()[0]["code"]
        first_values = by_region[first_code]
        if (
            _counts(get("regional-analyst", "/api/v1/analytics/overview"))
            != first_values
            or _counts(get("hospital-manager", "/api/v1/analytics/overview"))
            != first_values
        ):
            raise AssertionError("Restricted overview scope mismatch")
        foreign_code = next(code for code in by_region if code != first_code)
        foreign_ref = f"canonical:{hospital_ids[f'H-{foreign_code}']}"
        try:
            foreign = _counts(get(
                "hospital-manager", "/api/v1/analytics/overview",
                {"organization": foreign_ref},
            ))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
        else:
            if foreign != (0, 0, 0):
                raise AssertionError("Foreign hospital escaped restricted scope")
        restricted_hospitals = get(
            "hospital-manager", "/api/v1/hospitals", {"page_size": "100"}
        )["items"]
        if {item["code"] for item in restricted_hospitals} != {f"H-{first_code}"}:
            raise AssertionError("Restricted hospital directory scope mismatch")

        signals = get("admin", "/api/v1/signals", {"page_size": "100"})["items"]
        seeded = [
            item for item in signals
            if item["type"] == "DATA_STALE"
            and item["hospital_id"] in {
                hospital_ids[f"H-{code}"]
                for code in ("KZ-ASTANA", "KZ-ALMATY", "KZ-KARAGANDA")
            }
        ]
        if len(seeded) != 3:
            raise AssertionError("Three historical local signals were not published")
        for signal in seeded:
            detail = get("admin", f"/api/v1/signals/{signal['id']}")
            if (
                detail["evidence"].get("confirmed_complete_through")
                != LAST_DAY.isoformat()
                or detail["source"] != "SYNTHETIC_LOCAL_DEMO"
            ):
                raise AssertionError("Signal evidence does not match historical cutoff")

        forecast = get("admin", "/api/v1/forecasts/referrals/latest")
        assert_forecast_contract(forecast)
        historical = forecast["historical"]
        if not historical or any(
            days[item["date"]] != item["value"] for item in historical
        ):
            raise AssertionError("Forecast historical points differ from source CSV")
    return {
        "project": project_dir.name,
        "source_rows": expected,
        "canonical_regions": len(region_ids),
        "canonical_hospitals": len(hospital_ids),
        "published_mapping_aliases": mapping_aliases,
        "scope": "PASS",
        "signal_evidence": "PASS",
        "forecast_id": forecast["id"],
        "forecast_model": forecast["selected_model"],
        "forecast_mae_referrals_per_day": forecast["metrics"]["mae"],
        "forecast_baseline_mae_referrals_per_day": forecast["baseline_metrics"]["mae"],
        "forecast_period": (forecast["forecast_start"], forecast["forecast_end"]),
        "api": "PASS",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", required=True, type=Path)
    result = verify(parser.parse_args().project_dir)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
