'''
Created on Feb 11, 2013

@author: u0490822
'''
import unittest

from nornir_shared.checksum import DataChecksum


class Test(unittest.TestCase):


    def testChecksum(self):
        checkHello = DataChecksum("Hello World")
        self.assertTrue(len(checkHello) > 0)

        ch = DataChecksum(["Hello World", 3, 4, 5])
        self.assertTrue(len(ch) > 0)
        # Ensure that the list form of checksum doesn't just use the first item in the list
        self.assertFalse(ch == checkHello)

        ch = DataChecksum(2345)
        self.assertTrue(len(ch) > 0)

        ch = DataChecksum([2345, 123, 5135, 1325])
        self.assertTrue(len(ch) > 0)

        pass


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testChecksum']
    unittest.main()
