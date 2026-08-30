"""rmtree must not recurse through the executor it then blocks on.

The old implementation submitted *itself* into the caller's executor once per
subdirectory and then blocked on the results::

    directory_remover = functools.partial(rmtree, executor=executor, ...)
    for folder in folders:
        folder_futures.append(executor.submit(directory_remover, folder))
    ...
    for f in as_completed(folder_futures):
        f.result()

That is a self-inflicted thread-pool deadlock. A worker running one directory submits
its subdirectory behind itself in the same queue and then waits for it. Once every
worker is in that state, no queued item can ever start and the pool is wedged forever.

Measured against the original code, each case in its own child process with a 40 s
timeout. "HUNG" means killed at the timeout, not merely slow:

    tree shape                                     workers      before
    3 top dirs, 50 files + a 5-file subdir         2            HUNG
    8 top dirs, 50 files + a 60-file subdir        4            HUNG
    34 top dirs, 50 files + a 60-file subdir       32 (default) HUNG
    34 top dirs, 50 files + a 5-file subdir        32 (default) completed, 0.11 s
    chain of 60 nested dirs, 1 file each           32 (default) completed, 0.04 s
    chain of 200 nested dirs, 1 file each          32 (default) HUNG

Every case completes after the fix.

The two survivors are worth understanding, because they show the shutil shortcut is
what masked this. With 5-file subdirectories, tracing showed 29 of the 32 workers
blocked in the recursive path; it finished only because those subdirectories were small
enough to take the shutil branch and a few workers happened to stay free. It is luck,
not safety.

The chains explain why depth alone is not the trigger. `path_entry_count` counts
recursively, so in a 60-link chain only the top ~11 levels see 50 or more descendants
and take the threaded path; the rest fall to the shutil branch and return without
blocking. Eleven blocked workers out of 32 is survivable. At 200 links roughly 150
levels take the threaded path, which exhausts the pool and wedges it.

The fix submits only self-contained work: file unlinks, link removals, and small
subtrees removed whole by ``shutil.rmtree``, which never touches the caller's executor.
A worker that finds a subtree too large to remove whole hands it back, and the calling
thread walks it. Nothing inside the executor ever waits on the executor.

Submissions are kept to ``_RMTREE_MAX_PENDING_UNLINKS`` in flight so a tree of millions
of files does not materialise a future per file.

Deciding "is this subtree small" inside the worker rather than on the calling thread
matters for speed, not just tidiness. `path_entry_count` scans the subtree, and doing
that serially cost about 2x on trees of many small directories. Measured against the
original, best of 5 runs each, all shapes chosen so the original does not deadlock:

    shape                                            before      after
    4 dirs x 2500 files + 5-file subs  (10020)       717 ms      660 ms
    10 dirs x 500 files + 5-file subs  (5050)        328 ms      309 ms
    20 dirs x 200 files + 5-file subs  (4100)        252 ms      241 ms
    200 dirs x 20 files + 2-file subs  (4400)        201 ms      207 ms
    400 dirs x 10 files + 2-file subs  (4800)        233 ms      233 ms

Timeouts here are generous and every helper runs the call on a daemon thread, so a
regression reports as a failure instead of hanging the suite.
"""
from __future__ import annotations

import concurrent.futures
import os
import shutil
import tempfile
import threading
import time
import unittest

from nornir_shared import files

#: A regression deadlocks outright, so this only has to beat the real runtime, which is
#: hundredths of a second for these trees.
TIMEOUT_SECONDS = 30


def default_max_workers() -> int:
    return min(32, (os.cpu_count() or 1) + 4)


def call_with_timeout(fn, timeout_s=TIMEOUT_SECONDS):
    """Run fn on a daemon thread. Returns (finished, error). A wedged thread cannot
    block interpreter exit, so a regression fails rather than hanging the run."""
    outcome = {}

    def target():
        try:
            fn()
            outcome['error'] = None
        except BaseException as e:  # noqa: BLE001 - reported to the assertion below
            outcome['error'] = e

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout_s)
    if thread.is_alive():
        return False, None
    return True, outcome.get('error')


