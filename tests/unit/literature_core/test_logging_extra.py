"""Log records must render extra={...}, not silently drop it.

Dropping it is what made an Ollama outage look like a scoring result: the
warning said "MiniCheck call failed" while the exception text sat in extra=
and never reached the console.
"""
from __future__ import annotations

import logging

from literature_core.logging_config import DEFAULT_FORMAT, ExtraFormatter


def _render(**extra) -> str:
    record = logging.LogRecord(
        name="services.verification", level=logging.WARNING, pathname=__file__,
        lineno=1, msg="MiniCheck call failed", args=(), exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return ExtraFormatter(fmt=DEFAULT_FORMAT).format(record)


class TestExtraFormatter:
    def test_extra_fields_are_rendered(self):
        out = _render(error="ConnectError: connection refused", paper_id=110)
        assert "MiniCheck call failed" in out
        assert "error=ConnectError: connection refused" in out
        assert "paper_id=110" in out

    def test_message_unchanged_without_extra(self):
        out = _render()
        assert out.endswith("MiniCheck call failed")
        assert "|" in out  # the standard format separators survive

    def test_standard_record_attributes_are_not_leaked(self):
        out = _render(paper_id=7)
        for noise in ("pathname=", "levelno=", "msg=", "args="):
            assert noise not in out
