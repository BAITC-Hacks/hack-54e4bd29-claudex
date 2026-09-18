from __future__ import annotations

from types import SimpleNamespace

from app.core.http_metrics import route_label


def test_route_label_uses_template_not_identifier() -> None:
    scope = {
        "route": SimpleNamespace(path="/api/v1/signals/{signal_id}"),
        "path": "/api/v1/signals/4cb8d07d-4d03-4eed-a9df-4faecf33f501",
    }
    assert route_label(scope) == "/api/v1/signals/{signal_id}"


def test_unmatched_route_has_bounded_label() -> None:
    assert route_label({"path": "/random/high-cardinality/value"}) == "unmatched"
