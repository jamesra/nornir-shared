"""Lock files must age out, distinguish I/O errors, and not swallow Ctrl-C.

``TryEnterLockFile`` read the lock outside a ``with`` and wrapped the whole staleness
check in a bare ``except``::

    try:
        hLockFile = open(LockFile, 'r')
        LockingParty = hLockFile.readline().rstrip('\\n')
        FileTimeString = hLockFile.readline()
        hLockFile.close()          # skipped if either readline raises

        # Ignore the lock if it has been more than eighteen hours
        CreationTime = time.strptime(FileTimeString)
        ...
        if (Elapsed / (60 * 60)) > 48:
            ...remove stale lock...
    except:
        return False

``ReleaseLockFile`` had the same shape. Measured consequences, before and after:

    case                            before                    after
    fresh zero-byte lock            False (correct)           False (correct)
    48h+ old zero-byte lock         False forever             True, stale lock removed
    another host holds it           False                     False
    our own stale, valid timestamp  True                       True
    lock holding binary content     False                     False
    Ctrl-C during the check         SWALLOWED, returns False  propagates
    release a lock that is absent   "Exception releasing..."  "No lock file to release"

Three real defects:

1. A lock whose timestamp line is missing or unparseable was **permanently
   unacquirable**. ``time.strptime('')`` raised, the bare ``except`` returned False, and
   the stale-removal path below it was never reached, so the file never cleared. A
   process that created its lock and died before writing the timestamp wedged that path
   forever. The age now falls back to the file's mtime, so an undatable lock ages out
   like any other.
2. The bare ``except`` caught ``BaseException``, so ``KeyboardInterrupt`` during the
   check was converted into "could not take the lock".
3. Releasing a lock that does not exist reported the same message as a real I/O failure,
   even though it is the normal outcome after a stale lock was cleared.

The comment said "eighteen hours" while the code compared against 48. 48 is what
shipped, so it is kept and now named ``STALE_LOCK_HOURS``.

The filed handle leak is real as written -- ``close()`` is skipped when ``readline()``
raises -- but was **not** observable: CPython drops the last reference when the function
returns, so the probe found zero unclosed handles pointing at the lock file. The ``with``
blocks make it correct regardless of interpreter rather than fixing a measured leak.
"""
from __future__ import annotations

import os
import platform
import tempfile
import time
import unittest

from nornir_shared import parallel


