"""
MQTT configuration and mosquitto broker management for nornir_shared
"""
import os
import subprocess
import socket
import time
import tempfile
import sys
from typing import Optional
import logging


# MQTT Configuration
MQTT_HOST = "localhost"
MQTT_PORT = 1883
MQTT_KEEPALIVE = 60

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
    """Check if a port is already in use"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True


def create_mosquitto_config() -> str:
    """Create a basic mosquitto configuration file for localhost-only access"""
    config_content = f"""
# Mosquitto configuration for nornir_shared
# Only accepts connections from localhost, no authentication

listener {MQTT_PORT}
bind_address {MQTT_HOST}

# Disable authentication 
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
    except:
        os.close(config_fd)
        raise


def start_mosquitto_broker() -> Optional[subprocess.Popen]:
    """
    Start mosquitto broker if it's not already running
    Returns the subprocess.Popen object if started, None if already running
    """
    logger = logging.getLogger(__name__)
    
    # Check if mosquitto is already running on our port
    if is_port_in_use(MQTT_HOST, MQTT_PORT):
        logger.info(f"MQTT broker already running on {MQTT_HOST}:{MQTT_PORT}")
        return None
    
    try:
        # Create config file
        config_path = create_mosquitto_config()
        
        # Try to start mosquitto with our config
        cmd = ['mosquitto', '-c', config_path]
        
        # On Windows, mosquitto might be in different locations
        if sys.platform.startswith('win'):
            # Try common Windows locations
            possible_paths = [
                'mosquitto',
                'C:/Program Files/mosquitto/mosquitto.exe',
                'C:/Program Files (x86)/mosquitto/mosquitto.exe'
            ]
            
            mosquitto_path = None
            for path in possible_paths:
                try:
                    subprocess.run([path, '--help'], capture_output=True, timeout=5)
                    mosquitto_path = path
                    break
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                    continue
            
            if mosquitto_path:
                cmd[0] = mosquitto_path
            else:
                logger.warning("mosquitto not found in common Windows locations")
                return None
        
        # Start mosquitto as a background process
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform.startswith('win') else 0
        )
        
        # Give it a moment to start
        time.sleep(2)
        
        # Check if it's actually running
        if process.poll() is None and is_port_in_use(MQTT_HOST, MQTT_PORT):
            logger.info(f"Successfully started mosquitto broker on {MQTT_HOST}:{MQTT_PORT}")
            return process
        else:
            logger.error("Failed to start mosquitto broker")
            try:
                process.terminate()
            except:
                pass
            return None
            
    except FileNotFoundError:
        logger.warning("mosquitto executable not found. Please install mosquitto or ensure it's in PATH")
        return None
    except Exception as e:
        logger.error(f"Error starting mosquitto: {e}")
        return None


def stop_mosquitto_broker(process: subprocess.Popen):
    """Stop the mosquitto broker process"""
    if process and process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait() 

def __main__():
    """Main function to test the mosquitto broker"""

    start_mosquitto_broker()
