"""Structured MQTT telemetry helpers for the nornir build dashboard.

Publishes retained run metadata and pipeline events onto the run-scoped topic
tree defined in :mod:`nornir_shared.mqtt_config`. Keeps
:mod:`nornir_shared.prettyoutput` focused on console/MQTT log streaming.
"""
from __future__ import annotations

import os
import socket
import time
from typing import Any

from nornir_shared import prettyoutput
from nornir_shared.mqtt_config import (
    NORNIR_LOG_SESSION_ENV,
    get_or_create_run_id,
)

# Identity fields preserved across retained meta publishes so completion meta
# (status + end_ts only) does not wipe pipeline/volumepath on Mosquitto retain.
_IDENTITY_KEYS = (
    "pipeline",
    "volumepath",
    "host",
    "pid",
    "session_id",
    "compute",
    "start_ts",
)
_retained_identity: dict[str, Any] = {}


def clear_retained_identity_cache() -> None:
    """Clear the process-local retained meta identity cache (for tests)."""
    _retained_identity.clear()


def publish_run_meta(*, status: str | None = None, retain: bool = True,
                     **fields: Any) -> None:
    """Publish retained (or ephemeral) run metadata for the dashboard.

    Known fields include ``pipeline``, ``volumepath``, ``host``, ``pid``,
    ``session_id``, ``start_ts``, ``end_ts``, ``compute``, and ``status``.
    Only provided keys are sent; the dashboard merges them into the run row.

    When ``retain`` is True, previously published identity fields are merged
    into the payload so a completion-only meta publish still retains
    ``pipeline`` / ``volumepath`` (Mosquitto replace-on-retain). Explicit
    keyword values always win over the cache.
    """
    run_id = get_or_create_run_id() if prettyoutput.MQTT_AVAILABLE else os.environ.get("NORNIR_RUN_ID", "")
    metadata: dict[str, Any] = {"run_id": run_id}
    if status is not None:
        metadata["status"] = status
    for key, value in fields.items():
        if value is not None:
            metadata[key] = value

    if retain:
        for key in _IDENTITY_KEYS:
            if key not in metadata and key in _retained_identity:
                metadata[key] = _retained_identity[key]
        for key in _IDENTITY_KEYS:
            if key in metadata and metadata[key] is not None:
                _retained_identity[key] = metadata[key]

    pipeline = metadata.get("pipeline", "")
    volumepath = metadata.get("volumepath", "")
    message = f"{pipeline} {volumepath}".strip() or status or "meta"
    prettyoutput._publish_mqtt_message("meta", message, metadata, retain=retain)


def publish_run_event(event: str, **fields: Any) -> None:
    """Publish a structured pipeline event to the run ``event`` topic.

    Typical ``event`` values: ``stage_start``, ``stage_end``, ``stage_failed``,
    ``iterate_progress``. Extra fields (``module``, ``function``, ``section``,
    ``element``, ``current``, ``total``, ``label``, ``depth``, ``track_id``, …)
    are included in the JSON payload.
    """
    metadata: dict[str, Any] = {"event": event}
    for key, value in fields.items():
        if value is not None:
            metadata[key] = value

    message_bits = [event]
    if metadata.get("function"):
        message_bits.append(str(metadata["function"]))
    if metadata.get("label"):
        message_bits.append(str(metadata["label"]))
    if metadata.get("current") is not None and metadata.get("total") is not None:
        message_bits.append(f"{metadata['current']}/{metadata['total']}")
    prettyoutput._publish_mqtt_message("event", " ".join(message_bits), metadata)


def publish_early_run_meta(*, pipeline: str, volumepath: str,
                           status: str = "running",
                           **fields: Any) -> None:
    """Publish retained run metadata so the dashboard can list the build immediately.

    Fills host, pid, session id, start timestamp, and compute backend when
    available. Additional keyword fields override defaults.
    """
    now = time.time()
    defaults: dict[str, Any] = {
        "pipeline": pipeline,
        "volumepath": volumepath,
        "host": socket.gethostname(),
        "pid": os.getpid(),
        "session_id": os.environ.get(NORNIR_LOG_SESSION_ENV),
        "start_ts": now,
        "compute": os.environ.get("NORNIR_COMPUTATIONAL_LIBRARY"),
    }
    defaults.update(fields)
    publish_run_meta(status=status, retain=True, **defaults)
