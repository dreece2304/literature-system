#!/usr/bin/env python
"""Clean test runner with rich progress display."""
import subprocess
import sys
import time
from pathlib import Path

try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
    from rich.table import Table
    from rich.live import Live
    from rich.panel import Panel
except ImportError:
    print("Installing rich...")
    subprocess.run([sys.executable, "-m", "pip", "install", "rich", "-q"])
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
    from rich.table import Table
    from rich.live import Live
    from rich.panel import Panel

console = Console()


def collect_tests(test_path: str = "tests/unit/") -> list[str]:
    """Collect all test names."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", test_path, "--collect-only", "-q"],
        capture_output=True,
        text=True
    )
    tests = []
    for line in result.stdout.strip().split("\n"):
        if "::" in line and not line.startswith(" "):
            tests.append(line.strip())
    return tests


def run_tests(test_path: str = "tests/unit/", timeout_per_test: int = 30):
    """Run tests with rich progress display."""
    console.print(Panel.fit("[bold blue]Collecting tests...[/]"))

    tests = collect_tests(test_path)
    total = len(tests)

    if total == 0:
        console.print("[red]No tests found![/]")
        return

    console.print(f"[green]Found {total} tests[/]\n")

    passed = 0
    failed = 0
    errors = 0
    failed_tests = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        refresh_per_second=10,
    ) as progress:

        task = progress.add_task("[cyan]Running tests...", total=total)

        for i, test in enumerate(tests):
            # Update description to show current test (truncated)
            short_name = test.split("::")[-1][:40]
            progress.update(task, description=f"[cyan]{short_name}...")

            # Run single test with timeout
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pytest", test, "-x", "--tb=no", "-q"],
                    capture_output=True,
                    text=True,
                    timeout=timeout_per_test
                )

                if result.returncode == 0:
                    passed += 1
                else:
                    failed += 1
                    failed_tests.append((test, "FAILED"))

            except subprocess.TimeoutExpired:
                errors += 1
                failed_tests.append((test, f"TIMEOUT ({timeout_per_test}s)"))
                console.print(f"\n[red]TIMEOUT:[/] {test}")
            except Exception as e:
                errors += 1
                failed_tests.append((test, str(e)))

            progress.update(task, advance=1)

    # Summary
    console.print("\n")
    table = Table(title="Test Results")
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right")

    table.add_row("[green]Passed[/]", str(passed))
    table.add_row("[red]Failed[/]", str(failed))
    table.add_row("[yellow]Errors/Timeout[/]", str(errors))
    table.add_row("[blue]Total[/]", str(total))

    console.print(table)

    if failed_tests:
        console.print("\n[bold red]Failed Tests:[/]")
        for test, reason in failed_tests[:20]:  # Show first 20
            console.print(f"  [red]✗[/] {test} - {reason}")
        if len(failed_tests) > 20:
            console.print(f"  ... and {len(failed_tests) - 20} more")


def run_tests_fast(test_path: str = "tests/unit/", timeout: int = 300):
    """Run all tests at once with live output parsing."""
    console.print(Panel.fit("[bold blue]Running tests...[/]"))

    process = subprocess.Popen(
        [sys.executable, "-m", "pytest", test_path, "--tb=short", "-v", "--timeout=30"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    passed = 0
    failed = 0
    current_test = ""

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}", justify="left"),
        TextColumn("[green]{task.fields[passed]}[/] passed"),
        TextColumn("[red]{task.fields[failed]}[/] failed"),
        TimeElapsedColumn(),
        console=console,
        refresh_per_second=4,
    ) as progress:

        task = progress.add_task("Starting...", passed=0, failed=0)

        for line in process.stdout:
            line = line.strip()

            if "PASSED" in line:
                passed += 1
                current_test = line.split("::")[1].split()[0] if "::" in line else line[:50]
            elif "FAILED" in line:
                failed += 1
                current_test = line.split("::")[1].split()[0] if "::" in line else line[:50]
            elif "::" in line and ("test_" in line or "Test" in line):
                current_test = line.split("::")[-1][:50]

            progress.update(task, description=f"[cyan]{current_test[:40]}[/]", passed=passed, failed=failed)

        process.wait()

    console.print(f"\n[bold]Results:[/] [green]{passed} passed[/], [red]{failed} failed[/]")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run tests with rich progress")
    parser.add_argument("path", nargs="?", default="tests/unit/", help="Test path")
    parser.add_argument("--fast", action="store_true", help="Run all tests at once (faster)")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout per test in seconds")

    args = parser.parse_args()

    if args.fast:
        run_tests_fast(args.path)
    else:
        run_tests(args.path, args.timeout)
