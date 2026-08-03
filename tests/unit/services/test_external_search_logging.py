"""Tests that ExternalSearchService never writes diagnostics to stdout.

stdout is the JSON-RPC transport for the stdio MCP server; any print() in
this module corrupts protocol framing and can leak error detail to the
client (audit finding 2026-07-23). Diagnostics must go through the
literature_core logger instead.
"""
from __future__ import annotations

import inspect
import logging
import re
import sys
from pathlib import Path

# Add src to path for imports
_src_path = Path(__file__).parent.parent.parent.parent / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

import services.external_search as external_search  # noqa: E402
from services.external_search import ExternalSearchService  # noqa: E402


class TestNoStdoutDiagnostics:
    """No print() calls; diagnostics go to the configured logger."""

    def test_module_source_has_no_print_calls(self):
        source = inspect.getsource(external_search)
        matches = re.findall(r"(?<![\w.])print\(", source)
        assert matches == [], (
            f"found {len(matches)} print() call(s) in external_search.py - "
            "these corrupt the stdio JSON-RPC stream"
        )

    def test_module_uses_literature_core_logger(self):
        assert isinstance(external_search.logger, logging.Logger)

    async def test_find_pdf_url_error_path_writes_nothing_to_stdout(self, monkeypatch, capsys):
        import httpx

        class _ExplodingClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def get(self, *args, **kwargs):
                raise httpx.ConnectError("boom")

        monkeypatch.setattr(httpx, "AsyncClient", _ExplodingClient)

        service = ExternalSearchService()
        service.unpaywall_email = "test@example.org"
        result = await service.find_pdf_url("10.1234/example")

        assert result is None
        captured = capsys.readouterr()
        assert captured.out == ""
