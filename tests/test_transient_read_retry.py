"""Image reads retry the transient errors a CIFS share returns during an outage (RC3, storage2, 2026-11-21)."""

import errno
import os
import tempfile
import unittest
from unittest import mock

import nornir_shared.files
import nornir_shared.images
import numpy as np
from PIL import Image


class TestRetryTransientRead(unittest.TestCase):

    def _flaky(self, errors: list[OSError], result: object):
        def read():
            if errors:
                raise errors.pop(0)
            return result
        return read

    def test_retries_each_transient_errno(self) -> None:
        for code in (errno.EAGAIN, errno.ECONNABORTED, errno.EIO, errno.EFAULT, errno.EBUSY):
            sleeps: list[float] = []
            read = self._flaky([OSError(code, os.strerror(code))] * 2, 'ok')
            self.assertEqual(nornir_shared.files.retry_transient_read(read, 'x.png', sleep=sleeps.append), 'ok')
            self.assertEqual(len(sleeps), 2, errno.errorcode[code])

    def test_other_errors_raise_at_once(self) -> None:
        sleeps: list[float] = []
        read = self._flaky([FileNotFoundError(errno.ENOENT, 'missing')], 'ok')
        with self.assertRaises(FileNotFoundError):
            nornir_shared.files.retry_transient_read(read, 'x.png', sleep=sleeps.append)
        self.assertEqual(sleeps, [])

    def test_gives_up_after_attempts(self) -> None:
        sleeps: list[float] = []
        read = self._flaky([OSError(errno.EAGAIN, 'busy')] * 10, 'ok')
        with self.assertRaises(OSError):
            nornir_shared.files.retry_transient_read(read, 'x.png', attempts=3, sleep=sleeps.append)
        self.assertEqual(len(sleeps), 2)


class TestGetImageSizeRetries(unittest.TestCase):

    def test_size_read_survives_eagain(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, '889.png')
            Image.fromarray(np.zeros((30, 50), dtype=np.uint8)).save(path)
            real_open = Image.open
            failures = [OSError(errno.EAGAIN, 'Resource temporarily unavailable')]

            def flaky_open(*args, **kwargs):
                if failures:
                    raise failures.pop(0)
                return real_open(*args, **kwargs)

            with mock.patch.object(nornir_shared.images.Image, 'open', side_effect=flaky_open), \
                    mock.patch.object(nornir_shared.files.time, 'sleep'):
                size = nornir_shared.images.GetImageSize(path)
            np.testing.assert_array_equal(size, [30, 50])

    def test_unreadable_file_still_reports_path(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'broken.png')
            with open(path, 'wb') as f:
                f.write(b'not a png')
            with self.assertRaisesRegex(IOError, 'Unable to read size from'):
                nornir_shared.images.GetImageSize(path)


if __name__ == '__main__':
    unittest.main()
