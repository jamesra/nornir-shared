'''
Created on Jul 11, 2012

@author: Jamesan

Functions that are broadly used in Python programs but don't have a specific category
'''
import atexit
import logging
import logging.handlers
import multiprocessing
import os
import shlex
import subprocess
import sys
import time
from collections.abc import Sequence

logging_setup = False
_active_log_session_id: str | None = None
_multiprocess_logging_queue = None
_multiprocess_logging_listener = None
_multiprocess_logging_owner_pid: int | None = None

NORNIR_LOG_ROOT_ENV = 'NORNIR_LOG_ROOT'
NORNIR_LOG_SESSION_ENV = 'NORNIR_LOG_SESSION_ID'

MQTT_LOG_HANDLER_NAME = 'nornir_mqtt_log_handler'


class MQTTLogHandler(logging.Handler):
    """Forward warning/error/debug logging records to run-scoped MQTT topics.

    Info records are published by :func:`nornir_shared.prettyoutput.Log`. Records
    already marked with ``mqtt_published=True`` (set via ``extra=`` from
    prettyoutput) are skipped to avoid duplicate MQTT publishes.
    """

    def __init__(self, level: int = logging.DEBUG) -> None:
        super().__init__(level=level)
        self.name = MQTT_LOG_HANDLER_NAME

    def emit(self, record: logging.LogRecord) -> None:
        """Publish a single logging record to the matching MQTT log topic."""
        if getattr(record, 'mqtt_published', False):
            return

        topic_key: str | None = None
        if record.levelno >= logging.ERROR:
            topic_key = 'error'
        elif record.levelno >= logging.WARNING:
            topic_key = 'warning'
        elif record.levelno >= logging.DEBUG and record.levelno < logging.INFO:
            topic_key = 'debug'
        else:
            return

        try:
            from nornir_shared import prettyoutput
            message = self.format(record) if self.formatter else record.getMessage()
            prettyoutput._publish_mqtt_message(
                topic_key,
                message,
                {'logger_name': record.name},
            )
        except Exception:
            self.handleError(record)


def _ensure_mqtt_log_handler(handlers: list[logging.Handler] | None = None) -> MQTTLogHandler:
    """Return an MQTTLogHandler, adding it to *handlers* when provided and missing."""
    if handlers is not None:
        for handler in handlers:
            if getattr(handler, 'name', None) == MQTT_LOG_HANDLER_NAME:
                return handler  # type: ignore[return-value]

    mqtt_handler = MQTTLogHandler()
    mqtt_handler.setFormatter(logging.Formatter('%(levelname)s - %(name)s - %(message)s'))
    if handlers is not None:
        handlers.append(mqtt_handler)
    return mqtt_handler


def _resolve_unified_log_root() -> str | None:
    env_value = os.environ.get(NORNIR_LOG_ROOT_ENV)
    if env_value is None:
        return None

    stripped_value = env_value.strip()
    if len(stripped_value) == 0:
        return None

    return os.path.abspath(stripped_value)


def _get_or_create_session_id() -> str:
    global _active_log_session_id
    if _active_log_session_id is not None:
        return _active_log_session_id

    session_id = os.environ.get(NORNIR_LOG_SESSION_ENV)
    if session_id is not None:
        session_id = session_id.strip()

    if not session_id:
        session_id = time.strftime('%Y%m%d-%H%M%S', time.localtime())
        os.environ[NORNIR_LOG_SESSION_ENV] = session_id

    _active_log_session_id = session_id
    return _active_log_session_id


def _session_date_folder_name(session_id: str) -> str:
    if len(session_id) >= 8 and session_id[:8].isdigit():
        return f'{session_id[:4]}-{session_id[4:6]}-{session_id[6:8]}'

    return time.strftime('%Y-%m-%d', time.localtime())


def GetUnifiedSessionPaths() -> tuple[str, str, str] | None:
    """Returns (log_dir, session_log_path, error_log_path) for shared session logs."""
    log_root = _resolve_unified_log_root()
    if log_root is None:
        return None

    session_id = _get_or_create_session_id()
    date_folder = _session_date_folder_name(session_id)
    log_dir = os.path.join(log_root, date_folder)
    session_log_path = os.path.join(log_dir, f'nornir-session-{session_id}.log')
    error_log_path = os.path.join(log_dir, f'nornir-session-{session_id}-errors.log')
    return (log_dir, session_log_path, error_log_path)


def _directory_is_writable(path: str) -> bool:
    """Return True if log files can be created under ``path``."""
    try:
        os.makedirs(path, exist_ok=True)
        probe_path = os.path.join(path, f'.nornir-write-probe-{os.getpid()}')
        with open(probe_path, 'w', encoding='utf-8') as probe_file:
            probe_file.write('')
        os.remove(probe_path)
        return True
    except OSError:
        return False


