"""
slug.py
Converts a title string into a filesystem-safe slug for Loci filenames.

Rules:
- Lowercase
- Replace spaces and punctuation with hyphens; letters and digits in any
  script are kept (a Cyrillic title keeps its words rather than collapsing
  to whatever digits it contains)
- Strip leading/trailing hyphens
- Collapse consecutive hyphens
- Truncate at 60 characters (on word boundary where possible)
"""

import re
import sys


def slugify(title: str, max_length: int = 60) -> str:
    """Convert a title string to a URL/filename-safe slug."""
    if not title:
        raise ValueError("Title cannot be empty")

    # Lowercase
    slug = title.lower()

    # Replace accented characters with ASCII equivalents
    replacements = {
        'á': 'a', 'à': 'a', 'ä': 'a', 'â': 'a', 'ã': 'a',
        'é': 'e', 'è': 'e', 'ë': 'e', 'ê': 'e',
        'í': 'i', 'ì': 'i', 'ï': 'i', 'î': 'i',
        'ó': 'o', 'ò': 'o', 'ö': 'o', 'ô': 'o', 'õ': 'o',
        'ú': 'u', 'ù': 'u', 'ü': 'u', 'û': 'u',
        'ñ': 'n', 'ç': 'c',
    }
    for char, replacement in replacements.items():
        slug = slug.replace(char, replacement)

    # Replace anything that isn't a letter or digit with a hyphen. \w is
    # Unicode-aware, so non-Latin scripts survive; underscore is \w too and is
    # listed explicitly so it becomes a hyphen like other punctuation.
    slug = re.sub(r'[\W_]+', '-', slug)

    # Strip leading/trailing hyphens
    slug = slug.strip('-')

    # Truncate at max_length, trying to break on a word boundary
    if len(slug) > max_length:
        truncated = slug[:max_length]
        # Find last hyphen before max_length to avoid cutting mid-word
        last_hyphen = truncated.rfind('-')
        if last_hyphen > max_length // 2:
            truncated = truncated[:last_hyphen]
        slug = truncated.strip('-')

    return slug


def filename(title: str) -> str:
    """
    Generate a full Loci filename from title.

    Args:
        title: The item title

    Returns:
        e.g. "why-i-left-twitter.md"
    """
    return f"{slugify(title)}.md"


if __name__ == "__main__":  # pragma: no cover
    # Usage: python slug.py "Why I Left Twitter"
    # Output: why-i-left-twitter.md
    if len(sys.argv) < 2:
        print("Usage: python slug.py <title>")
        sys.exit(1)

    title = sys.argv[1]
    print(filename(title))
