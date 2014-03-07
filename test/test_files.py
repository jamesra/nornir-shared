'''
Created on Oct 21, 2013

@author: u0490822
'''
import unittest
import os
import shutil
from nornir_shared.files import RecurseSubdirectories, RecurseSubdirectoriesGenerator 

def CreateDirTree(path, dictSubTrees):
    print(str(dictSubTrees))
    for key in list(dictSubTrees.keys()):
        subtreepath = os.path.join(path, key)
        os.makedirs(subtreepath)

        CreateDirTree(subtreepath, dictSubTrees[key])


def RecurseDictValues(dictSubTrees, path):
    vals = list(dictSubTrees.keys())

    for key in list(dictSubTrees.keys()):
        subpath = os.path.join(path, key)
        vals.append(subpath)
        vals.extend(RecurseDictValues(dictSubTrees[key], subpath))

    return vals


class TestFiles(unittest.TestCase):

    DirTree = {'aaa' : {},
               'bbb' : {'baaa' : {}},
               'ccc' : {'ca':{}, 'cb':{'cba':{}}, 'cc':{'cca':{}, 'ccb':{}}}}


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

    def IsSubset(self, ListA, ListB):
        '''Verify ListA is a subset of ListB'''
        for l in ListA:
            self.assertTrue(l in ListB, str(l) + " is missing from target set")

    def IsSingleResult(self, ListA, result):
        self.assertEqual(len(ListA), 1, "Result list should have one entry")
        self.assertEqual(ListA[0], result, "Expected result not found, expected " + str(result) + " got " + str(ListA[0]))

    def testName(self):

        dirs = RecurseSubdirectories(self.TestOutputPath, RequiredFiles=[], ExcludedFiles=[], MatchNames=None, ExcludeNames=[], ExcludedDownsampleLevels=[])
        expectedDirs = RecurseDictValues(TestFiles.DirTree, self.TestOutputPath)
        self.IsSubset(dirs, expectedDirs)

        # One known match in root dir
        dirs = RecurseSubdirectories(self.TestOutputPath, RequiredFiles=[], ExcludedFiles=[], MatchNames=['aaa'], ExcludeNames=[], ExcludedDownsampleLevels=[])
        self.IsSingleResult(dirs, os.path.join(self.TestOutputPath, 'aaa'))

        dirs = RecurseSubdirectories(self.TestOutputPath, RequiredFiles=[], ExcludedFiles=[], MatchNames=['baaa'], ExcludeNames=[], ExcludedDownsampleLevels=[])
        self.IsSingleResult(dirs, os.path.join(self.TestOutputPath,'bbb\\baaa'))

        dirs = RecurseSubdirectories(self.TestOutputPath, RequiredFiles=[], ExcludedFiles=[], MatchNames=['cca'], ExcludeNames=[], ExcludedDownsampleLevels=[])
        self.IsSingleResult(dirs, os.path.join(self.TestOutputPath,'ccc\\cc\\cca'))

        dirs = RecurseSubdirectories(self.TestOutputPath, RequiredFiles=[], ExcludedFiles=[], MatchNames=[], ExcludeNames='ccc', ExcludedDownsampleLevels=[])
        expectedVals = [os.path.join(self.TestOutputPath, x) for x in ['aaa', 'bbb', 'bbb\\baaa']]
        self.IsSubset(dirs, expectedVals)

if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()