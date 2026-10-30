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

### 2. Run-scoped MQTT topics

Each `nornir-build` invocation is assigned a unique **run id** (see below) and
publishes to run-scoped topics so multiple concurrent and past runs can be told
apart:

- `nornir/run/{run_id}/meta` - retained run metadata and status
- `nornir/run/{run_id}/log/info`
- `nornir/run/{run_id}/log/warning`
- `nornir/run/{run_id}/log/error`
- `nornir/run/{run_id}/log/debug`
- `nornir/run/{run_id}/progress` - progress updates (from `CurseProgress()`)
- `nornir/run/{run_id}/status` - status updates (from `CurseString()`)
- `nornir/run/{run_id}/event` - structured pipeline events (stage start/end,
  iterate progress) emitted by `nornir-buildmanager`

Info messages are published by `prettyoutput.Log()`. Warning, error, and debug
records are forwarded centrally by `nornir_shared.misc.MQTTLogHandler`, which is
attached during `SetupLogging` (and to the multiprocess `QueueListener`) so
records from worker processes are published exactly once. Structured pipeline
events (`stage_start`, `iterate_progress`, …) are published by
`nornir_shared.mqtt_telemetry.publish_run_event` from `PipelineManager` and from
stage code via `nornir_buildmanager.progress.report_iterate`. Tile converters in
`nornir_imageregistration` report nested bars through
`prettyoutput.publish_task_progress` (wired to `iterate_progress`).

TEMBuild/TEMAlign track ids (ImportIDoc sections/tiles, AssembleStosOverlays,
SliceToVolume, MosaicToVolume, etc.) are listed in
`nornir-buildmanager/README.md`.

#### Run id

The run id is derived from the unified logging session id plus a short random
suffix (for example `20260626-182015-6679edd7`) and is exported in the
`NORNIR_RUN_ID` environment variable so worker processes inherit it.

#### Legacy flat topics (back-compat)

The original flat topics (`nornir/log/info`, `nornir/log/error`, ...) are still
defined for the curses console subscriber. They are **off by default**; set
`NORNIR_MQTT_LEGACY_TOPICS=1` to also mirror messages to them.

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
# Basic console (curses interface by default on a TTY)
python -m nornir_shared.console

# Console without the curses interface (plain output)
python -m nornir_shared.console -nocurses

# Console with debug output
python -m nornir_shared.console -debug

# Console with custom title
python -m nornir_shared.console -title "My Project Console"
```

### Message Format

MQTT messages are published as JSON with the following structure:

```json
{
    "run_id": "20260626-182015-6679edd7",
    "message": "The actual log message",
    "timestamp": 1234567890.123,
    "ts": 1234567890.123,
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

### Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `NORNIR_MQTT_HOST` | `127.0.0.1` | Broker host clients connect to |
| `NORNIR_MQTT_BIND` | `127.0.0.1` | Bind address when auto-starting mosquitto |
| `NORNIR_MQTT_PORT` | `1883` | Broker port |
| `NORNIR_MQTT_ENABLE` | `1` | Set to `0` to disable all MQTT publishing |
| `NORNIR_MQTT_LEGACY_TOPICS` | `0` | Set to `1` to also publish flat `nornir/log/*` topics |
| `NORNIR_RUN_ID` | derived | Unique id for the run (auto-set; inherited by workers) |

When `NORNIR_MQTT_HOST` points at a non-local host (for example a central
`mosquitto` compose service), the embedded broker is **not** auto-started; the
process simply connects to the configured broker.

### Publishing from remote machines to a central broker

To collect runs from several machines on one dashboard, expose the central
broker's `1883` port (see `nornir-docker/compose.dashboard.yaml`, published on
`NORNIR_MQTT_BIND_HOST`, default `0.0.0.0`) and point each build at it:

```bash
export NORNIR_MQTT_HOST=<central-host-ip-or-hostname>
export NORNIR_MQTT_PORT=1883
```

No code changes are needed - publishers read these variables and skip the
embedded broker for a remote host. The broker is anonymous and unencrypted, so
only expose it on a trusted network (scope `1883` with a host firewall).

### Mosquitto Configuration (embedded broker)

When pointed at localhost, the system auto-creates a mosquitto configuration:

```
listener 1883 127.0.0.1
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

# Terminal 2: Plain (non-curses) interface
python -m nornir_shared.console -nocurses -title "Status Monitor"

# Terminal 3: Debug console
python -m nornir_shared.console -debug -title "Debug Output"
```

All will receive the same MQTT messages but can display them differently.

## Web build dashboard

For a birds-eye view of one or many runs (live and historical) in a browser,
use the `nornir-dashboard` service. It subscribes to the run-scoped topics,
persists run/event history to SQLite, and serves a web UI showing the current
pipeline, current stage/command, current section, percent complete, and a
filterable log of errors and warnings per run.

Run the broker + dashboard together with Docker:

```bash
docker compose -f nornir-docker/compose.dashboard.yaml up -d mosquitto nornir-dashboard
# then run builds pointed at the shared broker (NORNIR_MQTT_HOST=mosquitto)
# and open http://127.0.0.1:8087
```

See `nornir-builddashboard/README.md` and `nornir-docker/README.md` for details.