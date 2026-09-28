from __future__ import annotations

from types import SimpleNamespace

from prometheus_client import REGISTRY

from app.core.http_metrics import observe_background_job, route_label


def test_route_label_uses_template_not_identifier() -> None:
    scope = {
        "route": SimpleNamespace(path="/api/v1/signals/{signal_id}"),
        "path": "/api/v1/signals/4cb8d07d-4d03-4eed-a9df-4faecf33f501",
    }
    assert route_label(scope) == "/api/v1/signals/{signal_id}"


def test_unmatched_route_has_bounded_label() -> None:
    assert route_label({"path": "/random/high-cardinality/value"}) == "unmatched"


def test_background_job_duration_records_without_identifiers() -> None:
    name = "ml.forecast_organization"
    before = (
        REGISTRY.get_sample_value(
            "medsignal_background_job_duration_seconds_count", {"task": name}
        )
        or 0
    )

    with observe_background_job(name):
        pass

    assert (
        REGISTRY.get_sample_value(
            "medsignal_background_job_duration_seconds_count", {"task": name}
        )
        == before + 1
    )