class _TreeFixture(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self._tmp, ignore_errors=True))

    def _write(self, path, text='x'):
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(text)

    def _wide_tree(self, num_top_dirs, files_per_dir=50, files_per_sub=60):
        """Each top dir clears the 50-entry threshold and owns a subdirectory, so the
        old code submitted a folder future and then blocked on it."""
        root = os.path.join(self._tmp, f'wide{num_top_dirs}_{files_per_sub}')
        for d in range(num_top_dirs):
            top = os.path.join(root, f'd{d:03d}')
            sub = os.path.join(top, 'sub')
            os.makedirs(sub, exist_ok=True)
            for f in range(files_per_dir):
                self._write(os.path.join(top, f'f{f:03d}.txt'))
            for f in range(files_per_sub):
                self._write(os.path.join(sub, f's{f:03d}.txt'))
        return root

    def _deep_chain(self, depth, files_per_level=1):
        """Depth alone wedges the pool: each level consumed a worker and waited on the
        next, so a chain longer than max_workers could never finish."""
        root = os.path.join(self._tmp, f'deep{depth}')
        path = root
        for level in range(depth):
            path = os.path.join(path, f'L{level:03d}')
            os.makedirs(path, exist_ok=True)
            for f in range(files_per_level):
                self._write(os.path.join(path, f'f{f}.txt'))
        return root

    def _assert_removed(self, root, finished, error):
        self.assertTrue(finished,
                        f'rmtree did not return within {TIMEOUT_SECONDS}s: deadlock')
        self.assertIsNone(error, f'rmtree raised {error!r}')
        self.assertFalse(os.path.exists(root), 'tree was not removed')


class TestDeadlockIsGone(_TreeFixture):

    def test_a_two_worker_executor_completes(self):
        """The smallest reproduction: 3 directories, 2 workers."""
        root = self._wide_tree(3, files_per_sub=5)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            finished, error = call_with_timeout(lambda: files.rmtree(root, executor=ex))

        self._assert_removed(root, finished, error)

    def test_a_single_worker_executor_completes(self):
        root = self._wide_tree(3, files_per_sub=5)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            finished, error = call_with_timeout(lambda: files.rmtree(root, executor=ex))

        self._assert_removed(root, finished, error)

    def test_more_top_dirs_than_workers_completes_on_the_default_pool(self):
        """Hung before the fix with no caller-supplied executor at all."""
        root = self._wide_tree(default_max_workers() + 2)

        finished, error = call_with_timeout(lambda: files.rmtree(root))

        self._assert_removed(root, finished, error)

    def test_exactly_as_many_top_dirs_as_workers_completes(self):
        root = self._wide_tree(default_max_workers())

        finished, error = call_with_timeout(lambda: files.rmtree(root))

        self._assert_removed(root, finished, error)

    def test_a_moderately_deep_chain_completes(self):
        """This depth completed before the fix too; kept as a shape check, since only
        the top ~11 levels of a 60-link chain clear the 50-descendant threshold."""
        root = self._deep_chain(60)

        finished, error = call_with_timeout(lambda: files.rmtree(root))

        self._assert_removed(root, finished, error)

    def test_a_very_deep_chain_completes(self):
        """200 links wedged the default pool: about 150 levels take the threaded path,
        far more than the 32 workers available."""
        root = self._deep_chain(200)

        finished, error = call_with_timeout(lambda: files.rmtree(root))

        self._assert_removed(root, finished, error)

    def test_a_four_worker_executor_on_eight_dirs_completes(self):
        root = self._wide_tree(8)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            finished, error = call_with_timeout(lambda: files.rmtree(root, executor=ex))

        self._assert_removed(root, finished, error)


def _scandir_entry(path: str) -> os.DirEntry:
    """The os.DirEntry for path, since the link predicate reads a cached lstat."""
    parent = os.path.dirname(path)
    name = os.path.basename(path)
    with os.scandir(parent) as entries:
        for entry in entries:
            if entry.name == name:
                return entry
    raise AssertionError(f'{path} not found by scandir')


def _executable_source(fn) -> str:
    """Source of fn with its docstring and comments removed.

    The docstring names both `functools.partial` and `as_completed` while explaining
    what used to go wrong here, so a plain substring scan of the source would match
    the explanation rather than any surviving code.
    """
    import ast
    import inspect
    import textwrap

    parsed = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    definition = parsed.body[0]
    body = definition.body
    if (isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]

    # ast.unparse drops comments, so only real code is left to scan.
    return '\n'.join(ast.unparse(node) for node in body)


