"""Tests for job pipeline stage derivation and application logging."""

from hireloop_api.routes.me import _pipeline_stage


def test_pipeline_stage_application_substatuses():
    assert (
        _pipeline_stage(
            saved_at=None,
            kit_id=None,
            application_status="interview",
            intro_status=None,
        )
        == "interview"
    )


def test_pipeline_stage_intro_before_application():
    assert (
        _pipeline_stage(
            saved_at=None,
            kit_id=None,
            application_status="applied",
            intro_status="pending",
        )
        == "intro_in_progress"
    )


def test_pipeline_stage_saved_after_kit():
    assert (
        _pipeline_stage(
            saved_at="2026-01-01",
            kit_id="kit",
            application_status=None,
            intro_status=None,
        )
        == "kit_ready"
    )
