import atexit
import socket
import subprocess

import console_constants

class ConsoleWindow(object):
    '''
    Creates a second console window which displays text output sent to this Console object
    '''

    def __init__(self, title=None, host=None, port=None, *args, **kwargs):
        '''
        :param str title: Title to place on new console
        :param str host: Host address to use
        :param int port: Port to use
        '''

        super(ConsoleWindow, self).__init__(*args, **kwargs)
        self.HOST = console_constants.DefaultHost if host is None else host
        self.PORT = console_constants.DefaultPort if port is None else int(port)
        self.title = '' if title is None else title.strip()

        self._socket = None
        self._consoleProc = subprocess.Popen(self.pycmd(self.title, self.HOST, self.PORT), stdin=subprocess.PIPE,
                                             shell=True)

    def pycmd(self, title, host, port):
        '''Command to use to launch python'''
        pycmd = "python -m nornir_shared.console -host %s -port %d" % (host, int(port))

        if len(self.title) > 0:
            pycmd += " -title {0}".format(self.title)

        debug = False
        cmd = 'start "%s" %s' % (title, pycmd)
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
            self._socket.sendall(console_constants.console_exit_string.encode())
            self._socket.close()
            self._socket = None


class CursesConsoleWindow(ConsoleWindow):

    def __init__(self, title=None, host=None, port=None, *args, **kwargs):
        super(CursesConsoleWindow, self).__init__(title=title, host=host, port=port, *args, **kwargs)

    def pycmd(self, title, host, port):
        '''Command to use to launch python'''
        pycmd = "python -m nornir_shared.console -host %s -port %d -usecurses " % (host, int(port))
        debug = False
        cmd = 'start "%s" %s ' % (title, pycmd)
        if debug:
            cmd = 'start "%s" %s -debug' % (title, pycmd)

        return cmd
