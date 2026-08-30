"""Tests for nornir_shared.misc helpers.

``format_startup_command_line`` and its ``SetupLogging`` call site were deleted as
collateral in a commit that added the phase profiler, leaving these tests importing a name
that no longer existed. That ``ImportError`` aborted collection for the whole directory, so
the submodule reported zero tests rather than one broken module (review #220).

The formatter had tests; the *wiring* did not, which is why removing the call from
``SetupLogging`` was silent. ``TestTheCommandLineReachesTheLog`` covers that end to end.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from nornir_shared.misc import GenNameFromDict, ListFromDelimited, format_startup_command_line


class TestGenNameFromDict(unittest.TestCase):
    def test_scalar_and_none(self) -> None:
        self.assertEqual(GenNameFromDict({'abc': 1, 'def': None}), '_abc1_defNone')

    def test_list_joins_all_elements(self) -> None:
        # Regression: prior code used value[1:-1] and overwrote ValueStr each loop.
        self.assertEqual(GenNameFromDict({'a': [1, 2, 3, 4]}), '_a1x2x3x4')
        self.assertEqual(GenNameFromDict({'xyz': [10, 20]}), '_xyz10x20')

    def test_empty_list(self) -> None:
        self.assertEqual(GenNameFromDict({'k': []}), '_k')


class TestFormatStartupCommandLine(unittest.TestCase):
    def test_includes_executable_and_arguments(self) -> None:
        formatted = format_startup_command_line(['pyre', '-stos', r'Y:\Volumes\RC2\pair.stos'])
        self.assertIn(os.path.basename(sys.executable), formatted)
        self.assertIn('pyre', formatted)
        self.assertIn('pair.stos', formatted)

    def test_does_not_duplicate_interpreter_path(self) -> None:
        formatted = format_startup_command_line([sys.executable, '-m', 'pyre'])
        self.assertEqual(formatted.count(sys.executable), 1)
        self.assertIn('-m', formatted)
        self.assertIn('pyre', formatted)

    def test_quotes_arguments_with_spaces(self) -> None:
        formatted = format_startup_command_line(['prog', os.path.join('dir with space', 'file.png')])
        self.assertIn('dir with space', formatted)
        if os.name == 'nt':
            self.assertIn('"', formatted)
        else:
            self.assertTrue("'" in formatted or '\\ ' in formatted)


class TestTheCommandLineReachesTheLog(unittest.TestCase):
    """``SetupLogging`` must actually emit the command line, not just be able to format it.

    Runs in a subprocess: ``SetupLogging`` sets a module-global guard, attaches root
    handlers and registers ``atexit`` hooks, so calling it in-process would leak into every
    other test.
    """

    def _run_setup_logging(self, level_expr: str = 'None') -> tuple[str, list[str]]:
        """Return ``(stderr, log_file_contents)`` after a real SetupLogging call."""
        script = textwrap.dedent(f"""
            import logging, os, sys
            from nornir_shared import misc
            misc.SetupLogging(Level={level_expr})
            logging.shutdown()
        """)
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, NORNIR_LOG_ROOT=tmp, PYTHONIOENCODING='utf-8')
            env.pop('NORNIR_LOG_SESSION_ID', None)
            proc = subprocess.run([sys.executable, '-c', script],
                                  capture_output=True, text=True, env=env, timeout=300)
            self.assertEqual(proc.returncode, 0,
                             f'SetupLogging failed: {proc.stdout}\n{proc.stderr}')
            contents = [p.read_text(encoding='utf-8', errors='replace')
                        for p in Path(tmp).rglob('*.log')]
            return proc.stderr, contents

    def test_setup_logging_records_the_command_line(self):
        stderr, logs = self._run_setup_logging()

        haystack = stderr + '\n'.join(logs)
        self.assertIn('Command line:', haystack,
                      'SetupLogging no longer logs the startup command line')

    def test_it_names_the_interpreter_that_is_running(self):
        stderr, logs = self._run_setup_logging()

        haystack = stderr + '\n'.join(logs)
        self.assertIn(os.path.basename(sys.executable), haystack)

    def test_a_warning_only_setup_still_persists_the_line(self):
        """Pyre configures WARNING; the line must survive that, not be dropped as INFO."""
        stderr, logs = self._run_setup_logging(level_expr='logging.WARNING')

        haystack = stderr + '\n'.join(logs)
        self.assertIn('Command line:', haystack)

    def test_the_helper_is_wired_into_setup_logging(self):
        """Guards the call site specifically -- deleting it is what went unnoticed."""
        import inspect

        from nornir_shared import misc

        source = inspect.getsource(misc.SetupLogging)

        self.assertIn('_log_startup_command_line', source)


class TestListFromDelimited(unittest.TestCase):
    def test_ints_floats_strings(self) -> None:
        self.assertEqual(ListFromDelimited('1,2.5,foo'), [1, 2.5, 'foo'])

    def test_non_string(self) -> None:
        self.assertEqual(ListFromDelimited(3), [3])
        self.assertEqual(ListFromDelimited([1, 2]), [1, 2])


if __name__ == '__main__':
    unittest.main()
