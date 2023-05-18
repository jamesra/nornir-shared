'''
Created on Oct 13, 2013

@author: Jamesan
'''
import unittest

import nornir_shared.console
import nornir_shared.consolewindow


class Test(unittest.TestCase):

    def testPipes(self):
        p = nornir_shared.consolewindow.ConsoleWindow()
        self.assertIsNotNone(p, "None process for prettyoutput")
        p.ConsoleProc.stdin.write("Hello world\n".encode())
        p.ConsoleProc.stdin.write("This is a test\n".encode())
        p.ConsoleProc.stdin.write("PrettyOutput.Exit\n".encode())
        pass


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testPipes']
    unittest.main()
