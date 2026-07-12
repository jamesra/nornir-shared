import os
import unittest
from unittest import mock

import nornir_shared.prettyoutput as prettyoutput
from nornir_shared import mqtt_config


class TestMqttConfig(unittest.TestCase):
    """Tests for mosquitto configuration and broker startup helpers."""

    def test_run_topic_root_and_helpers(self) -> None:
        """Run-scoped topic helpers must resolve under MQTT_RUN_TOPIC_ROOT."""
        self.assertEqual(mqtt_config.MQTT_RUN_TOPIC_ROOT, "nornir/run")
        self.assertTrue(mqtt_config.is_local_mqtt_host("127.0.0.1"))
        self.assertFalse(mqtt_config.is_local_mqtt_host("10.0.0.5"))

        with mock.patch.dict(os.environ, {"NORNIR_RUN_ID": "test-run-id"}, clear=False):
            self.assertEqual(mqtt_config.get_or_create_run_id(), "test-run-id")
            self.assertEqual(
                mqtt_config.run_topic_for_key("info"),
                "nornir/run/test-run-id/log/info",
            )
            self.assertEqual(
                mqtt_config.run_topic_for_key("meta"),
                "nornir/run/test-run-id/meta",
            )

    def test_create_mosquitto_config_uses_single_listener(self) -> None:
        """Ensure Mosquitto 2.x receives one listener directive, not listener plus bind_address."""
        config_path = mqtt_config.create_mosquitto_config(bind_host="127.0.0.1", port=1883)
        self.addCleanup(lambda: os.path.exists(config_path) and os.remove(config_path))

        with open(config_path, encoding="utf-8") as config_file:
            config_text = config_file.read()

        self.assertIn("listener 1883 127.0.0.1", config_text)
        self.assertNotIn("bind_address", config_text)

    def test_default_hosts_use_localhost_not_wildcard(self) -> None:
        """Clients and broker defaults must not use 0.0.0.0."""
        self.assertEqual(mqtt_config.MQTT_CONNECT_HOST, "127.0.0.1")
        self.assertEqual(mqtt_config.MQTT_BIND_HOST, "127.0.0.1")
        self.assertEqual(mqtt_config.MQTT_HOST, mqtt_config.MQTT_CONNECT_HOST)

    @unittest.skipUnless(mqtt_config._resolve_mosquitto_executable(), "mosquitto executable not available")
    def test_start_mosquitto_broker_starts_and_accepts_local_connections(self) -> None:
        """Integration check that generated config can start a broker once."""
        if mqtt_config.is_port_in_use(mqtt_config.MQTT_BIND_HOST, mqtt_config.MQTT_PORT):
            self.skipTest("MQTT port already in use")

        process = mqtt_config.start_mosquitto_broker()
        self.addCleanup(lambda: process and mqtt_config.stop_mosquitto_broker(process))

        self.assertIsNotNone(process)
        self.assertIsNone(process.poll())
        self.assertTrue(mqtt_config.is_port_in_use(mqtt_config.MQTT_BIND_HOST, mqtt_config.MQTT_PORT))

        import paho.mqtt.client as mqtt
        from paho.mqtt.enums import CallbackAPIVersion

        client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2)
        try:
            client.connect(mqtt_config.MQTT_CONNECT_HOST, mqtt_config.MQTT_PORT, mqtt_config.MQTT_KEEPALIVE)
        finally:
            client.disconnect()


class TestPrettyOutputMqttInit(unittest.TestCase):
    """Tests for one-shot MQTT initialization in prettyoutput."""

    def setUp(self) -> None:
        self._original_initialized = prettyoutput._mqtt_initialized
        self._original_client = prettyoutput._mqtt_client
        self._original_process = prettyoutput._mosquitto_process

    def tearDown(self) -> None:
        prettyoutput._mqtt_initialized = self._original_initialized
        prettyoutput._mqtt_client = self._original_client
        prettyoutput._mosquitto_process = self._original_process

    def test_initialize_mqtt_attempts_startup_only_once(self) -> None:
        """Failed initialization must not retry broker startup on every log publish."""
        prettyoutput._mqtt_initialized = False
        prettyoutput._mqtt_client = None
        prettyoutput._mosquitto_process = None

        with mock.patch("nornir_shared.prettyoutput.start_mosquitto_broker", return_value=None) as start_mock:
            with mock.patch("nornir_shared.prettyoutput.mqtt.Client") as client_cls:
                client = client_cls.return_value
                client.connect.side_effect = ConnectionError("broker unavailable")

                prettyoutput._publish_mqtt_message("info", "first")
                prettyoutput._publish_mqtt_message("info", "second")

        self.assertEqual(start_mock.call_count, 1)
        self.assertTrue(prettyoutput._mqtt_initialized)

    def test_publish_uses_run_scoped_topic(self) -> None:
        """Default publishes go to nornir/run/{run_id}/… not legacy flat topics."""
        prettyoutput._mqtt_initialized = True
        client = mock.Mock()
        prettyoutput._mqtt_client = client

        with mock.patch.dict(os.environ, {"NORNIR_RUN_ID": "unit-run"}, clear=False):
            with mock.patch("nornir_shared.prettyoutput.MQTT_LEGACY_TOPICS", False):
                with mock.patch("nornir_shared.prettyoutput.MQTT_ENABLE", True):
                    with mock.patch("nornir_shared.prettyoutput.MQTT_AVAILABLE", True):
                        prettyoutput._publish_mqtt_message("info", "hello")

        client.publish.assert_called_once()
        topic, body = client.publish.call_args[0][:2]
        self.assertEqual(topic, "nornir/run/unit-run/log/info")
        self.assertIn("hello", body)

    def test_publish_early_run_meta_retains_meta_topic(self) -> None:
        """Early meta must land on the retained run meta topic."""
        prettyoutput._mqtt_initialized = True
        client = mock.Mock()
        prettyoutput._mqtt_client = client

        with mock.patch.dict(os.environ, {"NORNIR_RUN_ID": "unit-run"}, clear=False):
            with mock.patch("nornir_shared.prettyoutput.MQTT_ENABLE", True):
                with mock.patch("nornir_shared.prettyoutput.MQTT_AVAILABLE", True):
                    prettyoutput.publish_early_run_meta(
                        pipeline="Assemble", volumepath="/data/vol")

        client.publish.assert_called()
        topic = client.publish.call_args[0][0]
        kwargs = client.publish.call_args.kwargs
        self.assertEqual(topic, "nornir/run/unit-run/meta")
        self.assertTrue(kwargs.get("retain"))


if __name__ == "__main__":
    unittest.main()
