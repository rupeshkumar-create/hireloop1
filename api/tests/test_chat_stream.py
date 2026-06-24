from hireloop_api.services.chat_stream import sse_done, sse_error, sse_event, sse_status, sse_text


def test_sse_event_roundtrip() -> None:
    assert sse_status("Thinking…") == 'data: {"status": "Thinking…"}\n\n'
    assert sse_text("hi") == 'data: {"text": "hi"}\n\n'
    assert sse_error("boom") == 'data: {"error": "boom"}\n\n'
    assert sse_done() == "data: [DONE]\n\n"
    custom = sse_event({"jobs": 3})
    assert '"jobs": 3' in custom
