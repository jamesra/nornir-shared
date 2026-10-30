"""Tests for curses fallback in prettyoutput (prefresh / short terminals)."""

from __future__ import annotations

import unittest
from unittest import mock

import nornir_shared.prettyoutput as prettyoutput


class TestPrettyOutputCursesFallback(unittest.TestCase):
    """prefresh ERR must not escape Log after a failed pad refresh."""

    def setUp(self) -> None:
        self._curses = prettyoutput.CURSES
        self._log_start = prettyoutput.LogStartY

    def tearDown(self) -> None:
        prettyoutput.CURSES = self._curses
        prettyoutput.LogStartY = self._log_start

    def test_safe_log_pad_refresh_rejects_short_terminal(self) -> None:
        prettyoutput.CURSES = True
        prettyoutput.LogStartY = 16
        prettyoutput.logWindow = mock.MagicMock()
        with mock.patch.object(prettyoutput, '_disable_curses') as disable:
            ok = prettyoutput._safe_log_pad_refresh(y_max=16, x_max=80)
        self.assertFalse(ok)
        disable.assert_called_once()
        prettyoutput.logWindow.refresh.assert_not_called()

    def test_safe_log_pad_refresh_uses_inclusive_screen_bounds(self) -> None:
        prettyoutput.CURSES = True
        prettyoutput.LogStartY = 16
        prettyoutput.logWindow = mock.MagicMock()
        ok = prettyoutput._safe_log_pad_refresh(y_max=40, x_max=80)
        self.assertTrue(ok)
        # smaxcol must be width-1 so the refresh rectangle stays on-screen.
        prettyoutput.logWindow.refresh.assert_called_once_with(0, 0, 16, 0, 39, 79)

    def test_safe_log_pad_refresh_disables_curses_on_prefresh_error(self) -> None:
        prettyoutput.CURSES = True
        prettyoutput.LogStartY = 16
        prettyoutput.logWindow = mock.MagicMock()
        err_type = prettyoutput._curses_error_type()
        prettyoutput.logWindow.refresh.side_effect = err_type('prefresh() returned ERR')
        with mock.patch.object(prettyoutput, '_disable_curses') as disable:
            ok = prettyoutput._safe_log_pad_refresh(y_max=40, x_max=80)
        self.assertFalse(ok)
        disable.assert_called_once()

    def test_log_does_not_raise_when_curses_disabled(self) -> None:
        prettyoutput.CURSES = False
        prettyoutput.Log('prune histogram ok')


if __name__ == '__main__':
    unittest.main()
