from hireloop_api.agents.aarya.agent import _detect_likely_intent


def test_chit_chat_intent() -> None:
    assert _detect_likely_intent("Hello!") == "chit_chat"
    assert _detect_likely_intent("Thanks Aarya") == "chit_chat"
    assert _detect_likely_intent("What can you do?") == "chit_chat"


def test_job_search_still_detected() -> None:
    assert _detect_likely_intent("Find me backend jobs in Bangalore") == "job_search"
