"""Canary tests: the db fixture must isolate EVERY service from the production DB.

These iterate all modules under src/services dynamically, so a newly added
service that binds get_session at import time can never silently escape the
test override again.
"""
import importlib
import pkgutil

import services


def _service_modules():
    for info in pkgutil.iter_modules(services.__path__):
        yield importlib.import_module(f"services.{info.name}")


class TestDatabaseIsolation:

    def test_every_service_module_gets_test_engine_sessions(self, db):
        """Any get_session reachable from a service must yield in-memory sessions."""
        checked = 0
        for mod in _service_modules():
            get_session = getattr(mod, "get_session", None)
            if get_session is None:
                continue
            with get_session() as session:
                url = str(session.get_bind().url)
                assert url == "sqlite:///:memory:", (
                    f"{mod.__name__}.get_session is bound to {url} — "
                    f"the db fixture is leaking to the production database"
                )
            checked += 1
        assert checked >= 5, "expected to find get_session in several services"

    def test_fts_get_engine_resolves_test_engine(self, db, test_engine):
        """literature_core.fts must see the test engine while the fixture is active."""
        from literature_core import fts

        assert fts.get_engine() is test_engine
