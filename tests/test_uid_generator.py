"""
tests/test_uid_generator.py
Tests for tools/uid_generator.py: generate_uid.
"""

import re
from loci.tools.uid_generator import generate_uid


def test_generate_uid_is_8_chars():
    assert len(generate_uid()) == 8


def test_generate_uid_is_lowercase_hex():
    uid = generate_uid()
    assert re.fullmatch(r"[0-9a-f]{8}", uid), f"Not a lowercase hex string: {uid!r}"


def test_generate_uid_is_unique():
    uids = {generate_uid() for _ in range(1000)}
    assert len(uids) == 1000
