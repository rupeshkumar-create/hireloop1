from hireloop_api.routes.voice import _sanitize_for_speech


def test_sanitize_for_speech_removes_markdown_and_emoji() -> None:
    text = "**Great fit** 🎯\n- Apply at [Razorpay](https://example.com)"

    spoken = _sanitize_for_speech(text)

    assert spoken == "Great fit. Apply at Razorpay"


def test_sanitize_for_speech_keeps_lpa_readable() -> None:
    text = "This role is around 30-40 LPA, hybrid in Bengaluru."

    spoken = _sanitize_for_speech(text)

    assert spoken == "This role is around 30-40 LPA, hybrid in Bengaluru."
