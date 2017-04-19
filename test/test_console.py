'''
Created on Oct 13, 2013

@author: Jamesan
'''
import random
import socket
import unittest

import nornir_shared.console
import nornir_shared.curses_console
import nornir_shared.prettyoutput


class TestConsole(unittest.TestCase):
     
     def test_WriteMessage(self):
         console = nornir_shared.console.Console()
         
         console.WriteMessage("testWriteMessage\n") 
         console.WriteMessage("This is a test\n")
         console.WriteMessage("Second line of data.Exit\n")
         
         console.Close()
         
     def test_WriteMessage_alternate_host_and_port(self):
         console = nornir_shared.console.Console(title="testWriteMessage_alternate_host_and_port", host='localhost', port=random.randint(50000, 51000))
         
         console.WriteMessage("testWriteMessage_alternate_host_and_port\n") 
         console.WriteMessage("This is a test\n")
         console.WriteMessage("Second line of data.Exit\n")
         
         console.Close()
        
     def test_WriteCursesMessage(self):
        console = nornir_shared.console.CursesConsole(title="WriteCursesMessage", port=random.randint(50000, 51000))
        
        console.WriteMessage("Owner:WriteCursesMessage\n") 
        console.WriteMessage("Data:This is a test\n")
        console.WriteMessage("Data:Second line of data.Exit\n")
        console.WriteMessage("Owner:WriteCursesMessageAgain\n") 
        
        console.Close()
    #===========================================================================
    #     
    # def test_WriteCurses(self): 
    #     nornir_shared.curses_console.InitCurses()
    #     nornir_shared.curses_console.CurseString("Owner:testWriteMessage_alternate_host_and_port\n") 
    #     nornir_shared.curses_console.CurseString("Data:This is a test\n")
    #     nornir_shared.curses_console.CurseString("Data:PrettyOutput.Exit\n")
    #      
    #===========================================================================
        
        

if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testPipes']
    unittest.main()
