from app.services.generation import (
    REFUSAL_TEXT,
    _build_preview,
    _parse_citations,
    _parse_verdict,
    _result,
    _strip_header,
    normalize_answer,
)

CHUNKS = [
    {"ticker": "TSLA", "filing_date": "2026-01-29", "section": "Item 8. Financial",
     "content": "Total revenues were $94,827 million in 2025."},
    {"ticker": "TSLA", "filing_date": "2026-01-29", "section": "Item 7. MD&A",
     "content": "Automotive revenues grew in 2025."},
]


def test_normalize_removes_markdown_and_dagger_citations():
    assert normalize_answer("**Revenue** was $94,827 million [1\u2020L5-L9]") == "Revenue was $94,827 million [1]"


def test_normalize_turns_dashes_into_hyphens():
    assert normalize_answer("FY2024\u20132025") == "FY2024-2025"


def test_parse_citations_keeps_only_valid_numbers():
    cites = _parse_citations("Revenue was $94,827 million [1][3].", CHUNKS)
    assert [c["number"] for c in cites] == [1]


def test_parse_citations_handles_grouped_form():
    cites = _parse_citations("Revenue grew [1, 2].", CHUNKS)
    assert [c["number"] for c in cites] == [1, 2]


def test_parse_verdict():
    assert _parse_verdict("SUPPORTED") == "SUPPORTED"
    assert _parse_verdict("UNSUPPORTED") == "UNSUPPORTED"
    assert _parse_verdict("NOT SUPPORTED") == "UNSUPPORTED"
    assert _parse_verdict("") is None


def test_preview_centers_on_dollar_figure():
    filler = "Automotive segment discussion. " * 20  # about 600 characters before the figure
    content = filler + "Total revenues were $94,827 million in 2025."
    preview = _build_preview("Revenue was $94,827 million [1].", content)
    assert "94,827" in preview


def test_strip_header_removes_company_line():
    content = "TESLA, INC. (TSLA) 10-K | Item 8. Financial\nThe body text."
    assert _strip_header(content) == "The body text."


def test_refusal_detected():
    res = _result(REFUSAL_TEXT, [])
    assert res["refused"] is True


def test_non_refusal_not_flagged():
    res = _result("Revenue was $94,827 million [1].", CHUNKS)
    assert res["refused"] is False