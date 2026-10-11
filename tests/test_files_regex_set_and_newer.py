"""Characterization tests for ``nornir_shared.files.ensure_regex_or_set`` and ``path_is_significantly_newer``.

``ensure_regex_or_set`` normalizes the ``RequiredFiles`` / ``ExcludedFiles`` / ``MatchNames``
arguments of ``RecurseSubdirectoriesGenerator`` and the SerialEM ``*.idoc`` importer pattern;
the result is applied with ``check_if_str_matches`` (``re.Pattern.match``).
``path_is_significantly_newer`` is the freshness check buildmanager's stos-group and
refine orchestrators call directly.
"""
from __future__ import annotations

import os
import re
import tempfile
import unittest

from hypothesis import example, given
from hypothesis import strategies as st
from nornir_shared import files

_NAME_CHARS = st.text(alphabet='abcXYZ019_-.', max_size=12)
_EXTENSIONS = st.text(alphabet='abcdefxyz0123', min_size=1, max_size=6)


def _touch(path: str) -> None:
    """Create an empty file at *path*."""
    with open(path, 'w'):
        pass


class EnsureRegexOrSetTests(unittest.TestCase):
    """``ensure_regex_or_set`` routes each argument shape to a regex or a frozenset."""

    def test_none_passes_through(self) -> None:
        self.assertIsNone(files.ensure_regex_or_set(None))
        self.assertIsNone(files.ensure_regex_or_set(None, caseInsensitive=True))

    def test_compiled_pattern_returned_unchanged(self) -> None:
        pattern = re.compile(r'tile\d+')
        self.assertIs(files.ensure_regex_or_set(pattern), pattern)
        # caseInsensitive does not recompile a caller's pattern.
        self.assertIs(files.ensure_regex_or_set(pattern, caseInsensitive=True), pattern)
        # A caller's flags survive (not rebuilt from ``pattern.pattern``).
        flagged = re.compile(r'Tile\d+', re.IGNORECASE)
        self.assertIs(files.ensure_regex_or_set(flagged, caseInsensitive=False), flagged)

    def test_star_glob_converted_to_anchored_regex(self) -> None:
        pattern = files.ensure_regex_or_set('*.idoc')
        assert isinstance(pattern, re.Pattern)
        self.assertEqual(pattern.pattern, r'.*\.idoc$')
        self.assertIsNotNone(pattern.match('capture.idoc'))
        self.assertIsNotNone(pattern.match('1.idoc'))
        self.assertIsNone(pattern.match('capture.idoc.bak'), 'pattern must be anchored at the end')
        self.assertIsNone(pattern.match('captureXidoc'), 'the dot must be escaped')
        self.assertIsNone(pattern.match('capture.IDOC'), 'case-sensitive by default')

    def test_case_insensitive_sets_ignorecase(self) -> None:
        pattern = files.ensure_regex_or_set('*.idoc', caseInsensitive=True)
        assert isinstance(pattern, re.Pattern)
        self.assertTrue(pattern.flags & re.IGNORECASE)
        self.assertIsNotNone(pattern.match('Capture.IDOC'))

        sensitive = files.ensure_regex_or_set('*.idoc', caseInsensitive=False)
        assert isinstance(sensitive, re.Pattern)
        self.assertFalse(sensitive.flags & re.IGNORECASE)

    def test_plain_string_compiled_as_regex(self) -> None:
        pattern = files.ensure_regex_or_set(r'tile\d+\.png')
        assert isinstance(pattern, re.Pattern)
        # Not glob-converted: the string is used as the regex verbatim.
        self.assertEqual(pattern.pattern, r'tile\d+\.png')
        self.assertIsNotNone(pattern.match('tile12.png'))
        self.assertIsNone(pattern.match('TILE12.png'))

        insensitive = files.ensure_regex_or_set(r'tile\d+\.png', caseInsensitive=True)
        assert isinstance(insensitive, re.Pattern)
        self.assertIsNotNone(insensitive.match('TILE12.PNG'))

    def test_sequence_becomes_frozenset(self) -> None:
        self.assertEqual(files.ensure_regex_or_set(['A.txt', 'b.txt']), frozenset({'A.txt', 'b.txt'}))
        self.assertEqual(files.ensure_regex_or_set(['A.txt', 'b.txt'], caseInsensitive=True),
                         frozenset({'a.txt', 'b.txt'}))
        self.assertEqual(files.ensure_regex_or_set([]), frozenset())

    def test_frozenset_identity_and_lowercasing(self) -> None:
        original = frozenset({'Mosaic', 'tem'})
        self.assertIs(files.ensure_regex_or_set(original), original)
        self.assertEqual(files.ensure_regex_or_set(original, caseInsensitive=True), frozenset({'mosaic', 'tem'}))

    @given(stem=_NAME_CHARS, ext=_EXTENSIONS, suffix=_NAME_CHARS, case_insensitive=st.booleans())
    @example(stem='a', ext='idoc', suffix='', case_insensitive=False)
    @example(stem='a', ext='idoc', suffix='.bak', case_insensitive=False)
    @example(stem='aXidoc', ext='idoc', suffix='', case_insensitive=False)
    def test_property_star_glob_matches_names_ending_in_extension(
            self, stem: str, ext: str, suffix: str, case_insensitive: bool) -> None:
        """``*.ext`` matches (with ``re.match``) exactly the names that end in ``.ext``."""
        pattern = files.ensure_regex_or_set('*.' + ext, caseInsensitive=case_insensitive)
        assert isinstance(pattern, re.Pattern)
        name = stem + '.' + ext + suffix
        if case_insensitive:
            expected = name.lower().endswith('.' + ext.lower())
        else:
            expected = name.endswith('.' + ext)
        self.assertEqual(pattern.match(name) is not None, expected, f'{pattern.pattern!r} vs {name!r}')

    @given(name=_NAME_CHARS, ext=_EXTENSIONS)
    def test_property_star_glob_rejects_wrong_separator(self, name: str, ext: str) -> None:
        """Any single character other than a dot before the extension is not accepted."""
        pattern = files.ensure_regex_or_set('*.' + ext)
        assert isinstance(pattern, re.Pattern)
        candidate = name.replace('.', '_') + 'X' + ext
        self.assertIsNone(pattern.match(candidate))


