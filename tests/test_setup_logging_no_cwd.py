"""Regression for #179: SetupLogging must not scatter logs into CWD."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

from nornir_shared import misc


class TestFallbackFileLogDir(unittest.TestCase):
    def test_prefers_testoutputpath(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            saved = os.environ.get('TESTOUTPUTPATH')
            try:
                os.environ['TESTOUTPUTPATH'] = tmp
                self.assertEqual(misc._fallback_file_log_dir(), tmp)
            finally:
                if saved is None:
                    os.environ.pop('TESTOUTPUTPATH', None)
                else:
                    os.environ['TESTOUTPUTPATH'] = saved

    def test_uses_tempdir_not_cwd(self) -> None:
        saved = os.environ.get('TESTOUTPUTPATH')
        try:
            os.environ.pop('TESTOUTPUTPATH', None)
            self.assertEqual(misc._fallback_file_log_dir(), tempfile.gettempdir())
            self.assertNotEqual(misc._fallback_file_log_dir(), os.getcwd())
        finally:
            if saved is None:
                os.environ.pop('TESTOUTPUTPATH', None)
            else:
                os.environ['TESTOUTPUTPATH'] = saved


class TestSetupLoggingDoesNotScatterIntoCwd(unittest.TestCase):
    def test_default_setup_without_log_root_leaves_cwd_clean(self) -> None:
        """#179: default SetupLogging must not create log-*.txt in CWD."""
        script = textwrap.dedent(
            """
            import os, tempfile, glob
            from nornir_shared import misc
            cwd = tempfile.mkdtemp()
            os.chdir(cwd)
            os.environ.pop('NORNIR_LOG_ROOT', None)
            os.environ.pop('TESTOUTPUTPATH', None)
            misc.logging_setup = False
            misc._active_log_session_id = None
            os.environ.pop(misc.NORNIR_LOG_SESSION_ENV, None)
            misc.SetupLogging()
            leftovers = glob.glob('log-*.txt')
            print('LEFTOVERS=' + repr(leftovers))
            print('CWD=' + cwd)
            """
        )
        completed = subprocess.run(
            [sys.executable, '-c', script],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("LEFTOVERS=[]", completed.stdout)

    def test_explicit_log_to_file_uses_temp_not_cwd(self) -> None:
        script = textwrap.dedent(
            """
            import os, tempfile, glob, logging
            from nornir_shared import misc
            cwd = tempfile.mkdtemp()
            os.chdir(cwd)
            os.environ.pop('NORNIR_LOG_ROOT', None)
            os.environ.pop('TESTOUTPUTPATH', None)
            misc.logging_setup = False
            misc._active_log_session_id = None
            os.environ.pop(misc.NORNIR_LOG_SESSION_ENV, None)
            # Clear handlers so FileHandler is visible under a fresh root.
            root = logging.getLogger()
            for handler in root.handlers[:]:
                root.removeHandler(handler)
                try:
                    handler.close()
                except Exception:
                    pass
            misc.SetupLogging(LogToFile=True)
            cwd_logs = glob.glob(os.path.join(cwd, 'log-*.txt'))
            temp_logs = glob.glob(os.path.join(tempfile.gettempdir(), 'log-*.txt'))
            print('CWD_LOGS=' + repr(cwd_logs))
            print('TEMP_HAS_LOG=' + str(any(os.path.isfile(p) for p in temp_logs)))
            """
        )
        completed = subprocess.run(
            [sys.executable, '-c', script],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("CWD_LOGS=[]", completed.stdout)
        self.assertIn("TEMP_HAS_LOG=True", completed.stdout)


if __name__ == '__main__':
    unittest.main()
