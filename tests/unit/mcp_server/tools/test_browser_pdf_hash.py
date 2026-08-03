"""Regression tests: browser_pdf must use the canonical PDF hash implementation.

Audit finding (2026-07-23): four independent SHA-256 file-hash implementations
existed; browser_pdf._compute_file_hash was a byte-identical copy of the
canonical PDFService.compute_file_hash and has been removed in favor of it.
"""


class TestBrowserPdfHashDeduplication:
    def test_no_local_hash_implementation(self):
        from mcp_server.tools import browser_pdf

        assert not hasattr(browser_pdf, "_compute_file_hash"), (
            "browser_pdf should delegate hashing to PDFService.compute_file_hash"
        )
        assert not hasattr(browser_pdf, "hashlib"), (
            "browser_pdf should not roll its own hashing"
        )

    def test_uses_canonical_pdfservice_hash(self):
        from mcp_server.tools import browser_pdf
        from services.pdf_service import PDFService

        assert browser_pdf.PDFService is PDFService