class _CountingExecutor:
    """Records what rmtree submits. rmtree only ever calls submit on a supplied
    executor, since it shuts down only executors it created itself."""

    def __init__(self, max_workers=4):
        self._real = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self.submitted = []
        self.outstanding = 0
        self.max_outstanding = 0
        self._lock = threading.Lock()

    def submit(self, fn, *args, **kwargs):
        with self._lock:
            self.submitted.append(fn)
            self.outstanding += 1
            self.max_outstanding = max(self.max_outstanding, self.outstanding)
        future = self._real.submit(fn, *args, **kwargs)
        future.add_done_callback(self._done)
        return future

    def _done(self, _future):
        with self._lock:
            self.outstanding -= 1

    def shutdown(self, wait=True):
        self._real.shutdown(wait=wait)


class TestNothingRecursesIntoTheExecutor(_TreeFixture):

    def test_only_self_contained_work_is_submitted(self):
        """Everything submitted must be able to finish without the executor.

        os.remove and _remove_link are plainly self-contained.
        _remove_subtree_if_small either calls shutil.rmtree, which never touches this
        executor, or declines and hands the subtree back to the calling thread.
        """
        root = self._wide_tree(6)
        ex = _CountingExecutor()
        self.addCleanup(ex.shutdown)

        finished, error = call_with_timeout(lambda: files.rmtree(root, executor=ex))

        self._assert_removed(root, finished, error)
        allowed = {os.remove, files._remove_link, files._remove_subtree_if_small}
        self.assertTrue(set(ex.submitted).issubset(allowed),
                        f'unexpected work submitted: {set(ex.submitted) - allowed}')

    def test_rmtree_is_never_submitted(self):
        root = self._wide_tree(6)
        ex = _CountingExecutor()
        self.addCleanup(ex.shutdown)

        call_with_timeout(lambda: files.rmtree(root, executor=ex))

        names = {getattr(fn, '__name__', repr(fn)) for fn in ex.submitted}
        self.assertNotIn('rmtree', names)

    def test_something_was_actually_submitted(self):
        """Guards the two tests above against passing on an empty submission list."""
        root = self._wide_tree(6)
        ex = _CountingExecutor()
        self.addCleanup(ex.shutdown)

        call_with_timeout(lambda: files.rmtree(root, executor=ex))

        self.assertGreater(len(ex.submitted), 100)

    def test_the_source_no_longer_partially_applies_rmtree(self):
        code = _executable_source(files.rmtree)

        self.assertNotIn('functools.partial', code)
        self.assertNotIn('as_completed', code)

    def test_the_body_still_submits_to_the_executor(self):
        """Guards the assertions above from passing on an empty or mis-parsed body."""
        code = _executable_source(files.rmtree)

        self.assertIn('executor.submit', code)


class TestUnlinksAreBounded(_TreeFixture):

    def test_the_cap_exists_and_is_sane(self):
        self.assertGreater(files._RMTREE_MAX_PENDING_UNLINKS, 0)

    def test_in_flight_unlinks_stay_near_the_cap(self):
        root = self._wide_tree(4)
        total = sum(len(f) for _, _, f in os.walk(root))
        ex = _CountingExecutor()
        self.addCleanup(ex.shutdown)

        original = files._RMTREE_MAX_PENDING_UNLINKS
        files._RMTREE_MAX_PENDING_UNLINKS = 8
        self.addCleanup(lambda: setattr(files, '_RMTREE_MAX_PENDING_UNLINKS', original))

        finished, error = call_with_timeout(lambda: files.rmtree(root, executor=ex))

        self._assert_removed(root, finished, error)
        self.assertGreater(total, 100, 'tree too small to say anything about bounding')
        self.assertLess(ex.max_outstanding, total // 2,
                        f'{ex.max_outstanding} unlinks in flight for {total} files')

    def test_a_tiny_cap_still_removes_everything(self):
        """Exercises the drain-as-you-go path rather than the final drain."""
        root = self._wide_tree(3)
        original = files._RMTREE_MAX_PENDING_UNLINKS
        files._RMTREE_MAX_PENDING_UNLINKS = 1
        self.addCleanup(lambda: setattr(files, '_RMTREE_MAX_PENDING_UNLINKS', original))

        finished, error = call_with_timeout(lambda: files.rmtree(root))

        self._assert_removed(root, finished, error)


