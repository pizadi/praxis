from app.core.search import like_contains


def test_like_contains_escapes_wildcards_and_backslash():
    assert like_contains("  a_b%c\\d  ") == "%a\\_b\\%c\\\\d%"


def test_like_contains_preserves_ordinary_text():
    assert like_contains(" نیما ") == "%نیما%"
