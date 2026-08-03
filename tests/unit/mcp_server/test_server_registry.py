"""Regression tests for MCP server tool-registry caching.

Audit finding: handle_list_tools claimed the registry is "built on first call
and cached" but rebuilt it on every call, re-registering every tool and
emitting a spurious 'Duplicate tool name' warning per tool on each repeated
tools/list request within a server process.
"""
import importlib

import pytest

# mcp_server/__init__.py re-exports the Server instance as `server`, which
# shadows the submodule on attribute-style imports — load the module directly.
server_module = importlib.import_module("mcp_server.server")


@pytest.fixture
def clean_registry(monkeypatch):
    """Reset the registry and tool-list cache around each test."""
    monkeypatch.setattr(server_module, "_ALL_TOOLS", None, raising=False)
    saved = dict(server_module.TOOL_REGISTRY)
    server_module.TOOL_REGISTRY.clear()
    yield
    server_module.TOOL_REGISTRY.clear()
    server_module.TOOL_REGISTRY.update(saved)


class TestToolRegistryCaching:
    async def test_registry_built_once(self, clean_registry, monkeypatch):
        calls = {"n": 0}
        real_list_tools = server_module.papers.list_tools

        async def counting_list_tools():
            calls["n"] += 1
            return await real_list_tools()

        monkeypatch.setattr(server_module.papers, "list_tools", counting_list_tools)

        tools_first = await server_module.build_tool_registry()
        tools_second = await server_module.build_tool_registry()

        assert calls["n"] == 1, (
            f"Tool modules iterated {calls['n']} times across two calls; registry must be cached"
        )
        assert tools_second is tools_first
        assert len(tools_first) > 0
        assert len(server_module.TOOL_REGISTRY) > 0

    async def test_repeated_list_tools_no_duplicate_warnings(self, clean_registry):
        from loguru import logger as loguru_logger

        messages: list[str] = []
        sink_id = loguru_logger.add(lambda m: messages.append(str(m)), level="WARNING")
        try:
            first = await server_module.handle_list_tools()
            second = await server_module.handle_list_tools()
        finally:
            loguru_logger.remove(sink_id)

        duplicate_warnings = [m for m in messages if "Duplicate tool name" in m]
        assert duplicate_warnings == [], (
            f"Repeated tools/list emitted {len(duplicate_warnings)} spurious duplicate warnings"
        )
        assert [t.name for t in first] == [t.name for t in second]
