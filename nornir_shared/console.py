"""
Created on Sep 3, 2014

@author: u0490822

MQTT-based console for nornir_shared
"""
import argparse
import os
import sys
import time
import traceback
import json
import signal

# MQTT imports
try:
    import paho.mqtt.enums as mqtt_enum
    import paho.mqtt.client as mqtt
    from paho.mqtt.properties import Properties
    from paho.mqtt.reasoncodes import ReasonCode
    from nornir_shared.mqtt_config import MQTT_HOST, MQTT_PORT, MQTT_KEEPALIVE, MQTT_TOPICS

    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False

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
_mqtt_client = None
_console_running = False

try:
    import pydevd  # type: ignore[reportMissingImports]

    pydevd_available = True
except ImportError:
    pass


def CreateParser() -> argparse.ArgumentParser:
    argparser = argparse.ArgumentParser()

    argparser.add_argument('-nocurses', '-c',
                           required=False,
                           default=False,
                           action='store_true',
                           help='Indicates the curses library should not be used for the console window.  It is used by default if available.',
                           dest='nocurses')

    argparser.add_argument('-debug',
                           required=False,
                           default=False,
                           action='store_true',
                           help='Create text files for console with received lines and exception information',
                           dest='debug')

    argparser.add_argument('-title',
                           required=False,
                           default='MQTT Console',
                           action='store',
                           type=str,
                           help='Title of the console window',
                           dest='title')

    argparser.add_argument('-host',
                           required=False,
                           default=MQTT_HOST,
                           help=f'MQTT broker host (default: {MQTT_HOST})',
                           dest='HOST')

    argparser.add_argument('-port',
                           required=False,
                           default=MQTT_PORT,
                           type=int,
                           help=f'MQTT broker port (default: {MQTT_PORT})',
                           dest='PORT')

    return argparser


def ConsoleModulePath() -> str:
    try:
        path = os.path.dirname(__file__)
    except:
        path = os.getcwd()

    return os.path.join(path, 'console.py')


def CreateDebugInfoFile(filename: str | None = None):
    if filename is None:
        filename = 'MQTT_Console_Debug_Output.txt'

    return open(os.path.join(os.getcwd(), filename), mode='w')


