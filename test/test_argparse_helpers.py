'''
Created on Apr 26, 2016

@author: u0490822
'''
import unittest
#import nornir_shared
import nornir_shared.argparse_helpers


class ArgParseHelpersTest(unittest.TestCase):


    def testFloatRange(self):
        
        self.assertTrue(nornir_shared.argparse_helpers.FloatRange('0') == [0.0])
        self.assertTrue(nornir_shared.argparse_helpers.FloatRange('0:3') == [0.0,1.0,2.0,3.0])
        self.assertTrue(nornir_shared.argparse_helpers.FloatRange('0:0.5:2') == [0.0,0.5,1.0,1.5,2.0])
        
        pass
    
    def testNumberPair(self):
        
        self.assertTrue(nornir_shared.argparse_helpers.NumberPair('256') == (256,256))
        self.assertTrue(nornir_shared.argparse_helpers.NumberPair('256,512') == (256,512))
        
        pass
    
    
    def testNumberList(self):
        a = nornir_shared.argparse_helpers.NumberList('3')
        self.assertTrue(nornir_shared.argparse_helpers.NumberList('3') == [3])
        self.assertTrue(nornir_shared.argparse_helpers.NumberList('3-5') == [3,4,5])
        self.assertTrue(nornir_shared.argparse_helpers.NumberList('1,3-5') == [1,3,4,5])
        self.assertTrue(nornir_shared.argparse_helpers.NumberList('3-5,7') == [3,4,5,7])
        self.assertTrue(nornir_shared.argparse_helpers.NumberList('1,3-5,7') == [1,3,4,5,7])
        self.assertTrue(nornir_shared.argparse_helpers.NumberList('1,7') == [1,7])
        
        pass


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()