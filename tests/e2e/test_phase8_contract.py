from __future__ import annotations

import pytest

from scripts.demo.reset import reset_command


def test_reset_is_limited_to_phase8_project() -> None:
    command = reset_command("phase8-demo")
    assert command[-3:] == ["down", "--volumes", "--remove-orphans"]
    assert "phase8-demo" in command
    assert all("Downloads" not in item and "data/source" not in item for item in command)


def test_reset_refuses_primary_project() -> None:
    with pytest.raises(ValueError, match="phase8-"):
        reset_command("medsignal")
