"""Literature Core Utilities - Shared helper functions.

This module contains reusable utility functions for the literature management system.

Usage:
    from literature_core import extract_first_author_surname, generate_citation_key

    # Extract surname from various author formats
    surname = extract_first_author_surname("Smith, John")  # "smith"
    surname = extract_first_author_surname("John Smith")   # "smith"
    surname = extract_first_author_surname([{"name": "Smith, J."}])  # "smith"

    # Generate citation key
    key = generate_citation_key("Machine Learning", "Smith, John", 2023)  # "smith2023machine"
"""
from __future__ import annotations

import re


def extract_first_author_surname(authors: list | str | None) -> str:
    """Extract first author's surname handling various name formats.

    Handles formats:
    - "LastName, FirstName" (e.g., "Smith, John")
    - "FirstName LastName" (e.g., "John Smith")
    - "Smith, J. and Doe, J." (multi-author strings)
    - List of Author objects with .name attribute
    - List of dicts with "name" key
    - List of strings

    Args:
        authors: Author name(s) in various formats

    Returns:
        Lowercase surname of the first author, cleaned of special characters.
        Empty string if authors is None/empty.

    Examples:
        >>> extract_first_author_surname("Smith, John")
        'smith'
        >>> extract_first_author_surname("John Smith")
        'smith'
        >>> extract_first_author_surname([{"name": "Smith, J."}])
        'smith'
    """
    if not authors:
        return ""

    # Get first author as string
    first_author_str = ""
    if isinstance(authors, str):
        first_author_str = authors
    elif isinstance(authors, list) and len(authors) > 0:
        first_author = authors[0]
        if hasattr(first_author, 'name'):
            # Author object with .name attribute
            first_author_str = first_author.name
        elif isinstance(first_author, dict):
            # Dict with "name" key
            first_author_str = first_author.get("name", "")
        else:
            # Assume string
            first_author_str = str(first_author)

    if not first_author_str:
        return ""

    # Normalize multi-author separators
    cleaned = first_author_str.replace(" and ", ", ").replace(";", ",")

    # Get just the first author (everything before the first comma
    # in "LastName, First" or between authors in multi-author strings)
    first_part = cleaned.split(",")[0].strip()

    # Split into words
    words = first_part.split()

    if not words:
        return ""

    # For "LastName, First" format: first_part is already the surname
    # For "First LastName" format: last word is the surname
    # Since we split on comma, if original was "LastName, First",
    # first_part = "LastName". If original was "First LastName",
    # first_part = "First LastName" so we take the last word.
    surname = words[-1] if len(words) > 1 else words[0]

    # Clean special characters and lowercase
    return re.sub(r'[^a-zA-Z]', '', surname).lower()


def generate_citation_key(
    title: str | None,
    authors: list | str | None,
    year: int | None = None,
) -> str:
    """Generate BibTeX citation key from paper metadata.

    Format: firstauthorYEARfirstword
    Example: smith2023machine

    Skips common articles (a, an, the, etc.) when selecting the first title word.

    Args:
        title: Paper title
        authors: Author name(s) in any supported format (see extract_first_author_surname)
        year: Publication year

    Returns:
        Citation key string (e.g., "smith2023machine")

    Examples:
        >>> generate_citation_key("Machine Learning", "Smith, John", 2023)
        'smith2023machine'
        >>> generate_citation_key("The Art of Programming", "John Smith", 2020)
        'smith2020art'
        >>> generate_citation_key("A Study of AI", [{"name": "Doe, Jane"}], None)
        'doestudy'
    """
    # Extract first author surname
    first_author = extract_first_author_surname(authors)
    if not first_author:
        first_author = "unknown"

    # Extract first meaningful word from title (skip common articles)
    title_word = ""
    if title:
        skip_words = {"a", "an", "the", "on", "of", "for", "in", "to"}
        for word in title.split():
            clean = re.sub(r'[^a-zA-Z]', '', word).lower()
            if clean and clean not in skip_words:
                title_word = clean
                break

    year_str = str(year) if year else ""

    return f"{first_author}{year_str}{title_word}"
