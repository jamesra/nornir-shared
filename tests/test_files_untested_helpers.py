"""Characterization tests for small ``nornir_shared.files`` helpers that had no coverage.

Covers ``try_locate_file`` (existing path, basename fallback for absolute paths,
whole relative path joined to alternate directories, not found), ``RemoveFilenameSpaces``
(spaces become underscores only for files with the requested extension), and
``seconds_to_ns`` (float epoch seconds to integer nanoseconds, used by the mtime skew
tolerance helpers).
"""
from __future__ import annotations

import os
import tempfile
import unittest
from fractions import Fraction

from hypothesis import example, given, settings
from hypothesis import strategies as st

from nornir_shared import files

# Lowercase letters and digits only: no '_' (so space replacement is injective), no glob
# metacharacters, and no case-only collisions on case-insensitive file systems.
_TOKEN = st.text(alphabet='abcdefghijklmnopqrstuvwxyz0123456789', min_size=1, max_size=6)
_SEPARATOR = st.sampled_from([' ', '  '])


@st.composite
def _stem_with_spaces(draw: st.DrawFn) -> str:
    """Build a file stem of tokens joined by one or two spaces, never leading or trailing."""
    tokens = draw(st.lists(_TOKEN, min_size=1, max_size=4))
    out = tokens[0]
    for token in tokens[1:]:
        out += draw(_SEPARATOR) + token
    return out


def _touch(path: str) -> None:
    """Create an empty file at *path*."""
    with open(path, 'w'):
        pass


class TryLocateFileTests(unittest.TestCase):
    """``try_locate_file`` returns the first existing candidate path, or None."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.alt_a = os.path.join(self.root, 'alt_a')
        self.alt_b = os.path.join(self.root, 'alt_b')
        os.makedirs(self.alt_a)
        os.makedirs(self.alt_b)

    def test_existing_path_is_returned_unchanged(self) -> None:
        existing = os.path.join(self.root, 'image.png')
        _touch(existing)
        _touch(os.path.join(self.alt_a, 'image.png'))
        self.assertEqual(files.try_locate_file(existing, [self.alt_a]), existing)

    def test_missing_absolute_path_falls_back_to_basename_in_alt_dirs(self) -> None:
        missing = os.path.join(self.root, 'gone', 'deeper', 'image.png')
        found = os.path.join(self.alt_b, 'image.png')
        _touch(found)
        self.assertEqual(files.try_locate_file(missing, [self.alt_a, self.alt_b]), found)

    def test_alt_dirs_searched_in_order(self) -> None:
        missing = os.path.join(self.root, 'gone', 'image.png')
        first = os.path.join(self.alt_a, 'image.png')
        _touch(first)
        _touch(os.path.join(self.alt_b, 'image.png'))
        self.assertEqual(files.try_locate_file(missing, [self.alt_a, self.alt_b]), first)

    def test_relative_path_is_joined_whole_not_by_basename(self) -> None:
        relative = os.path.join('sub', 'image.png')
        # Only the basename exists directly under alt_a; the relative path must not match it.
        _touch(os.path.join(self.alt_a, 'image.png'))
        self.assertIsNone(files.try_locate_file(relative, [self.alt_a]))

        os.makedirs(os.path.join(self.alt_b, 'sub'))
        whole = os.path.join(self.alt_b, 'sub', 'image.png')
        _touch(whole)
        self.assertEqual(files.try_locate_file(relative, [self.alt_a, self.alt_b]), whole)

    def test_not_found_returns_none(self) -> None:
        missing = os.path.join(self.root, 'gone', 'image.png')
        self.assertIsNone(files.try_locate_file(missing, [self.alt_a, self.alt_b]))
        self.assertIsNone(files.try_locate_file(missing, []))


class RemoveFilenameSpacesTests(unittest.TestCase):
    """``RemoveFilenameSpaces`` renames matching files, replacing each space with '_'."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name

    def test_ext_with_and_without_leading_dot(self) -> None:
        for ext in ('.mrc', 'mrc'):
            with self.subTest(ext=ext), tempfile.TemporaryDirectory() as d:
                _touch(os.path.join(d, '0001 my section.mrc'))
                files.RemoveFilenameSpaces(d, ext)
                self.assertEqual(sorted(os.listdir(d)), ['0001_my_section.mrc'])

    def test_only_matching_extension_is_renamed(self) -> None:
        _touch(os.path.join(self.root, 'a b.mrc'))
        _touch(os.path.join(self.root, 'c d.txt'))
        files.RemoveFilenameSpaces(self.root, '.mrc')
        self.assertEqual(sorted(os.listdir(self.root)), ['a_b.mrc', 'c d.txt'])

    def test_names_without_spaces_are_left_alone(self) -> None:
        _touch(os.path.join(self.root, 'plain.mrc'))
        files.RemoveFilenameSpaces(self.root, '.mrc')
        self.assertEqual(os.listdir(self.root), ['plain.mrc'])

    def test_missing_path_is_a_no_op(self) -> None:
        missing = os.path.join(self.root, 'does not exist')
        files.RemoveFilenameSpaces(missing, '.mrc')
        self.assertFalse(os.path.exists(missing))

    @settings(max_examples=40, deadline=None)
    @given(stems=st.lists(_stem_with_spaces(), min_size=1, max_size=5, unique=True))
    @example(stems=['0001 a', '0002  b c'])
    def test_property_every_space_becomes_underscore(self, stems: list[str]) -> None:
        """Each matching file is renamed exactly to its stem with spaces replaced, and no file is lost."""
        with tempfile.TemporaryDirectory() as d:
            for stem in stems:
                _touch(os.path.join(d, stem + '.png'))
            files.RemoveFilenameSpaces(d, 'png')
            expected = sorted(stem.replace(' ', '_') + '.png' for stem in stems)
            self.assertEqual(sorted(os.listdir(d)), expected)


