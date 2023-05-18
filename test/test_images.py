'''
Created on Apr 16, 2014

@author: u0490822
'''
import os
import unittest

import nornir_shared.images as images


class Test(unittest.TestCase):

    @property
    def TestInputPath(self):
        if 'TESTINPUTPATH' in os.environ:
            TestInputDir = os.environ["TESTINPUTPATH"]
            self.assertTrue(os.path.exists(TestInputDir),
                            "Test input directory specified by TESTINPUTPATH environment variable does not exist")
            return TestInputDir
        else:
            self.fail("TESTINPUTPATH environment variable should specify input data directory")

        return None

    def test_IsValidImage(self):

        ValidImagePath = os.path.join(self.TestInputPath, 'Transforms', 'FixedMoving_Registered.png')
        InvalidImagePath = os.path.join(self.TestInputPath, 'Transforms', 'FixedMoving_RBF.stos')

        valid = images.IsValidImage(ValidImagePath)
        self.assertTrue(valid, "Valid image is returning invalid")

        valid = images.IsValidImage(InvalidImagePath)
        self.assertFalse(valid, "invalid image is returning valid")

        pass


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.test_IsValidImage']
    unittest.main()
