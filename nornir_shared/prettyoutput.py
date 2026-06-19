import inspect
import logging
import os
import sys
import time
import typing
from typing import Any
import atexit
import json

import nornir_shared.consolewindow

# MQTT imports and setup
try:
    import paho.mqtt.client as mqtt
    import paho.mqtt.enums as mqtt_enum
    from paho.mqtt.properties import Properties
    from paho.mqtt.reasoncodes import ReasonCode
    from nornir_shared.mqtt_config import MQTT_CONNECT_HOST, MQTT_PORT, MQTT_KEEPALIVE, MQTT_TOPICS, \
        start_mosquitto_broker, stop_mosquitto_broker

    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False

ECLIPSE = 'ECLIPSE' in os.environ
CURSES = False

ProgressStartTime = None

# MQTT client globals
_mqtt_client = None
_mosquitto_process = None
_mqtt_initialized = False

if not ECLIPSE:
    try:
        # Jan 30 2024
        # Curses is causing trouble on Linux installs, so removing it for now
        stdin_is_tty = sys.stdin.isatty()
        stdout_is_tty = sys.stdout.isatty()
        stderr_is_tty = sys.stderr.isatty()
        streams_tty_ok = stdin_is_tty and stdout_is_tty and stderr_is_tty
        if streams_tty_ok:
            import curses
            CURSES = True
        else:
            CURSES = False
        pass
    except ImportError:
        CURSES = False
        pass

LastReportedProgress = 100

__IndentLevel = 0


def _initialize_mqtt():
    """Initialize MQTT client and start mosquitto broker if needed."""
    global _mqtt_client, _mosquitto_process, _mqtt_initialized

    if not MQTT_AVAILABLE or _mqtt_initialized:
        return

    # Mark initialized before attempting startup so worker log calls do not retry
    # broker startup on every message when mosquitto is unavailable or misconfigured.
    _mqtt_initialized = True

    try:
        _mosquitto_process = start_mosquitto_broker()

        _mqtt_client = mqtt.Client(callback_api_version=mqtt_enum.CallbackAPIVersion.VERSION2)

        def on_connect(client: mqtt.Client,
                       userdata: Any,
                       connect_flags: mqtt.ConnectFlags,
                       reason_code: ReasonCode,
                       properties: Properties | None = None):
            if reason_code == 0:  # SUCCESS:
                logging.getLogger(__name__).info("Connected to MQTT broker")
            else:
                logging.getLogger(__name__).error(f"Failed to connect to MQTT broker: {reason_code}")

        def on_disconnect(client: mqtt.Client,
                          userdata: Any,
                          disconnect_flags: mqtt.DisconnectFlags,
                          reason_code: ReasonCode,
                          properties: Properties | None = None):
            logging.getLogger(__name__).info("Disconnected from MQTT broker")

        _mqtt_client.on_connect = on_connect
        _mqtt_client.on_disconnect = on_disconnect

        _mqtt_client.connect(MQTT_CONNECT_HOST, MQTT_PORT, MQTT_KEEPALIVE)
        _mqtt_client.loop_start()

        atexit.register(_cleanup_mqtt)

    except Exception as e:
        logging.getLogger(__name__).info(f"Failed to initialize MQTT: {e}")
        _mqtt_client = None


def _cleanup_mqtt():
    """Cleanup MQTT client and broker"""
    global _mqtt_client, _mosquitto_process

    if _mqtt_client:
        try:
            _mqtt_client.loop_stop()
            _mqtt_client.disconnect()
        except:
            pass
        _mqtt_client = None

    if _mosquitto_process:
        try:
            stop_mosquitto_broker(_mosquitto_process)
        except:
            pass
        _mosquitto_process = None


def _publish_mqtt_message(topic_key: str, message: str, metadata: dict | None = None):
    """Publish a message to MQTT topic"""
    global _mqtt_client

    if not _mqtt_initialized:
        _initialize_mqtt()

    if not _mqtt_client or not MQTT_AVAILABLE:
        return

    try:
        topic = MQTT_TOPICS.get(topic_key, MQTT_TOPICS['info'])

        # Create message payload
        payload = {
            'message': message,
            'timestamp': time.time(),
            'severity': topic_key
        }

        if metadata is not None:
            payload.update(metadata)

        # Publish message
        _mqtt_client.publish(topic, json.dumps(payload))

    except Exception as e:
        logging.getLogger(__name__).warning(f"Failed to publish MQTT message: {e}")


