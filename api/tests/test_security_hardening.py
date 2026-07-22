"""Security regression tests: token encryption + SSRF guard."""

from __future__ import annotations

import socket

import pytest

from hireloop_api.services.role_jd_fetch import RoleImportError, _validate_public_url
from hireloop_api.services.token_crypto import decrypt_token, encrypt_token


def test_token_encrypt_roundtrip() -> None:
    ct = encrypt_token("ya29.super-secret-access-token")
    assert ct != "ya29.super-secret-access-token"  # not plaintext
    assert not ct.startswith("ya29")  # ciphertext, not the token
    assert decrypt_token(ct) == "ya29.super-secret-access-token"


def test_token_decrypt_legacy_plaintext_passthrough() -> None:
    # Pre-encryption rows must still decrypt (dual-read migration safety).
    assert decrypt_token("legacy-plaintext-token") == "legacy-plaintext-token"


def test_corrupt_fernet_token_fails_closed() -> None:
    assert decrypt_token("gAAAA-corrupt-ciphertext") is None


def test_token_encrypt_none_passthrough() -> None:
    assert encrypt_token(None) is None
    assert decrypt_token(None) is None
    assert encrypt_token("") == ""


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://localhost/x",
        "http://127.0.0.1/x",
        "http://10.0.0.5/x",  # RFC1918
        "http://192.168.1.1/x",
        "http://[::1]/x",  # IPv6 loopback
        "http://0.0.0.0/x",
        "ftp://example.com/x",  # non-http scheme
        "file:///etc/passwd",
    ],
)
def test_ssrf_blocks_internal_and_bad_scheme(url: str) -> None:
    with pytest.raises(RoleImportError):
        _validate_public_url(url)


def test_ssrf_allows_public_job_board(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("99.86.1.1", 0)),
        ],
    )
    assert _validate_public_url("https://boards.greenhouse.io/acme/jobs/123").startswith("https://")


def test_ssrf_allows_public_ipv4_and_well_known_nat64_dns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("99.86.1.1", 0)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("64:ff9b::6356:101", 0, 0, 0)),
        ],
    )

    assert _validate_public_url("https://jobs.example.com/role") == (
        "https://jobs.example.com/role"
    )


def test_ssrf_blocks_well_known_nat64_dns_embedding_private_ipv4(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("99.86.1.1", 0)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("64:ff9b::a00:5", 0, 0, 0)),
        ],
    )

    with pytest.raises(RoleImportError, match="Private network"):
        _validate_public_url("https://jobs.example.com/role")


@pytest.mark.parametrize(
    "url",
    [
        "http://[::ffff:99.86.1.1]/role",
        "http://[2001:db8::1]/role",
    ],
)
def test_ssrf_blocks_mapped_and_non_public_ipv6(url: str) -> None:
    with pytest.raises(RoleImportError, match="Private network"):
        _validate_public_url(url)
