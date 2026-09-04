"""
Multi-language support for tenant-facing communications.

Genuinely missing before this - confirmed by searching the whole
codebase for any translation/language capability and finding none: no
tenant preferred-language field, no translation of notifications, no
language-awareness in any AI-generated tenant-facing text (the AI
Copilot FAQ, DIY troubleshooting guidance).

Two different mechanisms, deliberately not the same one:
- For AI-GENERATED text (the FAQ assistant, DIY troubleshooting
  guidance): language_instruction() below is appended to the existing
  system prompt, so Claude writes its answer directly in the
  resident's language. No extra API call, no translation step - the
  model already writes fluently in every language in SUPPORTED_LANGUAGES.
- For ALREADY-WRITTEN, static/templated text (notification titles and
  bodies, e.g. "Payment received", built as an f-string elsewhere in
  the app): translate_text() below makes a real, separate Claude call
  to translate that exact string, since there's no "generation" step
  to inject a language instruction into.

Deliberately NOT applied to legal documents (leases, late notices) -
this app already has an explicit, real principle (see
routers/documents.py's own docstring) that it does not generate legal
language; auto-translating a legal document carries real risk of a
translation error changing its legal meaning, which is a different
and much higher-stakes problem than translating a notification or a
chat answer. If a translated lease is ever wanted, that needs its own
deliberate, careful design - not a quiet reuse of this utility.
"""
import os

from anthropic import AsyncAnthropic

anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"

# Deliberately a curated, small list rather than "every language" - these
# are consistently the most common languages among US renters with
# limited English proficiency per Census/HUD LEP data, which is a
# reasonable, defensible starting set for a US-focused property app
# rather than an arbitrary one. Keyed by a short code stored on the
# user record; value is the real language name used both in the
# frontend picker and in prompts to Claude.
SUPPORTED_LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "zh": "Chinese (Simplified)",
    "vi": "Vietnamese",
    "tl": "Tagalog",
    "ar": "Arabic",
    "fr": "French",
    "pt": "Portuguese",
    "ru": "Russian",
    "ko": "Korean",
}


def language_instruction(preferred_language: str | None) -> str:
    """For AI-GENERATED responses - appended to an existing system
    prompt. Returns "" for English/unset, so callers can always safely
    concatenate this without an extra branch."""
    if not preferred_language or preferred_language == "en":
        return ""
    language_name = SUPPORTED_LANGUAGES.get(preferred_language)
    if not language_name:
        return ""
    return f"\n\nRespond in {language_name}, since that is this resident's preferred language."


async def translate_text(text: str, target_language: str) -> str:
    """For ALREADY-WRITTEN, static text (e.g. a notification body built
    as an f-string elsewhere in the app) - a real, separate translation
    call. Returns the original text unchanged if target_language is
    English/unset/unrecognized, or if the translation call itself fails
    - a notification arriving in the wrong language (but still
    genuinely readable in English) is a far better failure mode than
    one that silently never arrives because a translation call errored."""
    if not text or not target_language or target_language == "en":
        return text
    language_name = SUPPORTED_LANGUAGES.get(target_language)
    if not language_name:
        return text
    try:
        response = await anthropic_client.messages.create(
            model=MODEL,
            max_tokens=500,
            system=(
                f"Translate the given text into {language_name}. Respond with ONLY the "
                f"translation, no explanation, no quotation marks, preserving the original "
                f"meaning and tone exactly."
            ),
            messages=[{"role": "user", "content": text}],
        )
        translated = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        return translated.strip() or text
    except Exception:
        return text
