'''
Created on Apr 26, 2016

@author: u0490822
'''
import unittest

import nornir_shared.argparse_helpers


# import nornir_shared
class ArgParseHelpersTest(unittest.TestCase):

    def testFloatRange(self):
        self.assertTrue(nornir_shared.argparse_helpers.FloatRange('-5:5:5') == [-5, 0, 5])

        self.assertTrue(nornir_shared.argparse_helpers.FloatRange('0') == [0.0])
        self.assertTrue(nornir_shared.argparse_helpers.FloatRange('0:3') == [0.0, 1.0, 2.0, 3.0])
        self.assertTrue(nornir_shared.argparse_helpers.FloatRange('0:0.5:2') == [0.0, 0.5, 1.0, 1.5, 2.0])

        pass

    def testIntegerPair(self):
        self.assertTrue(nornir_shared.argparse_helpers.IntegerPair('256') == (256, 256))
        self.assertTrue(nornir_shared.argparse_helpers.IntegerPair('256,512') == (256, 512))

        pass

    def testFloatPair(self):
        self.assertTrue(nornir_shared.argparse_helpers.FloatPair('256.5') == (256.5, 256.5))
        self.assertTrue(nornir_shared.argparse_helpers.FloatPair('-0.1,23.3') == (-0.1, 23.3))

        pass

    def testNumberList(self):
        a = nornir_shared.argparse_helpers.IntegerList('3')
        self.assertTrue(nornir_shared.argparse_helpers.IntegerList('3') == [3])
        self.assertTrue(nornir_shared.argparse_helpers.IntegerList('3-5') == [3, 4, 5])
        self.assertTrue(nornir_shared.argparse_helpers.IntegerList('1,3-5') == [1, 3, 4, 5])
        self.assertTrue(nornir_shared.argparse_helpers.IntegerList('3-5,7') == [3, 4, 5, 7])
        self.assertTrue(nornir_shared.argparse_helpers.IntegerList('1,3-5,7') == [1, 3, 4, 5, 7])
        self.assertTrue(nornir_shared.argparse_helpers.IntegerList('1,7,9,10-12,15') == [1, 7, 9, 10, 11, 12, 15])

        pass


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
