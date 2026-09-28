"""The edge log has timing/upstream context without sensitive request data."""

from pathlib import Path


def test_access_log_tracks_upstream_without_query_or_credentials() -> None:
    config = (
        Path(__file__).resolve().parents[2] / "infrastructure/nginx/nginx.conf"
    ).read_text(encoding="utf-8")
    log_format = config.split("log_format  medsignal", 1)[1].split(";", 1)[0]

    for required in (
        "$request_method",
        "$uri",
        "$status",
        "$upstream_status",
        "$upstream_response_time",
        "$request_time",
        "$medsignal_request_id",
    ):
        assert required in log_format
    for forbidden in (
        "$request_uri",
        "$args",
        "$http_authorization",
        "$http_cookie",
        "$http_set_cookie",
        "$request_body",
    ):
        assert forbidden not in log_format