def GetUnifiedConsoleLogPath() -> str | None:
    """Returns a unified console tee path for the active session, if configured."""
    session_paths = GetUnifiedSessionPaths()
    if session_paths is None:
        return None

    log_dir, _, _ = session_paths
    session_id = _get_or_create_session_id()
    return os.path.join(log_dir, f'nornir-console-{session_id}.log')


def _reset_root_logger(level=None):
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    if level is not None:
        root_logger.setLevel(level)


def _build_standard_handlers(level) -> list[logging.Handler]:
    formatter = logging.Formatter('%(levelname)s - %(name)s - %(message)s')
    handlers: list[logging.Handler] = []

    session_paths = GetUnifiedSessionPaths()
    if session_paths is not None:
        log_dir, log_file_name, errlog_file_name = session_paths
        os.makedirs(log_dir, exist_ok=True)

        info_handler = logging.FileHandler(log_file_name)
        info_handler.setLevel(level)
        info_handler.setFormatter(formatter)
        handlers.append(info_handler)

        error_handler = logging.FileHandler(errlog_file_name)
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        handlers.append(error_handler)

    if 'ECLIPSE' not in os.environ:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(level)
        stream_handler.setFormatter(formatter)
        handlers.append(stream_handler)

    return handlers


def StartMultiprocessLoggingListener(level=None):
    """Create and start a queue listener for multiprocess-safe logging."""
    global _multiprocess_logging_queue
    global _multiprocess_logging_listener
    global _multiprocess_logging_owner_pid

    if level is None:
        level = logging.INFO

    session_paths = GetUnifiedSessionPaths()
    if session_paths is None:
        logging.warning("Multiprocess file logging disabled because %s is not set", NORNIR_LOG_ROOT_ENV)
        return None

    if _multiprocess_logging_listener is not None and _multiprocess_logging_owner_pid == os.getpid():
        return _multiprocess_logging_queue

    handlers = _build_standard_handlers(level)
    if len(handlers) == 0:
        return None

    _ensure_mqtt_log_handler(handlers)

    _multiprocess_logging_queue = multiprocessing.Queue(-1)
    _multiprocess_logging_listener = logging.handlers.QueueListener(_multiprocess_logging_queue, *handlers)
    _multiprocess_logging_listener.start()
    _multiprocess_logging_owner_pid = os.getpid()
    atexit.register(StopMultiprocessLoggingListener)
    return _multiprocess_logging_queue


def StopMultiprocessLoggingListener():
    """Stop the active queue listener and close associated resources."""
    global _multiprocess_logging_queue
    global _multiprocess_logging_listener
    global _multiprocess_logging_owner_pid

    if _multiprocess_logging_listener is not None:
        try:
            _multiprocess_logging_listener.stop()
        except Exception:
            pass
        _multiprocess_logging_listener = None

    if _multiprocess_logging_queue is not None:
        try:
            _multiprocess_logging_queue.close()
        except Exception:
            pass
        _multiprocess_logging_queue = None

    _multiprocess_logging_owner_pid = None


def _suppress_noisy_libraries() -> None:
    """Raise the log level of chatty third-party libraries to WARNING.

    Called from both SetupLogging and ConfigureWorkerQueueLogging so that the
    suppression is applied in every process — parent, forked worker, and
    spawned/forkserver worker alike.
    """
    logging.getLogger('PIL').setLevel(logging.WARNING)
    # findfont score() dumps one DEBUG line per installed font when the root
    # logger is DEBUG (nornir-build -debug). That is not Nornir diagnostics.
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    logging.getLogger('matplotlib.font_manager').setLevel(logging.WARNING)


def ConfigureWorkerQueueLogging(log_queue=None, level=None):
    """Configure this process to emit logs via QueueHandler."""
    global logging_setup
    global _multiprocess_logging_queue

    if level is None:
        level = logging.INFO

    queue_to_use = log_queue if log_queue is not None else _multiprocess_logging_queue
    if queue_to_use is None:
        return False

    _multiprocess_logging_queue = queue_to_use
    _reset_root_logger(level)
    root_logger = logging.getLogger()
    root_logger.addHandler(logging.handlers.QueueHandler(queue_to_use))
    root_logger.setLevel(level)
    _suppress_noisy_libraries()
    logging_setup = True
    return True


def RunWithProfiler(functionStr, outputpath=None):
    import cProfile
    import pstats
    import sys

    if outputpath is None:
        outputpath = "C:\\Temp"

    ProfilePath = os.path.join(outputpath, 'BuildProfile.pr')

    ProfileDir = os.path.dirname(ProfilePath)
    os.makedirs(ProfileDir, exist_ok=True)

    logger = logging.getLogger(__name__ + '.RunWithProfiler')

    logger.info("Profiling: " + functionStr)

    try:
        cProfile.run(functionStr, ProfilePath)
    finally:
        if not os.path.exists(ProfilePath):
            logger.error("No profile file found" + ProfilePath)
            sys.exit()

        pr = pstats.Stats(ProfilePath)
        if pr is not None:
            pr.sort_stats('time')
            print(str(pr.print_stats(.1)))
            logger.info(str(pr.print_stats(0.1)))

    pr.print_callers(.1)


