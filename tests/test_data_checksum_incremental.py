"""DataChecksum must hash a list incrementally rather than materialising it.

Review finding C00-P002 read the mosaic and volume checksum paths as
"materializes whole mosaic/transform lists", to be accepted at metadata sizes and
rejected if image bytes ever embed. Measuring it showed the list branch does not
materialise anything: it iterates and feeds md5 one item at a time, so peak
allocation is flat in the size of the data.

Measured before writing these tests, hashing one grid-transform string per tile:

    tiles         data         peak  peak/data
     1000       1.84 MB       0.01 MB      0.006
    10000      18.42 MB       0.08 MB      0.004
   100000     184.15 MB       0.77 MB      0.004

That is the property worth pinning. Rewriting the branch as
``m.update("".join(data).encode())`` would be an easy "simplification" and would
restore exactly the whole-list allocation the finding worried about, so the tests
below fail if anyone does.

The digest itself is a persisted value. These checksums live in volume XML and
drive staleness decisions, so a changed digest invalidates every cached artifact
in every volume. The reference implementation below pins the current bytes fed to
md5, including the 4-byte big-endian length prefix per item.
"""
from __future__ import annotations

import hashlib
import tracemalloc
import unittest

from nornir_shared.checksum import DataChecksum


def _reference_list_digest(items) -> str:
    """What DataChecksum feeds md5 for a list, spelled out."""
    m = hashlib.md5()
    for item in items:
        encoded = str(item).encode()
        m.update(len(encoded).to_bytes(4, byteorder='big', signed=False))
        m.update(encoded)
    return m.hexdigest()


def _peak_bytes(fn) -> int:
    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        fn()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return peak


def _transform_strings(count: int) -> list[str]:
    """Roughly the shape of a real mosaic: one ~2 KB transform string per tile."""
    return [f'tile{i:06d} ' + ('1.234 5.678 ' * 160) for i in range(count)]


class TestDigestIsUnchanged(unittest.TestCase):
    """Persisted digests must not move."""

    def test_list_digest_matches_the_reference(self):
        items = ['Hello World', 3, 4, 5]

        self.assertEqual(DataChecksum(items), _reference_list_digest(items))

    def test_length_prefix_prevents_boundary_collisions(self):
        """['ab','c'] and ['a','bc'] concatenate identically; they must not collide."""
        self.assertNotEqual(DataChecksum(['ab', 'c']), DataChecksum(['a', 'bc']))

    def test_order_matters(self):
        self.assertNotEqual(DataChecksum(['a', 'b']), DataChecksum(['b', 'a']))

    def test_a_list_is_not_the_same_as_its_concatenation(self):
        """The list branch is deliberately not the string branch."""
        self.assertNotEqual(DataChecksum(['abc', 'def']), DataChecksum('abcdef'))

    def test_empty_list(self):
        self.assertEqual(DataChecksum([]), hashlib.md5().hexdigest())

    def test_none_returns_none(self):
        self.assertIsNone(DataChecksum(None))

    def test_non_string_items_are_stringified(self):
        self.assertEqual(DataChecksum([2345, 123]), _reference_list_digest([2345, 123]))

    def test_differing_lists_differ(self):
        self.assertNotEqual(DataChecksum(_transform_strings(4)),
                            DataChecksum(_transform_strings(5)))

    def test_returns_a_32_character_string(self):
        result = DataChecksum(['a'])

        self.assertIsInstance(result, str)
        assert result is not None
        self.assertEqual(len(result), 32)


class TestPeakMemoryIsBounded(unittest.TestCase):
    """The property that makes finding C00-P002 an accept rather than a defect."""

    TILES = 20000

    def test_peak_is_far_below_the_size_of_the_data(self):
        items = _transform_strings(self.TILES)
        data_bytes = sum(len(v.encode()) for v in items)

        peak = _peak_bytes(lambda: DataChecksum(items))

        self.assertLess(peak, data_bytes // 10,
                        f'peak {peak:,} should be a small fraction of the '
                        f'{data_bytes:,} bytes hashed')

    def test_joining_the_list_really_would_cost_the_whole_size(self):
        """Confirms the bound above is a meaningful comparison, not a vacuous one."""
        items = _transform_strings(self.TILES)
        data_bytes = sum(len(v.encode()) for v in items)

        def join_whole():
            m = hashlib.md5()
            m.update(''.join(items).encode())
            return m.hexdigest()

        self.assertGreaterEqual(_peak_bytes(join_whole), data_bytes)

    def test_peak_does_not_grow_with_the_amount_of_data(self):
        """Ten times the data must not cost ten times the peak."""
        small = _transform_strings(2000)
        large = _transform_strings(20000)

        small_peak = _peak_bytes(lambda: DataChecksum(small))
        large_peak = _peak_bytes(lambda: DataChecksum(large))

        # Generous headroom: the point is sublinear, not identical.
        self.assertLess(large_peak, small_peak * 3,
                        f'peak grew from {small_peak:,} to {large_peak:,} for 10x data')

    def test_a_generator_would_not_work_and_is_not_claimed_to(self):
        """A non-list iterable falls through to the str() branch; pin that.

        Callers pass lists (``sorted(...)``, so already materialised by the caller).
        A generator hashes its repr, which is nonsense but stable, and no caller does
        it. Pinned so a future "accept any iterable" change is a deliberate one.
        """
        gen_digest = DataChecksum(x for x in ['a', 'b'])

        self.assertNotEqual(gen_digest, DataChecksum(['a', 'b']))


class TestStringAndBytesBranchesAreUnaffected(unittest.TestCase):

    def test_string_whitespace_is_stripped(self):
        self.assertEqual(DataChecksum('Hello World'), DataChecksum('HelloWorld'))
        self.assertEqual(DataChecksum('a b\tc\r\nd'), DataChecksum('abcd'))

    def test_bytes_whitespace_is_not_stripped(self):
        self.assertEqual(DataChecksum(b'a b'), hashlib.md5(b'a b').hexdigest())
        self.assertNotEqual(DataChecksum(b'a b'), DataChecksum(b'ab'))

    def test_int_falls_through_to_str(self):
        self.assertEqual(DataChecksum(2345), hashlib.md5(b'2345').hexdigest())


if __name__ == '__main__':
    unittest.main()
