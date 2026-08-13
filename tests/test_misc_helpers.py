"""Tests for nornir_shared.misc helpers."""
import os
import sys
import unittest

from nornir_shared.misc import GenNameFromDict, ListFromDelimited, format_startup_command_line


class TestGenNameFromDict(unittest.TestCase):
    def test_scalar_and_none(self) -> None:
        self.assertEqual(GenNameFromDict({'abc': 1, 'def': None}), '_abc1_defNone')

    def test_list_joins_all_elements(self) -> None:
        # Regression: prior code used value[1:-1] and overwrote ValueStr each loop.
        self.assertEqual(GenNameFromDict({'a': [1, 2, 3, 4]}), '_a1x2x3x4')
        self.assertEqual(GenNameFromDict({'xyz': [10, 20]}), '_xyz10x20')

    def test_empty_list(self) -> None:
        self.assertEqual(GenNameFromDict({'k': []}), '_k')


class TestFormatStartupCommandLine(unittest.TestCase):
    def test_includes_executable_and_arguments(self) -> None:
        formatted = format_startup_command_line(['pyre', '-stos', r'Y:\Volumes\RC2\pair.stos'])
        self.assertIn(os.path.basename(sys.executable), formatted)
        self.assertIn('pyre', formatted)
        self.assertIn('pair.stos', formatted)

    def test_does_not_duplicate_interpreter_path(self) -> None:
        formatted = format_startup_command_line([sys.executable, '-m', 'pyre'])
        self.assertEqual(formatted.count(sys.executable), 1)
        self.assertIn('-m', formatted)
        self.assertIn('pyre', formatted)

    def test_quotes_arguments_with_spaces(self) -> None:
        formatted = format_startup_command_line(['prog', os.path.join('dir with space', 'file.png')])
        self.assertIn('dir with space', formatted)
        if os.name == 'nt':
            self.assertIn('"', formatted)
        else:
            self.assertTrue("'" in formatted or '\\ ' in formatted)


class TestListFromDelimited(unittest.TestCase):
    def test_ints_floats_strings(self) -> None:
        self.assertEqual(ListFromDelimited('1,2.5,foo'), [1, 2.5, 'foo'])

    def test_non_string(self) -> None:
        self.assertEqual(ListFromDelimited(3), [3])
        self.assertEqual(ListFromDelimited([1, 2]), [1, 2])


if __name__ == '__main__':
    unittest.main()