def format_startup_command_line(argv: Sequence[str] | None = None) -> str:
    """Return a shell-quoted command line for the current process.

    Includes ``sys.executable`` when *argv* does not already start with the
    interpreter path, then the remaining arguments.
    """
    parts = [str(part) for part in (sys.argv if argv is None else argv)]
    executable = sys.executable
    if not parts:
        parts = [executable]
    else:
        try:
            same_executable = os.path.normcase(os.path.abspath(parts[0])) == os.path.normcase(
                os.path.abspath(executable))
        except (OSError, TypeError, ValueError):
            same_executable = False
        if not same_executable:
            parts = [executable, *parts]
    if os.name == 'nt':
        return subprocess.list2cmdline(parts)
    return shlex.join(parts)


def _log_startup_command_line(configured_level: int) -> None:
    """Record the process command line after logging handlers are attached.

    Emits INFO when that level is enabled; otherwise uses *configured_level* so
    WARNING-only setups such as Pyre still persist the line.
    """
    emit_level = logging.INFO if configured_level <= logging.INFO else configured_level
    logging.getLogger(__name__).log(
        emit_level, "Command line: %s", format_startup_command_line())


def SetupLogging(LogToFile: bool = False, OutputPath: str | None = None, Level=None):
    '''
    :param bool LogToFile: True if logs should be saved to a file.  Automatically set to true if OutputPath is not None
    :param str OutputPath: Path to directory to use to save log files.
    :param Level: Level of messages to write to log
    '''
    global logging_setup
    if logging_setup:
        return

    logging_setup = True

    if Level is None:
        Level = logging.INFO

    _suppress_noisy_libraries()

    if ConfigureWorkerQueueLogging(level=Level):
        atexit.register(logging.shutdown)
        return

    formatter = logging.Formatter('%(levelname)s - %(name)s - %(message)s')

    unified_session_paths = None
    if OutputPath is None:
        unified_session_paths = GetUnifiedSessionPaths()
        if unified_session_paths is not None:
            LogToFile = True
        elif not LogToFile:
            # Fallback when unified log root is not configured: write to CWD.
            LogToFile = True

    if OutputPath is not None:
        LogToFile = True

    if LogToFile:
        LogPath = None
        logFileName = None
        errlogFileName = None

        if unified_session_paths is not None:
            LogPath, logFileName, errlogFileName = unified_session_paths
        else:
            # Figure out the loggging directory if it is not specified
            if OutputPath is not None and os.path.isabs(OutputPath):
                LogPath = OutputPath
            else:
                BaseLoggingDir = None
                if 'TESTOUTPUTPATH' in os.environ:
                    BaseLoggingDir = os.environ['TESTOUTPUTPATH']
                else:
                    BaseLoggingDir = os.getcwd()

                if OutputPath is not None:
                    LogPath = os.path.join(BaseLoggingDir, OutputPath)
                else:
                    LogPath = BaseLoggingDir

        if LogPath is not None and not _directory_is_writable(LogPath):
            rejected_path = LogPath
            fallback_paths = GetUnifiedSessionPaths()
            if fallback_paths is not None:
                LogPath, logFileName, errlogFileName = fallback_paths
            else:
                LogPath = os.environ.get('TESTOUTPUTPATH', os.getcwd())
                logFileName = None
                errlogFileName = None
            print(f"Log path not writable ({rejected_path}); using {LogPath}")

        if LogPath is not None:
            try:
                os.makedirs(LogPath, exist_ok=True)
            except:
                print("Could not create logging output directory: " + LogPath)
                pass

            if logFileName is None:
                logFileName = time.strftime('log-%M.%d.%y_%H.%M.txt', time.localtime())
                logFileName = os.path.join(LogPath, logFileName)

            if errlogFileName is None:
                errlogFileName = time.strftime('log-%M.%d.%y_%H.%M-Errors.txt', time.localtime())
                errlogFileName = os.path.join(LogPath, errlogFileName)

            logging.basicConfig(filename=logFileName, level=Level, format='%(levelname)s - %(name)s - %(message)s')

            eh = logging.FileHandler(errlogFileName)
            eh.setLevel(logging.ERROR)
            eh.setFormatter(formatter)
            logger = logging.getLogger()
            logger.addHandler(eh)
    else:
        logging.basicConfig(level=Level, format='%(levelname)s - %(name)s - %(message)s')

    if not 'ECLIPSE' in os.environ:
        ch = logging.StreamHandler()
        ch.setLevel(Level)
        ch.setFormatter(formatter)

        logger = logging.getLogger()
        logger.addHandler(ch)

    # Central MQTT forwarding for warning/error/debug (parent process only).
    root_logger = logging.getLogger()
    if not any(getattr(h, 'name', None) == MQTT_LOG_HANDLER_NAME for h in root_logger.handlers):
        root_logger.addHandler(_ensure_mqtt_log_handler())

    # Automatically shutdown logging when our process ends
    atexit.register(logging.shutdown)
    _log_startup_command_line(Level)


