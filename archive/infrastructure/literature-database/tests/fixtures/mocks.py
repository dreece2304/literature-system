"""Mock objects for testing external services."""
from typing import List, Dict, Any
from unittest.mock import MagicMock
from pathlib import Path
import json


class MockZoteroClient:
    """Mock pyzotero.Zotero client for testing."""

    def __init__(self, items: List[Dict] = None, collections: List[Dict] = None):
        self.items_data = items or []
        self.collections_data = collections or []
        self._call_count = {"items": 0, "collections": 0}

    def items(self, limit: int = 100, start: int = 0, **kwargs) -> List[Dict]:
        """Return mock items."""
        self._call_count["items"] += 1
        return self.items_data[start:start + limit]

    def collections(self, **kwargs) -> List[Dict]:
        """Return mock collections."""
        self._call_count["collections"] += 1
        return self.collections_data

    def top(self, **kwargs) -> List[Dict]:
        """Return top-level items."""
        return self.items_data

    def item(self, item_key: str) -> Dict:
        """Return a single item by key."""
        for item in self.items_data:
            if item.get("key") == item_key:
                return item
        return None

    def collection_items(self, collection_key: str, **kwargs) -> List[Dict]:
        """Return items in a collection."""
        # For simplicity, return all items
        return self.items_data

    @property
    def call_counts(self) -> Dict[str, int]:
        """Return number of times each method was called."""
        return self._call_count.copy()


class MockZoteroLocalAPI:
    """Mock Zotero local API responses."""

    def __init__(self, available: bool = True, items: List[Dict] = None):
        self.available = available
        self.items_data = items or []

    def is_available(self) -> bool:
        return self.available

    def get_items(self) -> List[Dict]:
        if not self.available:
            raise ConnectionError("Zotero local API not available")
        return self.items_data


class MockPDFExtractor:
    """Mock PDF extractor for testing."""

    def __init__(self, text: str = "Mock extracted text", metadata: Dict = None):
        self.text = text
        self.metadata = metadata or {
            "title": "Mock Title",
            "author": "Mock Author",
            "subject": "",
            "creator": "Mock Creator"
        }

    def extract_text(self, pdf_path: Path) -> str:
        """Return mock extracted text."""
        return self.text

    def extract_metadata(self, pdf_path: Path) -> Dict:
        """Return mock metadata."""
        return self.metadata

    def calculate_hash(self, pdf_path: Path) -> str:
        """Return mock file hash."""
        return "abc123def456" * 4  # 64 char fake SHA256


class MockSearchIndex:
    """Mock Whoosh search index for testing."""

    def __init__(self):
        self.documents = {}
        self._search_results = []

    def add_document(self, doc_id: str, content: Dict):
        """Add a document to the mock index."""
        self.documents[doc_id] = content

    def remove_document(self, doc_id: str):
        """Remove a document from the mock index."""
        self.documents.pop(doc_id, None)

    def search(self, query: str, limit: int = 10) -> List[Dict]:
        """Return mock search results."""
        if self._search_results:
            return self._search_results[:limit]
        # Simple mock: return all documents containing query string
        results = []
        for doc_id, content in self.documents.items():
            text = str(content).lower()
            if query.lower() in text:
                results.append({"id": doc_id, "score": 1.0, **content})
        return results[:limit]

    def set_search_results(self, results: List[Dict]):
        """Set predetermined search results for testing."""
        self._search_results = results

    def clear(self):
        """Clear all documents."""
        self.documents.clear()
        self._search_results.clear()


def load_mock_zotero_response(response_file: Path) -> Dict:
    """Load a mocked Zotero API response from a JSON file."""
    with open(response_file, 'r') as f:
        return json.load(f)


def create_mock_requests_response(
    status_code: int = 200,
    json_data: Any = None,
    text: str = "",
    headers: Dict = None
) -> MagicMock:
    """Create a mock requests.Response object."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = json_data
    mock_response.text = text
    mock_response.headers = headers or {}
    mock_response.ok = 200 <= status_code < 300
    mock_response.raise_for_status = MagicMock()
    if status_code >= 400:
        mock_response.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return mock_response