class TestRemovesTheWholeTree(_TreeFixture):

    def test_a_small_tree_takes_the_shutil_shortcut_and_is_removed(self):
        root = os.path.join(self._tmp, 'small')
        os.makedirs(root)
        for f in range(5):
            self._write(os.path.join(root, f'f{f}.txt'))

        files.rmtree(root)

        self.assertFalse(os.path.exists(root))

    def test_a_missing_directory_is_a_no_op(self):
        files.rmtree(os.path.join(self._tmp, 'never-existed'))

    def test_empty_nested_directories_are_removed(self):
        root = self._wide_tree(4)
        for d in range(4):
            os.makedirs(os.path.join(root, f'd{d:03d}', 'empty', 'deeper'))

        finished, error = call_with_timeout(lambda: files.rmtree(root))

        self._assert_removed(root, finished, error)

    def test_no_files_are_left_behind(self):
        root = self._wide_tree(6)
        expected = sum(len(f) for _, _, f in os.walk(root))
        self.assertGreater(expected, 0)

        finished, error = call_with_timeout(lambda: files.rmtree(root))

        self._assert_removed(root, finished, error)

    def test_a_sibling_tree_is_untouched(self):
        root = self._wide_tree(4)
        keep = os.path.join(self._tmp, 'keep')
        os.makedirs(keep)
        self._write(os.path.join(keep, 'precious.txt'), 'do not delete')

        call_with_timeout(lambda: files.rmtree(root))

        self.assertTrue(os.path.exists(os.path.join(keep, 'precious.txt')))


class TestErrorHandling(_TreeFixture):

    def _tree_with_failing_unlink(self, exception, unlink_anyway=False):
        """Make one unlink raise. With unlink_anyway the file really is removed first,
        which is what a genuine race looks like: something else already deleted it."""
        root = self._wide_tree(3)
        real_remove = os.remove
        target = {'hit': False}

        def failing_remove(path):
            if not target['hit'] and path.endswith('f000.txt'):
                target['hit'] = True
                if unlink_anyway:
                    real_remove(path)
                raise exception
            return real_remove(path)

        os.remove = failing_remove
        self.addCleanup(lambda: setattr(os, 'remove', real_remove))
        return root

    def test_a_failed_unlink_propagates_by_default(self):
        root = self._tree_with_failing_unlink(PermissionError('locked'))

        finished, error = call_with_timeout(lambda: files.rmtree(root))

        self.assertTrue(finished, 'rmtree hung instead of reporting the error')
        self.assertIsInstance(error, PermissionError)

    def test_ignore_errors_swallows_a_failed_unlink(self):
        root = self._tree_with_failing_unlink(PermissionError('locked'))

        finished, error = call_with_timeout(
            lambda: files.rmtree(root, ignore_errors=True))

        self.assertTrue(finished)
        self.assertIsNone(error, f'ignore_errors=True still raised {error!r}')

    def test_a_vanished_file_is_not_an_error(self):
        """FileNotFoundError is expected when something else is deleting too."""
        root = self._tree_with_failing_unlink(FileNotFoundError('already gone'),
                                              unlink_anyway=True)

        finished, error = call_with_timeout(lambda: files.rmtree(root))

        self.assertTrue(finished)
        self.assertIsNone(error, f'a vanished file raised {error!r}')
        self.assertFalse(os.path.exists(root))


def _can_symlink(directory):
    probe = os.path.join(directory, '_symlink_probe')
    target = os.path.join(directory, '_symlink_target')
    try:
        os.makedirs(target, exist_ok=True)
        os.symlink(target, probe, target_is_directory=True)
    except (OSError, NotImplementedError, AttributeError):
        return False
    finally:
        if os.path.islink(probe):
            os.unlink(probe)
    return True


