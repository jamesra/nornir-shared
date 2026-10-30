"""FileChecksum must stream the file rather than read it whole.

``FileChecksum`` called ``DataChecksum(f.read())``, allocating the entire file in
memory.  Checksumming a multi-gigabyte volume or .mrc therefore cost its full
size in RAM.

The digest must not change.  These checksums are persisted in XML and drive
staleness decisions, so a different digest would invalidate every cached
artifact in every volume.  md5 is incremental, so hashing in chunks is
bit-for-bit identical to hashing one buffer, and the tests below pin that.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import tracemalloc
import unittest

from nornir_shared.checksum import DataChecksum, FileChecksum


class _FileTestCase(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _write(self, name: str, data: bytes) -> str:
        path = os.path.join(self._tmp.name, name)
        with open(path, 'wb') as f:
            f.write(data)
        return path


class TestDigestIsUnchanged(_FileTestCase):
    """The digest is a persisted value; it must match the old implementation."""

    def test_matches_raw_md5(self):
        data = bytes(range(256)) * 100
        path = self._write('payload.bin', data)

        self.assertEqual(FileChecksum(path), hashlib.md5(data).hexdigest())

    def test_matches_the_previous_whole_file_implementation(self):
        """DataChecksum(f.read()) is exactly what FileChecksum used to do."""
        data = os.urandom(64 * 1024) + b'\x00' * 1024
        path = self._write('previous.bin', data)

        with open(path, 'rb') as f:
            previous = DataChecksum(f.read())

        self.assertEqual(FileChecksum(path), previous)

    def test_empty_file(self):
        path = self._write('empty.bin', b'')

        self.assertEqual(FileChecksum(path), hashlib.md5(b'').hexdigest())
        self.assertEqual(FileChecksum(path), 'd41d8cd98f00b204e9800998ecf8427e')

    def test_single_byte_file(self):
        path = self._write('one.bin', b'x')
        self.assertEqual(FileChecksum(path), hashlib.md5(b'x').hexdigest())

    def test_file_spanning_many_read_chunks(self):
        """Multi-chunk reads must not reorder or drop data."""
        data = bytes(i % 251 for i in range(5 * 1024 * 1024))
        path = self._write('multichunk.bin', data)

        self.assertEqual(FileChecksum(path), hashlib.md5(data).hexdigest())

    def test_size_boundaries_around_typical_chunk_sizes(self):
        for size in (4095, 4096, 4097, 65535, 65536, 65537, 1048576, 1048577):
            with self.subTest(size=size):
                data = bytes(i % 256 for i in range(size))
                path = self._write(f'size_{size}.bin', data)
                self.assertEqual(FileChecksum(path), hashlib.md5(data).hexdigest())

    def test_whitespace_bytes_are_not_stripped(self):
        """Binary content is hashed verbatim.

        DataChecksum strips whitespace for *str* input but not for bytes, and
        FileChecksum has always taken the bytes path.  Pinned so nobody
        "simplifies" this into the whitespace-stripping branch.
        """
        data = b'a b\tc\r\n d'
        path = self._write('whitespace.bin', data)

        self.assertEqual(FileChecksum(path), hashlib.md5(data).hexdigest())
        self.assertNotEqual(FileChecksum(path),
                            hashlib.md5(b''.join(data.split())).hexdigest())

    def test_differing_files_differ(self):
        a = self._write('a.bin', b'\x01' * 4096)
        b = self._write('b.bin', b'\x02' * 4096)

        self.assertNotEqual(FileChecksum(a), FileChecksum(b))


class TestPeakMemoryIsBounded(_FileTestCase):
    """The point of the change.

    Reliable to assert here because FileChecksum is the only allocator in the
    measured region -- unlike the assemble buffers in #12, where the warp's own
    allocations dominated the peak.
    """

    SIZE = 16 * 1024 * 1024

    def _peak_bytes(self, fn) -> int:
        tracemalloc.start()
        try:
            tracemalloc.reset_peak()
            fn()
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        return peak

    def test_peak_is_far_below_the_file_size(self):
        path = self._write('large.bin', b'\xa5' * self.SIZE)

        peak = self._peak_bytes(lambda: FileChecksum(path))

        self.assertLess(peak, self.SIZE // 4,
                        f'peak {peak} should be well under the {self.SIZE} byte file')

    def test_whole_file_read_really_does_cost_the_file_size(self):
        """Confirms the comparison is meaningful rather than vacuous."""
        path = self._write('large2.bin', b'\xa5' * self.SIZE)

        def read_whole():
            with open(path, 'rb') as f:
                return DataChecksum(f.read())

        self.assertGreaterEqual(self._peak_bytes(read_whole), self.SIZE)


class TestErrorHandling(_FileTestCase):

    def test_missing_file_raises(self):
        missing = os.path.join(self._tmp.name, 'does_not_exist.bin')

        with self.assertRaises(FileNotFoundError):
            FileChecksum(missing)

    def test_directory_raises(self):
        with self.assertRaises(OSError):
            FileChecksum(self._tmp.name)

    def test_returns_a_string(self):
        path = self._write('str.bin', b'abc')

        result = FileChecksum(path)

        self.assertIsInstance(result, str)
        assert result is not None
        self.assertEqual(len(result), 32)


if __name__ == '__main__':
    unittest.main()
