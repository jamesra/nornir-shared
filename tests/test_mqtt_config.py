import os
import unittest
from unittest import mock

import nornir_shared.prettyoutput as prettyoutput
from nornir_shared import mqtt_config


class TestMqttConfig(unittest.TestCase):
    """Tests for mosquitto configuration and broker startup helpers."""

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


if __name__ == "__main__":
    unittest.main()