def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown"""

    def signal_handler(signum, frame):
        global _console_running
        print("\nShutting down MQTT console...")
        _console_running = False
        if _mqtt_client:
            _mqtt_client.loop_stop()
            _mqtt_client.disconnect()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)


def MQTTConsoleLoop(HOST: str, PORT: int, title: str, handler_func):
    """
    Main MQTT console loop that subscribes to topics and handles messages
    :param HOST: MQTT broker host
    :param PORT: MQTT broker port  
    :param title: Console window title
    :param handler_func: Function to pass received data to
    """
    global _mqtt_client, _console_running, _DEBUG

    if not MQTT_AVAILABLE:
        print("MQTT not available. Cannot start console.")
        return

    debug_file = None
    try:
        if _DEBUG:
            debug_file = CreateDebugInfoFile(f'{title}_mqtt.log')
            debug_file.write(f'Title={title}\n')
            debug_file.write(f'HOST={HOST}\n')
            debug_file.write(f'PORT={PORT}\n')
            debug_file.write(f'Func={str(handler_func)}\n')
            debug_file.write(f'MQTT_Available={MQTT_AVAILABLE}\n')

        # Create MQTT client
        _mqtt_client = mqtt.Client(callback_api_version=mqtt_enum.CallbackAPIVersion.VERSION2)
        _console_running = True

        def on_connect(client: mqtt.Client,
                       userdata: object,
                       connect_flags: mqtt.ConnectFlags,
                       reason_code: ReasonCode,
                       properties: Properties | None = None):
            if reason_code == 0:  # SUCCESS
                print(f"MQTT Console '{title}' connected to broker at {HOST}:{PORT}")
                # Subscribe to all log topics
                for topic_name, topic in MQTT_TOPICS.items():
                    client.subscribe(topic)
                    print(f"Subscribed to {topic} ({topic_name})")
                if _DEBUG and debug_file:
                    debug_file.write(f"Connected and subscribed to topics\n")
            else:
                print(f"Failed to connect to MQTT broker: {reason_code}")
                global _console_running
                _console_running = False

        def on_message(client: mqtt.Client, userdata: object, msg: mqtt.MQTTMessage):
            try:
                payload = json.loads(msg.payload.decode())
                message = payload.get('message', '')
                severity = payload.get('severity', 'info')
                timestamp = payload.get('timestamp', time.time())

                if _DEBUG and debug_file:
                    debug_file.write(f"Received: {msg.topic} - {payload}\n")
                    debug_file.flush()

                # Format the message for the handler
                formatted_msg = f"{severity.upper()}:{message}"
                handler_func(formatted_msg)

            except Exception as e:
                error_msg = f"Error processing MQTT message: {e}"
                print(error_msg)
                if _DEBUG and debug_file:
                    debug_file.write(f"{error_msg}\n")

        def on_disconnect(client: mqtt.Client,
                          userdata: object,
                          disconnect_flags: mqtt.DisconnectFlags,
                          reason_code: ReasonCode,
                          properties: Properties | None = None):
            print(f"MQTT Console '{title}' disconnected from broker")
            if _DEBUG and debug_file:
                debug_file.write("Disconnected from broker\n")

        # Setup callbacks
        _mqtt_client.on_connect = on_connect
        _mqtt_client.on_message = on_message
        _mqtt_client.on_disconnect = on_disconnect

        # Connect to broker
        try:
            _mqtt_client.connect(HOST, PORT, MQTT_KEEPALIVE)
            _mqtt_client.loop_start()

            print(f"Starting MQTT console '{title}' - waiting for messages...")
            print("Press Ctrl+C to exit")

            # Keep the console running
            while _console_running:
                time.sleep(1)

        except Exception as e:
            print(f"Failed to connect to MQTT broker: {e}")
            _console_running = False

    except Exception as e:
        if debug_file is None:
            debug_file = CreateDebugInfoFile()

        error_msg = f"Console error: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        if debug_file:
            debug_file.write(error_msg + '\n')
    finally:
        if _mqtt_client:
            _mqtt_client.loop_stop()
            _mqtt_client.disconnect()
        if debug_file is not None:
            debug_file.close()


def NoCursesHandler(data_str: str):
    """
    Sends output to the console window. Input strings should contain "SEVERITY:TEXT" using the colon as a delimiter
    :param str data_str: Data received over MQTT
    """
    (severity, colon, text) = data_str.partition(':')
    timestamp = time.strftime('%H:%M:%S')
    formatted_output = f"[{timestamp}] [{severity}] {text}"
    print(formatted_output)


def CursesHandler(data_str: str):
    """
    Sends output to the curses window. Input strings should contain "SEVERITY:TEXT" using the colon as a delimiter
    :param str data_str: Data received over MQTT
    """
    global curses_available

    if not curses_available:
        NoCursesHandler(data_str)
    else:
        (severity, colon, text) = data_str.partition(':')
        # Map severity to topic for curses display
        topic = severity.lower().capitalize()
        nornir_shared.curses_console.CurseString(topic, text)


if __name__ == '__main__':

    try:
        parser = CreateParser()
        args = parser.parse_args()

        _DEBUG = args.debug

        print(f'MQTT Console Configuration:')
        print(f'Title: {args.title}')
        print(f'MQTT Host: {args.HOST}')
        print(f'MQTT Port: {args.PORT}')
        print(f'Use Curses: {not args.nocurses}')
        print(f'Debug: {_DEBUG}')
        print(f'pydevd_available: {pydevd_available}')
        print(f'MQTT_available: {MQTT_AVAILABLE}')
        print('')

        if _DEBUG:
            if not pydevd_available:
                print("Debug flag set but pydevd is not available.")
            else:
                pydevd.settrace(suspend=False)

        # Setup signal handlers for graceful shutdown
        setup_signal_handlers()

        if curses_available and not args.nocurses:
            try:
                success = nornir_shared.curses_console.InitCurses()
                assert success, "Could not InitCurses"
            except Exception as e:
                success = False
                sys.stdout.write(traceback.format_exc())
                with CreateDebugInfoFile('Console_Curses_Error.txt') as hFile:
                    hFile.write(traceback.format_exc())

            if success:
                MQTTConsoleLoop(HOST=args.HOST, PORT=args.PORT, title=args.title, handler_func=CursesHandler)
            else:
                MQTTConsoleLoop(HOST=args.HOST, PORT=args.PORT, title=args.title, handler_func=NoCursesHandler)
        else:
            MQTTConsoleLoop(HOST=args.HOST, PORT=args.PORT, title=args.title, handler_func=NoCursesHandler)

    except KeyboardInterrupt:
        print("\nConsole interrupted by user")
    except Exception as e:
        sys.stdout.write(f"Console error: {traceback.format_exc()}")
    finally:
        print("Console shutdown complete")

