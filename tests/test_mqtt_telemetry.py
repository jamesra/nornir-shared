"""Tests for nornir_shared.mqtt_telemetry run meta and event publishers."""
import os
import unittest
from unittest import mock

import nornir_shared.prettyoutput as prettyoutput
from nornir_shared import mqtt_telemetry


class TestMqttTelemetry(unittest.TestCase):
    """Verify run-scoped meta and event payloads."""

    def setUp(self) -> None:
        self._original_initialized = prettyoutput._mqtt_initialized
        self._original_client = prettyoutput._mqtt_client
        prettyoutput._mqtt_initialized = True
        self.client = mock.Mock()
        prettyoutput._mqtt_client = self.client
        mqtt_telemetry.clear_retained_identity_cache()

    def tearDown(self) -> None:
        prettyoutput._mqtt_initialized = self._original_initialized
        prettyoutput._mqtt_client = self._original_client
        mqtt_telemetry.clear_retained_identity_cache()

    def test_publish_run_event_uses_event_topic(self) -> None:
        with mock.patch.dict(os.environ, {"NORNIR_RUN_ID": "unit-run"}, clear=False):
            with mock.patch("nornir_shared.prettyoutput.MQTT_ENABLE", True):
                with mock.patch("nornir_shared.prettyoutput.MQTT_AVAILABLE", True):
                    mqtt_telemetry.publish_run_event(
                        "stage_start",
                        module="nornir_buildmanager.operations.tile",
                        function="AssembleTransform",
                        section=63,
                    )

        self.client.publish.assert_called()
        topic = self.client.publish.call_args[0][0]
        body = self.client.publish.call_args[0][1]
        self.assertEqual(topic, "nornir/run/unit-run/event")
        self.assertIn("stage_start", body)
        self.assertIn("AssembleTransform", body)
        self.assertIn('"section": 63', body)

    def test_publish_run_meta_retains_and_includes_status(self) -> None:
        with mock.patch.dict(os.environ, {"NORNIR_RUN_ID": "unit-run"}, clear=False):
            with mock.patch("nornir_shared.prettyoutput.MQTT_ENABLE", True):
                with mock.patch("nornir_shared.prettyoutput.MQTT_AVAILABLE", True):
                    mqtt_telemetry.publish_run_meta(
                        status="completed",
                        pipeline="Assemble",
                        volumepath="/data/vol",
                        end_ts=123.0,
                    )

        topic = self.client.publish.call_args[0][0]
        kwargs = self.client.publish.call_args.kwargs
        body = self.client.publish.call_args[0][1]
        self.assertEqual(topic, "nornir/run/unit-run/meta")
        self.assertTrue(kwargs.get("retain"))
        self.assertIn('"status": "completed"', body)
        self.assertIn('"end_ts": 123.0', body)

    def test_publish_early_run_meta_fills_defaults(self) -> None:
        env = {
            "NORNIR_RUN_ID": "unit-run",
            "NORNIR_LOG_SESSION_ID": "sess-1",
            "NORNIR_COMPUTATIONAL_LIBRARY": "cupy",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch("nornir_shared.prettyoutput.MQTT_ENABLE", True):
                with mock.patch("nornir_shared.prettyoutput.MQTT_AVAILABLE", True):
                    with mock.patch("nornir_shared.mqtt_telemetry.socket.gethostname",
                                    return_value="testhost"):
                        mqtt_telemetry.publish_early_run_meta(
                            pipeline="Assemble", volumepath="/storage4/RPC3")

        body = self.client.publish.call_args[0][1]
        self.assertIn('"host": "testhost"', body)
        self.assertIn('"session_id": "sess-1"', body)
        self.assertIn('"compute": "cupy"', body)
        self.assertIn('"status": "running"', body)
        self.assertIn("start_ts", body)

    def test_retained_completion_meta_merges_cached_identity(self) -> None:
        env = {"NORNIR_RUN_ID": "unit-run"}
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch("nornir_shared.prettyoutput.MQTT_ENABLE", True):
                with mock.patch("nornir_shared.prettyoutput.MQTT_AVAILABLE", True):
                    mqtt_telemetry.publish_run_meta(
                        status="running",
                        pipeline="AdjustContrast",
                        volumepath="/storage4/Wohl",
                        start_ts=100.0,
                    )
                    mqtt_telemetry.publish_run_meta(
                        status="completed",
                        end_ts=200.0,
                    )

        body = self.client.publish.call_args[0][1]
        self.assertIn('"status": "completed"', body)
        self.assertIn('"pipeline": "AdjustContrast"', body)
        self.assertIn('"volumepath": "/storage4/Wohl"', body)
        self.assertIn('"start_ts": 100.0', body)
        self.assertIn('"end_ts": 200.0', body)


class TestMqttLogHandler(unittest.TestCase):
    """MQTTLogHandler forwards warning/debug without duplicating prettyoutput."""

    def test_warning_publishes_to_warning_topic(self) -> None:
        import logging
        from nornir_shared.misc import MQTTLogHandler

        handler = MQTTLogHandler()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.WARNING,
            pathname=__file__,
            lineno=1,
            msg="file missing",
            args=(),
            exc_info=None,
        )
        with mock.patch("nornir_shared.prettyoutput._publish_mqtt_message") as publish:
            handler.emit(record)
        publish.assert_called_once()
        self.assertEqual(publish.call_args[0][0], "warning")
        self.assertIn("file missing", publish.call_args[0][1])

    def test_skips_already_published_records(self) -> None:
        import logging
        from nornir_shared.misc import MQTTLogHandler

        handler = MQTTLogHandler()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="already sent",
            args=(),
            exc_info=None,
        )
        record.mqtt_published = True  # type: ignore[attr-defined]
        with mock.patch("nornir_shared.prettyoutput._publish_mqtt_message") as publish:
            handler.emit(record)
        publish.assert_not_called()

    def test_skips_info_records(self) -> None:
        import logging
        from nornir_shared.misc import MQTTLogHandler

        handler = MQTTLogHandler()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="info only",
            args=(),
            exc_info=None,
        )
        with mock.patch("nornir_shared.prettyoutput._publish_mqtt_message") as publish:
            handler.emit(record)
        publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
