"""RunWithProfiler must not report success when cProfile cannot write its profile.

``cProfile.run`` either writes the profile file or raises from ``dump_stats``. When the
dump failed (an unwritable output folder), the bare ``sys.exit()`` in RunWithProfiler's
``finally`` replaced the error with exit status 0 (nornir-review#278).
"""
import contextlib
import cProfile
import io
import os
import tempfile
import unittest
from unittest import mock

from hypothesis import example, given, settings
from hypothesis import strategies as st

from nornir_shared import misc

_dump_errors = st.sampled_from([OSError, PermissionError, FileNotFoundError, IsADirectoryError])


class TestRunWithProfiler(unittest.TestCase):
    def test_writes_profile_and_returns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            misc.RunWithProfiler('sum(range(10))', tmp)
            self.assertTrue(os.path.isfile(os.path.join(tmp, 'BuildProfile.pr')))

    @settings(max_examples=10, deadline=None)
    @given(error=_dump_errors)
    @example(error=PermissionError)
    def test_profile_dump_failure_exits_with_error_status(self, error: type[OSError]) -> None:
        with (tempfile.TemporaryDirectory() as tmp,
              mock.patch.object(cProfile.Profile, 'dump_stats', side_effect=error('cannot write')),
              self.assertLogs('nornir_shared.misc.RunWithProfiler', level='ERROR') as logs,
              self.assertRaises(SystemExit) as raised):
            misc.RunWithProfiler('sum(range(10))', tmp)
        self.assertNotIn(raised.exception.code, (None, 0))
        self.assertTrue(any('BuildProfile.pr' in r.getMessage() for r in logs.records))


if __name__ == '__main__':
    unittest.main()
