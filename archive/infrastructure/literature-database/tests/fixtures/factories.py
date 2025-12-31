"""Factory functions for creating test data."""
from typing import List
import random
import string

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# noqa: E402 - must add to path before importing
from src.models import (  # noqa: E402
    Paper, Author, Tag, Collection, Note, Citation, Manuscript, CitationLocation
)


def random_string(length: int = 10) -> str:
    """Generate a random string."""
    return ''.join(random.choices(string.ascii_lowercase, k=length))


def random_doi() -> str:
    """Generate a random DOI."""
    return f"10.{random.randint(1000, 9999)}/{random_string(8)}.{random.randint(2020, 2024)}"


class PaperFactory:
    """Factory for creating Paper instances."""

    _counter = 0

    @classmethod
    def create(
        cls,
        title: str = None,
        abstract: str = None,
        year: int = None,
        doi: str = None,
        authors: List["Author"] = None,
        tags: List["Tag"] = None,
        **kwargs
    ) -> Paper:
        """Create a Paper instance with optional overrides."""
        cls._counter += 1

        paper = Paper(
            title=title or f"Test Paper {cls._counter}: {random_string(20).title()}",
            abstract=abstract or f"This is the abstract for test paper {cls._counter}. " * 3,
            year=year or random.randint(2015, 2024),
            doi=doi or random_doi(),
            journal=kwargs.get("journal", "Test Journal"),
            volume=kwargs.get("volume", str(random.randint(1, 100))),
            issue=kwargs.get("issue", str(random.randint(1, 12))),
            pages=kwargs.get("pages", f"{random.randint(1, 100)}-{random.randint(101, 200)}"),
            read_status=kwargs.get("read_status", "unread"),
            full_text=kwargs.get("full_text"),
            word_count=kwargs.get("word_count"),
            file_path=kwargs.get("file_path"),
            file_hash=kwargs.get("file_hash"),
            citation_key=kwargs.get("citation_key"),
            citation_count=kwargs.get("citation_count", 0),
            **{k: v for k, v in kwargs.items() if k not in [
                "journal", "volume", "issue", "pages", "read_status",
                "full_text", "word_count", "file_path", "file_hash",
                "citation_key", "citation_count"
            ]}
        )

        if authors:
            paper.authors.extend(authors)
        if tags:
            paper.tags.extend(tags)

        return paper

    @classmethod
    def create_batch(cls, count: int, **kwargs) -> List[Paper]:
        """Create multiple Paper instances."""
        return [cls.create(**kwargs) for _ in range(count)]

    @classmethod
    def reset_counter(cls):
        """Reset the counter."""
        cls._counter = 0


class AuthorFactory:
    """Factory for creating Author instances."""

    _counter = 0

    FIRST_NAMES = ["John", "Jane", "Alice", "Bob", "Carol", "David", "Emma", "Frank"]
    LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis"]
    AFFILIATIONS = [
        "MIT", "Stanford University", "UC Berkeley", "Caltech",
        "University of Washington", "Harvard University", "Princeton University"
    ]

    @classmethod
    def create(
        cls,
        name: str = None,
        orcid: str = None,
        email: str = None,
        affiliation: str = None
    ) -> Author:
        """Create an Author instance."""
        cls._counter += 1

        if name is None:
            first = random.choice(cls.FIRST_NAMES)
            last = random.choice(cls.LAST_NAMES)
            name = f"{first} {last}"

        return Author(
            name=name,
            orcid=orcid or f"0000-{cls._counter:04d}-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}",
            email=email or f"{name.lower().replace(' ', '.')}@example.edu",
            affiliation=affiliation or random.choice(cls.AFFILIATIONS)
        )

    @classmethod
    def create_batch(cls, count: int) -> List[Author]:
        """Create multiple Author instances."""
        return [cls.create() for _ in range(count)]

    @classmethod
    def reset_counter(cls):
        cls._counter = 0


class TagFactory:
    """Factory for creating Tag instances."""

    _counter = 0

    CATEGORIES = ["method", "field", "type", "topic", "material"]
    COLORS = ["#3498db", "#e74c3c", "#2ecc71", "#f39c12", "#9b59b6"]

    TAG_NAMES = {
        "method": ["machine-learning", "dft", "molecular-dynamics", "monte-carlo"],
        "field": ["materials-science", "chemistry", "physics", "engineering"],
        "type": ["review", "research", "theory", "experimental"],
        "topic": ["ald", "mld", "thin-films", "catalysis"],
        "material": ["oxide", "nitride", "polymer", "metal"]
    }

    @classmethod
    def create(
        cls,
        name: str = None,
        category: str = None,
        color: str = None
    ) -> Tag:
        """Create a Tag instance."""
        cls._counter += 1

        if category is None:
            category = random.choice(cls.CATEGORIES)

        if name is None:
            name = random.choice(cls.TAG_NAMES.get(category, ["unknown"]))
            name = f"{name}-{cls._counter}"  # Make unique

        return Tag(
            name=name,
            category=category,
            color=color or random.choice(cls.COLORS)
        )

    @classmethod
    def create_batch(cls, count: int, category: str = None) -> List[Tag]:
        """Create multiple Tag instances."""
        return [cls.create(category=category) for _ in range(count)]

    @classmethod
    def reset_counter(cls):
        cls._counter = 0


