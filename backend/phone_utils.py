"""
Shared phone number normalization helper.

REAL GAP THIS ADDRESSES: Twilio sends caller ID in E.164 format
(+16125559999) on every Voice webhook. Staff enter resident phone
numbers into the app in whatever free-form shape they're given
(612-555-9999, (612) 555-9999, 6125559999 - all seen in real testing
this session). A caller-ID lookup that compares these directly would
almost never match, even for the exact same real phone number - not
because the feature is broken, but because the two sides were never
in a comparable format to begin with.

US-specific, honestly: assumes a 10-digit number (area code + 7
digits) or an 11-digit number with a leading country code 1 - correct
for PropWise AI's current scope (this app's compliance rules are already
US state-specific), but would need real extension for international
numbers if that scope ever changes. Returns None rather than guessing
at anything that doesn't cleanly fit one of those two shapes, since a
wrong normalization that happens to collide with a different real
resident's number would be a much worse outcome than simply failing
to match.
"""
import re


def normalize_phone(phone: str | None) -> str | None:
    """Returns a US phone number in E.164 format (+1XXXXXXXXXX), or None
    if the input can't be confidently normalized (too few/many digits,
    empty, etc.)."""
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return None
