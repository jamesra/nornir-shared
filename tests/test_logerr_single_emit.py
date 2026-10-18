"""LogErr must emit each error exactly once locally and once to MQTT.

Regression: LogErr used to log the record, print it through an unstarted
ConsoleWindow, then log it again, so every error appeared three times in a
redirected run log (and twice on MQTT when MQTTLogHandler was installed).
"""

from __future__ import annotations

import contextlib
import io
import logging
import unittest
from unittest import mock

import nornir_shared.prettyoutput as prettyoutput
from nornir_shared.misc import MQTTLogHandler

LOGGER_NAME = 'tests.logerr_single_emit'
MESSAGE = 'ERROR high loss epoch=0 step=52 loss=62.6806'


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class TestLogErrSingleEmit(unittest.TestCase):
    def setUp(self) -> None:
        # Isolate from root so pytest/other handlers cannot add copies.
        self.logger = logging.getLogger(LOGGER_NAME)
        self._saved = (self.logger.handlers[:], self.logger.propagate, self.logger.level)
        self.logger.handlers = []
        self.logger.propagate = False
        self.logger.setLevel(logging.DEBUG)
        patcher = mock.patch.object(prettyoutput, '_publish_mqtt_message')
        self.publish = patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self) -> None:
        self.logger.handlers, self.logger.propagate, level = self._saved
        self.logger.setLevel(level)

    def test_one_record_and_no_stdout(self) -> None:
        handler = _ListHandler()
        self.logger.addHandler(handler)
        out = io.StringIO()
        for eclipse in (False, True):
            handler.records.clear()
            self.publish.reset_mock()
            with mock.patch.object(prettyoutput, 'ECLIPSE', eclipse), contextlib.redirect_stdout(out):
                prettyoutput.LogErr(MESSAGE, calling_func_name=LOGGER_NAME)
            self.assertEqual(len(handler.records), 1, f'ECLIPSE={eclipse}')
            self.assertIn(MESSAGE, handler.records[0].getMessage())
            self.publish.assert_called_once()
        self.assertEqual(out.getvalue(), '', 'LogErr must not print a duplicate to stdout')

    def test_mqtt_handler_does_not_republish(self) -> None:
        self.logger.addHandler(MQTTLogHandler())
        prettyoutput.LogErr(MESSAGE, calling_func_name=LOGGER_NAME)
        self.publish.assert_called_once()
        topic_key, text = self.publish.call_args.args[:2]
        self.assertEqual(topic_key, 'error')
        self.assertIn(MESSAGE, text)

    def test_no_handlers_still_reaches_stderr_once(self) -> None:
        err = io.StringIO()
        out = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            prettyoutput.LogErr(MESSAGE, calling_func_name=LOGGER_NAME)
        self.assertEqual(err.getvalue().count(MESSAGE), 1)
        self.assertEqual(out.getvalue(), '')


if __name__ == '__main__':
    unittest.main()
