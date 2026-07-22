from hireloop_api.services.chat_stream import (
    career_interview_completion_event,
    sse_career_interview_metadata,
    sse_done,
    sse_error,
    sse_event,
    sse_status,
    sse_text,
)


def test_sse_event_roundtrip() -> None:
    assert sse_status("Thinking…") == 'data: {"status": "Thinking…"}\n\n'
    assert sse_text("hi") == 'data: {"text": "hi"}\n\n'
    assert sse_error("boom") == 'data: {"error": "boom"}\n\n'
    assert sse_done() == "data: [DONE]\n\n"
    custom = sse_event({"jobs": 3})
    assert '"jobs": 3' in custom


def test_sse_career_interview_metadata_signals_coverage_complete() -> None:
    assert sse_career_interview_metadata(coverage_complete=True) == (
        'data: {"metadata": {"career_interview": {"coverage_complete": true}}}\n\n'
    )


def test_career_interview_completion_event_requires_successful_private_wrap_reply() -> None:
    expected = sse_career_interview_metadata(coverage_complete=True)

    assert (
        career_interview_completion_event(
            career_interview_mode=True,
            should_wrap=True,
            reply_persisted=True,
        )
        == expected
    )
    assert (
        career_interview_completion_event(
            career_interview_mode=False,
            should_wrap=True,
            reply_persisted=True,
        )
        is None
    )
    assert (
        career_interview_completion_event(
            career_interview_mode=True,
            should_wrap=False,
            reply_persisted=True,
        )
        is None
    )
    assert (
        career_interview_completion_event(
            career_interview_mode=True,
            should_wrap=True,
            reply_persisted=False,
        )
        is None
    )
