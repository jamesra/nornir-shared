"""Histogram statistics on degenerate input must not raise.

``_FindValueAtPercentile`` divided by the sample count of the bin the percentile
landed in, with no guard.  A blank tile -- every bin empty, which happens for
missing or edge tiles in a mosaic -- took ``AutoLevel`` and ``Median`` straight
into ZeroDivisionError, and an empty bin list raised IndexError.

The same divide also failed on *populated* histograms whenever the percentile
landed past the last sample, which ``Percentile=1.0`` always does when the
histogram has trailing empty bins.
"""
from __future__ import annotations

import unittest

from nornir_shared.histogram import Histogram, _FindValueAtPercentile


class TestBlankTile(unittest.TestCase):
    """Every bin empty: report the full range rather than raising."""

    def setUp(self):
        self.hist = Histogram.Init(minVal=0, maxVal=255, numBins=16,
                                   binVals=[0] * 16)

    def test_autolevel_does_not_raise(self):
        self.assertEqual(self.hist.AutoLevel(0.005, 0.005), (0, 255))

    def test_autolevel_with_zero_cutoffs(self):
        self.assertEqual(self.hist.AutoLevel(0.0, 0.0), (0, 255))

    def test_autolevel_full_range_is_the_safe_leveling(self):
        """No information means no contrast stretch, not a crash."""
        min_cutoff, max_cutoff = self.hist.AutoLevel(0.25, 0.25)
        self.assertEqual(min_cutoff, self.hist.MinValue)
        self.assertEqual(max_cutoff, self.hist.MaxValue)

    def test_median_does_not_raise(self):
        self.assertEqual(self.hist.Median(), self.hist.MinValue)

    def test_mean_reports_no_data(self):
        self.assertIsNone(self.hist.Mean())

    def test_peak_value_reports_no_data(self):
        """Every bin ties at zero, so there is no peak to report."""
        self.assertIsNone(self.hist.PeakValue())

    def test_nonzero_histogram_still_reports_a_peak(self):
        hist = Histogram.Init(minVal=0, maxVal=255, numBins=16,
                              binVals=[0] * 15 + [7])
        self.assertIsNotNone(hist.PeakValue())


class TestEmptyBinList(unittest.TestCase):

    def test_empty_bins_return_the_range_minimum(self):
        self.assertEqual(_FindValueAtPercentile([], 0.5, 1.0, 0), 0)

    def test_empty_bins_respect_the_offset(self):
        self.assertEqual(_FindValueAtPercentile([], 0.5, 1.0, 64), 64)

    def test_single_empty_bin(self):
        self.assertEqual(_FindValueAtPercentile([0], 0.5, 1.0, 7), 7)


class TestPercentilePastTheLastSample(unittest.TestCase):
    """A populated histogram with trailing empty bins also hit the divide."""

    def setUp(self):
        # Samples occupy bins 0-7 (values 0..127); bins 8-15 are empty.
        self.bins = [10] * 8 + [0] * 8
        self.hist = Histogram.Init(minVal=0, maxVal=255, numBins=16,
                                   binVals=list(self.bins))
        self.assertEqual(self.hist.BinWidth, 16.0)

    def test_percentile_one_returns_top_of_last_populated_bin(self):
        value = _FindValueAtPercentile(self.hist.Bins, 1.0, 16.0, 0)
        self.assertEqual(value, 128.0)

    def test_percentile_one_does_not_exceed_the_data(self):
        """128 is the upper edge of bin 7; nothing above it holds samples."""
        value = _FindValueAtPercentile(self.hist.Bins, 1.0, 16.0, 0)
        self.assertLessEqual(value, 128.0)

    def test_autolevel_with_full_min_cutoff(self):
        min_cutoff, _ = self.hist.AutoLevel(1.0, None)
        self.assertEqual(min_cutoff, 128.0)

    def test_autolevel_with_full_max_cutoff_stays_in_range(self):
        """Trimming every sample from the top must not report a negative value."""
        _, max_cutoff = self.hist.AutoLevel(None, 1.0)
        self.assertGreaterEqual(max_cutoff, self.hist.MinValue)
        self.assertLessEqual(max_cutoff, self.hist.MaxValue)

    def test_leading_empty_bins(self):
        hist = Histogram.Init(minVal=0, maxVal=255, numBins=16,
                              binVals=[0] * 8 + [10] * 8)
        self.assertEqual(hist.AutoLevel(0.0, 0.0), (128.0, 255.0))


class TestPopulatedHistogramIsUnchanged(unittest.TestCase):
    """The guards must not perturb the normal interpolation path."""

    def setUp(self):
        self.hist = Histogram.Init(minVal=0, maxVal=255, numBins=16,
                                   binVals=[10] * 16)

    def test_autolevel(self):
        self.assertEqual(self.hist.AutoLevel(0.0, 0.0), (0.0, 255.0))

    def test_median(self):
        self.assertEqual(self.hist.Median(), 128.0)

    def test_peak_value(self):
        self.assertEqual(self.hist.PeakValue(), 127.5)

    def test_interpolation_within_a_bin(self):
        """Half of bin 0's samples sit below its midpoint."""
        hist = Histogram.Init(minVal=0, maxVal=15, numBins=16,
                              binVals=[10] + [0] * 15)
        self.assertEqual(hist.BinWidth, 1.0)
        self.assertEqual(_FindValueAtPercentile(hist.Bins, 0.5, 1.0, 0), 0.5)

    def test_cutoffs_stay_within_the_histogram_range(self):
        for min_cut, max_cut in ((0.0, 0.0), (0.1, 0.1), (0.25, 0.25), (0.5, 0.0)):
            with self.subTest(cutoffs=(min_cut, max_cut)):
                lo, hi = self.hist.AutoLevel(min_cut, max_cut)
                self.assertGreaterEqual(lo, self.hist.MinValue)
                self.assertLessEqual(hi, self.hist.MaxValue)


if __name__ == '__main__':
    unittest.main()
