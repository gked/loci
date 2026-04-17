"""
uid_generator.py
Generates a stable 8-character hex UID using UUID4.
Used by the Loci save skill to assign a unique identifier to each vault item.
"""

import uuid
import sys


def generate_uid() -> str:
    """Generate a random 8-character hex UID."""
    return uuid.uuid4().hex[:8]


if __name__ == "__main__":  # pragma: no cover
    # Can be called directly from CLI or by Claude Code
    # Usage: python uid_generator.py
    # Output: a3f9c2b1
    uid = generate_uid()
    print(uid)
