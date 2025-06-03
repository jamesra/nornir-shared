# MQTT Integration for Nornir-Shared

This document describes the new MQTT-based messaging system that has been integrated into the nornir-shared project.

## Overview

The nornir-shared project has been modified to use MQTT messaging instead of socket-based communication for console output. This provides better reliability, message routing, and the ability to have multiple subscribers.

## Key Changes

### 1. MQTT Client Integration
- **prettyoutput.py**: Now publishes log messages to MQTT topics based on severity
- **consolewindow.py**: Modified to subscribe to MQTT topics instead of using sockets  
- **console.py**: Updated to work as an MQTT subscriber console
- **mqtt_config.py**: New module for MQTT configuration and mosquitto broker management

### 2. MQTT Topics by Severity

Messages are published to different MQTT topics based on their severity:

- `nornir/log/info` - General log messages (from `Log()` function)
- `nornir/log/error` - Error messages (from `LogErr()` and `error()` functions)
- `nornir/log/warning` - Warning messages
- `nornir/log/debug` - Debug messages
- `nornir/log/progress` - Progress updates (from `CurseProgress()` function)
- `nornir/log/status` - Status updates (from `CurseString()` function)

### 3. Automatic Mosquitto Broker Management

The system automatically:
- Checks if mosquitto broker is running on localhost:1883
- Starts mosquitto broker if not running
- Configures broker for localhost-only access with no authentication
- Manages broker lifecycle and cleanup

## Requirements

### Software Dependencies
- **paho-mqtt**: Python MQTT client library (added to dependencies)
- **mosquitto**: MQTT broker (must be installed separately)

### Installing Mosquitto

**Windows:**
1. Download from https://mosquitto.org/download/
2. Install to default location or ensure it's in PATH
3. The system will automatically find common installation paths

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install mosquitto mosquitto-clients
```

**macOS:**
```bash
brew install mosquitto
```

## Usage

### Basic Usage (Same API as Before)

The existing API remains unchanged, but now publishes to MQTT:

```python
import nornir_shared.prettyoutput as pretty

# Basic logging (published to info topic)
pretty.Log("This is a log message")

# Error logging (published to error topic)  
pretty.LogErr("This is an error message")

# Progress reporting (published to progress topic)
pretty.CurseProgress("Processing data", 50, 100)

# Status updates (published to status topic)
pretty.CurseString("Stage", "Data Loading")
```

### Running the Console Subscriber

Start the MQTT console subscriber in a separate terminal:

```bash
# Basic console
python -m nornir_shared.console

# Console with curses interface
python -m nornir_shared.console -usecurses

# Console with debug output
python -m nornir_shared.console -debug

# Console with custom title
python -m nornir_shared.console -title "My Project Console"
```

### Message Format

MQTT messages are published as JSON with the following structure:

```json
{
    "message": "The actual log message",
    "timestamp": 1234567890.123,
    "severity": "info",
    "logger_name": "module.function_name"
}
```

Progress messages include additional metadata:

```json
{
    "message": "Processing step 3 0.6 ETA: 00:02:15",
    "timestamp": 1234567890.123,
    "severity": "progress",
    "progress": 60,
    "total": 100,
    "fraction": 0.6,
    "eta_string": "ETA: 00:02:15"
}
```

## Configuration

### MQTT Broker Settings

Default settings in `mqtt_config.py`:

```python
MQTT_HOST = "localhost"
MQTT_PORT = 1883
MQTT_KEEPALIVE = 60
```

### Mosquitto Configuration

The system automatically creates a mosquitto configuration:

```
listener 1883
bind_address localhost
allow_anonymous true
persistence false
```

This ensures:
- Only accepts connections from localhost
- No authentication required
- No message persistence (avoids file system issues)

## Testing

Run the included example script to test the functionality:

```bash
# Terminal 1: Start the console subscriber
python -m nornir_shared.console

# Terminal 2: Run the demo
python example_mqtt_usage.py
```

You should see log messages appearing in the console with timestamps and severity levels.

## Troubleshooting

### Mosquitto Not Found
If mosquitto is not found:
1. Ensure mosquitto is installed
2. Add mosquitto to your PATH
3. On Windows, check common installation paths are accessible

### MQTT Connection Issues
If MQTT connection fails:
1. Check if port 1883 is available
2. Verify mosquitto service is running
3. Check firewall settings for localhost connections

### Fallback Behavior
If MQTT is not available:
- Log messages will still print to console normally
- Console windows will fallback to basic print statements
- No functionality is lost

## Migration from Socket-Based System

The migration should be seamless:
1. Existing code using `prettyoutput` functions continues to work
2. Console windows automatically use MQTT instead of sockets
3. Multiple console subscribers can run simultaneously
4. Better error handling and connection recovery

## Advanced Usage

### Custom MQTT Subscribers

You can create custom MQTT subscribers to process messages differently:

```python
import paho.mqtt.client as mqtt
import json
from nornir_shared.mqtt_config import MQTT_HOST, MQTT_PORT, MQTT_TOPICS

def on_message(client, userdata, msg):
    payload = json.loads(msg.payload.decode())
    print(f"Received: {payload['severity']} - {payload['message']}")

client = mqtt.Client()
client.on_message = on_message
client.connect(MQTT_HOST, MQTT_PORT, 60)

# Subscribe to specific topics
client.subscribe(MQTT_TOPICS['error'])  # Only error messages
client.subscribe(MQTT_TOPICS['progress'])  # Only progress updates

client.loop_forever()
```

### Multiple Console Windows

You can run multiple console windows with different configurations:

```bash
# Terminal 1: General console
python -m nornir_shared.console -title "General Log"

# Terminal 2: Curses interface  
python -m nornir_shared.console -usecurses -title "Status Monitor"

# Terminal 3: Debug console
python -m nornir_shared.console -debug -title "Debug Output"
```

All will receive the same MQTT messages but can display them differently. 