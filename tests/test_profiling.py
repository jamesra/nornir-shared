"""Regression for #178: phase profile paths follow NORNIR_LOG_ROOT session layout."""
from __future__ import annotations

import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nornir_shared import profiling


class TestPhaseProfileSessionLayout(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {
            key: os.environ.get(key)
            for key in (
                "NORNIR_PHASE_PROFILE_LOG",
                "NORNIR_PHASE_PROFILE_PSTATS",
                "NORNIR_LOG_ROOT",
                "NORNIR_LOG_SESSION_ID",
            )
        }
        import nornir_shared.misc as nornir_misc
        nornir_misc._active_log_session_id = None

    def tearDown(self) -> None:
        import nornir_shared.misc as nornir_misc
        nornir_misc._active_log_session_id = None
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_relative_log_path_resolves_under_log_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["NORNIR_LOG_ROOT"] = tmp
            os.environ["NORNIR_LOG_SESSION_ID"] = "20260101-120000"
            os.environ["NORNIR_PHASE_PROFILE_LOG"] = "agent-phases.ndjson"
            path = profiling._default_log_path()
            self.assertIsNotNone(path)
            assert path is not None
            self.assertTrue(path.is_absolute())
            self.assertEqual(path.name, "agent-phases.ndjson")
            self.assertEqual(path.parent, Path(tmp) / "2026-01-01")

    def test_sentinel_uses_session_ndjson_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["NORNIR_LOG_ROOT"] = tmp
            os.environ["NORNIR_LOG_SESSION_ID"] = "20260102-010203"
            os.environ["NORNIR_PHASE_PROFILE_LOG"] = "1"
            path = profiling._default_log_path()
            self.assertEqual(
                path,
                Path(tmp) / "2026-01-02" / "nornir-phase-profile-20260102-010203.ndjson",
            )

    def test_absolute_log_path_unchanged(self) -> None:
        absolute = Path(tempfile.gettempdir()) / "explicit-phase.ndjson"
        os.environ.pop("NORNIR_LOG_ROOT", None)
        os.environ["NORNIR_PHASE_PROFILE_LOG"] = str(absolute)
        self.assertEqual(profiling._default_log_path(), absolute)

    def test_write_failure_is_logged_not_swallowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "phases.ndjson"
            profiler = profiling.PhaseProfiler(log_path=log_path)
            with patch("builtins.open", side_effect=OSError("disk full")):
                with self.assertLogs(profiling._logger, level=logging.WARNING) as captured:
                    profiler.log_event(
                        hypothesis_id="T",
                        location="test",
                        message="should warn",
                    )
            self.assertTrue(any("disk full" in line for line in captured.output))


if __name__ == "__main__":
    unittest.main()