class TestDirectorySymlinksAreNotFollowed(_TreeFixture):
    """The small-directory branch delegates to shutil.rmtree, which refuses to follow
    directory symlinks, but the threaded branch used entry.is_dir(), which follows them.
    The same tree therefore deleted data outside itself or not depending only on how
    many entries it happened to have."""

    def setUp(self):
        super().setUp()
        if not _can_symlink(self._tmp):
            self.skipTest('creating directory symlinks is not permitted here')

    def test_the_symlink_target_contents_survive(self):
        root = self._wide_tree(3)
        outside = os.path.join(self._tmp, 'outside')
        os.makedirs(outside)
        precious = os.path.join(outside, 'precious.txt')
        self._write(precious, 'must survive')
        os.symlink(outside, os.path.join(root, 'd000', 'link'),
                   target_is_directory=True)

        finished, error = call_with_timeout(lambda: files.rmtree(root))

        self._assert_removed(root, finished, error)
        self.assertTrue(os.path.exists(precious),
                        'rmtree deleted through a directory symlink')

    def test_the_link_itself_is_removed(self):
        root = self._wide_tree(3)
        outside = os.path.join(self._tmp, 'outside2')
        os.makedirs(outside)
        link = os.path.join(root, 'd000', 'link')
        os.symlink(outside, link, target_is_directory=True)

        call_with_timeout(lambda: files.rmtree(root))

        self.assertFalse(os.path.lexists(link))


def _make_junction(link_path, target) -> bool:
    """Windows junctions need no elevation, unlike symlinks, so these tests actually
    run on a stock developer machine where the symlink cases above skip."""
    import subprocess

    if os.name != 'nt':
        return False

    completed = subprocess.run(['cmd', '/c', 'mklink', '/J', link_path, target],
                               capture_output=True, text=True)
    return completed.returncode == 0


class TestDirectoryJunctionsAreNotFollowed(_TreeFixture):
    """Junctions are the trap that symlink handling alone misses.

    A junction reports False from both os.path.islink and os.path.ismount, yet os.walk
    descends into it. Detecting only symlinks still walked out of the tree and deleted
    the target's contents. os.path.isjunction, added in Python 3.12, is what catches it.
    """

    def setUp(self):
        super().setUp()
        if os.name != 'nt':
            self.skipTest('junctions are Windows-only')

    def _tree_with_junction(self, name):
        root = self._wide_tree(3)
        outside = os.path.join(self._tmp, f'outside_{name}')
        os.makedirs(outside, exist_ok=True)
        precious = os.path.join(outside, 'precious.txt')
        self._write(precious, 'must survive')
        link = os.path.join(root, 'd000', 'link')
        if not _make_junction(link, outside):
            self.skipTest('could not create a junction here')
        return root, link, precious

    def test_the_junction_target_contents_survive(self):
        root, _link, precious = self._tree_with_junction('contents')

        finished, error = call_with_timeout(lambda: files.rmtree(root))

        self._assert_removed(root, finished, error)
        self.assertTrue(os.path.exists(precious),
                        'rmtree deleted through a directory junction')

    def test_the_junction_itself_is_removed(self):
        root, link, _precious = self._tree_with_junction('link')

        call_with_timeout(lambda: files.rmtree(root))

        self.assertFalse(os.path.lexists(link))

    def test_a_junction_does_not_stop_the_removal(self):
        """The original raised "Cannot call rmtree on a symbolic link" and left the
        tree half-deleted once recursion reached the junction."""
        root, _link, _precious = self._tree_with_junction('completes')

        finished, error = call_with_timeout(lambda: files.rmtree(root))

        self.assertIsNone(error, f'a junction in the tree raised {error!r}')
        self.assertFalse(os.path.exists(root))

    def test_the_link_predicate_recognises_a_junction(self):
        root, link, _precious = self._tree_with_junction('predicate')
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        self.assertTrue(files._entry_is_link(_scandir_entry(link)))

    def test_the_predicate_does_not_flag_a_real_directory(self):
        root = self._wide_tree(1)

        self.assertFalse(files._entry_is_link(_scandir_entry(
            os.path.join(root, 'd000'))))

    def test_the_predicate_does_not_flag_a_file(self):
        root = self._wide_tree(1)

        self.assertFalse(files._entry_is_link(_scandir_entry(
            os.path.join(root, 'd000', 'f000.txt'))))


if __name__ == '__main__':
    unittest.main()
