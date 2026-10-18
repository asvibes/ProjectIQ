"""Reusable source-text verification for extracted quotations."""
from app.services.ingestion.sanitizer import normalize_for_comparison

MIN_QUOTE_CHARS = 10
MAX_QUOTE_CHARS = 2000


def is_quote_supported(
    source_text: str,
    quotation: str,
    *,
    min_chars: int = MIN_QUOTE_CHARS,
    max_chars: int = MAX_QUOTE_CHARS,
) -> bool:
    """Return whether a sufficiently informative quotation occurs in source text.

    Matching is case-insensitive and tolerates normalized whitespace,
    typography, and punctuation variants handled by the sanitizer.
    This verifies textual presence only; it does not establish truth.
    """
    if not isinstance(source_text, str) or not isinstance(quotation, str):
        return False
    if min_chars < 1 or max_chars < min_chars:
        raise ValueError("Invalid quotation length limits")
    if len(quotation) > max_chars:
        return False

    normalized_quote = normalize_for_comparison(quotation)
    if len(normalized_quote) < min_chars:
        return False

    normalized_source = normalize_for_comparison(source_text)
    return normalized_quote in normalized_source
