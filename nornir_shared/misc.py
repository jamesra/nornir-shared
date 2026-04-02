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
import sys
import time

logging_setup = False
_active_log_session_id: str | None = None
_multiprocess_logging_queue = None
_multiprocess_logging_listener = None
_multiprocess_logging_owner_pid: int | None = None

NORNIR_LOG_ROOT_ENV = 'NORNIR_LOG_ROOT'
NORNIR_LOG_SESSION_ENV = 'NORNIR_LOG_SESSION_ID'


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

    # Automatically shutdown logging when our process ends
    atexit.register(logging.shutdown)


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


def GenNameFromDict(dictObj):
    '''Creates a mangled name unique to the contents of a dictionary.
       Take the first three letters from each entry name, append the value, and build a mangled name'''
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
            ValueStr = str(value[0])
            for e in value[1:-1]:
                ValueStr = 'x' + str(e)
        else:
            ValueStr = str(value)

        outstr = "{0}_{1}{2}".format(outstr, nameMangle, ValueStr)

    return outstr


def ListFromDelimited(value, delimiter=None):
    if delimiter is None:
        delimiter = ','

    ValueList = value
    if isinstance(value, str):
        ValueList = []
        Values = str(value).strip().split(delimiter)
        ValueList = list()
        for Value in Values:
            try:
                floatVal = float(Value)
                try:
                    intVal = int(Value)
                    ValueList.append(intVal)
                except:
                    ValueList.append(floatVal)
            except:
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
    '''Return true if arg is iterable and not a string'''
    return (not hasattr(arg, "strip") and
            hasattr(arg, "__getitem__") or
            hasattr(arg, "__iter__"))


if __name__ == '__main__':
    pass
