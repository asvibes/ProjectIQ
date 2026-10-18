import pytest

from app.services.verification.quote_checker import is_quote_supported


def test_accepts_exact_quotation():
    assert is_quote_supported(
        "The supplier must deliver all equipment within 30 days.",
        "The supplier must deliver all equipment within 30 days.",
    )


def test_accepts_case_and_whitespace_variations():
    assert is_quote_supported(
        "The Supplier   must deliver all equipment within 30 days.",
        "the supplier must deliver all equipment within 30 days.",
    )


def test_rejects_quotation_not_present_in_source():
    assert not is_quote_supported(
        "The supplier must deliver equipment within 30 days.",
        "The supplier must deliver equipment within 10 days.",
    )


@pytest.mark.parametrize("quotation", ["", "the", "ISO 9001"])
def test_rejects_empty_or_short_quotations(quotation):
    assert not is_quote_supported("ISO 9001 certification is required.", quotation)


def test_rejects_quotation_exceeding_maximum_length():
    assert not is_quote_supported("x" * 3000, "x" * 2001)


def test_rejects_non_string_inputs():
    assert not is_quote_supported(None, "A sufficiently long quotation.")
    assert not is_quote_supported("A sufficiently long source quotation.", None)


def test_rejects_quote_when_source_is_empty():
    assert not is_quote_supported("", "A sufficiently long quotation.")


def test_invalid_length_limits_raise_value_error():
    with pytest.raises(ValueError):
        is_quote_supported("Some source text", "Some quotation", min_chars=20, max_chars=10)
