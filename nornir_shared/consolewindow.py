import atexit
import json
import time
import threading
from typing import Any, Optional

# MQTT imports
try:
    import paho.mqtt.client as mqtt
    from paho.mqtt.properties import Properties
    from paho.mqtt.reasoncodes import ReasonCode
    from nornir_shared.mqtt_config import MQTT_HOST, MQTT_PORT, MQTT_KEEPALIVE, MQTT_TOPICS

    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False

import nornir_shared.console_constants


class ConsoleWindow(object):
    """
    Creates a second console window which displays text output sent to this Console object via MQTT
    """

    def __init__(self, title=None, auto_start=True, *args, **kwargs):
        """
        :param str title: Title to place on new console
        :param bool auto_start: Whether to automatically start the console subscriber
        """

        super(ConsoleWindow, self).__init__(*args, **kwargs)
        self.title = '' if title is None else title.strip()
        self._mqtt_client = None
        self._subscribed_topics = []
        self._running = False
        self._message_callback = None

        if auto_start and MQTT_AVAILABLE:
            self._initialize_mqtt_subscriber()

    def _initialize_mqtt_subscriber(self):
        """Initialize MQTT client for subscribing to console messages"""
        if not MQTT_AVAILABLE:
            print("MQTT not available, falling back to print statements")
            return

        try:
            # Create MQTT client
            self._mqtt_client = mqtt.Client()

            # Set up callbacks
            def on_connectclient(client: mqtt.Client,
                                 userdata: Any,
                                 connect_flags: mqtt.ConnectFlags,
                                 reason_code: ReasonCode,
                                 properties: Properties | None = None):
                if reason_code == 0:
                    print(f"Console '{self.title}' connected to MQTT broker")
                    # Subscribe to all log topics
                    for topic in MQTT_TOPICS.values():
                        client.subscribe(topic)
                        print(f"Subscribed to {topic}")
                else:
                    print(f"Failed to connect console to MQTT broker: {reason_code}")

            def on_message(client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage):
                try:
                    payload = json.loads(msg.payload.decode())
                    message = payload.get('message', '')
                    severity = payload.get('severity', 'info')
                    timestamp = payload.get('timestamp', time.time())

                    # Format message with timestamp and severity
                    formatted_msg = f"[{time.strftime('%H:%M:%S', time.localtime(timestamp))}] [{severity.upper()}] {message}"

                    if self._message_callback:
                        self._message_callback(formatted_msg)
                    else:
                        # Default behavior - print to console
                        print(formatted_msg.rstrip())

                except Exception as e:
                    print(f"Error processing MQTT message: {e}")

            def on_disconnect(client: mqtt.Client,
                              userdata: Any,
                              disconnect_flags: mqtt.DisconnectFlags,
                              reason_code: ReasonCode,
                              properties: Properties | None = None):
                print(f"Console '{self.title}' disconnected from MQTT broker")

            self._mqtt_client.on_connect = on_connectclient
            self._mqtt_client.on_message = on_message
            self._mqtt_client.on_disconnect = on_disconnect

            # Connect to broker
            self._mqtt_client.connect(MQTT_HOST, MQTT_PORT, MQTT_KEEPALIVE)
            self._mqtt_client.loop_start()
            self._running = True

            # Register cleanup function
            atexit.register(self.Close)

        except Exception as e:
            print(f"Failed to initialize MQTT console subscriber: {e}")

    def set_message_callback(self, callback):
        """Set a callback function to handle received messages"""
        self._message_callback = callback

    def WriteMessage(self, text):
        """
        For compatibility with existing code.
        This method is now redundant since messages are published directly from prettyoutput.
        """
        # If MQTT is not available, fallback to printing
        if not MQTT_AVAILABLE or not self._running:
            print(text.rstrip())

    def Close(self):
        """Close the MQTT connection"""
        if self._mqtt_client and self._running:
            try:
                self._mqtt_client.loop_stop()
                self._mqtt_client.disconnect()
                self._running = False
            except:
                pass


class CursesConsoleWindow(ConsoleWindow):
    """Console window that can work with curses interface"""

    def __init__(self, title=None, auto_start=True, *args, **kwargs):
        super(CursesConsoleWindow, self).__init__(title=title, auto_start=auto_start, *args, **kwargs)

        # Set up curses-specific message handling if needed
        self._setup_curses_handling()

    def _setup_curses_handling(self):
        """Setup curses-specific message handling"""

        def curses_message_handler(message):
            # Extract topic and text for curses display
            # Format: [timestamp] [severity] message
            parts = message.split('] ', 2)
            if len(parts) >= 3:
                topic = parts[1][1:]  # Remove the leading '['
                text = parts[2]
            else:
                topic = "Log"
                text = message

            # Print to console (curses handling would be in the console module)
            print(f"{topic}: {text}")

        self.set_message_callback(curses_message_handler)

