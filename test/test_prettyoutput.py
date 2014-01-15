'''
Created on Oct 13, 2013

@author: Jamesan
'''
import unittest
import nornir_shared.prettyoutput
import socket

class TestConsole(unittest.TestCase):
    
    def testWriteMessage(self):
        console = nornir_shared.prettyoutput.Console()
        
        console.WriteMessage("Hello world\n") 
        console.WriteMessage("This is a test\n")
        console.WriteMessage("PrettyOutput.Exit\n")
        
        console.Close()
        

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testPipes']
    unittest.main()