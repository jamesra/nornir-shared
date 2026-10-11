"""Characterization tests for small ``nornir_shared.files`` helpers that had no coverage.

Covers ``seconds_to_ns`` (float epoch seconds to integer nanoseconds, used by the mtime skew
tolerance helpers).
"""
from __future__ import annotations

import os
import tempfile
import unittest
from fractions import Fraction

from hypothesis import example, given
from hypothesis import strategies as st

from nornir_shared import files


def _touch(path: str) -> None:
    """Create an empty file at *path*."""
    with open(path, 'w'):
        pass


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
