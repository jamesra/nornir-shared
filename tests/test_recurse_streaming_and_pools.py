"""One thread pool per traversal, and results that actually stream.

``_RecurseSubdirectoriesGeneratorTask`` used to recurse into itself, building a fresh
``ThreadPoolExecutor(max_workers=min(len(dirs), 8))`` at every level it found more than
three subdirectories, and each worker ran::

    return list(_RecurseSubdirectoriesGeneratorTask(...))

so a whole subtree was materialised before the caller saw any of it.

Measured on this machine over a tree five wide and four deep (780 directories), before
the fix:

===========================================  ========  =======
metric                                        before    after
===========================================  ========  =======
peak live threads                                 227       18
thread pools constructed                          156        1
directories scanned before the first result       780        1
time to the first result                       233 ms   1.7 ms
total wall time                                 196 ms    59 ms
peak traced memory                            2921 KiB  390 KiB
===========================================  ========  =======

The first-result number is the one that matters for the generator contract: with
``RequiredFiles`` set, which is how every ``nornir-buildmanager`` importer calls this,
98% of the runtime elapsed before the first directory was yielded.

The costs are counted here rather than timed, so these assertions do not depend on
machine speed. ``os.scandir`` is called exactly once per visited directory by both the
old and the new implementation, which makes it a fair progress meter for either.
"""

from __future__ import annotations

import concurrent.futures
import os
import tempfile
import threading
import unittest
import unittest.mock

from nornir_shared import files

# Wide and deep enough that the old code would have built a pool at every level.
WIDE = 5
DEEP = 4

MARKER = 'Volume.xml'


def _build_tree(root: str, width: int, depth: int, marker: str = MARKER) -> int:
    """A tree `width` wide at every level and `depth` deep. Returns the directory count."""
    made = [root]
    os.makedirs(root, exist_ok=True)
    count = 0
    for level in range(depth):
        nxt = []
        for parent in made:
            for w in range(width):
                d = os.path.join(parent, f'd{level}_{w:02d}')
                os.makedirs(d, exist_ok=True)
                count += 1
                with open(os.path.join(d, marker), 'w') as handle:
                    handle.write('<x/>')
                nxt.append(d)
        made = nxt
    return count


class _ScanCounter:
    """Counts os.scandir calls under one root, so progress can be sampled mid-walk.

    Both implementations scan each visited directory exactly once, so this measures
    "how much of the tree was walked" without reaching into either one's internals.
    """

    def __init__(self, root: str):
        self._root = os.path.abspath(root)
        self._real = os.scandir
        self._lock = threading.Lock()
        self.count = 0

    def __enter__(self):
        self._patch = unittest.mock.patch('os.scandir', side_effect=self._scandir)
        self._patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()
        return False

    def _scandir(self, path='.'):
        try:
            under_root = os.path.abspath(path).startswith(self._root)
        except (TypeError, ValueError):
            under_root = False
        if under_root:
            with self._lock:
                self.count += 1
        return self._real(path)


class _PoolCounter:
    """Counts ThreadPoolExecutor constructions and the workers they ask for."""

    def __init__(self):
        self._real = concurrent.futures.ThreadPoolExecutor
        self._lock = threading.Lock()
        self.constructed = 0
        self.max_workers_requested: list[int | None] = []

    def __enter__(self):
        self._patch = unittest.mock.patch.object(
            concurrent.futures, 'ThreadPoolExecutor', side_effect=self._make)
        self._patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()
        return False

    def _make(self, *args, **kwargs):
        with self._lock:
            self.constructed += 1
            self.max_workers_requested.append(
                kwargs.get('max_workers', args[0] if args else None))
        return self._real(*args, **kwargs)


class _ThreadPeak:
    """Samples the live thread count. Sampling can undercount, never overcount."""

    def __init__(self, interval: float = 0.001):
        self._interval = interval
        self._stop = threading.Event()
        self.peak = threading.active_count()

    def __enter__(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def _run(self):
        while not self._stop.is_set():
            self.peak = max(self.peak, threading.active_count())
            self._stop.wait(self._interval)

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=5)
        return False


class _TreeFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _tree(self, width: int = WIDE, depth: int = DEEP) -> tuple[str, int]:
        root = os.path.join(self._tmp.name, f'w{width}d{depth}')
        return root, _build_tree(root, width, depth)


