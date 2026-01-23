"""Unit tests for literature_core.utils module.

Tests for:
- extract_first_author_surname(): handles various author name formats
- generate_citation_key(): generates BibTeX citation keys

These tests verify the fix for the BibTeX key generation bug where
"LastName, FirstName" format was incorrectly extracting the first name.
"""
from __future__ import annotations

import pytest
import sys
from pathlib import Path

# Add src to path for imports
_src_path = Path(__file__).parent.parent.parent.parent / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from literature_core.utils import extract_first_author_surname, generate_citation_key


class TestExtractFirstAuthorSurname:
    """Tests for extract_first_author_surname function."""

    # =========================================================================
    # Basic Name Formats
    # =========================================================================

    def test_lastname_firstname_format(self):
        """Test 'LastName, FirstName' format (the bug case)."""
        result = extract_first_author_surname("Smith, John")
        assert result == "smith"

    def test_firstname_lastname_format(self):
        """Test 'FirstName LastName' format."""
        result = extract_first_author_surname("John Smith")
        assert result == "smith"

    def test_single_name(self):
        """Test single name (no space)."""
        result = extract_first_author_surname("Aristotle")
        assert result == "aristotle"

    def test_lastname_initial_format(self):
        """Test 'LastName, J.' format."""
        result = extract_first_author_surname("Smith, J.")
        assert result == "smith"

    def test_lastname_initials_format(self):
        """Test 'LastName, J. K.' format."""
        result = extract_first_author_surname("O'Brien, J. K.")
        assert result == "obrien"

    # =========================================================================
    # Multi-Author Strings
    # =========================================================================

    def test_multiple_authors_and_separator(self):
        """Test 'Smith, J. and Doe, J.' format."""
        result = extract_first_author_surname("Smith, J. and Doe, J.")
        assert result == "smith"

    def test_multiple_authors_semicolon_separator(self):
        """Test 'Smith, J.; Doe, J.' format."""
        result = extract_first_author_surname("Smith, J.; Doe, J.")
        assert result == "smith"

    def test_multiple_authors_firstname_lastname(self):
        """Test 'John Smith and Jane Doe' format."""
        result = extract_first_author_surname("John Smith and Jane Doe")
        assert result == "smith"

    # =========================================================================
    # List Inputs
    # =========================================================================

    def test_list_of_dicts(self):
        """Test list of dicts with 'name' key."""
        authors = [{"name": "Smith, John"}, {"name": "Doe, Jane"}]
        result = extract_first_author_surname(authors)
        assert result == "smith"

    def test_list_of_dicts_firstname_lastname(self):
        """Test list of dicts with 'FirstName LastName' format."""
        authors = [{"name": "John Smith"}, {"name": "Jane Doe"}]
        result = extract_first_author_surname(authors)
        assert result == "smith"

    def test_list_of_strings(self):
        """Test list of plain strings."""
        authors = ["Smith, John", "Doe, Jane"]
        result = extract_first_author_surname(authors)
        assert result == "smith"

    def test_list_of_strings_firstname_lastname(self):
        """Test list of strings with 'FirstName LastName' format."""
        authors = ["John Smith", "Jane Doe"]
        result = extract_first_author_surname(authors)
        assert result == "smith"

    # =========================================================================
    # Author Objects (simulated)
    # =========================================================================

    def test_author_object_with_name_attribute(self):
        """Test Author object with .name attribute."""
        class MockAuthor:
            def __init__(self, name: str):
                self.name = name

        authors = [MockAuthor("Smith, John"), MockAuthor("Doe, Jane")]
        result = extract_first_author_surname(authors)
        assert result == "smith"

    def test_author_object_firstname_lastname(self):
        """Test Author object with 'FirstName LastName' format."""
        class MockAuthor:
            def __init__(self, name: str):
                self.name = name

        authors = [MockAuthor("John Smith")]
        result = extract_first_author_surname(authors)
        assert result == "smith"

    # =========================================================================
    # Edge Cases
    # =========================================================================

    def test_none_input(self):
        """Test None input returns empty string."""
        result = extract_first_author_surname(None)
        assert result == ""

    def test_empty_string(self):
        """Test empty string returns empty string."""
        result = extract_first_author_surname("")
        assert result == ""

    def test_empty_list(self):
        """Test empty list returns empty string."""
        result = extract_first_author_surname([])
        assert result == ""

    def test_list_with_empty_dict(self):
        """Test list with dict missing 'name' key."""
        authors = [{"id": 1}]
        result = extract_first_author_surname(authors)
        assert result == ""

    def test_special_characters_removed(self):
        """Test special characters are removed from surname."""
        result = extract_first_author_surname("Müller-Schmidt, Hans")
        # Only ASCII letters are kept
        assert result == "mllerschmidt"

    def test_whitespace_handling(self):
        """Test extra whitespace is handled."""
        result = extract_first_author_surname("  Smith  ,  John  ")
        assert result == "smith"


