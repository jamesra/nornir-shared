"""``plot.Histogram`` must not show a figure it does not own.

When the caller passes ``axes=``, it is composing a larger figure and decides how the
result is presented -- typically ``savefig`` into a test artifact. ``Histogram`` called
``plt.show()`` anyway whenever ``ImageFilename`` was None, which on a GUI backend blocked
on an event loop until someone closed a window the caller never asked for, and did so
*before* the caller's own savefig ran.

That combination wedged pytest sessions: ``nornir_imageregistration``'s
``test_metrics.py`` builds a two-panel figure, hands panel two to ``Histogram``, and only
then branches on ``is_headless()`` to save rather than show. The blocking show inside
``Histogram`` ran first, so the test's own headless guard never got the chance.
"""

from __future__ import annotations

import matplotlib
matplotlib.use('Agg')

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

from nornir_shared import histogram, plot  # noqa: E402


@pytest.fixture
def hist():
    h = histogram.Histogram.Init(0, 10, 10)
    h.Add([1.0, 2.0, 2.5, 3.0, 7.0, 9.5])
    return h


@pytest.fixture
def no_show(monkeypatch):
    """Record plt.show() calls instead of performing them."""
    calls: list[int] = []
    monkeypatch.setattr(plt, 'show', lambda *a, **k: calls.append(1))
    return calls


def test_caller_supplied_axes_are_not_shown(hist, no_show):
    """The whole point: drawing into someone else's axes must not call show."""
    fig, axes = plt.subplots(ncols=2)
    try:
        plot.Histogram(hist, axes=axes[1])
        assert not no_show, 'Histogram called plt.show() on a figure it does not own'
    finally:
        plt.close(fig)


def test_caller_supplied_axes_survive_for_the_caller_to_save(hist, no_show):
    """The caller must still be able to save the composed figure afterwards."""
    fig, axes = plt.subplots(ncols=2)
    try:
        plot.Histogram(hist, axes=axes[1])
        assert axes[1].has_data(), 'the histogram was not drawn into the caller axes'
        assert plt.fignum_exists(fig.number), 'Histogram closed the caller figure'
    finally:
        plt.close(fig)


def test_without_axes_or_filename_show_is_still_called(hist, no_show):
    """Standalone use is unchanged; only the caller-owned-axes case changed."""
    plot.Histogram(hist)
    assert len(no_show) == 1, 'standalone Histogram should still present the figure'
    plt.close('all')


def test_image_filename_saves_and_does_not_show(hist, no_show, tmp_path):
    """The save path never showed, and still must not."""
    out = tmp_path / 'hist.png'
    plot.Histogram(hist, ImageFilename=str(out))
    assert out.is_file() and out.stat().st_size > 0
    assert not no_show


def test_axes_and_filename_together_save_without_showing(hist, no_show, tmp_path):
    """ImageFilename wins over the caller-axes branch, and still does not show."""
    fig, axes = plt.subplots(ncols=2)
    out = tmp_path / 'hist2.png'
    try:
        plot.Histogram(hist, ImageFilename=str(out), axes=axes[1])
        assert out.is_file() and out.stat().st_size > 0
        assert not no_show
    finally:
        plt.close('all')
