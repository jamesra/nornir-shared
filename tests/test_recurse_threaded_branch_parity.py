"""The threaded and serial recursion branches must search identically.

``_RecurseSubdirectoriesGeneratorTask`` picks a branch on tree width::

    if len(dirs) > 3:
        with concurrent.futures.ThreadPoolExecutor(...) as executor:
            ...
            task = executor.submit(_RecurseSubdirectoriesListTask,
                                   Path=fullpath, ..., 
                                   ExcludedDownsampleLevels=ExcludedDownsampleLevels_set)
                                   # caseInsensitive was not forwarded
    else:
        ...
        yield from _RecurseSubdirectoriesGeneratorTask(fullpath, ...,
                                                       caseInsensitive=caseInsensitive)

Both helpers default ``caseInsensitive=True``, so omitting it did not raise -- it silently
restored case-insensitive matching for every directory below the split. A search with
``caseInsensitive=False`` therefore returned different results depending on how many
subdirectories the parent happened to have, and the threshold is 3.

Measured before the fix, ``MatchNames=['abc']`` against leaves named ``ABC``:

    caseInsensitive=True    serial 3/3 matched    threaded 4/4 matched   agree
    caseInsensitive=False   serial 0/3 matched    threaded 4/4 matched   diverge

These tests compare the two branches against each other on trees that differ only in
width, so they pin parity rather than either branch's absolute answer.

The finding also noted the missing ``MatchNames is not None`` guard in the threaded branch.
That one is redundant rather than harmful: ``check_if_str_matches`` returns ``None`` for a
``None`` criteria, which is falsy, so both branches skip. The guard is now present in both
so they read alike, and the behaviour is pinned below.
"""
from __future__ import annotations

import os
import tempfile
import unittest

from nornir_shared import files

# _RecurseSubdirectoriesGeneratorTask threads when a directory has more than this many
# subdirectories. Serial and threaded trees straddle it.
SERIAL_WIDTH = 3
THREADED_WIDTH = 4


