"""#3: ingest-time hard validator — drop structurally unusable postings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from hireloop_api.services.job_validator import validate_job_record


@dataclass
class _Job:
    title: str | None = "Backend Engineer"
    apply_url: str | None = "https://jobs.example.com/1"
    expires_at: datetime | None = None


def test_valid_job_passes() -> None:
    ok, reason = validate_job_record(_Job())
    assert ok is True and reason == ""


def test_missing_title_dropped() -> None:
    assert validate_job_record(_Job(title=""))[1] == "missing_title"
    assert validate_job_record(_Job(title=None))[1] == "missing_title"


def test_bad_apply_url_dropped() -> None:
    assert validate_job_record(_Job(apply_url=None))[1] == "bad_apply_url"
    assert validate_job_record(_Job(apply_url="mailto:x@y.com"))[1] == "bad_apply_url"
    assert validate_job_record(_Job(apply_url="/relative/path"))[1] == "bad_apply_url"


def test_expired_dropped() -> None:
    past = datetime.now(UTC) - timedelta(days=1)
    assert validate_job_record(_Job(expires_at=past))[1] == "expired"


def test_future_expiry_ok() -> None:
    future = datetime.now(UTC) + timedelta(days=10)
    assert validate_job_record(_Job(expires_at=future))[0] is True


def test_naive_expiry_handled() -> None:
    # tz-naive datetimes must not raise.
    naive_future = datetime.now() + timedelta(days=10)
    assert validate_job_record(_Job(expires_at=naive_future))[0] is True
