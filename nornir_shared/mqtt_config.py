"""
MQTT configuration and mosquitto broker management for nornir_shared
"""
import logging
import os
import socket
import subprocess
import sys
import tempfile
import time
from typing import Optional

# MQTT Configuration
# Clients must connect to a concrete address; never use 0.0.0.0.
MQTT_CONNECT_HOST = os.environ.get("NORNIR_MQTT_HOST", "127.0.0.1")
# Broker bind address (localhost-only by default).
MQTT_BIND_HOST = os.environ.get("NORNIR_MQTT_BIND", "127.0.0.1")
MQTT_PORT = int(os.environ.get("NORNIR_MQTT_PORT", "1883"))
MQTT_KEEPALIVE = 60

# Backward-compatible alias used by subscribers and CLI defaults.
MQTT_HOST = MQTT_CONNECT_HOST

# MQTT Topics based on log severity
MQTT_TOPICS = {
    'info': 'nornir/log/info',
    'error': 'nornir/log/error',
    'warning': 'nornir/log/warning',
    'debug': 'nornir/log/debug',
    'progress': 'nornir/log/progress',
    'status': 'nornir/log/status'
}


def is_port_in_use(host: str, port: int) -> bool:
    """Return True when the given host/port is already bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True


def create_mosquitto_config(bind_host: str | None = None, port: int | None = None) -> str:
    """Create a basic mosquitto configuration file for localhost-only access."""
    listener_host = MQTT_BIND_HOST if bind_host is None else bind_host
    listener_port = MQTT_PORT if port is None else port
    config_content = f"""
# Mosquitto configuration for nornir_shared
# Only accepts connections from {listener_host}, no authentication

listener {listener_port} {listener_host}

allow_anonymous true

# Log settings
log_dest stdout
log_type error
log_type warning
log_type notice
log_type information

# Disable persistence to avoid file system issues
persistence false

# Disable websockets
websockets_log_level 0
"""

    # Create temporary config file
    config_fd, config_path = tempfile.mkstemp(suffix='.conf', prefix='mosquitto_nornir_')
    try:
        with os.fdopen(config_fd, 'w') as f:
            f.write(config_content)
        return config_path
    except Exception:
        os.close(config_fd)
        raise


def _resolve_mosquitto_executable() -> str | None:
    """Return the mosquitto executable path when available on this platform."""
    if not sys.platform.startswith('win'):
        return 'mosquitto'

    possible_paths = [
        'mosquitto',
        'C:/Program Files/mosquitto/mosquitto.exe',
        'C:/Program Files (x86)/mosquitto/mosquitto.exe'
    ]

    for path in possible_paths:
        try:
            subprocess.run([path, '--help'], capture_output=True, timeout=5, check=False)
            return path
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

    return None


def start_mosquitto_broker() -> Optional[subprocess.Popen]:
    """
    Start mosquitto broker if it is not already running.

    Returns the subprocess.Popen object if this call started the broker, or None
    when a broker is already listening or startup failed.
    """
    logger = logging.getLogger(__name__)
    logger.debug(
        "start_mosquitto_broker bind=%s connect=%s port=%s platform=%s",
        MQTT_BIND_HOST,
        MQTT_CONNECT_HOST,
        MQTT_PORT,
        sys.platform,
    )

    if is_port_in_use(MQTT_BIND_HOST, MQTT_PORT):
        logger.info("MQTT broker already running on %s:%s", MQTT_BIND_HOST, MQTT_PORT)
        return None

    config_path: str | None = None
    process: subprocess.Popen | None = None

    try:
        config_path = create_mosquitto_config()
        mosquitto_path = _resolve_mosquitto_executable()
        if mosquitto_path is None:
            logger.warning("mosquitto executable not found. Please install mosquitto or ensure it is in PATH")
            return None

        process = subprocess.Popen(
            [mosquitto_path, '-c', config_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform.startswith('win') else 0,
        )

        # Give the broker a moment to bind the listener.
        time.sleep(2)

        if process.poll() is None and is_port_in_use(MQTT_BIND_HOST, MQTT_PORT):
            logger.info("Successfully started mosquitto broker on %s:%s", MQTT_BIND_HOST, MQTT_PORT)
            return process

        stderr = ""
        if process.stderr is not None:
            stderr = process.stderr.read().decode(errors="replace").strip()
        logger.info("Failed to start mosquitto broker%s", f": {stderr}" if stderr else "")
        try:
            process.terminate()
        except Exception:
            pass
        return None

    except FileNotFoundError:
        logger.warning("mosquitto executable not found. Please install mosquitto or ensure it is in PATH")
        return None
    except Exception as e:
        logger.error("Error starting mosquitto: %s", e)
        if process is not None:
            try:
                process.terminate()
            except Exception:
                pass
        return None
    finally:
        if config_path is not None:
            try:
                os.remove(config_path)
            except OSError:
                pass


def stop_mosquitto_broker(process: subprocess.Popen):
    """Stop the mosquitto broker process."""
    if process and process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def __main__():
    """Main function to test the mosquitto broker."""
    start_mosquitto_broker()
