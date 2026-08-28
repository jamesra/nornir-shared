"""Directory recursion must not be pruned by a dotted ancestor path.

``_RecurseSubdirectoriesGeneratorTask`` skipped directories whose *full path*
contained a '.', rather than their own name.  One dotted ancestor -- a volume
directory named ``RC3.v2``, or any scan rooted beneath one -- therefore matched
every subdirectory and pruned the whole search after the root, silently
returning no results.

``RemoveDirectorySpaces`` tested the same way against a full glob path.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from nornir_shared import files

# DefaultExcludeList prunes names like 'TEM' and 'Mosaic', so the fixtures below
# deliberately avoid them.
_LEAF_FILE = 'volumedata.xml'


class _TreeTestCase(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _build(self, parent_name: str, volumes: tuple[str, ...] = ('VolumeA', 'VolumeB')) -> str:
        base = os.path.join(self._tmp.name, parent_name)
        for volume in volumes:
            leaf = os.path.join(base, volume, 'Section', 'Leveled')
            os.makedirs(leaf, exist_ok=True)
            with open(os.path.join(leaf, _LEAF_FILE), 'w'):
                pass
        return base

    def _relative_results(self, base: str, **kwargs) -> list[str]:
        return sorted(os.path.relpath(result.path, base)
                      for result in files.RecurseSubdirectories(base, **kwargs))


class TestDottedAncestorDoesNotPruneTheScan(_TreeTestCase):

    def test_dotted_parent_matches_clean_parent(self):
        clean = self._relative_results(self._build('RC3'))
        dotted = self._relative_results(self._build('RC3.v2'))

        self.assertEqual(dotted, clean)
        self.assertIn(os.path.join('VolumeA', 'Section', 'Leveled'), dotted)

    def test_dotted_parent_finds_required_files(self):
        base = self._build('RC3.v2')
        results = self._relative_results(base, RequiredFiles=[_LEAF_FILE])

        self.assertEqual(results, [os.path.join('VolumeA', 'Section', 'Leveled'),
                                   os.path.join('VolumeB', 'Section', 'Leveled')])

    def test_scan_is_not_pruned_to_the_root_alone(self):
        """The regression: everything below a dotted root disappeared."""
        results = self._relative_results(self._build('RC3.v2'))
        self.assertGreater(len(results), 1)

    def test_several_dotted_ancestors(self):
        base = self._build(os.path.join('RC3.v2', 'run.1'))
        results = self._relative_results(base)
        self.assertIn(os.path.join('VolumeA', 'Section', 'Leveled'), results)

    def test_threaded_branch(self):
        """More than three subdirectories takes the thread-pool path."""
        volumes = tuple(f'Volume{i}' for i in range(6))
        clean = self._relative_results(self._build('RC3', volumes=volumes))
        dotted = self._relative_results(self._build('RC3.v2', volumes=volumes))

        self.assertEqual(dotted, clean)
        self.assertEqual(len(dotted), 1 + (len(volumes) * 3))

    def test_serial_branch(self):
        """Three or fewer subdirectories runs on the calling thread."""
        volumes = ('VolumeA',)
        clean = self._relative_results(self._build('RC3', volumes=volumes))
        dotted = self._relative_results(self._build('RC3.v2', volumes=volumes))

        self.assertEqual(dotted, clean)
        self.assertEqual(len(dotted), 4)


class TestDottedDirectoryNamesAreStillSkipped(_TreeTestCase):
    """The intended behaviour -- skipping dot-named directories -- must survive."""

    def test_dot_named_directory_is_skipped(self):
        base = self._build('RC3')
        os.makedirs(os.path.join(base, 'skip.me', 'child'), exist_ok=True)

        results = self._relative_results(base)

        self.assertNotIn('skip.me', results)
        self.assertNotIn(os.path.join('skip.me', 'child'), results)

    def test_dot_named_directory_is_skipped_under_a_dotted_parent(self):
        base = self._build('RC3.v2')
        os.makedirs(os.path.join(base, 'skip.me'), exist_ok=True)

        results = self._relative_results(base)

        self.assertNotIn('skip.me', results)
        self.assertIn('VolumeA', results)

    def test_hidden_directory_is_skipped(self):
        base = self._build('RC3')
        os.makedirs(os.path.join(base, '.git'), exist_ok=True)

        self.assertNotIn('.git', self._relative_results(base))


class TestRemoveDirectorySpacesUnderDottedParent(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _run(self, parent_name: str) -> list[str]:
        base = os.path.join(self._tmp.name, parent_name)
        os.makedirs(os.path.join(base, 'Volume A'), exist_ok=True)
        os.makedirs(os.path.join(base, 'Volume B'), exist_ok=True)

        files.RemoveDirectorySpaces(base)
        return sorted(os.listdir(base))

    def test_spaces_removed_under_clean_parent(self):
        self.assertEqual(self._run('RC3'), ['Volume_A', 'Volume_B'])

    def test_spaces_removed_under_dotted_parent(self):
        """A dotted parent used to make every subdirectory look dotted."""
        self.assertEqual(self._run('RC3.v2'), ['Volume_A', 'Volume_B'])

    def test_dot_named_directory_is_left_alone(self):
        base = os.path.join(self._tmp.name, 'RC3')
        os.makedirs(os.path.join(base, 'keep me.bak'), exist_ok=True)

        files.RemoveDirectorySpaces(base)

        self.assertEqual(os.listdir(base), ['keep me.bak'])


if __name__ == '__main__':
    unittest.main()
