"""Sample data fixtures for testing.

Provides realistic paper, author, tag, collection, and note data
for use in tests.
"""


def get_sample_paper_data() -> dict:
    """Sample paper data matching real academic paper structure."""
    return {
        "title": "Atomic Layer Deposition of Aluminum Oxide: A Comprehensive Review",
        "abstract": (
            "Atomic layer deposition (ALD) of aluminum oxide (Al2O3) has become "
            "a critical process in semiconductor manufacturing, optical coatings, "
            "and energy storage applications. This review covers the fundamental "
            "reaction mechanisms, precursor chemistry, and emerging applications."
        ),
        "year": 2023,
        "doi": "10.1016/j.surfcoat.2023.001234",
        "arxiv_id": None,
        "journal": "Surface and Coatings Technology",
        "read_status": "unread",
        "rating": None,
    }


def get_sample_paper_with_arxiv() -> dict:
    """Sample arXiv preprint paper data."""
    return {
        "title": "Neural Networks for Materials Property Prediction",
        "abstract": (
            "We present a novel deep learning approach for predicting materials "
            "properties directly from crystal structure. Our model achieves "
            "state-of-the-art performance on multiple benchmark datasets."
        ),
        "year": 2024,
        "doi": None,
        "arxiv_id": "2401.12345",
        "journal": None,
        "read_status": "unread",
    }


def get_sample_authors() -> list[dict]:
    """List of sample author data."""
    return [
        {
            "name": "John Smith",
            "orcid": "0000-0001-2345-6789",
            "email": "john.smith@university.edu",
            "affiliation": "MIT",
        },
        {
            "name": "Jane Doe",
            "orcid": "0000-0002-3456-7890",
            "email": "jane.doe@stanford.edu",
            "affiliation": "Stanford University",
        },
        {
            "name": "Robert Johnson",
            "orcid": None,
            "email": None,
            "affiliation": "Caltech",
        },
    ]


def get_sample_tags() -> list[dict]:
    """List of sample tag data."""
    return [
        {"name": "ALD", "category": "method", "color": "#3498db"},
        {"name": "materials-science", "category": "field", "color": "#2ecc71"},
        {"name": "review", "category": "type", "color": "#e74c3c"},
        {"name": "machine-learning", "category": "method", "color": "#9b59b6"},
        {"name": "thin-films", "category": "topic", "color": "#f39c12"},
    ]


def get_sample_collection() -> dict:
    """Sample collection data."""
    return {
        "name": "Thesis Literature Review",
        "description": "Papers for my dissertation literature review",
    }


def get_sample_child_collection() -> dict:
    """Sample child collection for hierarchy testing."""
    return {
        "name": "Chapter 3 - Methods",
        "description": "Papers specifically for the methods chapter",
    }


def get_sample_note() -> dict:
    """Sample note data."""
    return {
        "content": "Key finding: Growth rate of 1.1 A/cycle at 200C",
        "note_type": "highlight",
        "page_number": 5,
        "position": None,
    }


def get_sample_notes() -> list[dict]:
    """Multiple sample notes for testing."""
    return [
        {
            "content": "Key finding: Growth rate of 1.1 A/cycle at 200C",
            "note_type": "highlight",
            "page_number": 5,
        },
        {
            "content": "Compare this with CVD results from Smith et al.",
            "note_type": "comment",
            "page_number": 8,
        },
        {
            "content": "This paper provides a comprehensive overview of ALD precursors.",
            "note_type": "summary",
            "page_number": None,
        },
    ]


def get_sample_bibtex() -> str:
    """Sample BibTeX content for testing import/export."""
    return """
@article{smith2023ald,
    title = {Atomic Layer Deposition Review},
    author = {Smith, John and Doe, Jane},
    journal = {Surface Science},
    year = {2023},
    volume = {456},
    pages = {1-20},
    doi = {10.1234/test.2023}
}

@inproceedings{doe2022neural,
    title = {Neural Network Approaches for Materials Science},
    author = {Doe, Jane},
    booktitle = {International Conference on Machine Learning},
    year = {2022},
    pages = {100-110}
}

@article{johnson2021cvd,
    title = {Chemical Vapor Deposition of Metal Oxides},
    author = {Johnson, Robert and Smith, John},
    journal = {Journal of Vacuum Science},
    year = {2021},
    volume = {39},
    number = {4},
    doi = {10.1116/6.0001234}
}
"""


def get_sample_tex_content() -> str:
    """Sample LaTeX content with citations for testing."""
    return r"""
\documentclass{article}
\usepackage{natbib}

\begin{document}

\section{Introduction}
Atomic layer deposition (ALD) has become crucial for thin film synthesis
\cite{smith2023ald}. Recent advances in machine learning have enabled
new approaches to materials prediction \cite{doe2022neural}.

\section{Background}
Chemical vapor deposition (CVD) remains important \cite{johnson2021cvd},
but ALD offers superior conformality \cite{smith2023ald}.

\section{Methods}
We follow the methodology established by \citet{doe2022neural} and
extend it using insights from \citep{johnson2021cvd, smith2023ald}.

\bibliographystyle{apalike}
\bibliography{references}
\end{document}
"""


def get_multiple_papers_data(count: int = 5) -> list[dict]:
    """Generate multiple paper data entries for batch testing."""
    papers = []
    topics = ["ALD", "CVD", "PVD", "MBE", "Sputtering"]
    journals = [
        "Surface Science",
        "Thin Solid Films",
        "Journal of Vacuum Science",
        "Applied Physics Letters",
        "Nature Materials",
    ]

    for i in range(count):
        papers.append({
            "title": f"Study of {topics[i % len(topics)]} Process Optimization",
            "abstract": f"This paper investigates the {topics[i % len(topics)]} process "
                        f"for thin film deposition. We demonstrate improved film quality "
                        f"through optimized parameters.",
            "year": 2020 + (i % 5),
            "doi": f"10.1234/test.{2020 + i}.{i:04d}",
            "journal": journals[i % len(journals)],
            "read_status": ["unread", "reading", "read"][i % 3],
        })

    return papers
