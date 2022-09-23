'''
Created on Sep 3, 2014

@author: u0490822
'''
import argparse 
import atexit
import os
import socket
import subprocess
import sys
import time
import traceback 


curses_available = False
try:
    import curses
    curses_available = True
except ImportError:
    pass


if curses_available:
    import nornir_shared.curses_console
    
_curses_topic_line_dict = {}
pydevd_available = False

try:
    import pydevd
    pydevd_available = True
except ImportError: 
    pass
    
'''The string to send to a second console process to close it'''
_console_exit_string = 'Console.Exit\n'
DefaultPort = 50007
DefaultHost = '127.0.0.1'
_DEBUG = False

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
    
    parser.add_argument('-debug',
                        required=False,
                        default=False,
                        action='store_true',
                        help='Create text files for second console with recieved lines and exception information',
                        dest='debug')
    
    parser.add_argument('-title',
                        required=False,
                        default='',
                        action='store',
                        type=str,
                        help='Title of the window',
                        dest='title')
    
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
        self.HOST = DefaultHost if host is None else host
        self.PORT = DefaultPort if port is None else int(port)
        self.title = '' if title is None else title.strip()
        
        self._socket = None
        self._consoleProc = subprocess.Popen(self.pycmd(self.title, self.HOST, self.PORT), stdin=subprocess.PIPE, shell=True)
         
         
    def pycmd(self, title, host, port):
        '''Command to use to launch python'''
        pycmd = "python -m nornir_shared.console -host %s -port %d" % (host, int(port))
        
        if len(self.title) > 0:
            pycmd += " -title {0}".format(self.title)
            
        debug = False
        cmd =  'start "%s" %s' % (title, pycmd)
        if debug:
            # Debug does not seem to be working for non-curses consoles for some reason
            cmd = 'start "%s" %s -debug' % (title, pycmd)
            
        return cmd

    @property
    def socket(self):

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
        debug = False
        cmd = 'start "%s" %s ' % (title, pycmd)
        if debug:
            cmd = 'start "%s" %s -debug' % (title, pycmd)
            
        return cmd
     

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
        time.sleep(0.5)
        return None
    
    data_str = data.decode('utf8')
    
    line_buffer_str += data_str 
    return len(data_str)

def GetNextLine():
    '''Returns line if it is ready, otherwise None'''
        
    global line_buffer_str
    
    if '\n' in line_buffer_str:
        iNewline = line_buffer_str.find('\n')
        line = line_buffer_str[:iNewline + 1]
        line_buffer_str = line_buffer_str[iNewline + 1:]
        
        return line

    return None

def IsLineAvailable():
    global line_buffer_str
    
    return '\n' in line_buffer_str


def CreateDebugInfoFile(filename=None):
    if filename is None:
        filename = 'Console_Debug_Output.txt'
        
    return open(os.path.join(os.getcwd(), filename), mode='w')
             
def ListenLoop(HOST, PORT, title, handler_func):
    '''
    :param func handler_func: Function to pass data recieved on the socket to
    '''
    
    # sys.stdout.write("Starting second output window on %s:%d\n" % (HOST, PORT)) 

    global curses_available
    global _DEBUG
    
    hFile = None
    try:
        if _DEBUG:
            hFile = CreateDebugInfoFile(title + '.log')
        
            hFile.write('Title=%s\n' % title)
            hFile.write('HOST=%s\n' % HOST)
            hFile.write('PORT=%d\n' % PORT)
            hFile.write('Func=%s\n' % str(handler_func))
            hFile.write('Curses_Available=%d\n' % curses_available)
        
        exit_signal_received = False
            
        while not exit_signal_received:
            
            conn = None
            try:
                conn = _CreateConnection(HOST, PORT)
                
                if pydevd_available and _DEBUG:
                    pydevd.settrace(suspend=False)
                
                incoming_line = None
                while not exit_signal_received:
                    ReadFromStream(conn)
                    
                    while IsLineAvailable():
                        incoming_line = GetNextLine()
                        
                        if _DEBUG:
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
        if hFile is None:
            hFile = CreateDebugInfoFile()
            
        hFile.write(str(e) + '\n')
        sys.stdout.write(traceback.format_exc()) 
        hFile.write(traceback.format_exc() + '\n')
        exit_signal_received = True 
    finally:
        if not hFile is None:
            hFile.close()
            
def NoCursesHandler(data_str):
    '''
    Sends output to the console window.  Input strings should contain "TOPIC:TEXT" using the semicolon as a delimiter
    :param str data_str: Data received over the socket
    ''' 
    
    (topic, colon, text) = data_str.partition(':')
    sys.stdout.write(text)
    
        
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
        
if __name__ == '__main__':
    
    try:
        parser = CreateParser()
        args = parser.parse_args()
        
        _DEBUG = args.debug
        
        print('Title=%s\n' % args.title)
        print('HOST=%s\n' % args.HOST)
        print('PORT=%d\n' % args.PORT) 
        print('Curses=%d\n' % args.curses)
        print('Debug=%d\n' % _DEBUG)
        print('pydevd_available=%d' % pydevd_available)
        
        if _DEBUG:
            if not pydevd_available:
                print("Debug flag set but pydevd is not available.  Try running debug flag in eclipse to use breakpoints in remote process.")
            else:  
                pydevd.settrace(suspend=False)
        
        if curses_available:
            try:
                success = nornir_shared.curses_console.TryInitCurses()
                assert(success), "Could not InitCurses"
            except Exception as e:
                sys.stdout.write(traceback.format_exc()) 
                hFile = CreateDebugInfoFile('Console_Curses_Error.txt')
                hFile.write(traceback.format_exc(e))
                hFile.close()  
            
            if success: 
                ListenLoop(HOST=args.HOST, PORT=args.PORT, title='Main', handler_func=CursesHandler)
            else:
                ListenLoop(HOST=args.HOST, PORT=args.PORT, title='Main', handler_func=NoCursesHandler)
        else: 
            ListenLoop(HOST=args.HOST, PORT=args.PORT, title='Main', handler_func=NoCursesHandler)
                
    except:
        sys.stdout.write(traceback.format_exc()) 
        pass
    finally:
        time.sleep(15)
    
