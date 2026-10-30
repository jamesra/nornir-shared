"""`AreValidImages` must return the entries the caller passed, whatever shape they were in.

Review #230: the multi-file branch appended `os.path.basename` of the *joined* path while
the single-file branch returned `filenamelist[0]` unchanged, so the shape of the result
depended on how many files you passed:

    AreValidImages([valid, invalid]) -> ['FixedMoving_RBF.stos']            # basename
    AreValidImages([invalid])        -> ['D:\\...\\FixedMoving_RBF.stos']  # full path

A comment claimed the basename was "matching the single-file path", which it was not.

That went unnoticed because it is invisible in the common case: both production callers
pass `ImageDir` with bare filenames, and `basename(join(dir, name)) == name`. It bites in
two other cases, and both matter:

  - `ImageDir=None` with absolute paths, where the directory is stripped and the caller
    cannot resolve the result at all -- which is exactly what `tests/test_images.py`
    asserts, and why that test failed once #220 let it run;
  - entries carrying a subdirectory component, where that component is dropped. Both
    callers then do `os.path.join(ImageDir, entry)` on a truncated entry, and
    `MosaicFile.RemoveInvalidMosaicImages` additionally does
    `if InvalidImage in self.ImageToTransformString` against keys it supplied, so the
    lookup misses and the invalid image is silently kept rather than removed.

These tests are self-contained rather than reusing the shared test corpus, so the contract
is pinned independently of what happens to be on disk.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from PIL import Image

from nornir_shared import images


class _Fixture(unittest.TestCase):
    """A directory holding one real PNG, one file that is not an image, and a subdirectory."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='nornir_images_230_')
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

        self.valid_name = 'good.png'
        Image.new('L', (4, 4)).save(os.path.join(self.root, self.valid_name))

        self.invalid_name = 'bad.png'  # .png extension, but not image data
        with open(os.path.join(self.root, self.invalid_name), 'w', encoding='utf-8') as f:
            f.write('this is not a png')

        self.sub = 'nested'
        os.makedirs(os.path.join(self.root, self.sub))
        self.sub_invalid = os.path.join(self.sub, 'bad2.png')
        with open(os.path.join(self.root, self.sub_invalid), 'w', encoding='utf-8') as f:
            f.write('also not a png')

    @property
    def valid_abs(self) -> str:
        return os.path.join(self.root, self.valid_name)

    @property
    def invalid_abs(self) -> str:
        return os.path.join(self.root, self.invalid_name)


class TestThePremiseHolds(_Fixture):
    """Confirm the fixture really is one valid and two invalid images."""

    def test_the_png_is_valid(self):
        self.assertTrue(images.IsValidImage(self.valid_abs))

    def test_the_impostors_are_not(self):
        self.assertFalse(images.IsValidImage(self.invalid_abs))
        self.assertFalse(images.IsValidImage(os.path.join(self.root, self.sub_invalid)))


class TestOneEntryAndManyAgree(_Fixture):
    """The bug was a difference between the single-file and multi-file branches."""

    def test_absolute_paths_come_back_absolute_either_way(self):
        alone = images.AreValidImages([self.invalid_abs])
        together = images.AreValidImages([self.valid_abs, self.invalid_abs])
        self.assertEqual([self.invalid_abs], alone)
        self.assertEqual([self.invalid_abs], together,
                         'the two-file call used to return a bare basename here')
        self.assertEqual(alone, together)

    def test_bare_names_with_a_dir_come_back_bare_either_way(self):
        alone = images.AreValidImages([self.invalid_name], self.root)
        together = images.AreValidImages([self.valid_name, self.invalid_name], self.root)
        self.assertEqual([self.invalid_name], alone)
        self.assertEqual([self.invalid_name], together)

    def test_a_valid_image_is_never_reported(self):
        self.assertEqual([], images.AreValidImages([self.valid_abs]))
        self.assertEqual([], images.AreValidImages([self.valid_name], self.root))

    def test_two_invalid_entries_are_both_reported_as_given(self):
        got = images.AreValidImages([self.invalid_abs, self.valid_abs, self.invalid_abs])
        self.assertEqual([self.invalid_abs, self.invalid_abs], got)


class TestTheCallerCanStillUseTheResult(_Fixture):
    """Both production callers join the result against ImageDir, or look it up."""

    def test_the_result_joins_back_to_a_real_file(self):
        for entry in images.AreValidImages([self.valid_name, self.invalid_name], self.root):
            self.assertTrue(os.path.exists(os.path.join(self.root, entry)),
                            f'{entry!r} must still resolve under ImageDir, or tile.py '
                            'deletes nothing and mosaicfile.py removes nothing')

    def test_a_subdirectory_component_survives(self):
        # The MosaicFile hazard: a dropped 'nested/' makes the dict lookup miss silently.
        got = images.AreValidImages([self.valid_name, self.sub_invalid], self.root)
        self.assertEqual([self.sub_invalid], got,
                         'basename() used to reduce this to bad2.png')
        self.assertTrue(os.path.exists(os.path.join(self.root, got[0])))

    def test_the_entry_can_be_looked_up_by_what_was_passed(self):
        # Mirrors MosaicFile.RemoveInvalidMosaicImages' membership test.
        supplied = {self.valid_name: 'transform-a', self.sub_invalid: 'transform-b'}
        invalid = images.AreValidImages(list(supplied.keys()), self.root)
        self.assertEqual(1, len(invalid))
        self.assertIn(invalid[0], supplied,
                      'the returned entry must be a key the caller supplied')


class TestTheEdgesAreUnchanged(_Fixture):
    """Behaviour the fix must not have disturbed."""

    def test_an_empty_list_is_empty(self):
        self.assertEqual([], images.AreValidImages([]))

    def test_a_bare_string_is_accepted(self):
        self.assertEqual([self.invalid_abs], images.AreValidImages(self.invalid_abs))
        self.assertEqual([], images.AreValidImages(self.valid_abs))

    def test_numpy_entries_are_skipped_not_reported(self):
        # .npy is not checked at all, so it must never appear in the invalid list even
        # though no such file exists.
        got = images.AreValidImages(
            ['absent.npy', self.valid_name, self.invalid_name], self.root)
        self.assertEqual([self.invalid_name], got)
        self.assertEqual([], images.AreValidImages(['absent.npy'], self.root))

    def test_a_missing_file_is_invalid_and_named_as_given(self):
        self.assertEqual(['absent.png'],
                         images.AreValidImages(['absent.png', self.valid_name], self.root))

    def test_order_follows_the_input(self):
        second = 'bad_b.png'
        with open(os.path.join(self.root, second), 'w', encoding='utf-8') as f:
            f.write('nope')
        self.assertEqual([self.invalid_name, second],
                         images.AreValidImages(
                             [self.invalid_name, self.valid_name, second], self.root))
        self.assertEqual([second, self.invalid_name],
                         images.AreValidImages(
                             [second, self.valid_name, self.invalid_name], self.root))


if __name__ == '__main__':
    unittest.main()
