"""``plot.Histogram`` saving to a file must not touch pyplot, so it is safe on worker threads.

ImportIDoc plots the section histogram on a pool thread. On a desktop, nornir_imageregistration and
nornir_buildmanager select the QtAgg backend (whatever MPLBACKEND says), and ``plt.clf()`` on a non-main thread
with a GUI backend segfaulted the import (RC2_Micro/17, -NoCrush, 2026-11-05). Saving now uses its own Figure on
the Agg canvas.
"""

from __future__ import annotations

import os
import tempfile
import threading

import matplotlib.pyplot as plt
import pytest

from nornir_shared import histogram, plot


@pytest.fixture
def hist():
    h = histogram.Histogram.Init(0, 1000, 100)
    h.Add([float(v) for v in range(50, 950, 3)])
    return h


@pytest.fixture
def pyplot_forbidden(monkeypatch):
    """Any pyplot state call while saving is a failure: on a GUI backend it is unsafe off the main thread."""
    def forbidden(*args, **kwargs):
        raise AssertionError('plot.Histogram touched pyplot while saving to a file')

    for name in ('clf', 'axes', 'gcf', 'gca', 'sca', 'savefig', 'close', 'figure', 'show'):
        monkeypatch.setattr(plt, name, forbidden)


def test_histogram_saves_from_a_worker_thread_without_pyplot(hist, pyplot_forbidden):
    errors: list[BaseException] = []
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'Histogram.png')

        def run():
            try:
                plot.Histogram(hist, path, MinCutoffPercent=0.01, MaxCutoffPercent=0.01, LinePosList=[200.0, 800.0])
            except BaseException as e:  # noqa: BLE001 - re-raised on the main thread below
                errors.append(e)

        worker = threading.Thread(target=run)
        worker.start()
        worker.join(timeout=60)
        assert not worker.is_alive()
        assert not errors, errors
        assert os.path.getsize(path) > 0
