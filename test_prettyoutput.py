'''
Created on Oct 13, 2013

@author: Jamesan
'''
import unittest
import nornir_shared.prettyoutput

class Test(unittest.TestCase):


    def testPipes(self):
        p = nornir_shared.prettyoutput.Console.CreateConsoleProc()
        self.assertIsNotNone(p, "None process for prettyoutput")
        p.stdin.write("Hello world\n")
        p.stdin.write("This is a test\n")
        p.stdin.write("PrettyOutput.Exit\n")
        pass


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testPipes']
    unittest.main()