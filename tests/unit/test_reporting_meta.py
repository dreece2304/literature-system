"""Meta-tests: the test reporter must never hide a failure.

Each test writes a deliberately broken test file under tests/, runs pytest on
it in a subprocess with the project's own config, and asserts the failure is
actually visible in the output. These lock in "green means green" — the Rich
reporter previously printed a checkmark on collection errors and swallowed
setup errors and tracebacks entirely.
"""
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).parent.parent
PROJECT_ROOT = TESTS_DIR.parent


@pytest.fixture
def run_pytest_on(tmp_path_factory):
    """Write a test file under tests/ and run pytest on just that file."""
    created = []

    def _run(source: str):
        # Must live under tests/ so tests/conftest.py (the Rich reporter) loads
        target = TESTS_DIR / "_meta_probe_test_file.py"
        target.write_text(source)
        created.append(target)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(target)],
            capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=120,
        )
        return proc

    yield _run
    for f in created:
        f.unlink(missing_ok=True)


class TestReporterNeverHidesFailures:

    def test_collection_error_is_visible_and_not_green(self, run_pytest_on):
        proc = run_pytest_on("import module_that_does_not_exist_xyz\n")
        output = proc.stdout + proc.stderr

        assert proc.returncode != 0
        assert "module_that_does_not_exist_xyz" in output
        assert "✓" not in output

    def test_setup_error_is_counted_and_traceback_shown(self, run_pytest_on):
        proc = run_pytest_on(
            "import pytest\n"
            "@pytest.fixture\n"
            "def broken():\n"
            "    raise RuntimeError('fixture exploded xyzzy')\n"
            "def test_uses_broken(broken):\n"
            "    pass\n"
            "def test_fine():\n"
            "    pass\n"
        )
        output = proc.stdout + proc.stderr

        assert proc.returncode != 0
        assert "xyzzy" in output, "setup error traceback must be shown"
        assert "✓" not in output, "must not show success icon when a setup failed"

    def test_assertion_failure_shows_traceback(self, run_pytest_on):
        proc = run_pytest_on(
            "def test_fails():\n"
            "    assert 1 + 1 == 3, 'arithmetic broke plugh'\n"
        )
        output = proc.stdout + proc.stderr

        assert proc.returncode != 0
        assert "plugh" in output, "assertion message must be shown"
