"""Downsample level exclusion must accept string levels, which the signature promises.

``RecurseSubdirectoriesGenerator`` excluded pyramid directories with::

    ExcludeNames_set.union([DownsampleFormat % level for level in ExcludedDownsampleLevels_set])

where ``DownsampleFormat`` is ``'%03d'``. The set it iterates comes from
``ensure_string_set``, whose name and docstring ("Ensure the input is a set of lowercase
strings") both promise coercion it does not perform: a ``frozenset`` is returned unchanged,
and otherwise only items that are *already* strings get lowercased. Numbers stay numbers
and strings stay strings.

So ``'%03d' % level`` raised for any string level::

    TypeError: %d format: a real number is required, not str

The parameter is annotated ``Sequence[int] | frozenset[str] | None``, so string levels are
documented input. Worse, this module's own ``DefaultLevelStrings`` -- ``frozenset({'001',
'002', ...})`` -- was an invalid argument to its own function.

Measured before the fix:

    default (None)          ok
    ints [1, 2]             ok
    strings ['1', '2']      TypeError: %d format: a real number is required, not str
    frozenset({'001'})      TypeError: %d format: a real number is required, not str
    mixed [1, "2"]          TypeError: %d format: a real number is required, not str

In-tree callers all pass ``[]``, so nothing shipped was broken; the defect is in the API
surface. ``format_downsample_level`` now coerces, and reports a non-numeric level as a
``ValueError`` naming the value instead of a ``TypeError`` about ``%d``.
"""
from __future__ import annotations

import os
import tempfile
import unittest

from nornir_shared import files


class TestFormatDownsampleLevel(unittest.TestCase):

    def test_an_int_renders_zero_padded(self):
        self.assertEqual(files.format_downsample_level(1), '001')
        self.assertEqual(files.format_downsample_level(32), '032')

    def test_levels_wider_than_the_padding_are_not_truncated(self):
        self.assertEqual(files.format_downsample_level(1024), '1024')

    def test_a_numeric_string_renders_the_same_as_the_int(self):
        self.assertEqual(files.format_downsample_level('1'),
                         files.format_downsample_level(1))

    def test_an_already_formatted_level_round_trips(self):
        """'001' must come back as '001', not '00001' or a TypeError."""
        self.assertEqual(files.format_downsample_level('001'), '001')

    def test_the_modules_own_level_strings_are_valid_input(self):
        """DefaultLevelStrings used to be an invalid argument to this module."""
        rendered = {files.format_downsample_level(lev)
                    for lev in files.DefaultLevelStrings}

        self.assertEqual(rendered, set(files.DefaultLevelStrings))

    def test_default_levels_render_to_the_default_level_strings(self):
        rendered = {files.format_downsample_level(lev) for lev in files.DefaultLevels}

        self.assertEqual(rendered, set(files.DefaultLevelStrings))

    def test_a_non_numeric_level_raises_value_error_naming_the_value(self):
        with self.assertRaises(ValueError) as ctx:
            files.format_downsample_level('not-a-level')

        self.assertIn('not-a-level', str(ctx.exception))
        self.assertIn('numeric strings', str(ctx.exception))

    def test_a_non_numeric_level_is_not_a_type_error_about_percent_d(self):
        with self.assertRaises(ValueError):
            files.format_downsample_level(None)  # type: ignore[arg-type]


class TestEnsureStringSetDoesNotCoerce(unittest.TestCase):
    """Pin the behaviour that made the bug: the helper's name overpromises."""

    def test_a_frozenset_passes_through_unchanged(self):
        original = frozenset({'1', '2'})

        self.assertIs(files.ensure_string_set(original), original)

    def test_ints_stay_ints(self):
        result = files.ensure_string_set([1, 2], caseInsensitive=True)

        assert result is not None
        self.assertEqual({type(x) for x in result}, {int})


class TestExclusionAcceptsEveryDocumentedLevelType(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name

        os.makedirs(os.path.join(self.root, '001'))
        os.makedirs(os.path.join(self.root, '002'))
        os.makedirs(os.path.join(self.root, 'Keep'))

    def _walked_names(self, levels):
        results = list(files.RecurseSubdirectoriesGenerator(
            self.root, ExcludedDownsampleLevels=levels))
        return sorted(os.path.basename(r[0]) for r in results)

    def test_int_levels_exclude_the_matching_directories(self):
        names = self._walked_names([1, 2])

        self.assertNotIn('001', names)
        self.assertNotIn('002', names)
        self.assertIn('Keep', names)

    def test_string_levels_exclude_the_same_directories(self):
        self.assertEqual(self._walked_names(['1', '2']), self._walked_names([1, 2]))

    def test_preformatted_string_levels_exclude_the_same_directories(self):
        self.assertEqual(self._walked_names(['001', '002']), self._walked_names([1, 2]))

    def test_a_frozenset_of_strings_is_accepted(self):
        names = self._walked_names(frozenset({'001'}))

        self.assertNotIn('001', names)
        self.assertIn('Keep', names)

    def test_mixed_int_and_string_levels_are_accepted(self):
        self.assertEqual(self._walked_names([1, '2']), self._walked_names([1, 2]))

    def test_an_empty_level_list_excludes_nothing(self):
        """What every in-tree caller passes; must not change."""
        names = self._walked_names([])

        self.assertIn('001', names)
        self.assertIn('002', names)
        self.assertIn('Keep', names)

    def test_the_default_excludes_pyramid_levels(self):
        results = list(files.RecurseSubdirectoriesGenerator(self.root))
        names = sorted(os.path.basename(r[0]) for r in results)

        self.assertNotIn('001', names)
        self.assertIn('Keep', names)

    def test_a_non_numeric_level_reports_the_offending_value(self):
        with self.assertRaises(ValueError) as ctx:
            self._walked_names(['nonsense'])

        self.assertIn('nonsense', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