def IncreaseIndent():
    global __IndentLevel
    __IndentLevel += 1


def DecreaseIndent():
    global __IndentLevel
    __IndentLevel -= 1


def ResetIndent():
    global __IndentLevel
    __IndentLevel = 0


stdscr = None

if CURSES:
    import atexit


    def __EndCurses__():
        curses.endwin()


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
                    }  # type: dict[str, int]

    # sys.stdout = logFile

    try:
        stdscr = curses.initscr()
        (maxY, maxX) = stdscr.getmaxyx()
        if maxX == 0 or maxY == 0:
            raise RuntimeError(f"Terminal reported zero dimensions ({maxY}x{maxX}); curses unavailable")
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
    except BaseException as e:
        try:
            curses.endwin()
        except Exception:
            pass
        CURSES = False
        logging.getLogger(__name__).debug("Curses initialization failed, falling back to plain output: %s", e)


def CurseString(topic: str, text: str):
    if CURSES:
        y = 0
        x = 0

        if topic in cursesCoords:
            y = cursesCoords[topic]

        (yMax, xMax) = statusWindow.getmaxyx()  # type: ignore[union-attr]

        outStr = topic + " : " + text
        # Log(outStr)
        statusWindow.addstr(y, x, outStr)  # type: ignore[union-attr]
        statusWindow.clrtoeol()  # type: ignore[union-attr]
        statusWindow.move(yMax - 1, 0)  # type: ignore[union-attr]
        statusWindow.refresh()  # type: ignore[union-attr]
    else:
        output_message = topic + ": " + text
        print(output_message)

        # Also publish status messages to MQTT
        _publish_mqtt_message('status', output_message, {'topic': topic})
        return


def CurseProgress(text: str, Progress: float, Total: float | None = None):
    """If Total is specified we display a percentage, otherwise
       a number"""

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
    # ETASec = 0
    tstruct = None
    ETAString = ""
    fraction = None

    if Total is not None:
        fraction = float(Progress / float(Total))
        if fraction > 0:
            elapsedSec = float(time.time() - ProgressStartTime)  # type: ignore[operator]
            ETASec = (elapsedSec / fraction) * (1.0 - fraction)
            tstruct = time.gmtime(ETASec)
            ETAString = "ETA: " + time.strftime("%H:%M:%S", tstruct)

    # Prepare progress message for MQTT
    progress_info = {
        'progress': Progress,
        'total': Total,
        'fraction': fraction,
        'eta_string': ETAString
    }

    progress_message = text if text is not None else ""
    if fraction is not None:
        progress_message += f" {fraction:0.3g}"
        if ETAString:
            progress_message += " " + ETAString

    # Publish progress to MQTT
    _publish_mqtt_message('progress', progress_message, progress_info)

    if CURSES:
        (yMax, xMax) = statusWindow.getmaxyx()  # type: ignore[union-attr]

        if "Task" in cursesCoords:
            TaskY = cursesCoords["Task"]

        if "Progress" in cursesCoords:
            ProgressY = cursesCoords["Progress"]

        if text is not None:
            # TaskStr = "Task: " + text
            # Log(TaskStr)
            statusWindow.addnstr(TaskY, TaskX, "Task: " + text, console_width)  # type: ignore[union-attr]
            statusWindow.clrtoeol()  # type: ignore[union-attr]

        if Total is not None:
            progress_str = "Progress : %4.2f%%" % (fraction * 100.0)  # type: ignore[operator]
            if tstruct is not None:
                progress_str = progress_str + "        " + ETAString

            # Log(ProgressStr)

            statusWindow.addnstr(ProgressY, ProgressX, progress_str, console_width)  # type: ignore[union-attr]
            statusWindow.clrtoeol()  # type: ignore[union-attr]
            statusWindow.move(yMax - 1, 0)  # type: ignore[union-attr]
            statusWindow.refresh()  # type: ignore[union-attr]
    else:
        output_str = text
        if output_str is None:
            output_str = ""

        if fraction is not None:
            output_str = f'{output_str} {fraction:0.3g}'
            if ETAString is not None:
                output_str += ETAString

        if ECLIPSE:
            print(output_str)
        else:
            # Erase previous output
            padding_needed = console_width - len(output_str)
            if padding_needed < 0:
                padding_needed = 0

            text = ('\b' * console_width) + output_str + (' ' * padding_needed)
            print(text)


