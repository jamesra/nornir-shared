"""Fallback log file names must record the month and stay unique per run.

SetupLogging's fallback branch -- used whenever NORNIR_LOG_ROOT is not
configured -- named files with ``time.strftime('log-%M.%d.%y_%H.%M.txt')``.
``%M`` is minutes, so the month position held minutes: the name recorded the
minute twice and the month never.  Production logs cited in
nornir-imageregistration/docs show exactly that, e.g. ``log-16.31.26_04.16.txt``
and ``log-43.01.26_05.43.txt``, where the first field always equals the last.

Two runs starting in the same minute of the same day also produced identical
names, and logging.basicConfig appends, so unrelated runs merged into one file.

Names now derive from the shared session ID, which carries seconds and is
inherited through the environment so every process in a run shares one file.
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
import time
import unittest

from nornir_shared import misc

_SESSION_NAME = re.compile(r'^log-(\d{8})-(\d{6})(-Errors)?\.txt$')


class _SessionIdTestCase(unittest.TestCase):
    """Isolates the module-level session ID cache and its environment variable."""

    def setUp(self):
        self._saved_env = os.environ.get(misc.NORNIR_LOG_SESSION_ENV)
        self._saved_cache = misc._active_log_session_id
        self.addCleanup(self._restore)

        os.environ.pop(misc.NORNIR_LOG_SESSION_ENV, None)
        misc._active_log_session_id = None

    def _restore(self):
        misc._active_log_session_id = self._saved_cache
        if self._saved_env is None:
            os.environ.pop(misc.NORNIR_LOG_SESSION_ENV, None)
        else:
            os.environ[misc.NORNIR_LOG_SESSION_ENV] = self._saved_env


class TestSessionIdRecordsTheMonth(_SessionIdTestCase):

    def test_session_id_shape(self):
        session_id = misc._get_or_create_session_id()
        self.assertRegex(session_id, r'^\d{8}-\d{6}$')

    def test_month_matches_the_clock(self):
        """The regression: the month field used to hold minutes."""
        session_id = misc._get_or_create_session_id()
        expected_month = time.strftime('%m', time.localtime())
        self.assertEqual(session_id[4:6], expected_month)

    def test_month_is_not_the_minute(self):
        session_id = misc._get_or_create_session_id()
        month = session_id[4:6]
        self.assertGreaterEqual(int(month), 1)
        self.assertLessEqual(int(month), 12)

    def test_date_prefix_matches_today(self):
        session_id = misc._get_or_create_session_id()
        self.assertEqual(session_id[:8], time.strftime('%Y%m%d', time.localtime()))

    def test_seconds_are_recorded(self):
        """Seconds are what keep two runs in the same minute apart."""
        session_id = misc._get_or_create_session_id()
        self.assertEqual(len(session_id.split('-')[1]), 6)


class TestSessionIdIsSharedAcrossProcesses(_SessionIdTestCase):
    """One run must produce one log file, not one per process."""

    def test_session_id_is_published_to_the_environment(self):
        session_id = misc._get_or_create_session_id()
        self.assertEqual(os.environ[misc.NORNIR_LOG_SESSION_ENV], session_id)

    def test_a_child_process_inherits_the_session_id(self):
        parent_id = misc._get_or_create_session_id()

        # A child starts with an empty cache but inherits the environment.
        misc._active_log_session_id = None
        self.assertEqual(misc._get_or_create_session_id(), parent_id)

    def test_repeated_calls_are_stable(self):
        self.assertEqual(misc._get_or_create_session_id(),
                         misc._get_or_create_session_id())

    def test_explicit_session_id_is_honoured(self):
        os.environ[misc.NORNIR_LOG_SESSION_ENV] = '20260101-000000'
        self.assertEqual(misc._get_or_create_session_id(), '20260101-000000')


class TestFallbackLogFileNames(_SessionIdTestCase):
    """The names SetupLogging's fallback branch builds."""

    def _names(self) -> tuple[str, str]:
        session_id = misc._get_or_create_session_id()
        return f'log-{session_id}.txt', f'log-{session_id}-Errors.txt'

    def test_names_are_well_formed(self):
        for name in self._names():
            with self.subTest(name=name):
                self.assertRegex(name, _SESSION_NAME)

    def test_month_field_is_a_real_month(self):
        log_name, _ = self._names()
        match = _SESSION_NAME.match(log_name)
        self.assertIsNotNone(match)
        assert match is not None
        month = int(match.group(1)[4:6])
        self.assertGreaterEqual(month, 1)
        self.assertLessEqual(month, 12)

    def test_error_log_is_distinct_from_the_session_log(self):
        log_name, err_name = self._names()
        self.assertNotEqual(log_name, err_name)

    def test_two_runs_in_the_same_minute_do_not_collide(self):
        os.environ[misc.NORNIR_LOG_SESSION_ENV] = '20260827-143701'
        misc._active_log_session_id = None
        first, _ = self._names()

        os.environ[misc.NORNIR_LOG_SESSION_ENV] = '20260827-143759'
        misc._active_log_session_id = None
        second, _ = self._names()

        self.assertNotEqual(first, second)

    def test_old_format_would_have_collided(self):
        """Documents why the format changed rather than only fixing %m."""
        same_minute_a = time.strptime('2026-08-27 14:37:01', '%Y-%m-%d %H:%M:%S')
        same_minute_b = time.strptime('2026-08-27 14:37:59', '%Y-%m-%d %H:%M:%S')
        fmt = 'log-%m.%d.%y_%H.%M.txt'
        self.assertEqual(time.strftime(fmt, same_minute_a),
                         time.strftime(fmt, same_minute_b))

    def test_old_format_hid_the_month(self):
        """The bug itself: month field took the minute value."""
        moment = time.strptime('2026-08-27 14:37:22', '%Y-%m-%d %H:%M:%S')
        buggy = time.strftime('log-%M.%d.%y_%H.%M.txt', moment)
        self.assertEqual(buggy, 'log-37.27.26_14.37.txt')
        self.assertNotIn('08', buggy.split('_')[0])


