"""Synthetic configuration tests; real identity secrets are never fixtures."""

import json

import pytest

from scripts.security.acceptance_identities import load_identities


def manifest():
    return [
        {
            "username": "synthetic-role",
            "password": "synthetic-password",
            "role": "HOSPITAL_MANAGER",
            "global_scope": False,
            "hospital_codes": ["SYNTHETIC-A"],
        }
    ]


def test_acceptance_has_no_default_passwords(monkeypatch):
    monkeypatch.delenv("MEDSIGNAL_TEST_IDENTITIES", raising=False)
    with pytest.raises(ValueError, match="MEDSIGNAL_TEST_IDENTITIES"):
        load_identities()


def test_password_is_not_represented_or_exposed_by_configuration_error(monkeypatch):
    monkeypatch.setenv("MEDSIGNAL_TEST_IDENTITIES", json.dumps(manifest()))
    identity = load_identities()[0]
    assert identity.password == manifest()[0]["password"]
    assert "synthetic-password" not in repr(identity)
    malformed = manifest()
    malformed[0]["role"] = "unrecognized-sensitive-input"
    monkeypatch.setenv("MEDSIGNAL_TEST_IDENTITIES", json.dumps(malformed))
    with pytest.raises(ValueError) as error:
        load_identities()
    assert "sensitive-input" not in str(error.value)
    assert "synthetic-password" not in str(error.value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("global_scope", "false"),
        ("hospital_codes", "A"),
        ("password", ""),
        ("role", "ADMINISTRATOR"),
        ("username", ""),
    ],
)
def test_invalid_identity_rejected(monkeypatch, field, value):
    values = manifest()
    values[0][field] = value
    monkeypatch.setenv("MEDSIGNAL_TEST_IDENTITIES", json.dumps(values))
    with pytest.raises(ValueError):
        load_identities()


def test_duplicate_subjects_are_rejected(monkeypatch):
    monkeypatch.setenv("MEDSIGNAL_TEST_IDENTITIES", json.dumps(manifest() * 2))
    with pytest.raises(ValueError):
        load_identities()