def get_calling_func_name() -> str | None:
    """Beware that calling this function is fairly slow."""
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

    mod_name = module.__name__

    return mod_name + "." + func_name


#   stack = traceback.extract_stack()
#   filename, codeline, funcName, text = stack[-3]

#   return funcName

def input_to_string(input_str: Any, tablevel: int = 0) -> str | None:
    """
    Converts an input variable into a string we can print in the log
    :param input_str:
    :param tablevel:
    :return:
    """
    if input_str is None:
        return None

    tabs = '\t' * tablevel

    if isinstance(input_str, str):
        return tabs + input_str

    if isinstance(input_str, (int, float)):
        return tabs + str(input_str)

    if isinstance(input_str, typing.Iterable):
        return os.linesep.join([tabs + input_to_string(obj, tablevel=tablevel + 1) for obj in input_str])  # type: ignore[operator]
    else:
        return tabs + str(input_str)


def Log(text: str | list[Any] | Any | None = None, logger_name: str | None = None):
    output = input_to_string(text)
    if output is None:
        return

    tabs = '  ' * __IndentLevel

    # output = tabs + output
    output.replace('\n', '\n' + tabs)

    # if logger_name is None:
    # logger_name = get_calling_func_name()

    logger = logging.getLogger(logger_name)
    logger.info(output)

    # Publish to MQTT
    _publish_mqtt_message('info', output, {'logger_name': logger_name})

    if CURSES:
        output += os.linesep

        sys.stdout.write(output)
        sys.stdout.flush()

        numChars = len(output)

        (yMax, xMax) = stdscr.getmaxyx()  # type: ignore[union-attr]

        numLines = int(numChars / xMax)
        if numChars % xMax != 0:
            numLines += 1

        logWindow.move(0, 0)  # type: ignore[union-attr]

        for i in range(numLines):
            logWindow.insertln()  # type: ignore[union-attr]

        logWindow.addstr(0, 0, output)  # type: ignore[union-attr]
        logWindow.clrtoeol()  # type: ignore[union-attr]
        logWindow.refresh(0, 0, LogStartY, 0, yMax - 1, xMax)  # type: ignore[union-attr]
    elif ECLIPSE:
        output = output.replace('\b', '')
        print(output)
    else:
        print(output)


_error_console = None  # type: nornir_shared.consolewindow.ConsoleWindow | None


def error(error_message: str | None = None):
    LogErr(error_message, calling_func_name=get_calling_func_name())


def LogErr(error_message: str | None = None, calling_func_name: str | None = None):
    error_output = input_to_string(error_message)
    assert error_output is not None

    if error_output[-1] != '\n':
        error_output += '\n'

    if calling_func_name is None:
        calling_func_name = get_calling_func_name()

    logger = logging.getLogger(calling_func_name)
    logger.error(error_output)

    # Publish to MQTT
    _publish_mqtt_message('error', error_output, {'logger_name': calling_func_name})

    if not ECLIPSE:
        try:
            global _error_console
            import multiprocessing

            # Check if we're in a child process
            is_child_process = multiprocessing.current_process().name != 'MainProcess'

            # Only create a console window in the main process or if one doesn't exist yet
            if _error_console is None:
                # Create a console window with create_window=True only in the main process
                # In child processes, set create_window=False to ensure they connect to the parent's console
                _error_console = nornir_shared.consolewindow.ConsoleWindow(
                    title="Error Console",
                    create_window=not is_child_process  # Only create a window in the main process
                )

            # Send the error message to the console
            _error_console.WriteMessage(error_output)
            logger = logging.getLogger(calling_func_name)
            logger.error(error_output)
        except Exception as e:
            # If there's an error with the console window, log it and continue
            print(f"Error with console window: {e}")
            _error_console = None
            pass
    else:
        logger = logging.getLogger(get_calling_func_name())
        logger.error(error_output)


def PrettyOutputModulePath() -> str:
    try:
        path = os.path.dirname(__file__)
    except:
        path = os.getcwd()

    return os.path.join(path, 'prettyoutput.py')

