from hireloop_api.routes.chat import tool_status_label


def test_tool_status_label_is_specific_for_job_search() -> None:
    assert (
        tool_status_label("job_search", voice_mode=False) == "Searching roles in your market (~8s)…"
    )


def test_tool_status_label_is_spoken_for_voice() -> None:
    assert (
        tool_status_label("job_search", voice_mode=True)
        == "I'm searching roles in your market now (~8s)…"
    )


def test_tool_status_label_handles_unknown_tool() -> None:
    assert tool_status_label("unknown_tool", voice_mode=False) == "Working on your request…"
