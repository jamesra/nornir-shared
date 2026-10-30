'''
Created on Oct 21, 2013

@author: u0490822
'''
import datetime
import os
import shutil
import tempfile
import unittest
import unittest.mock

import nornir_shared.files
from nornir_shared.files import RecurseSubdirectories, IsOlderThan, file_mtime_ns, format_mtime_ns, path_list_to_mtime_ns_map, ensure_directory


def CreateDirTree(path, dictSubTrees):
    print(str(dictSubTrees))
    for key in dictSubTrees.keys():
        subtreepath = os.path.join(path, key)

        if '.' in key:  # Check if it is a file
            with open(key, 'w+') as f:
                f.write("test file")

        else:
            os.makedirs(subtreepath)
            CreateDirTree(subtreepath, dictSubTrees[key])


def RecurseDictValues(dictSubTrees, path: str) -> list[str]:
    vals = list(dictSubTrees.keys())

    for (key, value) in dictSubTrees.items():
        if value is None:  # Skip file entries
            continue
        subpath = os.path.join(path, key)
#        vals.append(subpath)
        vals.extend(RecurseDictValues(dictSubTrees[key], subpath))

    vals.append(path)

    return vals


class TestFiles(unittest.TestCase):
    DirTree = {'aaa': {},
               'bbb': {'baaa': {}, '1.idoc': None, '1.png': None, '2.png': None},
               'ccc': {'ca': {}, 'cb': {'cba': {}}, 'cc': {'cca': {}, 'ccb': {}, '2.idoc': None}},
               'ddd': {'cc': {}}}

    @property
    def classname(self):
        return str(self.__class__.__name__)

    @property
    def TestOutputPath(self):
        if 'TESTOUTPUTPATH' in os.environ:
            TestOutputDir = os.environ["TESTOUTPUTPATH"]
            TestOutputDir = os.path.join(TestOutputDir, self.classname)
            if not os.path.exists(TestOutputDir):
                os.makedirs(TestOutputDir)
            return TestOutputDir
        else:
            self.fail("TESTOUTPUTPATH environment variable should specify test output directory")

        return None

    def setUp(self):
        shutil.rmtree(self.TestOutputPath)
        CreateDirTree(path=self.TestOutputPath, dictSubTrees=TestFiles.DirTree)

    def tearDown(self):
        outdir = self.TestOutputPath
        shutil.rmtree(outdir)

    def IsSubset(self, ListA: list[nornir_shared.files.FindFileResult], ListB: list[str]):
        '''Verify ListA is a subset of ListB'''
        for l in ListA:
            self.assertTrue(l.path in ListB, str(l) + " is missing from target set")

    def IsSingleResult(self, ListA, result):
        self.assertEqual(len(ListA), 1, "Result list should have one entry")
        self.assertEqual(ListA[0].path, result,
                         "Expected result not found, expected " + str(result) + " got " + str(ListA[0]))

    def test_recursesubdirectories(self):
        dirs = RecurseSubdirectories(self.TestOutputPath, RequiredFiles=[], ExcludedFiles=[], MatchNames=None,
                                     ExcludeNames=[], ExcludedDownsampleLevels=[])
        expectedDirs = RecurseDictValues(TestFiles.DirTree, self.TestOutputPath)
        self.IsSubset(dirs, expectedDirs)

        # One known match in root dir
        dirs = RecurseSubdirectories(self.TestOutputPath, RequiredFiles=[], ExcludedFiles=[], MatchNames=['aaa'],
                                     ExcludeNames=[], ExcludedDownsampleLevels=[])
        self.IsSingleResult(dirs, os.path.join(self.TestOutputPath, 'aaa'))

        dirs = RecurseSubdirectories(self.TestOutputPath, RequiredFiles=[], ExcludedFiles=[], MatchNames=['baaa'],
                                     ExcludeNames=[], ExcludedDownsampleLevels=[])
        self.IsSingleResult(dirs, os.path.join(self.TestOutputPath, os.path.join('bbb','baaa')))

        dirs = RecurseSubdirectories(self.TestOutputPath, RequiredFiles=[], ExcludedFiles=[], MatchNames=['cca'],
                                     ExcludeNames=[], ExcludedDownsampleLevels=[])
        self.IsSingleResult(dirs, os.path.join(self.TestOutputPath, os.path.join('ccc','cc', 'cca')))

        dirs = RecurseSubdirectories(self.TestOutputPath, RequiredFiles=[], ExcludedFiles=[], MatchNames=[],
                                     ExcludeNames='ccc', ExcludedDownsampleLevels=[])
        expectedVals = [os.path.join(self.TestOutputPath, x) for x in ['aaa', 'bbb', os.path.join('bbb','baaa'), 'ddd', os.path.join('ddd', 'cc')]]
        expectedVals.append(self.TestOutputPath)
        self.IsSubset(dirs, expectedVals)

        dirs = RecurseSubdirectories(self.TestOutputPath, RequiredFiles='*.idoc', ExcludedFiles=[], MatchNames=[],
                                     ExcludeNames='ccc', ExcludedDownsampleLevels=[])
        expectedVals = [os.path.join(self.TestOutputPath, x) for x in ['bbb', 'cc']]
        expectedVals.append(self.TestOutputPath)
        self.IsSubset(dirs, expectedVals)

        dirs = RecurseSubdirectories(self.TestOutputPath, RequiredFiles=None, ExcludedFiles='*.idoc', MatchNames=[],
                                     ExcludeNames='ccc', ExcludedDownsampleLevels=[])
        expectedDirs = set(RecurseDictValues(TestFiles.DirTree, self.TestOutputPath))
        remove_dirs = os.path.join(self.TestOutputPath, 'ccc')
        expectedVals = list(filter(lambda x: remove_dirs not in x, expectedDirs))
        #expectedVals = expectedDirs - set([os.path.join(self.TestOutputPath, x) for x in ['ccc']])
        expectedVals.append(self.TestOutputPath)
        self.IsSubset(dirs, expectedVals)

    def test_IsOlderThan(self):
        testPath = os.path.join(self.TestOutputPath, "IsOlderThanTest.tmp")
        newer_date = datetime.date.today() + datetime.timedelta(days=1)

        try:
            with open(testPath, 'w') as file_handle:
                file_handle.close()

            file_ns = file_mtime_ns(testPath)
            reference_before_file = (file_ns - 1_000_000) / 1_000_000_000.0
            reference_after_file = (file_ns + 1_000_000) / 1_000_000_000.0
            reference_before_file_dt = datetime.datetime.fromtimestamp(reference_before_file)
            reference_after_file_dt = datetime.datetime.fromtimestamp(reference_after_file)

            self.assertFalse(IsOlderThan(testPath, DateTime=reference_before_file))
            self.assertFalse(IsOlderThan(testPath, DateTime=reference_before_file_dt))
            self.assertTrue(IsOlderThan(testPath, DateTime=reference_after_file))
            self.assertTrue(IsOlderThan(testPath, DateTime=reference_after_file_dt))
            self.assertTrue(IsOlderThan(testPath, DateTime=newer_date))

            self.assertFalse(IsOlderThan(testPath, DateTime=0))
            self.assertTrue(IsOlderThan(testPath, DateTime=reference_after_file))

            self.assertFalse(IsOlderThan(testPath, DateTime=int(reference_before_file)))
            self.assertTrue(IsOlderThan(testPath, DateTime=int(reference_after_file + 60)))

            date_time_format = '%Y-%m-%d %H:%M:%S.%f'
            self.assertFalse(
                IsOlderThan(testPath, DateTime=reference_before_file_dt.strftime(date_time_format),
                            DateTimeFormat=date_time_format))
            self.assertTrue(
                IsOlderThan(testPath, DateTime=reference_after_file_dt.strftime(date_time_format),
                            DateTimeFormat=date_time_format))

        finally:
            if os.path.exists(testPath):
                os.remove(testPath)

    def test_file_mtime_ns_helpers(self):
        test_path = os.path.join(self.TestOutputPath, "mtime_ns_helpers.tmp")
        with open(test_path, 'w') as file_handle:
            file_handle.write("mtime test")

        mtime_ns = file_mtime_ns(test_path)
        self.assertEqual(mtime_ns, os.stat(test_path).st_mtime_ns)

        mtime_map = path_list_to_mtime_ns_map([test_path])
        self.assertEqual(mtime_map, {test_path: mtime_ns})

        formatted = format_mtime_ns(mtime_ns)
        self.assertIn(str(mtime_ns), formatted)

        os.remove(test_path)

    def test_IsOlderThan_subsecond_reference(self):
        """Reference timestamps with sub-second precision must not truncate to whole seconds."""
        test_path = os.path.join(self.TestOutputPath, "IsOlderThanSubsecond.tmp")
        try:
            with open(test_path, 'w') as file_handle:
                file_handle.close()

            file_ns = file_mtime_ns(test_path)
            reference_after_file = (file_ns + 1_000) / 1_000_000_000.0
            reference_before_file = (file_ns - 1_000) / 1_000_000_000.0

            self.assertTrue(IsOlderThan(test_path, DateTime=reference_after_file))
            self.assertFalse(IsOlderThan(test_path, DateTime=reference_before_file))
        finally:
            os.remove(test_path)


