"""
Created on Sep 3, 2014

@author: u0490822
"""
import argparse
import os
import socket
import sys
import time
import traceback

import nornir_shared.console_constants

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
_DEBUG = False

try:
    import pydevd

    pydevd_available = True
except ImportError:
    pass


def CreateParser() -> argparse.ArgumentParser:
    argparser = argparse.ArgumentParser()

    argparser.add_argument('-port',
                           required=False,
                           default=50007,
                           type=int,
                           help='Port # for second console.  Defaults to 50007',
                           dest='PORT')

    argparser.add_argument('-host',
                           required=False,
                           default='127.0.0.1',
                           help='Host IP for the second console.  Defaults to 127.0.0.1 (localhost)',
                           dest='HOST')

    argparser.add_argument('-usecurses', '-c',
                           required=False,
                           default=False,
                           action='store_true',
                           help='Indicates the curses library should be used for the second window',
                           dest='curses')

    argparser.add_argument('-debug',
                           required=False,
                           default=False,
                           action='store_true',
                           help='Create text files for second console with recieved lines and exception information',
                           dest='debug')

    argparser.add_argument('-title',
                           required=False,
                           default='',
                           action='store',
                           type=str,
                           help='Title of the window',
                           dest='title')

    return argparser


def ConsoleModulePath() -> str:
    try:
        path = os.path.dirname(__file__)
    except:
        path = os.getcwd()

    return os.path.join(path, 'console.py')


def _CreateConnection(HOST: str, PORT: int) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((HOST, PORT))
    s.listen(1)
    conn, addr = s.accept()
    return conn


line_buffer_str = ""


def ReadFromStream(conn) -> int | None:
    global line_buffer_str

    data = conn.recv(1024)
    if not data:
        time.sleep(0.5)
        return None

    data_str = data.decode('utf8')

    line_buffer_str += data_str
    return len(data_str)


def GetNextLine() -> str | None:
    """Returns line if it is ready, otherwise None"""

    global line_buffer_str

    if '\n' in line_buffer_str:
        iNewline = line_buffer_str.find('\n')
        line = line_buffer_str[:iNewline + 1]
        line_buffer_str = line_buffer_str[iNewline + 1:]

        return line

    return None


def IsLineAvailable() -> bool:
    global line_buffer_str

    return '\n' in line_buffer_str


def CreateDebugInfoFile(filename: str | None = None):
    if filename is None:
        filename = 'Console_Debug_Output.txt'

    return open(os.path.join(os.getcwd(), filename), mode='w')


def ListenLoop(HOST: str, PORT: int, title: str, handler_func: callable(any)):
    """
    :param HOST:
    :param PORT:
    :param title:
    :param func handler_func: Function to pass data recieved on the socket to
    """

    # sys.stdout.write("Starting second output window on %s:%d\n" % (HOST, PORT)) 

    global curses_available
    global _DEBUG

    debug_file = None
    try:
        if _DEBUG:
            debug_file = CreateDebugInfoFile(title + '.log')

            debug_file.write('Title=%s\n' % title)
            debug_file.write('HOST=%s\n' % HOST)
            debug_file.write('PORT=%d\n' % PORT)
            debug_file.write('Func=%s\n' % str(handler_func))
            debug_file.write('Curses_Available=%d\n' % curses_available)

        exit_signal_received = False

        while not exit_signal_received:

            with _CreateConnection(HOST, PORT) as conn:

                if pydevd_available and _DEBUG:
                    pydevd.settrace(suspend=False)

                incoming_line = None
                while not exit_signal_received:
                    ReadFromStream(conn)

                    while IsLineAvailable():
                        incoming_line = GetNextLine()

                        if _DEBUG:
                            debug_file.write(incoming_line)

                        if nornir_shared.console_constants.console_exit_string in incoming_line:
                            exit_signal_received = True
                            break
                        else:
                            handler_func(incoming_line)

    except Exception as e:
        if debug_file is None:
            debug_file = CreateDebugInfoFile()

        debug_file.write(str(e) + '\n')
        sys.stdout.write(traceback.format_exc())
        debug_file.write(traceback.format_exc() + '\n')
    finally:
        if debug_file is not None:
            debug_file.close()


def NoCursesHandler(data_str: str):
    """
    Sends output to the console window.  Input strings should contain "TOPIC:TEXT" using the semicolon as a delimiter
    :param str data_str: Data received over the socket
    """

    (topic, colon, text) = data_str.partition(':')
    sys.stdout.write(text)


def CursesHandler(data_str: str):
    """
    Sends output to the curses window.  Input strings should contain "TOPIC:TEXT" using the semicolon as a delimiter
    :param str data_str: Data received over the socket
    """
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

        print('Title=%s' % args.title)
        print('HOST=%s' % args.HOST)
        print('PORT=%d' % args.PORT)
        print('Curses=%d' % args.curses)
        print('Debug=%d' % _DEBUG)
        print('pydevd_available=%d' % pydevd_available)
        print('')

        if _DEBUG:
            if not pydevd_available:
                print(
                    "Debug flag set but pydevd is not available.  Try running debug flag in eclipse to use breakpoints in remote process.")
            else:
                pydevd.settrace(suspend=False)

        if curses_available:
            try:
                success = nornir_shared.curses_console.InitCurses()
                assert success, "Could not InitCurses"
            except Exception as e:
                sys.stdout.write(traceback.format_exc())
                with CreateDebugInfoFile('Console_Curses_Error.txt') as hFile:
                    hFile.write(traceback.format_exc())

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
