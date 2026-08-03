"""Security-focused unit tests for PDFService.

Covers audit findings (2026-07-23):
- Path traversal via unsanitized arxiv_id/DOI in generate_filename
- Unbounded PDF download read into memory (no size cap)
- Non-http(s) URL schemes must not be fetched by _download_pdf
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add src to path for imports
_src_path = Path(__file__).parent.parent.parent.parent / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from services.pdf_service import PDFService  # noqa: E402


# ============================================================================
# generate_filename sanitization
# ============================================================================


class TestGenerateFilenameSanitization:
    """Filename components must never escape the PDF storage directory."""

    def test_benign_doi_unchanged(self):
        """Historical behavior for normal DOIs must be stable (existing files resolve)."""
        paper = {"id": 1, "doi": "10.1021/jacs.0c01234", "arxiv_id": ""}
        assert PDFService.generate_filename(paper) == "10.1021_jacs.0c01234.pdf"

    def test_benign_doi_with_colon_unchanged(self):
        paper = {"id": 1, "doi": "10.1000/ISBN:123", "arxiv_id": ""}
        assert PDFService.generate_filename(paper) == "10.1000_ISBN_123.pdf"

    def test_benign_arxiv_id_unchanged(self):
        paper = {"id": 2, "doi": "", "arxiv_id": "2301.12345v2"}
        assert PDFService.generate_filename(paper) == "arxiv_2301.12345v2.pdf"

    def test_fallback_to_paper_id(self):
        paper = {"id": 3, "doi": "", "arxiv_id": ""}
        assert PDFService.generate_filename(paper) == "paper_3.pdf"

    def test_malicious_arxiv_id_cannot_traverse(self, tmp_path):
        """The audit's failure scenario: arxiv_id from a poisoned external result."""
        paper = {"id": 4, "doi": "", "arxiv_id": "../../../../home/user/.config/evil"}
        filename = PDFService.generate_filename(paper)
        assert "/" not in filename
        assert "\\" not in filename
        target = (tmp_path / filename).resolve()
        assert target.is_relative_to(tmp_path.resolve())

    def test_malicious_doi_cannot_traverse(self, tmp_path):
        paper = {"id": 5, "doi": "..\\..\\windows\\system32\\evil", "arxiv_id": ""}
        filename = PDFService.generate_filename(paper)
        assert "/" not in filename
        assert "\\" not in filename
        target = (tmp_path / filename).resolve()
        assert target.is_relative_to(tmp_path.resolve())

    def test_control_characters_stripped(self):
        paper = {"id": 6, "doi": "", "arxiv_id": "2301.\n\x0012345"}
        filename = PDFService.generate_filename(paper)
        assert "\n" not in filename
        assert "\x00" not in filename

    def test_id_that_sanitizes_to_nothing_falls_back_to_paper_id(self):
        paper = {"id": 7, "doi": "", "arxiv_id": "..."}
        assert PDFService.generate_filename(paper) == "paper_7.pdf"


# ============================================================================
# _download_pdf: fakes for httpx
# ============================================================================


class _FakeResponse:
    """Fake httpx response supporting both .content and streaming access."""

    def __init__(self, status_code=200, headers=None, chunks=None):
        self.status_code = status_code
        self.headers = headers if headers is not None else {"content-type": "application/pdf"}
        self._chunks = chunks or []
        self.chunks_yielded = 0

    @property
    def content(self):
        # Non-streaming implementations buffer the full body here.
        return b"".join(self._chunks)

    async def aiter_bytes(self):
        for chunk in self._chunks:
            self.chunks_yielded += 1
            yield chunk


class _FakeStream:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *args):
        return False


def _fake_client_class(response):
    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, *args, **kwargs):
            return response

        def stream(self, method, url, *args, **kwargs):
            return _FakeStream(response)

    return _FakeClient


# ============================================================================
# _download_pdf size cap
# ============================================================================


class TestDownloadPdfSizeCap:
    """Downloads must be capped so a hostile endpoint cannot exhaust memory/disk."""

    async def test_rejects_content_length_over_cap(self, tmp_path, monkeypatch):
        import httpx

        monkeypatch.setattr(PDFService, "MAX_PDF_SIZE_BYTES", 1000, raising=False)
        response = _FakeResponse(
            headers={"content-type": "application/pdf", "content-length": "5000"},
            chunks=[b"%PDF" + b"x" * 4996],
        )
        monkeypatch.setattr(httpx, "AsyncClient", _fake_client_class(response))

        out = tmp_path / "out.pdf"
        result = await PDFService._download_pdf("https://example.org/big.pdf", out)
        assert result is False
        assert not out.exists()

    async def test_aborts_stream_over_cap(self, tmp_path, monkeypatch):
        import httpx

        monkeypatch.setattr(PDFService, "MAX_PDF_SIZE_BYTES", 1000, raising=False)
        chunks = [b"%PDF" + b"a" * 496, b"b" * 600, b"c" * 600]
        response = _FakeResponse(headers={"content-type": "application/pdf"}, chunks=chunks)
        monkeypatch.setattr(httpx, "AsyncClient", _fake_client_class(response))

        out = tmp_path / "out.pdf"
        result = await PDFService._download_pdf("https://example.org/big.pdf", out)
        assert result is False
        assert not out.exists()
        # The stream must be aborted mid-flight, not consumed to the end.
        assert response.chunks_yielded < len(chunks)

    async def test_small_pdf_download_succeeds(self, tmp_path, monkeypatch):
        import httpx

        content = b"%PDF-1.4 test-content"
        response = _FakeResponse(headers={"content-type": "application/pdf"}, chunks=[content])
        monkeypatch.setattr(httpx, "AsyncClient", _fake_client_class(response))

        out = tmp_path / "out.pdf"
        result = await PDFService._download_pdf("https://example.org/ok.pdf", out)
        assert result is True
        assert out.read_bytes() == content


# ============================================================================
# _download_pdf scheme check (SSRF hardening)
# ============================================================================


class TestDownloadPdfSchemeCheck:
    """Only http(s) URLs may be fetched (resolver-scraped URLs are untrusted)."""

    async def test_rejects_non_http_schemes_without_network(self, tmp_path, monkeypatch):
        import httpx

        class _Bomb:
            def __init__(self, *args, **kwargs):
                raise AssertionError("HTTP client must not be constructed for non-http(s) URL")

        monkeypatch.setattr(httpx, "AsyncClient", _Bomb)

        out = tmp_path / "out.pdf"
        assert await PDFService._download_pdf("file:///etc/passwd", out) is False
        assert await PDFService._download_pdf("ftp://internal.host/evil.pdf", out) is False
        assert not out.exists()