class TestGenerateCitationKey:
    """Tests for generate_citation_key function."""

    # =========================================================================
    # Basic Key Generation
    # =========================================================================

    def test_basic_key(self):
        """Test basic citation key generation."""
        key = generate_citation_key("Machine Learning", "Smith, John", 2023)
        assert key == "smith2023machine"

    def test_firstname_lastname_format(self):
        """Test with 'FirstName LastName' author format."""
        key = generate_citation_key("Machine Learning", "John Smith", 2023)
        assert key == "smith2023machine"

    def test_list_authors(self):
        """Test with list of author dicts."""
        authors = [{"name": "Smith, John"}, {"name": "Doe, Jane"}]
        key = generate_citation_key("Machine Learning", authors, 2023)
        assert key == "smith2023machine"

    # =========================================================================
    # Article Skipping
    # =========================================================================

    def test_skips_article_the(self):
        """Test 'the' is skipped in title."""
        key = generate_citation_key("The Art of Programming", "John Smith", 2020)
        assert key == "smith2020art"

    def test_skips_article_a(self):
        """Test 'a' is skipped in title."""
        key = generate_citation_key("A Study of AI", "John Smith", 2020)
        assert key == "smith2020study"

    def test_skips_article_an(self):
        """Test 'an' is skipped in title."""
        key = generate_citation_key("An Introduction to ML", "John Smith", 2020)
        assert key == "smith2020introduction"

    def test_skips_prepositions(self):
        """Test prepositions are skipped."""
        key = generate_citation_key("On the Nature of Things", "Lucretius", 50)
        assert key == "lucretius50nature"

    def test_skips_multiple_articles(self):
        """Test multiple leading articles are skipped."""
        key = generate_citation_key("The On To In Of", "Smith", 2020)
        # All common words skipped, so key might be empty for title or take first available
        # Looking at implementation, it will take first non-skip word
        assert key == "smith2020"  # No valid title word found

    # =========================================================================
    # Missing Data Handling
    # =========================================================================

    def test_no_year(self):
        """Test missing year."""
        key = generate_citation_key("Machine Learning", "Smith, John", None)
        assert key == "smithmachine"

    def test_no_authors(self):
        """Test missing authors uses 'unknown'."""
        key = generate_citation_key("Machine Learning", None, 2023)
        assert key == "unknown2023machine"

    def test_empty_authors(self):
        """Test empty authors string uses 'unknown'."""
        key = generate_citation_key("Machine Learning", "", 2023)
        assert key == "unknown2023machine"

    def test_no_title(self):
        """Test missing title."""
        key = generate_citation_key(None, "Smith, John", 2023)
        assert key == "smith2023"

    def test_empty_title(self):
        """Test empty title string."""
        key = generate_citation_key("", "Smith, John", 2023)
        assert key == "smith2023"

    def test_all_missing(self):
        """Test all parameters missing."""
        key = generate_citation_key(None, None, None)
        assert key == "unknown"

    # =========================================================================
    # Special Characters
    # =========================================================================

    def test_special_chars_in_title(self):
        """Test special characters are removed from title word."""
        key = generate_citation_key("C++ Programming", "Smith", 2020)
        assert key == "smith2020c"

    def test_special_chars_in_author(self):
        """Test special characters are removed from author."""
        key = generate_citation_key("Programming", "O'Brien, J.", 2020)
        assert key == "obrien2020programming"

    # =========================================================================
    # Regression Tests (Bug Fixes)
    # =========================================================================

    def test_regression_lastname_comma_firstname(self):
        """Regression test: 'Smith, John' should produce 'smith...' not 'john...'."""
        # This was the bug: split()[-1] on "Smith, John" gives "John"
        key = generate_citation_key("Test Paper", "Smith, John", 2023)
        assert key.startswith("smith"), f"Expected key starting with 'smith', got '{key}'"

    def test_regression_list_of_authors_lastname_first(self):
        """Regression test: List with 'LastName, First' should use LastName."""
        authors = [{"name": "Garcia, Maria"}, {"name": "Lee, David"}]
        key = generate_citation_key("Data Science", authors, 2024)
        assert key.startswith("garcia"), f"Expected key starting with 'garcia', got '{key}'"

    def test_regression_author_object_lastname_first(self):
        """Regression test: Author object with 'LastName, First' should use LastName."""
        class MockAuthor:
            def __init__(self, name: str):
                self.name = name

        authors = [MockAuthor("Wang, Wei")]
        key = generate_citation_key("Neural Networks", authors, 2024)
        assert key.startswith("wang"), f"Expected key starting with 'wang', got '{key}'"
