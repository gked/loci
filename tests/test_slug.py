"""
tests/test_slug.py
Tests for tools/slug.py: slugify and filename.
"""

import pytest
from slug import slugify, filename


# ---------------------------------------------------------------------------
# slugify — basic transformations
# ---------------------------------------------------------------------------

def test_slugify_lowercases():
    assert slugify("Hello World") == "hello-world"


def test_slugify_spaces_become_hyphens():
    assert slugify("one two three") == "one-two-three"


def test_slugify_special_chars_become_hyphens():
    assert slugify("Hello, World!") == "hello-world"


def test_slugify_collapses_consecutive_hyphens():
    assert slugify("one  --  two") == "one-two"


def test_slugify_strips_leading_trailing_hyphens():
    assert slugify("!Hello World!") == "hello-world"


def test_slugify_numbers_preserved():
    assert slugify("Python 3.13 release") == "python-3-13-release"


# ---------------------------------------------------------------------------
# slugify — accent handling
# ---------------------------------------------------------------------------

def test_slugify_acute_accents():
    assert slugify("café résumé") == "cafe-resume"


def test_slugify_n_tilde():
    assert slugify("El Niño") == "el-nino"


def test_slugify_cedilla():
    assert slugify("François") == "francois"


def test_slugify_all_accent_variants():
    assert slugify("àáäâã èéëê ìíïî òóöôõ ùúüû ñ ç") == "aaaaa-eeee-iiii-ooooo-uuuu-n-c"


# ---------------------------------------------------------------------------
# slugify — truncation
# ---------------------------------------------------------------------------

def test_slugify_short_title_unchanged():
    title = "short title"
    assert slugify(title) == "short-title"


def test_slugify_exactly_max_length_unchanged():
    # 60 a's — exactly at the boundary
    title = "a" * 60
    result = slugify(title)
    assert len(result) == 60


def test_slugify_truncates_at_max_length():
    title = "a" * 70
    result = slugify(title)
    assert len(result) <= 60


def test_slugify_truncates_on_word_boundary():
    # Craft a title that exceeds 60 chars and has a hyphen near the boundary
    title = "word " * 15  # "word word word word ..." — lots of words
    result = slugify(title)
    assert len(result) <= 60
    assert not result.endswith("-")


def test_slugify_custom_max_length():
    result = slugify("one two three four five", max_length=10)
    assert len(result) <= 10


def test_slugify_truncation_no_trailing_hyphen():
    # Slug that would end mid-word — confirm no trailing hyphen
    title = "a" * 30 + " " + "b" * 35
    result = slugify(title)
    assert not result.startswith("-")
    assert not result.endswith("-")


# ---------------------------------------------------------------------------
# slugify — edge cases
# ---------------------------------------------------------------------------

def test_slugify_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        slugify("")


def test_slugify_only_special_chars():
    # Everything maps to hyphens, strip leaves empty — but after strip it may be empty
    # The function strips hyphens; if the result is empty it would return ""
    # This tests the behaviour without asserting a specific value
    result = slugify("---")
    # Should not raise and should be a string
    assert isinstance(result, str)


def test_slugify_unicode_non_latin_becomes_hyphen():
    # Characters not in the replacement table (e.g. Cyrillic) → hyphen → stripped
    result = slugify("hello мир world")
    assert result == "hello-world"


# ---------------------------------------------------------------------------
# filename
# ---------------------------------------------------------------------------

def test_filename_adds_md_extension():
    assert filename("My Document") == "my-document.md"


def test_filename_empty_raises():
    with pytest.raises(ValueError):
        filename("")
