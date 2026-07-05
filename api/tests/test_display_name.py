from hireloop_api.services.display_name import pick_display_name, sanitize_display_name


def test_sanitize_display_name_strips_contact_prefix() -> None:
    assert sanitize_display_name("Contact Vivek Kumar") == "Vivek Kumar"
    assert sanitize_display_name("contact  Jane Doe") == "Jane Doe"


def test_pick_display_name_sanitizes_linkedin_junk() -> None:
    assert (
        pick_display_name(
            user_full_name="Contact Vivek Kumar",
            linkedin_full_name="Contact Vivek Kumar",
        )
        == "Vivek Kumar"
    )
