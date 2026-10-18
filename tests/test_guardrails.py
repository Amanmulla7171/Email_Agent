import pytest
from app.core.guardrails import (
    auto_heal_placeholders,
    find_unresolved_placeholders,
    enforce_email_guardrails,
    APPLICANT_FULL_NAME,
    APPLICANT_EMAIL,
    APPLICANT_PHONE,
    APPLICANT_LINKEDIN,
)

def test_auto_heal_applicant_placeholders():
    raw_body = (
        "Dear Nidhi,\n\n"
        "I am writing to express my interest in internship opportunities at Innovyq.\n\n"
        "Best regards,\n"
        "[Applicant Name]\n"
        "[Phone Number]\n"
        "[LinkedIn Profile]\n"
        "[Your Email]"
    )
    healed, subs = auto_heal_placeholders(raw_body, recipient_name="Nidhi")
    assert APPLICANT_FULL_NAME in healed
    assert APPLICANT_PHONE in healed
    assert APPLICANT_LINKEDIN in healed
    assert APPLICANT_EMAIL in healed
    assert "[Applicant Name]" not in healed
    assert "[Phone Number]" not in healed
    assert "[LinkedIn Profile]" not in healed
    assert len(subs) >= 4


def test_find_unresolved_placeholders():
    text_with_placeholders = "Please review on [Date] for [Company Name]."
    unresolved = find_unresolved_placeholders(text_with_placeholders)
    assert "[Date]" in unresolved
    assert "[Company Name]" in unresolved

    # Verify standard markdown links are NOT treated as placeholders
    text_with_markdown_link = "Check out [My Resume](https://example.com/resume.pdf) for details."
    unresolved_md = find_unresolved_placeholders(text_with_markdown_link)
    assert len(unresolved_md) == 0


def test_enforce_email_guardrails_blocks_unresolved():
    bad_body = (
        "Dear Hiring Team,\n\n"
        "I would love to join your company starting on [Start Date].\n\n"
        "Best regards,\n"
        "Aman Mulla"
    )
    with pytest.raises(ValueError) as excinfo:
        enforce_email_guardrails(bad_body, strict_raise=True)
    assert "GUARDRAIL VIOLATION" in str(excinfo.value)
    assert "[Start Date]" in str(excinfo.value)


def test_enforce_email_guardrails_heals_and_passes():
    body_with_known = (
        "Dear Recruiter,\n\n"
        "I am applying for the role.\n\n"
        "Best regards,\n"
        "[Your Name]\n"
        "[Contact Number]"
    )
    clean_body, actions = enforce_email_guardrails(body_with_known, strict_raise=True)
    assert "Aman Mulla" in clean_body
    assert "+91 9730971586" in clean_body
    assert "[Your Name]" not in clean_body
    assert len(actions) == 2