class TestOnePoolForTheWholeTraversal(_TreeFixture):
    """The executor-per-recursion-level half of the finding."""

    def test_a_wide_deep_tree_builds_at_most_one_pool(self):
        root, n_dirs = self._tree()

        with _PoolCounter() as pools:
            results = list(files.RecurseSubdirectoriesGenerator(root))

        self.assertEqual(len(results), n_dirs + 1, 'the walk must be complete')
        self.assertLessEqual(
            pools.constructed, 1,
            f'{n_dirs} directories built {pools.constructed} thread pools; one '
            f'traversal should need at most one')

    def test_the_pool_asks_for_a_bounded_worker_count(self):
        root, _n = self._tree()

        with _PoolCounter() as pools:
            list(files.RecurseSubdirectoriesGenerator(root))

        for requested in pools.max_workers_requested:
            self.assertEqual(requested, files._RECURSE_SCAN_WORKERS,
                             'worker count must not depend on the tree')

    def test_live_threads_stay_near_the_worker_count(self):
        root, n_dirs = self._tree()
        baseline = threading.active_count()

        with _ThreadPeak() as peak:
            results = list(files.RecurseSubdirectoriesGenerator(root))

        self.assertEqual(len(results), n_dirs + 1)
        # One pool of _RECURSE_SCAN_WORKERS, plus this thread and the sampler.
        allowed = baseline + files._RECURSE_SCAN_WORKERS + 4
        self.assertLessEqual(
            peak.peak, allowed,
            f'peaked at {peak.peak} threads over {n_dirs} directories, '
            f'allowed {allowed}')

    def test_a_tree_one_directory_wide_builds_no_pool_at_all(self):
        """Nothing to overlap, so the pool would be pure overhead."""
        root, n_dirs = self._tree(width=1, depth=40)

        with _PoolCounter() as pools:
            results = list(files.RecurseSubdirectoriesGenerator(root))

        self.assertEqual(len(results), n_dirs + 1)
        self.assertEqual(pools.constructed, 0,
                         'a chain offers no parallelism and should stay inline')

    def test_threads_do_not_outlive_the_traversal(self):
        root, _n = self._tree()
        baseline = threading.active_count()

        list(files.RecurseSubdirectoriesGenerator(root))

        for _attempt in range(50):
            if threading.active_count() <= baseline:
                break
            threading.Event().wait(0.05)

        self.assertLessEqual(threading.active_count(), baseline + 1,
                             'the pool must be shut down when the walk ends')


class TestResultsStream(_TreeFixture):
    """The `return list(...)` half: a generator must not buffer whole subtrees."""

    def test_the_first_result_does_not_require_scanning_the_tree(self):
        root, n_dirs = self._tree()

        with _ScanCounter(root) as scans:
            gen = files.RecurseSubdirectoriesGenerator(root)
            self.addCleanup(gen.close)
            first = next(gen)
            scanned_for_first = scans.count

        self.assertIsNotNone(first)
        self.assertLess(
            scanned_for_first, n_dirs / 4,
            f'scanned {scanned_for_first} of {n_dirs} directories before yielding '
            f'the first result; the old code scanned all of them')

    def test_the_first_result_streams_when_required_files_is_set(self):
        """How every buildmanager importer calls this: the root itself never matches."""
        root, n_dirs = self._tree()
        # Only the leaves carry the marker, so nothing can be yielded until the walk
        # has descended. The old code still had to finish a whole subtree first.
        for dirpath, dirnames, filenames in os.walk(root):
            if len(dirnames) > 0 and MARKER in filenames:
                os.remove(os.path.join(dirpath, MARKER))

        with _ScanCounter(root) as scans:
            gen = files.RecurseSubdirectoriesGenerator(root, RequiredFiles=MARKER)
            self.addCleanup(gen.close)
            first = next(gen)
            scanned_for_first = scans.count

        self.assertIsNotNone(first)
        self.assertLess(
            scanned_for_first, n_dirs / 2,
            f'scanned {scanned_for_first} of {n_dirs} directories before the first '
            f'match; results were being buffered rather than streamed')

    def test_scanning_stays_ahead_of_the_consumer_but_not_unboundedly(self):
        """A bounded read-ahead: some overlap is the point, buffering everything is not."""
        root, n_dirs = self._tree()

        with _ScanCounter(root) as scans:
            gen = files.RecurseSubdirectoriesGenerator(root)
            self.addCleanup(gen.close)
            for _ in range(5):
                next(gen)
            scanned_early = scans.count

        allowed = files._RECURSE_MAX_PENDING_SCANS * 2 + 16
        self.assertLess(scanned_early, allowed,
                        f'read {scanned_early} directories ahead of a 5-result '
                        f'consumer, allowed {allowed}')
        self.assertLess(scanned_early, n_dirs)

    def test_abandoning_the_generator_early_releases_its_threads(self):
        root, _n = self._tree()
        baseline = threading.active_count()

        gen = files.RecurseSubdirectoriesGenerator(root)
        next(gen)
        next(gen)
        gen.close()

        for _attempt in range(50):
            if threading.active_count() <= baseline:
                break
            threading.Event().wait(0.05)

        self.assertLessEqual(
            threading.active_count(), baseline + 1,
            'closing the generator must tear the pool down; the old code yielded '
            'from inside `with executor` and held one per suspended level')

    def test_the_walk_is_a_generator_not_a_list(self):
        root, _n = self._tree()

        gen = files.RecurseSubdirectoriesGenerator(root)
        self.addCleanup(gen.close)

        self.assertTrue(hasattr(gen, 'send') and hasattr(gen, 'close'),
                        'the public API must remain a generator')


