"""Tests for structured phase profiling helpers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from nornir_shared.profiling import PhaseProfiler, configure_phase_profiler, phase_timer


class TestPhaseProfiler(unittest.TestCase):
    def test_phase_writes_ndjson_start_and_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "profile.log"
            profiler = PhaseProfiler(session_id="test", log_path=log_path, run_id="run1")
            with profiler.phase("H1", "module.py:fn", "work", count=3):
                pass
            lines = log_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            start = json.loads(lines[0])
            end = json.loads(lines[1])
            self.assertEqual(start["message"], "work:start")
            self.assertEqual(start["data"]["count"], 3)
            self.assertEqual(end["message"], "work:end")
            self.assertIn("elapsed_ms", end["data"])
            self.assertGreaterEqual(end["data"]["elapsed_ms"], 0.0)

    def test_records_include_pid_and_tid(self) -> None:
        import os
        import threading

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "profile.log"
            profiler = PhaseProfiler(session_id="test", log_path=log_path)
            profiler.log_event(hypothesis_id="H1", location="m.py:f", message="one")
            record = json.loads(log_path.read_text(encoding="utf-8").strip())
            self.assertEqual(record["pid"], os.getpid())
            self.assertEqual(record["tid"], threading.get_ident())

    def test_disabled_profiler_is_noop(self) -> None:
        profiler = PhaseProfiler(session_id="test", log_path=None, enabled=False)
        profiler.log_event(
            hypothesis_id="H1",
            location="x",
            message="noop",
        )
        self.assertFalse(profiler.enabled)

    def test_module_helpers_use_configured_profiler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "profile.log"
            configure_phase_profiler(
                PhaseProfiler(session_id="test", log_path=log_path),
            )
            with phase_timer("H2", "module.py:fn", "helper"):
                pass
            lines = log_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0])["hypothesisId"], "H2")

    def test_next_seq_is_monotonic(self) -> None:
        profiler = PhaseProfiler(session_id="test", log_path=None, enabled=False)
        self.assertEqual(profiler.next_seq("alignment"), 1)
        self.assertEqual(profiler.next_seq("alignment"), 2)
