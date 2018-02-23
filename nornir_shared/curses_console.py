'''
Created on Sep 3, 2014

@author: u0490822

This facilitates the output console window to use the curses library
'''

import atexit
import curses 


_status_window = None
_curses_screen = None

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

    _curses_screen = curses.initscr()
 
    # sys.stdout = logFile

    try:
        (num_rows, num_cols) = _curses_screen.getmaxyx()
        # LogStartY = 16
        # ScreenWidth = maxX

        _status_window = curses.newwin(num_rows, num_cols, 0, 0)
#===============================================================================
#         logWindow = curses.newpad(9999, ScreenWidth)
# 
#         _curses_screen.erase()
#         _curses_screen.refresh()
# 
#         logWindow.move(0, 0)
#         logWindow.standout()
#===============================================================================
        _status_window.standend()

        atexit.register(__EndCurses__)
    except Exception as e:
        curses.endwin()
        raise e
