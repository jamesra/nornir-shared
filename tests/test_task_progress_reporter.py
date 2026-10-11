"""Characterization tests for the throttled ``TaskProgressReporter``.

A small reference model of the throttle (start / update / complete) is compared
against the real reporter on Hypothesis-generated call sequences, with
``time.time`` pinned per call so the time-based throttle is deterministic.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from typing import Any
from unittest import mock

from hypothesis import example, given, settings
from hypothesis import strategies as st
from nornir_shared import prettyoutput

_TASK_KEY = "unit:task"
_NAME = "Unit task"
_SECTION = 7


@dataclass
class _Op:
    """One call on the reporter at a fixed wall-clock time."""

    kind: str
    at: float
    current: int = 0
    element: str | None = None
    path: str | None = None


@dataclass
class _Model:
    """Reference model of the progress throttle and the events it emits."""

    total: int
    min_interval_s: float
    started: bool = False
    completed: bool = False
    last_published: int = -1
    last_time: float = 0.0
    element: str | None = None
    path: str | None = None
    events: list[tuple[Any, ...]] = field(default_factory=list)

    @property
    def step(self) -> int:
        """Item step that forces a publish (1% of total, at least 1)."""
        return max(1, max(0, self.total) // 100) if self.total > 0 else 1

    def _pub(self, current: int, at: float) -> None:
        self.last_published = current
        self.last_time = at
        self.events.append(("progress", current, self.total, self.element, self.path))

    def start(self, at: float) -> None:
        """Model ``start``."""
        if self.total <= 0 or self.started:
            return
        self.started = True
        self._pub(0, at)

    def update(self, op: _Op) -> None:
        """Model ``update``."""
        if self.total <= 0 or self.completed:
            return
        if not self.started:
            self.start(op.at)
        if op.element is not None:
            self.element = op.element
        if op.path is not None:
            self.path = op.path
        current = min(max(0, op.current), self.total)
        if (current >= self.total
                or self.last_published < 0
                or current - self.last_published >= self.step
                or op.at - self.last_time >= self.min_interval_s):
            self._pub(current, op.at)

    def complete(self, at: float) -> None:
        """Model ``complete`` (no-op when never started)."""
        if self.completed or self.total <= 0 or not self.started:
            return
        self.completed = True
        self._pub(self.total, at)
        self.events.append(("complete", self.total))


def _run_real(total: int, min_interval_s: float, ops: list[_Op]) -> list[tuple[Any, ...]]:
    """Drive a real reporter and return the recorded publish events."""
    events: list[tuple[Any, ...]] = []
    clock = [0.0]

    def fake_progress(task_key: str, current: int, total_: int, name: str | None = None,
                      element: str | None = None, path: str | None = None,
                      section: int | str | None = None) -> None:
        assert task_key == _TASK_KEY
        assert name == _NAME
        assert section == _SECTION
        events.append(("progress", current, total_, element, path))

    def fake_complete(task_key: str, total_: int) -> None:
        assert task_key == _TASK_KEY
        events.append(("complete", total_))

    with mock.patch.object(prettyoutput, "publish_task_progress", side_effect=fake_progress), \
            mock.patch.object(prettyoutput, "publish_task_complete", side_effect=fake_complete), \
            mock.patch("time.time", side_effect=lambda: clock[0]):
        reporter = prettyoutput.TaskProgressReporter(
            _TASK_KEY, total, name=_NAME, min_interval_s=min_interval_s, section=_SECTION)
        for op in ops:
            clock[0] = op.at
            if op.kind == "start":
                reporter.start()
            elif op.kind == "update":
                reporter.update(op.current, element=op.element, path=op.path)
            else:
                reporter.complete()
    return events


def _run_model(total: int, min_interval_s: float, ops: list[_Op]) -> list[tuple[Any, ...]]:
    """Drive the reference model and return its events."""
    model = _Model(total=max(0, total), min_interval_s=min_interval_s)
    for op in ops:
        if op.kind == "start":
            model.start(op.at)
        elif op.kind == "update":
            model.update(op)
        else:
            model.complete(op.at)
    return model.events


@st.composite
def _op_sequences(draw: st.DrawFn) -> list[_Op]:
    """Generate call sequences with non-decreasing timestamps."""
    n = draw(st.integers(min_value=0, max_value=40))
    at = 1000.0
    ops: list[_Op] = []
    for _ in range(n):
        at += draw(st.sampled_from([0.0, 0.01, 0.1, 0.3, 2.0]))
        kind = draw(st.sampled_from(["start", "update", "update", "update", "complete"]))
        ops.append(_Op(
            kind=kind,
            at=at,
            current=draw(st.integers(min_value=-5, max_value=1100)),
            element=draw(st.sampled_from([None, "e1", "e2"])),
            path=draw(st.sampled_from([None, "p1"])),
        ))
    return ops


class TestTaskProgressReporterThrottle(unittest.TestCase):
    """Pin the publish sequence of ``TaskProgressReporter``."""

    @settings(max_examples=300, deadline=None)
    @given(
        total=st.integers(min_value=-3, max_value=1000),
        min_interval_s=st.sampled_from([0.0, 0.25, 1.0]),
        ops=_op_sequences(),
    )
    @example(total=0, min_interval_s=0.25, ops=[_Op("update", 1.0, 1), _Op("complete", 2.0)])
    @example(total=10, min_interval_s=0.25, ops=[_Op("complete", 1.0)])
    def test_matches_reference_model(self, total: int, min_interval_s: float,
                                     ops: list[_Op]) -> None:
        """Publish events match the reference throttle model."""
        self.assertEqual(_run_model(total, min_interval_s, ops),
                         _run_real(total, min_interval_s, ops))

    def test_complete_before_start_publishes_nothing(self) -> None:
        """``complete`` on a never-started reporter is a no-op."""
        self.assertEqual([], _run_real(5, 0.25, [_Op("complete", 1.0)]))

    def test_element_and_path_are_sticky(self) -> None:
        """Later publishes carry the most recent element and path."""
        events = _run_real(200, 10.0, [
            _Op("update", 1.0, 1, element="a", path="p"),
            _Op("update", 1.0, 2, element="b"),
            _Op("complete", 1.0),
        ])
        self.assertEqual([
            ("progress", 0, 200, None, None),
            ("progress", 2, 200, "b", "p"),
            ("progress", 200, 200, "b", "p"),
            ("complete", 200),
        ], events)

    def test_step_and_time_throttle(self) -> None:
        """Updates inside both the item step and the interval are dropped."""
        events = _run_real(1000, 1.0, [
            _Op("start", 0.0),
            _Op("update", 0.5, 5),
            _Op("update", 0.6, 10),
            _Op("update", 2.0, 11),
            _Op("update", 2.1, 2000),
        ])
        self.assertEqual([
            ("progress", 0, 1000, None, None),
            ("progress", 10, 1000, None, None),
            ("progress", 11, 1000, None, None),
            ("progress", 1000, 1000, None, None),
        ], events)


if __name__ == "__main__":
    unittest.main()
