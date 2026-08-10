"""Tests for nornir_shared.misc helpers."""
import unittest

from nornir_shared.misc import GenNameFromDict, ListFromDelimited


class TestGenNameFromDict(unittest.TestCase):
    def test_scalar_and_none(self) -> None:
        self.assertEqual(GenNameFromDict({'abc': 1, 'def': None}), '_abc1_defNone')

    def test_list_joins_all_elements(self) -> None:
        # Regression: prior code used value[1:-1] and overwrote ValueStr each loop.
        self.assertEqual(GenNameFromDict({'a': [1, 2, 3, 4]}), '_a1x2x3x4')
        self.assertEqual(GenNameFromDict({'xyz': [10, 20]}), '_xyz10x20')

    def test_empty_list(self) -> None:
        self.assertEqual(GenNameFromDict({'k': []}), '_k')


class TestListFromDelimited(unittest.TestCase):
    def test_ints_floats_strings(self) -> None:
        self.assertEqual(ListFromDelimited('1,2.5,foo'), [1, 2.5, 'foo'])

    def test_non_string(self) -> None:
        self.assertEqual(ListFromDelimited(3), [3])
        self.assertEqual(ListFromDelimited([1, 2]), [1, 2])


if __name__ == '__main__':
    unittest.main()