class PathIsSignificantlyNewerTests(unittest.TestCase):
    """``path_is_significantly_newer`` compares two files' mtimes with a skew deadband."""

    _BASE_NS = 1_760_000_000 * 1_000_000_000

    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.a = os.path.join(self._dir.name, 'a.txt')
        self.b = os.path.join(self._dir.name, 'b.txt')
        _touch(self.a)
        _touch(self.b)

    def _set_mtimes(self, a_ns: int, b_ns: int) -> None:
        """Stamp exact modification times (in ns) on the two files."""
        os.utime(self.a, ns=(a_ns, a_ns))
        os.utime(self.b, ns=(b_ns, b_ns))

    def test_missing_path_returns_none(self) -> None:
        missing = os.path.join(self._dir.name, 'missing.txt')
        self.assertIsNone(files.path_is_significantly_newer(missing, self.b))
        self.assertIsNone(files.path_is_significantly_newer(self.a, missing))
        self.assertIsNone(files.path_is_significantly_newer(missing, missing))

    def test_explicit_tolerance_boundary(self) -> None:
        tolerance_ns = 2_000_000_000
        # Windows NTFS stores mtimes in 100 ns units, so offsets are multiples of 100 ns.
        self._set_mtimes(self._BASE_NS + tolerance_ns, self._BASE_NS)
        self.assertFalse(files.path_is_significantly_newer(self.a, self.b, tolerance_ns=tolerance_ns),
                         'exactly at the tolerance is not significantly newer')

        self._set_mtimes(self._BASE_NS + tolerance_ns + 100, self._BASE_NS)
        self.assertTrue(files.path_is_significantly_newer(self.a, self.b, tolerance_ns=tolerance_ns))
        # Direction matters: b is not newer than a.
        self.assertFalse(files.path_is_significantly_newer(self.b, self.a, tolerance_ns=tolerance_ns))

    def test_zero_tolerance_strict_ordering(self) -> None:
        self._set_mtimes(self._BASE_NS, self._BASE_NS)
        self.assertFalse(files.path_is_significantly_newer(self.a, self.b, tolerance_ns=0))
        self._set_mtimes(self._BASE_NS + 100, self._BASE_NS)
        self.assertTrue(files.path_is_significantly_newer(self.a, self.b, tolerance_ns=0))

    def test_default_tolerance_from_environment(self) -> None:
        old = os.environ.get(files.MTIME_SKEW_TOLERANCE_ENV)
        os.environ[files.MTIME_SKEW_TOLERANCE_ENV] = '5'
        try:
            self._set_mtimes(self._BASE_NS + 4_000_000_000, self._BASE_NS)
            self.assertFalse(files.path_is_significantly_newer(self.a, self.b))
            self._set_mtimes(self._BASE_NS + 6_000_000_000, self._BASE_NS)
            self.assertTrue(files.path_is_significantly_newer(self.a, self.b))
        finally:
            if old is None:
                del os.environ[files.MTIME_SKEW_TOLERANCE_ENV]
            else:
                os.environ[files.MTIME_SKEW_TOLERANCE_ENV] = old

    def test_comparison_is_passed_to_stat(self) -> None:
        """CREATION compares ``st_ctime_ns``, which ``os.utime`` does not move."""
        self._set_mtimes(self._BASE_NS + 10_000_000_000, self._BASE_NS)
        self.assertTrue(files.path_is_significantly_newer(
            self.a, self.b, files.FileTimeComparison.MODIFIED, tolerance_ns=0))
        expected = files.is_significantly_newer(os.stat(self.a).st_ctime_ns, os.stat(self.b).st_ctime_ns,
                                                tolerance_ns=0)
        self.assertEqual(files.path_is_significantly_newer(
            self.a, self.b, files.FileTimeComparison.CREATION, tolerance_ns=0), expected)
        # Both files were created a moment apart, far less than the forced 10 s mtime gap.
        self.assertFalse(files.path_is_significantly_newer(
            self.a, self.b, files.FileTimeComparison.CREATION, tolerance_ns=5_000_000_000))

        # Same check with mtimes a year in the future, so mixing one file's mtime with the
        # other's ctime would also show up as "newer" (catches a dropped argument on path_a).
        future_ns = os.stat(self.b).st_ctime_ns + 365 * 86_400 * 1_000_000_000
        self._set_mtimes(future_ns + 10_000_000_000, future_ns)
        self.assertFalse(files.path_is_significantly_newer(
            self.a, self.b, files.FileTimeComparison.CREATION, tolerance_ns=5_000_000_000))

    def test_unknown_comparison_raises(self) -> None:
        with self.assertRaises(ValueError):
            files.path_is_significantly_newer(self.a, self.b, 99)  # type: ignore[arg-type]


if __name__ == '__main__':
    unittest.main()
