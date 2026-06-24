"""
P23 observability: pure helpers for readiness + the admin agent-activity payload.
DB-backed endpoints follow the repo's existing no-DB-test convention; the logic
that shapes their output is unit-tested here.
"""

from __future__ import annotations

from hireloop_api.routes.admin import _shape_observability
from hireloop_api.routes.health import build_readiness


def test_readiness_ready_when_all_ok() -> None:
    code, body = build_readiness({"database": "ok"})
    assert code == 200
    assert body["status"] == "ready"


def test_readiness_degraded_returns_503() -> None:
    code, body = build_readiness({"database": "error"})
    assert code == 503
    assert body["status"] == "degraded"
    assert body["checks"]["database"] == "error"


def test_shape_observability_computes_error_rate() -> None:
    payload = _shape_observability(
        action_rows=[
            {"action_type": "job_search", "total": 8, "avg_ms": 120, "errors": 1},
            {"action_type": "request_intro", "total": 2, "avg_ms": 40, "errors": 0},
        ],
        funnel_rows=[
            {"status": "pending", "n": 5},
            {"status": "accepted", "n": 2},
        ],
        totals={"actions": 10, "errors": 1},
        window_days=7,
    )
    assert payload["window_days"] == 7
    assert payload["totals"] == {"agent_actions": 10, "errors": 1, "error_rate": 0.1}
    assert payload["agent_actions_by_type"][0]["action_type"] == "job_search"
    assert payload["intro_funnel"] == [
        {"status": "pending", "count": 5},
        {"status": "accepted", "count": 2},
    ]


def test_shape_observability_handles_empty() -> None:
    payload = _shape_observability(action_rows=[], funnel_rows=[], totals=None, window_days=30)
    assert payload["totals"] == {"agent_actions": 0, "errors": 0, "error_rate": 0.0}
    assert payload["agent_actions_by_type"] == []
    assert payload["intro_funnel"] == []


def test_shape_observability_null_avg_ms() -> None:
    payload = _shape_observability(
        action_rows=[{"action_type": "x", "total": 1, "avg_ms": None, "errors": 0}],
        funnel_rows=[],
        totals={"actions": 1, "errors": 0},
        window_days=7,
    )
    assert payload["agent_actions_by_type"][0]["avg_ms"] is None