class CollectionFactory:
    """Factory for creating Collection instances."""

    _counter = 0

    @classmethod
    def create(
        cls,
        name: str = None,
        description: str = None,
        parent: "Collection" = None
    ) -> Collection:
        """Create a Collection instance."""
        cls._counter += 1

        return Collection(
            name=name or f"Test Collection {cls._counter}",
            description=description or f"Description for collection {cls._counter}",
            parent_id=parent.id if parent else None
        )

    @classmethod
    def create_hierarchy(cls, depth: int = 2, breadth: int = 2) -> List[Collection]:
        """Create a hierarchy of collections."""
        collections = []

        def create_level(parent: Collection = None, current_depth: int = 0):
            if current_depth >= depth:
                return
            for i in range(breadth):
                coll = cls.create(
                    name=f"Level {current_depth} - Collection {i}",
                    parent=parent
                )
                collections.append(coll)
                create_level(coll, current_depth + 1)

        create_level()
        return collections

    @classmethod
    def reset_counter(cls):
        cls._counter = 0


class NoteFactory:
    """Factory for creating Note instances."""

    _counter = 0

    NOTE_TYPES = ["highlight", "comment", "summary"]

    @classmethod
    def create(
        cls,
        paper: Paper = None,
        content: str = None,
        note_type: str = None,
        page_number: int = None
    ) -> Note:
        """Create a Note instance."""
        cls._counter += 1

        note = Note(
            content=content or f"This is note {cls._counter} with some important observations.",
            note_type=note_type or random.choice(cls.NOTE_TYPES),
            page_number=page_number or random.randint(1, 20)
        )

        if paper:
            note.paper_id = paper.id

        return note

    @classmethod
    def reset_counter(cls):
        cls._counter = 0


class CitationFactory:
    """Factory for creating Citation (paper-to-paper) instances."""

    @classmethod
    def create(
        cls,
        citing_paper: Paper,
        cited_paper: Paper,
        context: str = None
    ) -> Citation:
        """Create a Citation instance."""
        return Citation(
            citing_paper_id=citing_paper.id,
            cited_paper_id=cited_paper.id,
            context=context or "...as shown in previous work [ref]..."
        )


class ManuscriptFactory:
    """Factory for creating Manuscript instances."""

    _counter = 0

    @classmethod
    def create(
        cls,
        name: str = None,
        project_path: str = None,
        tex_directory: str = None,
        bib_file: str = None,
        description: str = None
    ) -> Manuscript:
        """Create a Manuscript instance."""
        cls._counter += 1

        return Manuscript(
            name=name or f"Test Manuscript {cls._counter}",
            project_path=project_path or f"/home/user/project{cls._counter}",
            tex_directory=tex_directory or "paper/tex",
            bib_file=bib_file or "paper/bib/references.bib",
            description=description or f"Test manuscript {cls._counter} for unit testing"
        )

    @classmethod
    def reset_counter(cls):
        cls._counter = 0


class CitationLocationFactory:
    """Factory for creating CitationLocation instances."""

    _counter = 0

    SECTIONS = ["introduction", "methods", "results", "discussion", "background"]

    @classmethod
    def create(
        cls,
        paper: Paper = None,
        manuscript: Manuscript = None,
        citation_key: str = None,
        file_path: str = None,
        line_number: int = None,
        context: str = None,
        section_inferred: str = None,
        priority: str = None
    ) -> CitationLocation:
        """Create a CitationLocation instance."""
        cls._counter += 1

        location = CitationLocation(
            citation_key=citation_key or f"Author{2020 + cls._counter % 5}Paper",
            file_path=file_path or f"chapter{cls._counter % 5 + 1}.tex",
            line_number=line_number or random.randint(10, 500),
            context=context or f"...as demonstrated in previous work \\cite{{{citation_key or 'ref'}}}...",
            section_inferred=section_inferred or random.choice(cls.SECTIONS),
            priority=priority
        )

        if paper:
            location.paper_id = paper.id
        if manuscript:
            location.manuscript_id = manuscript.id

        return location

    @classmethod
    def create_batch(cls, count: int, manuscript: Manuscript = None) -> List[CitationLocation]:
        """Create multiple CitationLocation instances."""
        return [cls.create(manuscript=manuscript) for _ in range(count)]

    @classmethod
    def reset_counter(cls):
        cls._counter = 0


def reset_all_factories():
    """Reset all factory counters."""
    PaperFactory.reset_counter()
    AuthorFactory.reset_counter()
    TagFactory.reset_counter()
    CollectionFactory.reset_counter()
    NoteFactory.reset_counter()
    ManuscriptFactory.reset_counter()
    CitationLocationFactory.reset_counter()
