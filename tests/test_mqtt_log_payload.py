"""Pin how the MQTT console subscribers decode prettyoutput's JSON log payloads."""
import contextlib
import io
import json
import time
import unittest
from types import SimpleNamespace
from typing import Any
from unittest import mock

from hypothesis import example, given
from hypothesis import strategies as st

from nornir_shared import console, consolewindow, mqtt_config

_NOW = 1_762_500_000.25

_severities = st.one_of(
    st.sampled_from(["info", "warning", "error", "err", "critical", "fatal", "debug", "ERROR", "Fatal"]),
    st.text(max_size=8),
    st.none(),
    st.integers(-5, 5),
)
_payloads = st.fixed_dictionaries(
    {},
    optional={
        "message": st.text(max_size=40),
        "severity": _severities,
        "timestamp": st.floats(min_value=86_400.0, max_value=4.0e9, allow_nan=False),
        "run_id": st.text(max_size=8),
    },
)


def _consolewindow_output(raw: bytes, title: str = "General") -> tuple[list[str], str]:
    """Feed *raw* to ConsoleWindow's on_message; return callback lines and printed text."""
    window = consolewindow.ConsoleWindow(title=title, auto_start=False)
    received: list[str] = []
    window.set_message_callback(received.append)
    stdout = io.StringIO()
    with mock.patch.object(consolewindow.mqtt, "Client") as client_cls, \
            mock.patch.object(consolewindow.atexit, "register"), \
            mock.patch("time.time", return_value=_NOW), \
            contextlib.redirect_stdout(stdout):
        window._initialize_mqtt_subscriber()
        client_cls.return_value.on_message(None, None, SimpleNamespace(topic="nornir/run/x/log/info", payload=raw))
        window.Close()
    return received, stdout.getvalue()


def _console_output(raw: bytes) -> tuple[list[str], str]:
    """Feed *raw* to MQTTConsoleLoop's on_message; return handler lines and printed text."""
    received: list[str] = []
    stdout = io.StringIO()

    with mock.patch.object(console.mqtt, "Client") as client_cls, \
            mock.patch("time.time", return_value=_NOW), \
            contextlib.redirect_stdout(stdout):
        def deliver_then_stop() -> None:
            client_cls.return_value.on_message(None, None, SimpleNamespace(topic="nornir/run/x/log/info", payload=raw))
            console._console_running = False

        client_cls.return_value.loop_start.side_effect = deliver_then_stop
        console.MQTTConsoleLoop("127.0.0.1", 1883, "Test", received.append)
    return received, stdout.getvalue()


def _expected_window_line(payload: dict[str, Any]) -> str:
    stamp = time.strftime('%H:%M:%S', time.localtime(payload.get('timestamp', _NOW)))
    return f"[{stamp}] [{payload.get('severity', 'info').upper()}] {payload.get('message', '')}"


class TestMqttLogPayloadDecoding(unittest.TestCase):

    def test_full_payload(self):
        payload = {'run_id': 'r', 'message': 'Copied 3 tiles', 'timestamp': 1_762_400_000.0, 'ts': 1.0,
                   'severity': 'warning'}
        raw = json.dumps(payload).encode()
        self.assertEqual(_console_output(raw)[0], ["WARNING:Copied 3 tiles"])
        self.assertEqual(_consolewindow_output(raw)[0], [_expected_window_line(payload)])

    def test_missing_fields_use_defaults(self):
        raw = b"{}"
        self.assertEqual(_console_output(raw)[0], ["INFO:"])
        stamp = time.strftime('%H:%M:%S', time.localtime(_NOW))
        self.assertEqual(_consolewindow_output(raw)[0], [f"[{stamp}] [INFO] "])

    def test_undecodable_payload_is_reported_not_delivered(self):
        for raw in (b"not json", b"\xff\xfe", b"[1, 2]", b'{"message": "\xff"}', '{"message": "m"}'.encode('utf-16')):
            for run in (_console_output, _consolewindow_output):
                received, printed = run(raw)
                self.assertEqual(received, [], (run.__name__, raw))
                self.assertIn("Error processing MQTT message:", printed, (run.__name__, raw))

    def test_non_string_severity_is_reported_not_delivered(self):
        raw = json.dumps({'message': 'm', 'severity': None}).encode()
        for run in (_console_output, _consolewindow_output):
            received, printed = run(raw)
            self.assertEqual(received, [], run.__name__)
            self.assertIn("Error processing MQTT message:", printed, run.__name__)

    def test_error_console_drops_non_error_severities(self):
        for severity, delivered in (("error", True), ("ERR", True), ("Critical", True), ("fatal", True),
                                    ("warning", False), ("info", False), (5, False)):
            raw = json.dumps({'message': 'm', 'severity': severity, 'timestamp': _NOW}).encode()
            received, _ = _consolewindow_output(raw, title="Error Console")
            self.assertEqual(len(received), 1 if delivered else 0, severity)

    def test_parse_log_payload_returns_decoded_payload(self):
        payload = {'message': 'm', 'severity': 'debug', 'timestamp': 12.5, 'section': 7}
        self.assertEqual(mqtt_config.parse_log_payload(json.dumps(payload).encode()),
                         (payload, 'm', 'debug', 12.5))
        with mock.patch("time.time", return_value=_NOW):
            self.assertEqual(mqtt_config.parse_log_payload(b'{"x": 1}'), ({'x': 1}, '', 'info', _NOW))

    @given(_payloads)
    @example({'message': 'ünïcode ✓', 'severity': 'Error'})
    @example({'severity': ''})
    def test_both_subscribers_decode_alike(self, payload: dict[str, Any]):
        raw = json.dumps(payload).encode()
        severity = payload.get('severity', 'info')
        console_lines, console_printed = _console_output(raw)
        window_lines, window_printed = _consolewindow_output(raw)
        if not isinstance(severity, str):
            self.assertEqual((console_lines, window_lines), ([], []))
            self.assertIn("Error processing MQTT message:", console_printed)
            self.assertIn("Error processing MQTT message:", window_printed)
            return
        self.assertEqual(console_lines, [f"{severity.upper()}:{payload.get('message', '')}"])
        self.assertEqual(window_lines, [_expected_window_line(payload)])


if __name__ == "__main__":
    unittest.main()
