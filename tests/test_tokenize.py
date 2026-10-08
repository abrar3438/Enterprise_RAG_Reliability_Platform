from app.services.tokenize import tokenize


def test_stopwords_removed():
    assert "what" not in tokenize("What was the revenue?")
    assert "revenue" in tokenize("What was the revenue?")


def test_plural_stripped():
    assert "revenue" in tokenize("revenues")


def test_possessive_stripped():
    assert tokenize("Tesla's") == ["tesla"]


def test_single_characters_dropped():
    assert "x" not in tokenize("x y 2025")
    assert "2025" in tokenize("x y 2025")