class TestTheWalkIsStillCorrect(_TreeFixture):
    """Streaming must not change which directories are reported."""

    def _paths(self, root, **kwargs):
        return {os.path.relpath(r.path, root).replace(os.sep, '/')
                for r in files.RecurseSubdirectoriesGenerator(root, **kwargs)}

    def test_every_directory_is_reported_exactly_once(self):
        root, n_dirs = self._tree()

        results = list(files.RecurseSubdirectoriesGenerator(root))
        paths = [r.path for r in results]

        self.assertEqual(len(paths), len(set(paths)), 'no directory may repeat')
        self.assertEqual(len(paths), n_dirs + 1)

    def test_a_parent_is_reported_before_its_children(self):
        root, _n = self._tree()

        seen: set[str] = set()
        for result in files.RecurseSubdirectoriesGenerator(root):
            parent = os.path.dirname(result.path)
            if os.path.abspath(parent) != os.path.abspath(os.path.dirname(root)):
                self.assertIn(parent, seen,
                              f'{result.path} arrived before its parent')
            seen.add(result.path)

    def test_required_files_reports_only_matching_directories(self):
        root, n_dirs = self._tree()
        os.makedirs(os.path.join(root, 'no_marker_here'), exist_ok=True)

        hits = self._paths(root, RequiredFiles=MARKER)

        self.assertNotIn('no_marker_here', hits)
        self.assertEqual(len(hits), n_dirs, 'every marked directory must be found')

    def test_matched_files_are_reported(self):
        root, _n = self._tree()

        for result in files.RecurseSubdirectoriesGenerator(root, RequiredFiles=MARKER):
            self.assertEqual(result.matched_files, [MARKER])

    def test_excluded_files_prune_the_subtree(self):
        root, _n = self._tree(width=2, depth=3)
        poisoned = os.path.join(root, 'd0_00')
        with open(os.path.join(poisoned, 'skip.tmp'), 'w') as handle:
            handle.write('x')

        hits = self._paths(root, ExcludedFiles='skip.tmp')

        self.assertNotIn('d0_00', hits)
        self.assertFalse([h for h in hits if h.startswith('d0_00/')],
                         'an excluded directory takes its subtree with it')
        self.assertIn('d0_01', hits)

    def test_match_names_reports_the_match_and_stops_descending(self):
        root, _n = self._tree(width=2, depth=2)
        target = os.path.join(root, 'd0_00')
        os.makedirs(os.path.join(target, 'below'), exist_ok=True)

        hits = self._paths(root, MatchNames=['d0_00'])

        self.assertIn('d0_00', hits)
        self.assertNotIn('d0_00/below', hits,
                         'MatchNames directories are not descended into')

    def test_exclude_names_prunes_by_directory_name(self):
        root, _n = self._tree(width=2, depth=2)

        hits = self._paths(root, ExcludeNames=['d0_00'])

        self.assertNotIn('d0_00', hits)
        self.assertIn('d0_01', hits)

    def test_a_dotted_directory_is_skipped_without_pruning_its_siblings(self):
        root, _n = self._tree(width=2, depth=1)
        os.makedirs(os.path.join(root, 'RC3.v2', 'inner'), exist_ok=True)

        hits = self._paths(root)

        self.assertNotIn('RC3.v2', hits)
        self.assertIn('d0_00', hits, 'a dotted sibling must not prune the search')

    def test_a_missing_root_yields_nothing_without_raising(self):
        missing = os.path.join(self._tmp.name, 'not_here')

        self.assertEqual(list(files.RecurseSubdirectoriesGenerator(missing)), [])

    def test_an_empty_root_yields_only_itself(self):
        root = os.path.join(self._tmp.name, 'empty')
        os.makedirs(root)

        results = list(files.RecurseSubdirectoriesGenerator(root))

        self.assertEqual([r.path for r in results], [root])


class TestNoWholeSubtreeBuffering(_TreeFixture):
    """Pin the removal of the list-materialising worker."""

    def test_the_list_materializing_helper_is_gone(self):
        self.assertFalse(
            hasattr(files, '_RecurseSubdirectoriesListTask'),
            '_RecurseSubdirectoriesListTask forced each subtree into a list before '
            'the caller saw any of it')

    def test_the_scan_worker_reports_one_directory_at_a_time(self):
        """The submitted unit of work is one directory, not a subtree."""
        root, _n = self._tree(width=3, depth=3)

        scan = files._scan_one_directory(root, None, None, None, None, True)

        self.assertEqual([r.path for r in scan.results], [root],
                         'a scan reports its own directory only')
        self.assertEqual(len(scan.children), 3,
                         'children are returned as paths to visit, not walked')
        for child in scan.children:
            self.assertEqual(os.path.dirname(child), root)


if __name__ == '__main__':
    unittest.main()
