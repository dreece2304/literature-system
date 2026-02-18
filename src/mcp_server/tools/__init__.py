"""MCP Tools for Literature Management."""

from . import papers
from . import search
from . import external
from . import citations
from . import pdf
from . import collections
from . import notes
from . import import_export
from . import project
# Zotero removed per Phase 4 - user no longer needs sync
from . import browser_pdf
from . import discovery
from . import citation_network
from . import validation
from . import extraction

__all__ = [
    "papers", "search", "external", "citations", "pdf",
    "collections", "notes", "import_export", "project",
    "browser_pdf", "discovery", "citation_network", "validation", "extraction"
]
