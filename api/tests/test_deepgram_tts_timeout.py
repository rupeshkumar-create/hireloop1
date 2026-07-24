from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src/hireloop_api/services/voice/deepgram_tts.py"


def test_deepgram_tts_httpx_timeout_is_ten_seconds() -> None:
    text = SRC.read_text(encoding="utf-8")
    assert "timeout=10.0" in text or "timeout=10" in text
    assert "timeout=60.0" not in text
