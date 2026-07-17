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


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