def lowpriority():
    """ Set the priority of the process to below-normal.
        Copied from: http://stackoverflow.com/questions/1023038/change-process-priority-in-python-cross-platform"""

    try:
        sys.getwindowsversion()
    except:
        isWindows = False
    else:
        isWindows = True

    try:
        if isWindows:
            # Based on:
            #   "Recipe 496767: Set Process Priority In Windows" on ActiveState
            #   http://code.activestate.com/recipes/496767/
            import win32api  # type: ignore[reportMissingModuleSource]
            import win32process  # type: ignore[reportMissingModuleSource]
            import win32con  # type: ignore[reportMissingModuleSource]
            pid = os.getpid()
            handle = win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, True, pid)
            win32process.SetPriorityClass(handle, win32process.BELOW_NORMAL_PRIORITY_CLASS)
            win32api.CloseHandle(handle)
        else:
            # Unix and Mac should have a nice function
            getattr(os, 'nice', lambda _: None)(1)  # type: ignore[attr-defined]
    except:
        logger = logging.getLogger(__name__ + '.lowpriority')
        if not logger is None:
            logger.warning("Could not lower process priority")
            if isWindows:
                logger.warning("Are you missing Win32 extensions for python? http://sourceforge.net/projects/pywin32/")
        pass


def enum(*sequential, **named):
    '''Generates a dictionary of names to number values used as an enumeration'''
    enums = dict(zip(sequential, range(len(sequential))), **named)
    return type('Enum', (), enums)


def ArgumentsFromDict(dictObj):
    '''Generates an argument string for a command line program from a dictionary
    Takes a dictionary and returns a string with '-' prepended to the entry name, a space, and the entry string verbatim'''

    outstr = " "

    for entry in dictObj.items():
        assert (isinstance(entry[0], str))
        outstr = "{0} -{1} {2} ".format(outstr, entry[0], str(entry[1]))
        # outstr = outstr + " -" + entry[0] + " " + str(entry[1]) + " "

    return outstr


def GenNameFromDict(dictObj: dict) -> str:
    """Create a mangled name unique to the contents of a dictionary.

    Uses the first three letters of each key plus a string form of the value.
    List values are joined with ``x`` (e.g. ``[1, 2, 3]`` → ``1x2x3``).
    """
    outstr = ""

    sorted_keys = sorted(dictObj.keys())

    for key in sorted_keys:
        value = dictObj[key]
        assert (isinstance(key, str))
        nameMangle = key
        if len(nameMangle) > 3:
            nameMangle = nameMangle[0:3]

        ValueStr = ""
        if value is None:
            ValueStr = "None"
        elif isinstance(value, list):
            # Join all elements; previous code used value[1:-1] and overwrote
            # ValueStr each iteration, dropping the first/last entries.
            ValueStr = 'x'.join(str(e) for e in value)
        else:
            ValueStr = str(value)

        outstr = "{0}_{1}{2}".format(outstr, nameMangle, ValueStr)

    return outstr


def ListFromDelimited(value, delimiter: str | None = None) -> list:
    """Split a delimited string into ints/floats/strings, or wrap a scalar in a list."""
    if delimiter is None:
        delimiter = ','

    ValueList = value
    if isinstance(value, str):
        Values = str(value).strip().split(delimiter)
        ValueList = list()
        for Value in Values:
            try:
                floatVal = float(Value)
                try:
                    intVal = int(Value)
                    ValueList.append(intVal)
                except ValueError:
                    ValueList.append(floatVal)
            except ValueError:
                if len(Value) > 0:
                    ValueList.append(Value)

    elif not isinstance(value, list):
        ValueList = [value]

    return ValueList


def SortedListFromDelimited(value, delimiter=None):
    ValueList = ListFromDelimited(value, delimiter)
    ValueList.sort()
    return ValueList


def ListFromAttribute(attrib):
    return ListFromDelimited(attrib, delimiter=',')


def IsSequence(arg):
    '''Return true if arg is iterable and not a string or bytes.'''
    return not isinstance(arg, (str, bytes)) and hasattr(arg, "__iter__")


if __name__ == '__main__':
    pass
