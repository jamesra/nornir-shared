"""Tests for nornir_shared.pool_load throttled MQTT publisher."""
from __future__ import annotations

import unittest
from unittest import mock

from nornir_shared import pool_load


class TestReportPoolLoad(unittest.TestCase):
    def setUp(self) -> None:
        pool_load.clear_pool_load_throttle_state()

    def tearDown(self) -> None:
        pool_load.clear_pool_load_throttle_state()

    def test_publishes_pool_load_fields(self) -> None:
        with mock.patch.object(pool_load, "publish_run_event") as publish:
            ok = pool_load.report_pool_load(
                "Global thread pool",
                queued=3,
                active=2,
                max_workers=8,
                interval_s=0,
            )
        self.assertTrue(ok)
        publish.assert_called_once_with(
            "pool_load",
            name="Global thread pool",
            queued=3,
            outstanding=5,
            active=2,
            max_workers=8,
        )

    def test_throttles_repeat_publishes(self) -> None:
        with mock.patch.object(pool_load, "publish_run_event") as publish:
            self.assertTrue(pool_load.report_pool_load("p", queued=1, active=0, interval_s=60))
            self.assertFalse(pool_load.report_pool_load("p", queued=2, active=0, interval_s=60))
        self.assertEqual(publish.call_count, 1)

    def test_publishes_on_zero_edge(self) -> None:
        with mock.patch.object(pool_load, "publish_run_event") as publish:
            self.assertTrue(pool_load.report_pool_load("p", queued=1, active=0, interval_s=60))
            self.assertTrue(pool_load.report_pool_load("p", queued=0, active=0, interval_s=60))
        self.assertEqual(publish.call_count, 2)


if __name__ == "__main__":
    unittest.main()