class _TreeFixture(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _tree(self, width, leaf_name='ABC', files_in_leaf=()):
        """`width` children at the root, each holding one leaf directory."""
        root = os.path.join(self._tmp.name, f'w{width}_{leaf_name}_{len(files_in_leaf)}')
        for i in range(width):
            leaf = os.path.join(root, f'sub{i}', leaf_name)
            os.makedirs(leaf, exist_ok=True)
            for filename in files_in_leaf:
                open(os.path.join(leaf, filename), 'w').close()
        return root

    def _relative_hits(self, width, **kwargs):
        """Walk a tree of the given width, as root-relative posix paths."""
        root = self._tree(width, leaf_name=kwargs.pop('leaf_name', 'ABC'),
                          files_in_leaf=kwargs.pop('files_in_leaf', ()))
        results = files.RecurseSubdirectoriesGenerator(root, **kwargs)
        return sorted(os.path.relpath(r[0], root).replace(os.sep, '/') for r in results)

    def _leaf_match_fraction(self, width, leaf_name='ABC', **kwargs):
        """Fraction of leaves reported, so widths 3 and 4 are comparable."""
        hits = self._relative_hits(width, leaf_name=leaf_name, **kwargs)
        matched = [p for p in hits if p.endswith(leaf_name)]
        return len(matched) / width


class TestCaseSensitiveMatchNamesParity(_TreeFixture):
    """The regression: caseInsensitive=False was honoured only on the serial branch."""

    def test_case_sensitive_match_agrees_across_branches(self):
        serial = self._leaf_match_fraction(SERIAL_WIDTH, MatchNames=['abc'],
                                           caseInsensitive=False)
        threaded = self._leaf_match_fraction(THREADED_WIDTH, MatchNames=['abc'],
                                             caseInsensitive=False)

        self.assertEqual(serial, threaded,
                         'tree width must not change case sensitivity')

    def test_a_case_sensitive_search_does_not_match_a_differing_case_leaf(self):
        """Pins the correct answer, not just agreement."""
        for width in (SERIAL_WIDTH, THREADED_WIDTH):
            with self.subTest(width=width):
                self.assertEqual(
                    self._leaf_match_fraction(width, MatchNames=['abc'],
                                              caseInsensitive=False),
                    0.0)

    def test_case_insensitive_match_agrees_across_branches(self):
        serial = self._leaf_match_fraction(SERIAL_WIDTH, MatchNames=['abc'],
                                           caseInsensitive=True)
        threaded = self._leaf_match_fraction(THREADED_WIDTH, MatchNames=['abc'],
                                             caseInsensitive=True)

        self.assertEqual(serial, threaded)

    def test_a_case_insensitive_search_matches_every_leaf(self):
        for width in (SERIAL_WIDTH, THREADED_WIDTH):
            with self.subTest(width=width):
                self.assertEqual(
                    self._leaf_match_fraction(width, MatchNames=['abc'],
                                              caseInsensitive=True),
                    1.0)

    def test_an_exact_case_match_works_on_both_branches(self):
        """caseInsensitive=False must still match when the case genuinely agrees."""
        for width in (SERIAL_WIDTH, THREADED_WIDTH):
            with self.subTest(width=width):
                self.assertEqual(
                    self._leaf_match_fraction(width, MatchNames=['ABC'],
                                              caseInsensitive=False),
                    1.0)

    def test_the_two_settings_actually_differ(self):
        """Guards the test itself: without this the parity checks could pass vacuously."""
        insensitive = self._leaf_match_fraction(THREADED_WIDTH, MatchNames=['abc'],
                                                caseInsensitive=True)
        sensitive = self._leaf_match_fraction(THREADED_WIDTH, MatchNames=['abc'],
                                              caseInsensitive=False)

        self.assertNotEqual(insensitive, sensitive)


class TestWidthDoesNotChangeResults(_TreeFixture):
    """Nothing about the search should depend on which branch ran."""

    def _shape(self, width, **kwargs):
        """Root-relative hits with the width-specific sub<N> prefix removed."""
        hits = self._relative_hits(width, **kwargs)
        return sorted({p.split('/', 1)[1] if '/' in p else '.' for p in hits})

    def test_default_search_shape_matches(self):
        self.assertEqual(self._shape(SERIAL_WIDTH), self._shape(THREADED_WIDTH))

    def test_case_sensitive_default_search_shape_matches(self):
        self.assertEqual(self._shape(SERIAL_WIDTH, caseInsensitive=False),
                         self._shape(THREADED_WIDTH, caseInsensitive=False))

    def test_required_files_shape_matches_case_sensitively(self):
        kwargs = dict(files_in_leaf=('Marker.TXT',), RequiredFiles=['Marker.TXT'],
                      caseInsensitive=False)

        self.assertEqual(self._shape(SERIAL_WIDTH, **kwargs),
                         self._shape(THREADED_WIDTH, **kwargs))

    def test_excluded_downsample_levels_shape_matches(self):
        kwargs = dict(leaf_name='001', ExcludedDownsampleLevels=[1])

        self.assertEqual(self._shape(SERIAL_WIDTH, **kwargs),
                         self._shape(THREADED_WIDTH, **kwargs))

    def test_wide_trees_still_thread(self):
        """A much wider tree, past the 8-worker cap, stays consistent."""
        wide = self._leaf_match_fraction(20, MatchNames=['abc'], caseInsensitive=False)

        self.assertEqual(wide, 0.0)


class TestNoneMatchNamesIsFalsy(_TreeFixture):
    """The redundant-guard half of the finding."""

    def test_check_if_str_matches_returns_none_for_a_none_criteria(self):
        for ci in (True, False):
            with self.subTest(caseInsensitive=ci):
                result = files.check_if_str_matches('anything', None, ci)

                self.assertIsNone(result)
                self.assertFalse(bool(result), 'both branches rely on this being falsy')

    def test_a_search_without_match_names_still_recurses(self):
        """If the None case were truthy, the walk would stop at depth 1."""
        for width in (SERIAL_WIDTH, THREADED_WIDTH):
            with self.subTest(width=width):
                hits = self._relative_hits(width, leaf_name='Deep')

                self.assertTrue(any('/' in p for p in hits),
                                'recursion must reach below the root')


if __name__ == '__main__':
    unittest.main()
