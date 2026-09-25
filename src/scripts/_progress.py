"""Shared console progress for the batch scripts.

Every batch runner grew its own Progress setup, and `enrich_pipeline` never
grew one at all - it used bare print() per paper, so a burst of log warnings
shredded the output into hundreds of lines. This is the single definition:

    with quiet_logging(), StageProgress("verify", len(ids)) as bar:
        for pid in ids:
            bar.item(f"paper {pid}")
            ...
            bar.done(accepted=1)

Usage:
    from scripts._progress import StageProgress, quiet_logging
"""
from __future__ import annotations

import logging
from contextlib import contextmanager

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)

# Libraries that log per-request chatter. Silenced only while a progress
# display owns the terminal; restored on exit so nothing is hidden globally.
QUIET_LOGGERS = ("services", "embeddings", "literature_core", "httpx", "httpcore")


@contextmanager
def quiet_logging(level: int = logging.ERROR):
    """Temporarily raise library log levels so they don't tear up the bar."""
    saved = {name: logging.getLogger(name).level for name in QUIET_LOGGERS}
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(level)
    try:
        from loguru import logger as loguru_logger  # services/embeddings use loguru
        for name in ("services", "embeddings"):
            loguru_logger.disable(name)
    except ImportError:
        loguru_logger = None
    try:
        yield
    finally:
        for name, lvl in saved.items():
            logging.getLogger(name).setLevel(lvl)
        if loguru_logger is not None:
            for name in ("services", "embeddings"):
                loguru_logger.enable(name)


class StageProgress:
    """Layered progress: a stage bar plus a detail line for the current item.

    The detail line is where per-item substeps land, so a long extraction
    shows what it is doing instead of looking hung.
    """

    def __init__(self, stage: str, total: int, console: Console | None = None):
        self.console = console or Console()
        self.stage = stage
        self.total = total
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=30),
            MofNCompleteColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=self.console,
            transient=False,
        )
        self._stage_task = None
        self._detail_task = None

    def __enter__(self) -> "StageProgress":
        self._progress.start()
        self._stage_task = self._progress.add_task(
            f"[cyan]{self.stage}", total=self.total)
        self._detail_task = self._progress.add_task("[dim]waiting...", total=1)
        return self

    def __exit__(self, *exc) -> None:
        self._progress.stop()

    def item(self, label: str, substeps: int = 1) -> None:
        """Start a new item; resets the detail line."""
        self._progress.reset(self._detail_task, total=substeps,
                             description=f"[dim]{label}")

    def step(self, message: str, advance: int = 1) -> None:
        """Advance the detail line within the current item."""
        self._progress.update(self._detail_task, advance=advance,
                              description=f"[dim]{message}")

    def done(self, **stats) -> None:
        """Finish the current item and advance the stage bar."""
        self._progress.update(self._stage_task, advance=1)
        if stats:
            summary = "  ".join(f"{k}={v}" for k, v in stats.items())
            self._progress.update(self._stage_task,
                                  description=f"[cyan]{self.stage}  [dim]{summary}")

    def note(self, message: str) -> None:
        """Print a line above the bars without disturbing them."""
        self._progress.console.print(message)
