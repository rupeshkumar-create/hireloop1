from hireloop_api.services.public_profile_chat import _profile_context, _system_prompt


def test_profile_context_omits_private_contact() -> None:
    profile = {
        "display_name": "Alex",
        "contact": {"hidden": True, "email": None, "phone": None},
        "skills": ["Python"],
        "experience": [],
        "education": [],
    }
    ctx = _profile_context(profile)
    assert "Alex" in ctx
    assert '"contact_hidden": true' in ctx
    assert "secret@" not in ctx


def test_system_prompt_uses_display_name() -> None:
    prompt = _system_prompt({"display_name": "Priya Sharma"})
    assert "Priya Sharma" in prompt
    assert "Aarya" in prompt