class _LockFixture(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.me = platform.node()

    def _base(self, name):
        return os.path.join(self._tmp.name, name)

    def _lock_path(self, base):
        return base + '.lock'

    def _write_lock(self, base, party, timestamp=None, age_hours=None):
        """Create a lock file, optionally backdating its mtime."""
        path = self._lock_path(base)
        with open(path, 'w', encoding='utf-8') as handle:
            if party is not None:
                handle.write(party + '\n')
            if timestamp is not None:
                handle.write(timestamp)
        if age_hours is not None:
            when = time.time() - (age_hours * 60 * 60)
            os.utime(path, (when, when))
        return path

    def _ctime_hours_ago(self, hours):
        return time.ctime(time.time() - (hours * 60 * 60))


class TestHappyPath(_LockFixture):

    def test_an_unlocked_path_can_be_locked(self):
        base = self._base('free')

        self.assertTrue(parallel.TryEnterLockFile(base))
        self.assertTrue(os.path.exists(self._lock_path(base)))

    def test_our_own_lock_can_be_re_entered(self):
        base = self._base('reenter')
        parallel.TryEnterLockFile(base)

        self.assertTrue(parallel.TryEnterLockFile(base))

    def test_releasing_our_lock_removes_the_file(self):
        base = self._base('release')
        parallel.TryEnterLockFile(base)

        parallel.ReleaseLockFile(base)

        self.assertFalse(os.path.exists(self._lock_path(base)))

    def test_a_lock_held_by_another_host_is_refused(self):
        base = self._base('theirs')
        self._write_lock(base, 'some-other-host', self._ctime_hours_ago(1))

        self.assertFalse(parallel.TryEnterLockFile(base))

    def test_another_hosts_lock_is_not_removed(self):
        base = self._base('theirs-kept')
        self._write_lock(base, 'some-other-host', self._ctime_hours_ago(1))

        parallel.TryEnterLockFile(base)

        self.assertTrue(os.path.exists(self._lock_path(base)))

    def test_we_do_not_release_another_hosts_lock(self):
        base = self._base('theirs-release')
        self._write_lock(base, 'some-other-host', self._ctime_hours_ago(1))

        parallel.ReleaseLockFile(base)

        self.assertTrue(os.path.exists(self._lock_path(base)))

    def test_lock_path_helpers_agree_with_the_file_helpers(self):
        directory = os.path.join(self._tmp.name, 'adir')
        os.makedirs(directory)

        self.assertTrue(parallel.TryEnterLockPath(directory))
        parallel.ReleaseLockPath(directory)

        self.assertFalse(os.path.exists(os.path.join(directory, 'Path.lock')))


class TestStaleLocks(_LockFixture):

    def test_an_old_lock_from_another_host_is_removed_and_taken(self):
        base = self._base('stale-theirs')
        self._write_lock(base, 'some-other-host',
                         self._ctime_hours_ago(parallel.STALE_LOCK_HOURS + 24))

        self.assertTrue(parallel.TryEnterLockFile(base))

    def test_a_lock_just_inside_the_window_is_respected(self):
        base = self._base('fresh-enough')
        self._write_lock(base, 'some-other-host',
                         self._ctime_hours_ago(parallel.STALE_LOCK_HOURS - 1))

        self.assertFalse(parallel.TryEnterLockFile(base))

    def test_the_stale_window_is_the_documented_48_hours(self):
        """The old comment said eighteen; the code said 48."""
        self.assertEqual(parallel.STALE_LOCK_HOURS, 48)


class TestUndatableLocksAgeOut(_LockFixture):
    """The regression: an unparseable timestamp used to wedge the path forever."""

    def test_an_old_zero_byte_lock_can_be_acquired(self):
        base = self._base('zero-old')
        self._write_lock(base, None, None,
                         age_hours=parallel.STALE_LOCK_HOURS + 24)

        self.assertTrue(parallel.TryEnterLockFile(base),
                        'a lock with no timestamp must age out by mtime, not wedge')

    def test_a_fresh_zero_byte_lock_is_still_respected(self):
        """A process may have just created it and be about to write; do not steal it."""
        base = self._base('zero-fresh')
        self._write_lock(base, None, None)

        self.assertFalse(parallel.TryEnterLockFile(base))

    def test_a_fresh_zero_byte_lock_is_not_deleted(self):
        base = self._base('zero-fresh-kept')
        self._write_lock(base, None, None)

        parallel.TryEnterLockFile(base)

        self.assertTrue(os.path.exists(self._lock_path(base)))

    def test_an_old_lock_with_a_garbage_timestamp_can_be_acquired(self):
        base = self._base('garbage-ts-old')
        self._write_lock(base, 'some-other-host', 'not a timestamp at all',
                         age_hours=parallel.STALE_LOCK_HOURS + 24)

        self.assertTrue(parallel.TryEnterLockFile(base))

    def test_a_fresh_lock_with_a_garbage_timestamp_is_respected(self):
        base = self._base('garbage-ts-fresh')
        self._write_lock(base, 'some-other-host', 'not a timestamp at all')

        self.assertFalse(parallel.TryEnterLockFile(base))

    def test_an_old_binary_lock_can_be_acquired(self):
        base = self._base('binary-old')
        path = self._lock_path(base)
        with open(path, 'wb') as handle:
            handle.write(b'\xff\xfe\x00binary garbage\n\xff')
        when = time.time() - ((parallel.STALE_LOCK_HOURS + 24) * 60 * 60)
        os.utime(path, (when, when))

        self.assertTrue(parallel.TryEnterLockFile(base))

    def test_a_fresh_binary_lock_is_refused_without_raising(self):
        """Must return False, not propagate UnicodeDecodeError."""
        base = self._base('binary-fresh')
        path = self._lock_path(base)
        with open(path, 'wb') as handle:
            handle.write(b'\xff\xfe\x00binary garbage\n\xff')

        self.assertFalse(parallel.TryEnterLockFile(base))

    def test_repeated_attempts_on_an_undatable_lock_eventually_succeed(self):
        """Pins that the path is not permanently wedged."""
        base = self._base('zero-retry')
        self._write_lock(base, None, None,
                         age_hours=parallel.STALE_LOCK_HOURS + 1)

        results = [parallel.TryEnterLockFile(base) for _ in range(3)]

        self.assertTrue(all(results), f'expected all attempts to succeed, got {results}')


class TestInterruptsAreNotSwallowed(_LockFixture):
    """The bare except caught BaseException, including KeyboardInterrupt."""

    def _raise_during_check(self, exception):
        real = time.strptime

        def boom(*args, **kwargs):
            raise exception

        time.strptime = boom
        self.addCleanup(lambda: setattr(time, 'strptime', real))

    def test_keyboard_interrupt_propagates(self):
        base = self._base('interrupt')
        self._write_lock(base, self.me, self._ctime_hours_ago(1))
        self._raise_during_check(KeyboardInterrupt('ctrl-c'))

        with self.assertRaises(KeyboardInterrupt):
            parallel.TryEnterLockFile(base)

    def test_system_exit_propagates(self):
        base = self._base('sysexit')
        self._write_lock(base, self.me, self._ctime_hours_ago(1))
        self._raise_during_check(SystemExit(1))

        with self.assertRaises(SystemExit):
            parallel.TryEnterLockFile(base)

    def test_the_module_has_no_bare_except(self):
        import inspect

        source = inspect.getsource(parallel)
        code = '\n'.join(line.split('#', 1)[0] for line in source.splitlines())

        self.assertNotIn('except:', code)


class TestReleaseDistinguishesMissingFromBroken(_LockFixture):

    def test_releasing_an_absent_lock_is_not_reported_as_an_exception(self):
        base = self._base('absent')

        with _CapturedStdout() as out:
            parallel.ReleaseLockFile(base)

        self.assertIn('No lock file to release', out.text)
        self.assertNotIn('Exception', out.text)

    def test_releasing_an_absent_lock_does_not_raise(self):
        base = self._base('absent-quiet')

        parallel.ReleaseLockFile(base)  # must simply return

    def test_releasing_after_a_stale_lock_was_cleared_is_quiet(self):
        """The realistic path: our lock aged out and something else removed it."""
        base = self._base('cleared')
        parallel.TryEnterLockFile(base)
        os.remove(self._lock_path(base))

        with _CapturedStdout() as out:
            parallel.ReleaseLockFile(base)

        self.assertNotIn('Exception', out.text)


class _CapturedStdout:
    """Minimal stdout capture; this module reports through print()."""

    def __enter__(self):
        import io
        import sys
        self._real = sys.stdout
        self._buffer = io.StringIO()
        sys.stdout = self._buffer
        return self

    def __exit__(self, *exc_info):
        import sys
        sys.stdout = self._real
        self.text = self._buffer.getvalue()
        return False


if __name__ == '__main__':
    unittest.main()