class TestSetupLoggingUsesSessionNamedFiles(_SessionIdTestCase):
    """End-to-end: the file SetupLogging actually opens in the fallback branch.

    Asserted via the error log, which is created with logging.FileHandler
    directly.  The main log goes through logging.basicConfig, which is a no-op
    when the root logger already has handlers (as it does under pytest).
    """

    def setUp(self):
        super().setUp()

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

        self._saved_log_root = os.environ.get('NORNIR_LOG_ROOT')
        self._saved_setup_flag = misc.logging_setup
        root = logging.getLogger()
        self._saved_handlers = root.handlers[:]
        self._saved_level = root.level

        # Registered after the temp dir so it runs first and closes the handlers
        # before the directory is removed.
        self.addCleanup(self._restore_logging)

        # Force the fallback branch: no unified log root.
        os.environ.pop('NORNIR_LOG_ROOT', None)
        misc.logging_setup = False

    def _restore_logging(self):
        root = logging.getLogger()
        for handler in root.handlers[:]:
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass
        for handler in self._saved_handlers:
            root.addHandler(handler)
        root.setLevel(self._saved_level)

        misc.logging_setup = self._saved_setup_flag
        if self._saved_log_root is None:
            os.environ.pop('NORNIR_LOG_ROOT', None)
        else:
            os.environ['NORNIR_LOG_ROOT'] = self._saved_log_root

    def test_error_log_is_named_from_the_session_id(self):
        misc.SetupLogging(OutputPath=self._tmp.name)

        created = os.listdir(self._tmp.name)
        error_logs = [name for name in created if name.endswith('-Errors.txt')]
        self.assertEqual(len(error_logs), 1,
                         f'expected one error log, found {created}')

        match = _SESSION_NAME.match(error_logs[0])
        self.assertIsNotNone(match, f'{error_logs[0]} is not session-named')
        assert match is not None

        self.assertEqual(match.group(1), misc._get_or_create_session_id()[:8])
        month = int(match.group(1)[4:6])
        self.assertGreaterEqual(month, 1)
        self.assertLessEqual(month, 12)

    def test_error_log_name_is_not_the_old_minute_format(self):
        misc.SetupLogging(OutputPath=self._tmp.name)

        for name in os.listdir(self._tmp.name):
            with self.subTest(name=name):
                # The old names looked like log-37.27.26_14.37-Errors.txt
                self.assertNotRegex(name, r'^log-\d\d\.\d\d\.\d\d_')


if __name__ == '__main__':
    unittest.main()
