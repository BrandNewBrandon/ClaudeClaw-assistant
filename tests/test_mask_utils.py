from app.mask_utils import mask_token


def test_mask_token_none():
    assert mask_token(None) == "(not set)"


def test_mask_token_empty():
    assert mask_token("") == "(not set)"


def test_mask_token_short():
    assert mask_token("abc") == "****"


def test_mask_token_normal():
    result = mask_token("1234567890abcdef")
    assert result == "****...cdef"
    assert "1234" not in result


def test_mask_token_custom_visible():
    result = mask_token("1234567890", visible_chars=6)
    assert result == "****...567890"
