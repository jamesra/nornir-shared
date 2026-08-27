"""Structured phase timing and optional cProfile capture for Nornir packages."""

from __future__ import annotations

import cProfile
import json
import os
import pstats
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from nornir_shared.tasktimer import TaskTimer

_ENV_LOG_PATH = "NORNIR_PHASE_PROFILE_LOG"
_ENV_PROFILE_PATH = "NORNIR_PHASE_PROFILE_PSTATS"
_ENV_SESSION_ID = "NORNIR_PHASE_PROFILE_SESSION"
_ENV_RUN_ID = "NORNIR_PHASE_PROFILE_RUN_ID"


def _default_log_path() -> Path | None:
    configured = os.environ.get(_ENV_LOG_PATH, "").strip()
    if not configured:
        return None
    return Path(configured)


def _default_profile_path() -> Path | None:
    configured = os.environ.get(_ENV_PROFILE_PATH, "").strip()
    if not configured:
        return None
    return Path(configured)


class PhaseProfiler:
    """Record phase timings to NDJSON and optional cProfile snapshots."""

    _session_id: str
    _run_id: str
    _log_path: Path | None
    _profile_path: Path | None
    _timer: TaskTimer
    _active_profile: cProfile.Profile | None
    _seq_counters: dict[str, int]

    def __init__(
            self,
            *,
            session_id: str | None = None,
            log_path: Path | str | None = None,
            profile_path: Path | str | None = None,
            run_id: str | None = None,
            enabled: bool = True,
    ) -> None:
        self._session_id = (
            session_id
            or os.environ.get(_ENV_SESSION_ID, "").strip()
            or "nornir"
        )
        self._run_id = (
            run_id
            or os.environ.get(_ENV_RUN_ID, "").strip()
            or "default"
        )
        resolved_log = Path(log_path) if log_path is not None else _default_log_path()
        resolved_profile = (
            Path(profile_path) if profile_path is not None else _default_profile_path()
        )
        self._log_path = resolved_log
        self._profile_path = resolved_profile
        self._enabled = enabled and self._log_path is not None
        self._timer = TaskTimer()
        self._active_profile = None
        self._seq_counters = {}

    @property
    def enabled(self) -> bool:
        """True when structured NDJSON logging is active."""
        return self._enabled

    @property
    def log_path(self) -> Path | None:
        """Configured NDJSON log path, if any."""
        return self._log_path

    @property
    def profile_path(self) -> Path | None:
        """Configured cProfile output path, if any."""
        return self._profile_path

    @property
    def elapsed_times(self) -> dict[str, float]:
        """Accumulated phase wall times in seconds from :meth:`phase`."""
        return self._timer.ElapsedTimes

    def next_seq(self, name: str = "default") -> int:
        """Return a monotonic sequence number for correlating multi-step work."""
        value = self._seq_counters.get(name, 0) + 1
        self._seq_counters[name] = value
        return value

    def log_event(
            self,
            *,
            hypothesis_id: str,
            location: str,
            message: str,
            data: dict[str, Any] | None = None,
            run_id: str | None = None,
    ) -> None:
        """Append one NDJSON record when profiling is enabled."""
        if not self._enabled or self._log_path is None:
            return
        payload = {
            "sessionId": self._session_id,
            "runId": run_id or self._run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            # pid/tid distinguish parent from pool workers appending to one log file.
            "pid": os.getpid(),
            "tid": threading.get_ident(),
            "timestamp": int(time.time() * 1000),
        }
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._log_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, default=str) + "\n")
        except OSError:
            pass

    @contextmanager
    def phase(
            self,
            hypothesis_id: str,
            location: str,
            phase_name: str,
            **extra: Any,
    ) -> Iterator[None]:
        """Time a code block and log start/end records with elapsed milliseconds."""
        task_key = f"{location}:{phase_name}"
        self.log_event(
            hypothesis_id=hypothesis_id,
            location=location,
            message=f"{phase_name}:start",
            data=extra,
        )
        self._timer.Start(task_key)
        try:
            yield
        finally:
            self._timer.End(task_key, print_elapsed=False)
            elapsed_ms = self._timer.ElapsedTimes.get(task_key, 0.0) * 1000.0
            self.log_event(
                hypothesis_id=hypothesis_id,
                location=location,
                message=f"{phase_name}:end",
                data={**extra, "elapsed_ms": round(elapsed_ms, 3)},
            )

    def start_cprofile(self, tag: str) -> None:
        """Begin a cProfile capture tagged for the next :meth:`stop_cprofile` call."""
        if self._profile_path is None:
            return
        self._active_profile = cProfile.Profile()
        self._active_profile.enable()
        self.log_event(
            hypothesis_id="profile",
            location="nornir_shared.profiling:PhaseProfiler.start_cprofile",
            message="cProfile started",
            data={"tag": tag},
        )

    def stop_cprofile(self, tag: str, *, top_n: int = 25) -> None:
        """Stop cProfile, write ``.pstats``, and log top cumulative-time frames."""
        prof = self._active_profile
        if prof is None or self._profile_path is None:
            return
        prof.disable()
        self._active_profile = None
        self._profile_path.parent.mkdir(parents=True, exist_ok=True)
        prof.dump_stats(str(self._profile_path))
        stats = pstats.Stats(prof)
        stats.sort_stats("cumtime")
        top: list[dict[str, Any]] = []
        raw_stats = getattr(stats, "stats", {})
        for (filename, line, func), (_cc, nc, _tt, ct, _callers) in raw_stats.items():
            top.append({
                "func": f"{filename}:{line}({func})",
                "cumtime": round(ct, 4),
                "ncalls": nc,
            })
        top.sort(key=lambda item: item["cumtime"], reverse=True)
        self.log_event(
            hypothesis_id="profile",
            location="nornir_shared.profiling:PhaseProfiler.stop_cprofile",
            message="cProfile saved",
            data={
                "tag": tag,
                "profile_path": str(self._profile_path),
                "top_cumtime": top[:top_n],
            },
        )


