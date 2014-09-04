'''
Created on Sep 3, 2014

@author: u0490822
'''
import os
import subprocess
import socket
import sys
import time
import argparse 
import traceback 

curses_available = None
import nornir_shared.curses_console
curses_available = True

import atexit

    
'''The string to send to a second console process to close it'''
_console_exit_string = 'Console.Exit\n'
DefaultPort = 50007
DefaultHost = '127.0.0.1'

def CreateParser():
    parser = argparse.ArgumentParser()
    
    parser.add_argument('-port',
                        required=False,
                        default=50007,
                        type=int,
                        help='Port # for second console.  Defaults to 50007',
                        dest='PORT')


    parser.add_argument('-host',
                        required=False,
                        default='127.0.0.1',
                        help='Host IP for the second console.  Defaults to 127.0.0.1 (localhost)',
                        dest='HOST')
    
    parser.add_argument('-usecurses', '-c',
                        required=False,
                        default=False,  
                        action='store_true',
                        help='Indicates the curses library should be used for the second window',
                        dest='curses')
    
    return parser
    
def ConsoleModulePath():
    try:
        path = os.path.dirname(__file__)
    except:
        path = os.getcwd()

    return os.path.join(path, 'console.py')

class Console(object):
    '''
    Creates a second console window which displays text output sent to this Console object
    ''' 

    def __init__(self, title=None, host=None, port=None, *args, **kwargs):
        '''
        :param str title: Title to place on new console
        :param str host: Host address to use
        :param int port: Port to use
        '''
        
        global DefaultHost
        global DefaultPort
        
        super(Console, self).__init__(*args, **kwargs)
        self.HOST = DefaultHost
        if not host is None:
            self.HOST = host
        
        self.PORT = DefaultPort
        if not port is None:
            self.PORT = int(port)
            
        self.title = title
        if self.title is None:
            self.title = ''
        
        self._socket = None
        self._consoleProc = None
         
         
    def pycmd(self, title, host, port):
        '''Command to use to launch python'''
        pycmd = "python -m nornir_shared.console -host %s -port %d -usecurses " % (host, int(port))
        debug = False
        cmd_prefix = 'start "%s" %s' % (title, pycmd)
        if debug:
            cmd_prefix = 'cmd.exe /k %s' % (pycmd)
            
        return cmd_prefix + pycmd

    @property
    def socket(self):
        if self._consoleProc is None: 
            self._consoleProc = subprocess.Popen(self.pycmd(self.title, self.HOST, self.PORT), stdin=subprocess.PIPE, shell=True)

        if self._socket is None:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.connect((self.HOST, self.PORT))
            atexit.register(self._socket.close)

        return self._socket

    @property
    def ConsoleProc(self):
        return self._consoleProc

    def WriteMessage(self, text):
        self.socket.sendall(text.encode())
        
    def Close(self): 
        if not self._socket is None:
            self._socket.sendall(_console_exit_string.encode())
            self._socket.close()
            self._socket = None
            

class CursesConsole(Console):
    
    def __init__(self, title=None, host=None, port=None, *args, **kwargs):
        super(CursesConsole, self).__init__(title=title, host=host, port=port, *args, **kwargs)
    
    def pycmd(self, title, host, port):
        '''Command to use to launch python'''
        pycmd = "python -m nornir_shared.console -host %s -port %d -usecurses " % (host, int(port))
        debug = True
        cmd_prefix = 'start "%s" %s ' % (title,pycmd)
        if debug:
            cmd_prefix = 'start "%s" %s ' % (title,pycmd)
            
        return cmd_prefix
     

def _CreateConnection(HOST, PORT):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((HOST, PORT))
    s.listen(1)
    conn, addr = s.accept()
    return conn

line_buffer_str = ""

def ReadFromStream(conn):
    
    global line_buffer_str
    
    data = conn.recv(1024)
    if not data:
        return None
    
    data_str = data.decode('utf8')
    
    line_buffer_str += data_str 
    return len(data_str)

def GetNextLine():
    '''Returns line if it is ready, otherwise None'''
        
    global line_buffer_str
    
    if '\n' in line_buffer_str:
        iNewline = line_buffer_str.find('\n')
        line = line_buffer_str[:iNewline+1]
        line_buffer_str = line_buffer_str[iNewline+1:]
        
        return line

    return None

def IsLineAvailable():
    global line_buffer_str
    
    return '\n' in line_buffer_str

             
def ListenLoop(HOST, PORT, handler_func):
    '''
    :param func handler_func: Function to pass data recieved on the socket to
    '''
    
    #sys.stdout.write("Starting second output window on %s:%d\n" % (HOST, PORT)) 

    global curses_available
    
    try:
        hFile = open('C:\\Temp\\ListenLoop.txt', mode='w')
    
        hFile.write('HOST=%s\n' % HOST)
        hFile.write('PORT=%d\n' % PORT)
        hFile.write('Func=%s\n' % str(handler_func))
        hFile.write('Curses_Available=%d\n' % curses_available)
        
        exit_signal_received = False
            
        while not exit_signal_received:
            
            conn = None
            try:
                conn = _CreateConnection(HOST, PORT)
                
                #pydevd.settrace(suspend=False)
                
                incoming_line = None
                while not exit_signal_received:
                    ReadFromStream(conn)
                    
                    while IsLineAvailable():
                        incoming_line = GetNextLine()
                        hFile.write(incoming_line)
                        
                        if _console_exit_string in incoming_line:
                            exit_signal_received = True
                            break
                        else:
                            handler_func(incoming_line) 
                            
            finally:
                if not conn is None:
                    conn.close()
                    conn = None
            
    except Exception as e:
        hFile.write(str(e)+'\n')
        sys.stdout.write(traceback.format_exc()) 
        hFile.write(traceback.format_exc()+'\n')
        exit_signal_received = True 
    finally:
        hFile.close()
        
        
def CursesHandler(data_str):
    '''
    Sends output to the curses window.  Input strings should contain "TOPIC:TEXT" using the semicolon as a delimiter
    :param str data_str: Data received over the socket
    '''
    global curses_available
    
    if not curses_available:
        sys.stdout.write(data_str)
    else:
        (topic, colon, text) = data_str.partition(':')
        nornir_shared.curses_console.CurseString(topic, text)
   

_curses_screen = None
'''
Mapping 
'''
_curses_topic_line_dict = {}
 
        
if __name__ == '__main__':
    
    import pydevd
    
    parser = CreateParser()
    args = parser.parse_args()
    print('HOST=%s\n' % args.HOST)
    print('PORT=%d\n' % args.PORT) 
    print('Curses=%d\n' % args.curses)
    if not args.curses:
        ListenLoop(HOST=args.HOST, PORT=args.PORT, handler_func=sys.stdout.write)
    else: 
        hFile = open('C:\\Temp\\OuterLoop.txt', mode='w')
        
        try:
            nornir_shared.curses_console.InitCurses()
            hFile.write("Init OK")
        except Exception as e:
            hFile.write(traceback.format_exc(e))  
        finally:
            hFile.close()
            
        ListenLoop(HOST=args.HOST, PORT=args.PORT, handler_func=CursesHandler)

    print("This window will close in 30 seconds")
    time.sleep(30)
    