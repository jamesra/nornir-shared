"""Histogram statistics must include the top bin.

``_MinMaxBinIndicies`` returned ``NumBins - 1`` as a default and
``MapIntensityToBin(maxVal)`` when given a maximum, while every caller treats
the value as an exclusive bound.  The top bin -- and the bin holding an explicit
``maxVal`` -- were therefore dropped from ``Median``, ``Mean`` and
``PeakValue``, which feed auto-level and gamma.

With saturated data the effect is severe rather than cosmetic, which is what
these tests pin down.
"""
from __future__ import annotations

import pickle
import unittest

from nornir_shared.histogram import Histogram


class TestTopBinIsIncluded(unittest.TestCase):
    """A populated top bin must not be invisible to the statistics."""

    def setUp(self):
        # 100k saturated samples in the top bin against 150 spread below it.
        # Any statistic that ignores the top bin reports a value near 120
        # instead of near 248.
        self.bins = [10] * 15 + [100000]
        self.hist = Histogram.Init(minVal=0, maxVal=255, numBins=16,
                                   binVals=list(self.bins))
        self.assertEqual(self.hist.BinWidth, 16.0)

        # Bin 15 holds the integers 240..255, mean 247.5.
        self.top_bin_value = 247.5

    def test_mean_reflects_the_saturated_top_bin(self):
        total = sum(self.bins)
        expected = sum(count * (i * 16 + 7.5)
                       for i, count in enumerate(self.bins)) / total
        mean = self.hist.Mean()
        self.assertIsNotNone(mean)
        assert mean is not None
        self.assertAlmostEqual(mean, expected, places=6)
        self.assertGreater(mean, 240.0)

    def test_peak_value_finds_the_top_bin(self):
        """The overwhelming peak is in the top bin; it must be reported."""
        self.assertEqual(self.hist.PeakValue(), self.top_bin_value)

    def test_median_reflects_the_saturated_top_bin(self):
        self.assertGreater(self.hist.Median(), 240.0)

    def test_every_statistic_counts_all_samples(self):
        """A uniform histogram's mean must sit at the centre of the full range."""
        hist = Histogram.Init(minVal=0, maxVal=255, numBins=16, binVals=[10] * 16)
        # Bins cover integers 0..255 uniformly.
        self.assertEqual(hist.Mean(), 127.5)


class TestExplicitMaxValIsInclusive(unittest.TestCase):
    """The bin containing maxVal belongs inside the requested range."""

    def setUp(self):
        self.hist = Histogram.Init(minVal=0, maxVal=255, numBins=16,
                                   binVals=[10] * 16)

    def test_full_range_matches_no_range(self):
        self.assertEqual(self.hist.Mean(0, 255), self.hist.Mean())
        self.assertEqual(self.hist.PeakValue(0, 255), self.hist.PeakValue())

    def test_max_bin_index_is_exclusive_upper_bound(self):
        _, iMax, _ = self.hist._MinMaxBinIndicies(None, None)
        self.assertEqual(iMax, self.hist.NumBins)

    def test_bin_holding_maxval_is_included(self):
        _, iMax, _ = self.hist._MinMaxBinIndicies(0, 255)
        self.assertEqual(iMax, self.hist.NumBins)

    def test_narrow_range_includes_both_end_bins(self):
        """A range covering exactly two bins must average both, not just one."""
        hist = Histogram.Init(minVal=0, maxVal=15, numBins=16,
                              binVals=[10] * 16)
        self.assertEqual(hist.BinWidth, 1.0)
        # Bins 4 and 5 hold the values 4 and 5.
        self.assertEqual(hist.Mean(4, 5), 4.5)

    def test_single_bin_range_is_not_empty(self):
        """minVal and maxVal inside one bin must still measure that bin."""
        hist = Histogram.Init(minVal=0, maxVal=15, numBins=16,
                              binVals=[10] * 16)
        self.assertEqual(hist.Mean(7, 7), 7.0)


class TestIntegerAwareBinRepresentative(unittest.TestCase):
    """Bins of integers are represented by the mean of those integers."""

    def test_integer_representative_for_unit_bins(self):
        """A width-1 bin can only hold one integer, so that is its value."""
        hist = Histogram.Init(minVal=64, maxVal=191, numBins=128,
                              binVals=[10] * 128)
        self.assertEqual(hist.BinWidth, 1.0)
        self.assertEqual(hist.BinRepresentativeValue(0), 64.0)
        self.assertEqual(hist.Mean(), 127.5)

    def test_integer_representative_for_wide_bins(self):
        hist = Histogram.Init(minVal=0, maxVal=255, numBins=16,
                              binVals=[10] * 16)
        # Bin 0 holds integers 0..15, mean 7.5.
        self.assertEqual(hist.BinRepresentativeValue(0), 7.5)

    def test_float_data_uses_the_continuous_midpoint(self):
        hist = Histogram.Init(minVal=0, maxVal=255, numBins=16,
                              binVals=[10] * 16, integerValues=False)
        self.assertEqual(hist.BinRepresentativeValue(0), 8.0)
        self.assertEqual(hist.Mean(), 128.0)

    def test_integer_default(self):
        """Nornir intensities are integers, so that is the default."""
        self.assertTrue(Histogram.Init(minVal=0, maxVal=255, numBins=16).IntegerValues)

    def test_sub_unit_bins_fall_back_to_the_midpoint(self):
        """A bin narrower than 1 cannot hold a range of integers."""
        hist = Histogram.Init(minVal=0.0, maxVal=1.0, numBins=10,
                              binVals=[10] * 10)
        self.assertLess(hist.BinWidth, 1.0)
        self.assertAlmostEqual(hist.BinRepresentativeValue(0),
                               hist.BinValue(0, fraction=0.5), places=9)


class TestIntegerValuesRoundTrips(unittest.TestCase):
    """The flag has to survive the ways histograms are persisted."""

    def test_xml_round_trip(self):
        for integer_values in (True, False):
            with self.subTest(integerValues=integer_values):
                hist = Histogram.Init(minVal=0, maxVal=255, numBins=16,
                                      binVals=[10] * 16,
                                      integerValues=integer_values)
                restored = Histogram.FromXML(hist.ToXML())
                self.assertIsNotNone(restored)
                assert restored is not None
                self.assertEqual(restored.IntegerValues, integer_values)
                self.assertEqual(restored.Mean(), hist.Mean())

    def test_pickle_round_trip(self):
        hist = Histogram.Init(minVal=0, maxVal=255, numBins=16,
                              binVals=[10] * 16, integerValues=False)
        restored = pickle.loads(pickle.dumps(hist))
        self.assertFalse(restored.IntegerValues)
        self.assertEqual(restored.Mean(), hist.Mean())

    def test_histogram_predating_the_flag_is_treated_as_integer(self):
        """Older XML has no IntegerValues attribute; intensities were integers."""
        hist = Histogram.Init(minVal=0, maxVal=255, numBins=16,
                              binVals=[10] * 16)
        xml_str = hist.ToXML().replace(' IntegerValues="True"', '')
        self.assertNotIn('IntegerValues', xml_str)

        restored = Histogram.FromXML(xml_str)
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertTrue(restored.IntegerValues)

    def test_pickle_predating_the_flag_is_treated_as_integer(self):
        state = {'MinValue': 0, 'MaxValue': 255, 'NumBins': 16,
                 'NumSamples': 160, 'Bins': [10] * 16}
        hist = Histogram()
        hist.__setstate__(state)
        self.assertTrue(hist.IntegerValues)


if __name__ == '__main__':
    unittest.main()