_active_profiler: PhaseProfiler | None = None


def configure_phase_profiler(profiler: PhaseProfiler) -> PhaseProfiler:
    """Install *profiler* as the module-level default used by helper functions."""
    global _active_profiler
    _active_profiler = profiler
    return profiler


def get_phase_profiler() -> PhaseProfiler | None:
    """Return the configured module-level profiler, if any."""
    return _active_profiler


def log_event(
        *,
        hypothesis_id: str,
        location: str,
        message: str,
        data: dict[str, Any] | None = None,
        run_id: str | None = None,
) -> None:
    """Log through the active :class:`PhaseProfiler`, if configured."""
    profiler = get_phase_profiler()
    if profiler is None:
        return
    profiler.log_event(
        hypothesis_id=hypothesis_id,
        location=location,
        message=message,
        data=data,
        run_id=run_id,
    )


@contextmanager
def phase_timer(
        hypothesis_id: str,
        location: str,
        phase_name: str,
        **extra: Any,
) -> Iterator[None]:
    """Context manager alias for :meth:`PhaseProfiler.phase` on the active profiler."""
    profiler = get_phase_profiler()
    if profiler is None:
        yield
        return
    with profiler.phase(hypothesis_id, location, phase_name, **extra):
        yield


def start_cprofile(tag: str) -> None:
    """Start cProfile on the active profiler."""
    profiler = get_phase_profiler()
    if profiler is not None:
        profiler.start_cprofile(tag)


def stop_cprofile(tag: str, *, top_n: int = 25) -> None:
    """Stop cProfile on the active profiler."""
    profiler = get_phase_profiler()
    if profiler is not None:
        profiler.stop_cprofile(tag, top_n=top_n)


def next_seq(name: str = "default") -> int:
    """Return the next sequence number from the active profiler."""
    profiler = get_phase_profiler()
    if profiler is None:
        return 0
    return profiler.next_seq(name)
