"""Pool / executor load telemetry for the nornir build dashboard.

Publishes ``pool_load`` events (separate from ``iterate_progress``) so the
dashboard can render a distinct Pools section without affecting stage bars.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from nornir_shared.mqtt_telemetry import publish_run_event

# Per-pool throttle state: name -> (last_publish_time, last_outstanding)
_pool_load_state: dict[str, tuple[float, int]] = {}
_pool_load_lock = threading.Lock()

# Publish at least this often while load is changing; always on 0 <-> nonzero.
_DEFAULT_INTERVAL_S = 0.75


def clear_pool_load_throttle_state() -> None:
    """Clear throttle state (for unit tests)."""
    with _pool_load_lock:
        _pool_load_state.clear()


def report_pool_load(
    name: str,
    *,
    queued: int,
    active: int | None = None,
    max_workers: int | None = None,
    interval_s: float = _DEFAULT_INTERVAL_S,
) -> bool:
    """Publish a throttled ``pool_load`` event for *name*.

    Parameters
    ----------
    name:
        Stable pool / executor label shown in the dashboard Pools section.
    queued:
        Tasks waiting to run.
    active:
        Tasks currently executing, when known.
    max_workers:
        Optional worker capacity hint for tooltips.
    interval_s:
        Minimum seconds between publishes for the same name unless outstanding
        transitions to or from zero.

    Returns
    -------
    bool
        True when an event was published.
    """
    name = str(name or "").strip() or "pool"
    queued_i = max(0, int(queued))
    active_i: int | None
    if active is None:
        active_i = None
        outstanding = queued_i
    else:
        active_i = max(0, int(active))
        outstanding = queued_i + active_i

    now = time.time()
    with _pool_load_lock:
        prev = _pool_load_state.get(name)
        if prev is not None:
            last_time, last_outstanding = prev
            zero_edge = (outstanding == 0) != (last_outstanding == 0)
            if not zero_edge and (now - last_time) < interval_s:
                return False
        _pool_load_state[name] = (now, outstanding)

    fields: dict[str, Any] = {
        "name": name,
        "queued": queued_i,
        "outstanding": outstanding,
    }
    if active_i is not None:
        fields["active"] = active_i
    if max_workers is not None:
        fields["max_workers"] = int(max_workers)

    publish_run_event("pool_load", **fields)
    return True