class SecondsToNsTests(unittest.TestCase):
    """``seconds_to_ns`` rounds float seconds to the nearest integer nanosecond."""

    def test_examples(self) -> None:
        self.assertEqual(files.seconds_to_ns(0.0), 0)
        self.assertEqual(files.seconds_to_ns(1.5), 1_500_000_000)
        self.assertEqual(files.seconds_to_ns(-1.5), -1_500_000_000)
        # Rounds to nearest rather than truncating toward zero.
        self.assertEqual(files.seconds_to_ns(9.999e-10), 1)
        self.assertIsInstance(files.seconds_to_ns(1.25), int)

    def test_matches_stat_mtime_ns_for_a_real_file(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'f.txt')
            _touch(path)
            st_ns = os.stat(path).st_mtime_ns
            # A float epoch timestamp near 2026 resolves about 240 ns; allow 1 microsecond.
            self.assertLessEqual(abs(files.seconds_to_ns(os.path.getmtime(path)) - st_ns), 1_000)

    @given(seconds=st.floats(min_value=-4e9, max_value=4e9, allow_nan=False, allow_infinity=False))
    @example(seconds=1_760_000_000.123456)
    def test_property_nearest_nanosecond(self, seconds: float) -> None:
        """The result is within half a nanosecond of the exact product, plus one float rounding."""
        exact = Fraction(seconds) * 1_000_000_000
        float_error = abs(exact) * Fraction(2) ** -52
        self.assertLessEqual(abs(files.seconds_to_ns(seconds) - exact), Fraction(1, 2) + float_error)

    @given(a=st.floats(min_value=0, max_value=4e9), b=st.floats(min_value=0, max_value=4e9))
    def test_property_monotonic(self, a: float, b: float) -> None:
        """Later timestamps never convert to fewer nanoseconds."""
        lo, hi = sorted((a, b))
        self.assertLessEqual(files.seconds_to_ns(lo), files.seconds_to_ns(hi))


if __name__ == '__main__':
    unittest.main()