class TestEnsureDirectory(unittest.TestCase):
    """CIFS-tolerant directory creation helper."""

    def test_ensure_directory_creates_nested_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = os.path.join(temp_dir, "a", "b", "c")
            self.assertEqual(ensure_directory(target), os.path.abspath(target))
            self.assertTrue(os.path.isdir(target))

    def test_ensure_directory_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertEqual(ensure_directory(temp_dir), os.path.abspath(temp_dir))

    def test_ensure_directory_retries_file_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = os.path.join(temp_dir, "child")
            original_mkdir = os.mkdir
            calls = {"count": 0}

            def mkdir_side_effect(path: str, *args, **kwargs):
                calls["count"] += 1
                if calls["count"] == 1 and path == target:
                    raise FileNotFoundError(path)
                return original_mkdir(path, *args, **kwargs)

            with unittest.mock.patch("os.mkdir", side_effect=mkdir_side_effect):
                self.assertEqual(ensure_directory(target), os.path.abspath(target))
            self.assertTrue(os.path.isdir(target))
            self.assertGreater(calls["count"], 1)

    def test_ensure_directory_waits_until_directory_is_writable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = os.path.join(temp_dir, "child")
            original_writable = nornir_shared.files._directory_writable
            calls = {"count": 0}

            def writable_side_effect(path: str) -> bool:
                calls["count"] += 1
                if path == os.path.abspath(target) and calls["count"] < 3:
                    return False
                return original_writable(path)

            with unittest.mock.patch(
                "nornir_shared.files._directory_writable",
                side_effect=writable_side_effect,
            ):
                self.assertEqual(ensure_directory(target, retries=6), os.path.abspath(target))
            self.assertTrue(os.path.isdir(target))
            self.assertGreaterEqual(calls["count"], 3)

    def test_copy_file_retries_when_dest_open_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src = os.path.join(temp_dir, "src.png")
            dest_dir = os.path.join(temp_dir, "dest")
            os.makedirs(dest_dir, exist_ok=True)
            with open(src, "wb") as handle:
                handle.write(b"png")
            dst = os.path.join(dest_dir, "tile.png")

            original_atomic = nornir_shared.files._copy_file_atomic
            calls = {"count": 0}

            def atomic_side_effect(src_path: str, dst_path: str, parent: str) -> None:
                calls["count"] += 1
                if calls["count"] == 1:
                    raise FileNotFoundError(dst_path)
                return original_atomic(src_path, dst_path, parent)

            with unittest.mock.patch.object(
                nornir_shared.files,
                "_copy_file_atomic",
                side_effect=atomic_side_effect,
            ):
                nornir_shared.files.copy_file(src, dst, retries=4, base_delay_s=0.0)

            self.assertTrue(os.path.isfile(dst))
            self.assertGreater(calls["count"], 1)

    def test_copy_file_creates_missing_dest_parent_on_enoent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src = os.path.join(temp_dir, "src.png")
            with open(src, "wb") as handle:
                handle.write(b"png")
            dest_dir = os.path.join(temp_dir, "missing_dest")
            dst = os.path.join(dest_dir, "tile.png")

            nornir_shared.files.copy_file(src, dst, retries=4, base_delay_s=0.0)

            self.assertTrue(os.path.isdir(dest_dir))
            self.assertTrue(os.path.isfile(dst))


