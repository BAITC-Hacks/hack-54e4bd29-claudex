from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from app.business.ingestion.delivery import assess_delivery
from app.shared.delivery import DeliveryManifest, DeliveryMode

M = DeliveryManifest(
    "synthetic",
    "REFERRALS",
    "IS_BG",
    "v1",
    DeliveryMode.DELTA,
    date(2025, 1, 1),
    date(2025, 1, 31),
    None,
    ("a" * 64,),
    2,
    "test-v1",
)


def check(m=M, **changes):
    args = {
        "received_hashes": frozenset(m.file_hashes),
        "overlaps_published_period": False,
        "contract_approved": True,
    }
    args.update(changes)
    return assess_delivery(m, **args)


def test_changed_hash_does_not_authorize_overlapping_events():
    assert check(replace(M, file_hashes=("b" * 64,)), overlaps_published_period=True) == (
        False,
        "OVERLAPPING_DELIVERY",
    )


@pytest.mark.parametrize(
    ("manifest", "kwargs", "reason"),
    [
        (M, {"contract_approved": False}, "CONTRACT_NOT_APPROVED"),
        (M, {"received_hashes": frozenset()}, "PARTS_MISMATCH"),
        (replace(M, mode=DeliveryMode.REPLACEMENT), {}, "REPLACEMENT_NOT_SUPPORTED"),
        (replace(M, mode=DeliveryMode.SNAPSHOT), {}, "UNKNOWN_SNAPSHOT_DATE"),
        (replace(M, period_start=None), {}, "UNKNOWN_PERIOD"),
        (replace(M, period_start=date(2025, 2, 1)), {}, "INVALID_PERIOD"),
        (replace(M, file_hashes=()), {}, "INVALID_MANIFEST"),
        (replace(M, file_hashes=("a" * 64, "a" * 64)), {}, "INVALID_MANIFEST"),
        (replace(M, expected_rows=-1), {}, "INVALID_MANIFEST"),
    ],
)
def test_closed_delivery_gates(manifest, kwargs, reason):
    assert check(manifest, **kwargs) == (False, reason)


def test_same_snapshot_with_changed_contents_is_overlap():
    m = replace(
        M,
        mode=DeliveryMode.SNAPSHOT,
        snapshot_date=date(2025, 1, 31),
        file_hashes=("b" * 64,),
    )
    assert check(m, overlaps_published_period=True) == (False, "OVERLAPPING_DELIVERY")


def test_reviewed_complete_nonoverlapping_delivery_ready():
    assert check() == (True, "READY")


def test_event_period_outside_reviewed_manifest_fails_closed():
    from app.business.ingestion.delivery import assess_evidence
    from app.shared.delivery import DeliveryEvidence

    evidence = DeliveryEvidence(2, date(2024, 12, 31), date(2025, 1, 15), None)
    assert assess_evidence(M, evidence) == (False, "EVENT_PERIOD_MISMATCH")


def test_missing_event_evidence_is_not_client_assertion():
    from app.business.ingestion.delivery import assess_evidence

    assert assess_evidence(M, None) == (False, "EVENT_EVIDENCE_UNAVAILABLE")


def test_snapshot_must_match_actual_fact_snapshot():
    from app.business.ingestion.delivery import assess_evidence
    from app.shared.delivery import DeliveryEvidence

    m = replace(M, mode=DeliveryMode.SNAPSHOT, snapshot_date=date(2025, 1, 31))
    assert assess_evidence(m, DeliveryEvidence(2, None, None, date(2025, 1, 30))) == (
        False,
        "SNAPSHOT_MISMATCH",
    )
