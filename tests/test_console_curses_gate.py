"""Tests for the curses gate in nornir_shared.console (CursesHandler)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import textwrap
import unittest
from unittest import mock

import nornir_shared.console
import nornir_shared.curses_console

_CURSES_IMPORTABLE = importlib.util.find_spec('curses') is not None


class TestConsoleCursesGate(unittest.TestCase):
    """CursesHandler draws through curses_console only when curses imports."""

    @unittest.skipUnless(_CURSES_IMPORTABLE, 'curses is not importable here')
    def test_handler_draws_severity_topic_when_curses_imports(self) -> None:
        with mock.patch.object(nornir_shared.curses_console, 'CurseString') as curse_string, \
                mock.patch.object(nornir_shared.console, 'NoCursesHandler') as no_curses:
            nornir_shared.console.CursesHandler('WARNING:disk full: 3 GB left')
        curse_string.assert_called_once_with('Warning', 'disk full: 3 GB left')
        no_curses.assert_not_called()

    def test_handler_prints_when_curses_cannot_import(self) -> None:
        """A missing curses module (sys.modules entry None) must fall back to plain printing."""
        script = textwrap.dedent("""
            import sys
            sys.modules['curses'] = None
            import nornir_shared.console as console
            console.CursesHandler('INFO:hello world')
        """)
        result = subprocess.run([sys.executable, '-c', script], check=False, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout.strip(), r'^\[\d\d:\d\d:\d\d\] \[INFO\] hello world$')


if __name__ == '__main__':
    unittest.main()