class TestMtimeSkewTolerance(unittest.TestCase):
    """Freshness gates absorb SMB client/server mtime skew; ordering helpers stay strict."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.reference = os.path.join(self._temp.name, "reference.tmp")
        self.test = os.path.join(self._temp.name, "test.tmp")
        for path in (self.reference, self.test):
            with open(path, 'w') as f:
                f.write("x")
        self._base_ns = file_mtime_ns(self.test)
        self.addCleanup(os.environ.pop, nornir_shared.files.MTIME_SKEW_TOLERANCE_ENV, None)
        os.environ.pop(nornir_shared.files.MTIME_SKEW_TOLERANCE_ENV, None)

    def _set_reference_offset(self, offset_ns: int) -> None:
        """Set test mtime to the base and reference mtime to base + offset."""
        os.utime(self.test, ns=(self._base_ns, self._base_ns))
        ref_ns = self._base_ns + offset_ns
        os.utime(self.reference, ns=(ref_ns, ref_ns))

    def test_default_tolerance_is_two_seconds(self) -> None:
        self.assertEqual(nornir_shared.files.mtime_skew_tolerance_ns(), 2_000_000_000)

    def test_within_tolerance_is_not_outdated(self) -> None:
        self._set_reference_offset(1_000_000_000)
        self.assertFalse(nornir_shared.files.IsOutdated(self.reference, self.test))
        self.assertFalse(nornir_shared.files.OutdatedFile(self.reference, self.test))

    def test_exactly_at_tolerance_is_not_outdated(self) -> None:
        self._set_reference_offset(2_000_000_000)
        self.assertFalse(nornir_shared.files.IsOutdated(self.reference, self.test))

    def test_beyond_tolerance_is_outdated(self) -> None:
        self._set_reference_offset(2_000_001_000)
        self.assertTrue(nornir_shared.files.IsOutdated(self.reference, self.test))
        self.assertTrue(nornir_shared.files.OutdatedFile(self.reference, self.test))

    def test_older_reference_is_not_outdated(self) -> None:
        self._set_reference_offset(-10_000_000_000)
        self.assertFalse(nornir_shared.files.IsOutdated(self.reference, self.test))

    def test_missing_file_semantics_unchanged(self) -> None:
        missing = os.path.join(self._temp.name, "missing.tmp")
        self.assertTrue(nornir_shared.files.IsOutdated(self.reference, missing))
        self.assertTrue(nornir_shared.files.IsOutdated(missing, self.test))
        self.assertIsNone(nornir_shared.files.OutdatedFile(self.reference, missing))

    def test_env_override_changes_tolerance(self) -> None:
        self._set_reference_offset(1_000_000_000)
        os.environ[nornir_shared.files.MTIME_SKEW_TOLERANCE_ENV] = '0.5'
        self.assertEqual(nornir_shared.files.mtime_skew_tolerance_ns(), 500_000_000)
        self.assertTrue(nornir_shared.files.IsOutdated(self.reference, self.test))

    def test_env_override_zero_restores_strict_compare(self) -> None:
        self._set_reference_offset(1_000)
        os.environ[nornir_shared.files.MTIME_SKEW_TOLERANCE_ENV] = '0'
        self.assertTrue(nornir_shared.files.IsOutdated(self.reference, self.test))

    def test_invalid_and_negative_env_values(self) -> None:
        os.environ[nornir_shared.files.MTIME_SKEW_TOLERANCE_ENV] = 'banana'
        self.assertEqual(nornir_shared.files.mtime_skew_tolerance_ns(), 2_000_000_000)
        os.environ[nornir_shared.files.MTIME_SKEW_TOLERANCE_ENV] = 'nan'
        self.assertEqual(nornir_shared.files.mtime_skew_tolerance_ns(), 2_000_000_000)
        os.environ[nornir_shared.files.MTIME_SKEW_TOLERANCE_ENV] = '-5'
        self.assertEqual(nornir_shared.files.mtime_skew_tolerance_ns(), 0)

    def test_significantly_newer_and_equivalent_boundaries(self) -> None:
        tol = 1_000
        self.assertFalse(nornir_shared.files.is_significantly_newer(1_000, 0, tolerance_ns=tol))
        self.assertTrue(nornir_shared.files.is_significantly_newer(1_001, 0, tolerance_ns=tol))
        self.assertFalse(nornir_shared.files.is_significantly_newer(0, 5_000, tolerance_ns=tol))
        self.assertTrue(nornir_shared.files.mtimes_equivalent(0, 1_000, tolerance_ns=tol))
        self.assertTrue(nornir_shared.files.mtimes_equivalent(1_000, 0, tolerance_ns=tol))
        self.assertFalse(nornir_shared.files.mtimes_equivalent(0, 1_001, tolerance_ns=tol))

    def test_newest_file_stays_strict(self) -> None:
        self._set_reference_offset(1_000)
        self.assertEqual(nornir_shared.files.NewestFile(self.reference, self.test), self.reference)
        self._set_reference_offset(-1_000)
        self.assertEqual(nornir_shared.files.NewestFile(self.reference, self.test), self.test)
        self._set_reference_offset(0)
        self.assertEqual(nornir_shared.files.NewestFile(self.reference, self.test), self.test)

    def test_is_older_than_stays_strict(self) -> None:
        reference_ns = self._base_ns + 1_000
        self.assertTrue(IsOlderThan(self.test, DateTime=reference_ns / 1_000_000_000.0 + 1e-3))

    def test_remove_outdated_file_respects_tolerance(self) -> None:
        self._set_reference_offset(1_000_000_000)
        self.assertFalse(nornir_shared.files.RemoveOutdatedFile(self.reference, self.test))
        self.assertTrue(os.path.exists(self.test))
        self._set_reference_offset(10_000_000_000)
        self.assertTrue(nornir_shared.files.RemoveOutdatedFile(self.reference, self.test))
        self.assertFalse(os.path.exists(self.test))

    def test_remove_outdated_file_routes_timestamps_to_is_older_than(self) -> None:
        """Every non-path timestamp type is compared with IsOlderThan and never deletes anything."""
        timestamps = [
            datetime.datetime(2020, 1, 2, 3, 4, 5),
            datetime.date(2020, 1, 2),
            datetime.datetime(2020, 1, 2).timetuple(),
            1_600_000_000.5,
            1_600_000_000,
            True,
        ]
        for value in timestamps:
            for older in (True, False):
                with self.subTest(type=type(value).__name__, older=older):
                    with unittest.mock.patch.object(nornir_shared.files, 'IsOlderThan',
                                                    return_value=older) as is_older_than, \
                            unittest.mock.patch.object(nornir_shared.files, 'OutdatedFile') as outdated_file:
                        result = nornir_shared.files.RemoveOutdatedFile(
                            self.reference, value, comparison=nornir_shared.files.FileTimeComparison.CREATION)
                    self.assertFalse(result)
                    is_older_than.assert_called_once_with(
                        self.reference, value, comparison=nornir_shared.files.FileTimeComparison.CREATION)
                    outdated_file.assert_not_called()
                    self.assertTrue(os.path.exists(self.reference))

    def test_remove_outdated_file_rejects_unsupported_types(self) -> None:
        for value in (None, [1.0], b'path', 1 + 2j):
            with self.subTest(type=type(value).__name__), self.assertRaises(ValueError):
                nornir_shared.files.RemoveOutdatedFile(self.reference, value)  # type: ignore[arg-type]

    def test_remove_outdated_file_routes_path_to_outdated_file(self) -> None:
        with unittest.mock.patch.object(nornir_shared.files, 'OutdatedFile', return_value=False) as outdated_file, \
                unittest.mock.patch.object(nornir_shared.files, 'IsOlderThan') as is_older_than:
            self.assertFalse(nornir_shared.files.RemoveOutdatedFile(self.reference, self.test))
        outdated_file.assert_called_once_with(
            self.reference, self.test, comparison=nornir_shared.files.FileTimeComparison.MODIFIED)
        is_older_than.assert_not_called()


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
