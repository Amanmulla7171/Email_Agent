"""
Strict Email Guardrails and Content Verification Engine.

Prevents and eliminates unpopulated placeholders (e.g. [Applicant Name], [Phone Number],
[LinkedIn Profile], [Your Name]) from email drafts and outgoing emails.
Enforces that every outgoing email contains real, concrete information.
"""

import re
from typing import Tuple, List, Optional

# Verified applicant profile details
APPLICANT_FULL_NAME = "Aman Mulla"
APPLICANT_EMAIL = "amanmulla4020@gmail.com"
APPLICANT_PHONE = "+91 9730971586"
APPLICANT_LINKEDIN = "https://www.linkedin.com/in/aman-mulla"
APPLICANT_GITHUB = "https://github.com/amanmulla"

APPLICANT_SIGNATURE_BLOCK = (
    "Aman Mulla\n"
    "📧 amanmulla4020@gmail.com\n"
    "📱 +91 9730971586\n"
    "LinkedIn: https://www.linkedin.com/in/aman-mulla\n"
    "GitHub: https://github.com/amanmulla"
)


# Known placeholder patterns mapped to concrete values
PLACEHOLDER_SUBSTITUTIONS = [
    # Applicant name variants
    (re.compile(r"\[\s*(?:applicant|candidate|your|my|sender|full)?\s*name\s*\]", re.IGNORECASE), APPLICANT_FULL_NAME),
    # Phone number variants
    (re.compile(r"\[\s*(?:your\s+)?phone(?:\s*number)?\s*\]", re.IGNORECASE), APPLICANT_PHONE),
    (re.compile(r"\[\s*(?:mobile|contact)(?:\s*number)?\s*\]", re.IGNORECASE), APPLICANT_PHONE),
    # Email variants
    (re.compile(r"\[\s*(?:your\s+)?email(?:\s*address)?\s*\]", re.IGNORECASE), APPLICANT_EMAIL),
    # Social links
    (re.compile(r"\[\s*linkedin(?:\s*profile|\s*url|\s*link)?\s*\]", re.IGNORECASE), f"LinkedIn: {APPLICANT_LINKEDIN}"),
    (re.compile(r"\[\s*github(?:\s*profile|\s*url|\s*link)?\s*\]", re.IGNORECASE), f"GitHub: {APPLICANT_GITHUB}"),
    (re.compile(r"\[\s*(?:portfolio|website)(?:\s*url|\s*link)?\s*\]", re.IGNORECASE), f"Portfolio: {APPLICANT_GITHUB}"),
    # Document references
    (re.compile(r"\[\s*(?:resume|cv)(?:\s*link|\s*attachment)?\s*\]", re.IGNORECASE), "attached resume (Aman_Mulla_Resume.pdf)"),
]

# Pattern for unpopulated standalone bracket placeholders (excluding markdown links like [text](url))
UNRESOLVED_PLACEHOLDER_REGEX = re.compile(r"\[(?!\s*\])[A-Za-z][A-Za-z0-9\s/_\-]{1,50}\](?!\s*\()", re.IGNORECASE)


def auto_heal_placeholders(text: str, recipient_name: Optional[str] = None) -> Tuple[str, List[str]]:
    """
    Scans text for known placeholder patterns and replaces them with concrete applicant data.

    Args:
        text: Email body or subject string.
        recipient_name: Optional recipient name to replace [Recipient Name] placeholders.

    Returns:
        Tuple of (healed_text, list_of_substitutions_made).
    """
    substitutions_made = []
    healed = text

    # Handle recipient placeholders if provided
    if recipient_name and recipient_name.strip():
        recip_clean = recipient_name.strip()
        recip_pat = re.compile(r"\[\s*(?:recipient|hiring\s*manager|contact|recruiter)(?:\s*name)?\s*\]", re.IGNORECASE)
        matches = recip_pat.findall(healed)
        if matches:
            for m in matches:
                substitutions_made.append(f"{m} -> {recip_clean}")
            healed = recip_pat.sub(recip_clean, healed)

    # Normalize markdown links e.g. [email](mailto:email) -> email, [url](url) -> url
    healed = re.sub(r"\[([^\]]+)\]\(mailto:[^\)]+\)", r"\1", healed)
    healed = re.sub(r"\[(https?://[^\]]+)\]\([^\)]+\)", r"\1", healed)

    # Replace known applicant placeholders
    for pattern, replacement in PLACEHOLDER_SUBSTITUTIONS:
        matches = pattern.findall(healed)
        if matches:
            for m in matches:
                substitutions_made.append(f"{m} -> {replacement}")
            healed = pattern.sub(replacement, healed)

    return healed, substitutions_made


def find_unresolved_placeholders(text: str) -> List[str]:
    """
    Finds any remaining bracket placeholders in text that are not part of markdown links.

    Args:
        text: Text to check.

    Returns:
        List of matched placeholder strings (e.g. ['[Date]', '[Company Name]']).
    """
    matches = UNRESOLVED_PLACEHOLDER_REGEX.findall(text)
    # Ensure there is alphabetical content (avoids matching pure numbers or punctuation)
    placeholders = [m for m in matches if any(c.isalpha() for c in m)]
    return placeholders


def enforce_email_guardrails(
    body: str,
    recipient_name: Optional[str] = None,
    auto_heal: bool = True,
    strict_raise: bool = True,
) -> Tuple[str, List[str]]:
    """
    Validates and sanitizes email body against placeholders.
    1. Replaces known placeholders with verified applicant data.
    2. Strictly verifies that NO remaining placeholders exist.
    3. Raises ValueError if unpopulated placeholders remain and strict_raise is True.

    Args:
        body: The email body text.
        recipient_name: Recipient's name for recipient placeholder substitution.
        auto_heal: Whether to substitute known placeholders automatically.
        strict_raise: If True, raises ValueError on unresolved placeholders.

    Returns:
        Tuple of (clean_body, actions_taken).

    Raises:
        ValueError: If strict_raise is True and unresolved placeholders remain.
    """
    actions = []
    clean_body = body

    if auto_heal:
        clean_body, subs = auto_heal_placeholders(clean_body, recipient_name)
        actions.extend(subs)

    # Check for remaining unpopulated placeholders
    unresolved = find_unresolved_placeholders(clean_body)
    if unresolved:
        unique_unresolved = sorted(list(set(unresolved)))
        err_msg = (
            f"GUARDRAIL VIOLATION: Unpopulated placeholder(s) detected in email body: {', '.join(unique_unresolved)}. "
            "Outgoing emails must NEVER contain placeholder brackets like [Applicant Name], [Phone Number], or [Date]. "
            "Please provide real, concrete information."
        )
        if strict_raise:
            raise ValueError(err_msg)
        else:
            actions.append(f"WARNING: Unresolved placeholders: {', '.join(unique_unresolved)}")

    return clean_body, actions
