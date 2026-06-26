from hireloop_api.agents.aarya.agent import _detect_hinglish


def test_detect_hinglish_devanagari() -> None:
    assert _detect_hinglish("मुझे job chahiye")


def test_detect_hinglish_romanized() -> None:
    assert _detect_hinglish("kya salary hai bhai")


def test_detect_hinglish_english_only() -> None:
    assert not _detect_hinglish("find me backend jobs in Bengaluru")
