'''
Created on Sep 3, 2014

@author: u0490822

This facilitates the output console window to use the curses library
'''

import atexit

curses_available = False
try:
    import curses

    curses_available = True
except ImportError:
    pass

_status_window = None
_curses_screen = None

_log_window = None

num_rows = None  # Number of rows in the curses window
num_cols = None  # Number of columns in the curses window

cur_log_row = 0  # The next log row we should write to

'''Maps a topic string to a row in the curses window'''
topic_row_list = []


def __EndCurses__():
    curses.endwin()


def GetOrCreateTopicRow(topic):
    global topic_row_list

    if topic in topic_row_list:
        return topic_row_list.index(topic)
    else:
        topic_row_list.append(topic)
        return len(topic_row_list) - 1


def CurseString(topic, text):
    global _status_window
    y = 0
    x = 0

    y = GetOrCreateTopicRow(topic)

    (yMax, xMax) = _status_window.getmaxyx()

    outStr = "%s : %s" % (topic, text)
    # Log(outStr)
    _status_window.addstr(y, x, outStr)
    _status_window.clrtoeol()
    _status_window.move(yMax - 1, 0)
    _status_window.refresh()


def InitCurses():
    global _curses_screen
    global _status_window
    global _log_window
    global num_rows
    global num_cols

    if not curses_available:
        return False

    _curses_screen = curses.initscr()

    # sys.stdout = logFile

    try:
        (num_rows, num_cols) = _curses_screen.getmaxyx()
        # LogStartY = 16
        # ScreenWidth = maxX

        _status_window = curses.newwin(num_rows, num_cols, 0, 0)
        # ===============================================================================
        #        _log_window = curses.newpad(9999, num_cols)
        #        _log_window.idlok(True)
        #         _curses_screen.erase()
        #         _curses_screen.refresh()
        #
        #         logWindow.move(0, 0)
        #         logWindow.standout()
        # ===============================================================================
        # _status_window.standend()
        # _status_window.idlok(True)

        atexit.register(__EndCurses__)

        return True
    except Exception as e:
        curses.endwin()
        raise e
