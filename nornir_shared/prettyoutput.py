import inspect
import logging
import os
import sys
import time

import nornir_shared.consolewindow

ECLIPSE = 'ECLIPSE' in os.environ
CURSES = False

ProgressStartTime = None

if not ECLIPSE:
    try:
        import curses

        CURSES = True
    except ImportError:
        pass

LastReportedProgress = 100

__IndentLevel = 0


def IncreaseIndent():
    global __IndentLevel
    __IndentLevel = __IndentLevel + 1


def DecreaseIndent():
    global __IndentLevel
    __IndentLevel = __IndentLevel - 1


def ResetIndent():
    global __IndentLevel
    __IndentLevel = 0


if not os.path.exists('Logs'):
    try:
        os.mkdir('Logs')
    except OSError as E:
        if E.errno == 17:
            # Log("Log dir already exists: " + 'Logs')
            pass

stdscr = None

if CURSES:
    import atexit


    def __EndCurses__():
        curses.endwin()


    stdscr = curses.initscr()

    statusWindow = []
    logWindow = []

    cursesCoords = {"Cores": 1,
                    "Section": 2,
                    "Stage": 3,
                    "Task": 4,
                    "Progress": 5,
                    "PIDs": 6,
                    "Lock": 7,
                    "Path": 8,
                    "Cmd": 9
                    }

    # sys.stdout = logFile

    try:
        (maxY, maxX) = stdscr.getmaxyx()
        LogStartY = 16
        ScreenWidth = maxX

        statusWindow = curses.newwin(15, maxX, 0, 0)
        logWindow = curses.newpad(9999, ScreenWidth)

        stdscr.erase()
        stdscr.refresh()

        logWindow.move(0, 0)
        logWindow.standout()
        statusWindow.standend()

        atexit.register(__EndCurses__)
    except Exception as e:
        curses.endwin()
        raise e


def CurseString(topic, text):
    if CURSES:
        y = 0
        x = 0

        if cursesCoords.has_key(topic):
            y = cursesCoords[topic]

        (yMax, xMax) = statusWindow.getmaxyx()

        outStr = topic + " : " + text
        # Log(outStr)
        statusWindow.addstr(y, x, outStr)
        statusWindow.clrtoeol()
        statusWindow.move(yMax - 1, 0)
        statusWindow.refresh()
    else:
        print(topic + ": " + text)
        return


def CurseProgress(text: str, Progress: float, Total=None):
    '''If Total is specified we display a percentage, otherwise
       a number'''

    # This is used to calculate an ETA for completion
    global LastReportedProgress
    global ProgressStartTime
    if Progress < LastReportedProgress:
        ProgressStartTime = float(time.time())

    console_width = 80

    LastReportedProgress = Progress
    # if Total is None:
    # 	Total = Progress
    # 	if(Total == 0):
    # 		Total = 1

    ProgressY = 0
    ProgressX = 0

    TaskX = 0
    TaskY = 0

    # Estimate how long until we reach total
    ETASec = 0
    tstruct = None
    ETAString = ""
    fraction = None

    if Total is not None:
        fraction = float(Progress / float(Total))
        if fraction > 0:
            elapsedSec = float(time.time() - ProgressStartTime)
            ETASec = (elapsedSec / fraction) * (1.0 - fraction)
            tstruct = time.gmtime(ETASec)
            ETAString = "ETA: " + time.strftime("%H:%M:%S", tstruct)

    if CURSES:
        (yMax, xMax) = statusWindow.getmaxyx()

        if cursesCoords.has_key("Task"):
            TaskY = cursesCoords["Task"]

        if cursesCoords.has_key("Progress"):
            ProgressY = cursesCoords["Progress"]

        if text is not None:
            # TaskStr = "Task: " + text
            # Log(TaskStr)
            statusWindow.addnstr(TaskY, TaskX, "Task: " + text, console_width)
            statusWindow.clrtoeol()

        if Total is not None:
            ProgressStr = "Progress : %4.2f%%" % (fraction * 100.0)
            if not tstruct is None:
                ProgressStr = ProgressStr + "        " + ETAString

            # Log(ProgressStr)

            statusWindow.addnstr(ProgressY, ProgressX, ProgressStr, console_width)
            statusWindow.clrtoeol()
            statusWindow.move(yMax - 1, 0)
            statusWindow.refresh()
    else:
        output_str = text
        if output_str is None:
            output_str = ""

        if fraction is not None:
            output_str = f'{output_str} {fraction:0.3g}'
            if ETAString is not None:
                output_str = output_str + ETAString

        if ECLIPSE:
            print(output_str)
        else:
            # Erase previous output
            padding_needed = console_width - len(output_str)
            if padding_needed < 0:
                padding_needed = 0

            text = ('\b' * console_width) + output_str + (' ' * padding_needed)
            print(text)


def get_calling_func_name():
    '''Beware that calling this function is fairly slow.'''
    stack = inspect.stack()
    if len(stack) < 3:
        return None

    records = stack[2]
    if records is None:
        return None

    if len(records) < 4:
        return None

    func_name = records[3]

    module = inspect.getmodule(records[0])
    if module is None:
        return func_name

    mod_name = inspect.getmodule(records[0]).__name__

    return mod_name + "." + func_name


#   stack = traceback.extract_stack()
#   filename, codeline, funcName, text = stack[-3]

#   return funcName


def Log(text=None, logger_name=None):
    if text is None or len(text) == 0:
        text = os.linesep
    elif not isinstance(text, str):
        text = str(text)

    tabs = ''.join(['  ' for x in range(__IndentLevel)])

    text = tabs + text
    text.replace('\n', '\n' + tabs)

    # if logger_name is None:
    # logger_name = get_calling_func_name()

    logger = logging.getLogger(logger_name)
    logger.info(text)

    if CURSES:
        text = text + os.linesep

        sys.stdout.write(text)
        sys.stdout.flush()

        numChars = len(text)

        (yMax, xMax) = stdscr.getmaxyx()

        numLines = int(numChars / xMax)
        if numChars % xMax != 0:
            numLines = numLines + 1

        logWindow.move(0, 0)

        for i in range(numLines):
            logWindow.insertln()

        logWindow.addstr(0, 0, text)
        logWindow.clrtoeol()
        logWindow.refresh(0, 0, LogStartY, 0, yMax - 1, xMax)
    elif ECLIPSE:
        text = text.replace('\b', '')
        print(text)
    else:
        print(text)


_error_console = None


def error(error_message=None):
    LogErr(error_message, calling_func_name=get_calling_func_name())


def LogErr(error_message=None, calling_func_name=None):
    if error_message is None or len(error_message) == 0:
        error_message = "\n"
    elif not isinstance(error_message, str):
        error_message = str(error_message)

    if error_message[-1] != '\n':
        error_message = error_message + '\n'

    if calling_func_name is None:
        calling_func_name = get_calling_func_name()

    logger = logging.getLogger(calling_func_name)
    logger.error(error_message)

    if not ECLIPSE:
        try:
            global _error_console

            if _error_console is None:
                _error_console = nornir_shared.consolewindow.ConsoleWindow()

            _error_console.WriteMessage(error_message)
            logger = logging.getLogger(calling_func_name)
            logger.error(error_message)
        except:
            _error_console = None
            # logger = logging.getLogger(calling_func_name)
            # logger.error(error_message)
            pass
    else:
        logger = logging.getLogger(get_calling_func_name())
        logger.error(error_message)


def PrettyOutputModulePath():
    try:
        path = os.path.dirname(__file__)
    except:
        path = os.getcwd()

    return os.path.join(path, 'prettyoutput.py')
