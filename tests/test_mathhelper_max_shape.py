"""Tests for nornir_shared.mathhelper.max_shape.

The real caller (``stos_brute`` 180-degree disambiguation) passes a list of array
``.shape`` tuples and unpacks the result into height and width, so these tests pin that
contract: elementwise maximum over shapes of equal length, integer dtype, and an empty
integer array for no shapes.
"""
import unittest

import numpy as np
from hypothesis import example, given
from hypothesis import strategies as st
from nornir_shared.mathhelper import max_shape

# Image dimensions in real volumes reach the hundreds of thousands of pixels.
_dim = st.integers(min_value=0, max_value=1_000_000)


@st.composite
def _shape_lists(draw: st.DrawFn) -> list[tuple[int, ...]]:
    """Draw one or more shapes that all share the same number of dimensions."""
    ndim = draw(st.integers(min_value=1, max_value=4))
    count = draw(st.integers(min_value=1, max_value=6))
    return [tuple(draw(st.lists(_dim, min_size=ndim, max_size=ndim))) for _ in range(count)]


class TestMaxShape(unittest.TestCase):
    def test_two_image_shapes_like_stos_brute(self) -> None:
        source = np.zeros((512, 1024), dtype=np.float32)
        target = np.zeros((1024, 256), dtype=np.float32)
        height, width = max_shape([source.shape, target.shape])
        self.assertEqual((height, width), (1024, 1024))

    def test_result_is_integer_array(self) -> None:
        result = max_shape([(3, 4), (5, 2)])
        self.assertIsInstance(result, np.ndarray)
        self.assertEqual(result.dtype.kind, 'i')
        np.testing.assert_array_equal(result, [5, 4])

    def test_accepts_ndarray_shapes(self) -> None:
        result = max_shape([np.array([3, 9]), np.array([7, 1])])
        np.testing.assert_array_equal(result, [7, 9])

    def test_single_shape_is_returned(self) -> None:
        np.testing.assert_array_equal(max_shape([(6, 8)]), [6, 8])

    def test_empty_returns_empty_int_array(self) -> None:
        result = max_shape([])
        self.assertEqual(result.shape, (0,))
        self.assertEqual(result.dtype.kind, 'i')

    def test_does_not_mutate_input(self) -> None:
        shapes = [(1, 2), (3, 0)]
        max_shape(shapes)
        self.assertEqual(shapes, [(1, 2), (3, 0)])

    @given(_shape_lists())
    @example([(0, 0)])
    @example([(1_000_000, 1), (1, 1_000_000)])
    def test_matches_elementwise_max(self, shapes: list[tuple[int, ...]]) -> None:
        expected = [max(column) for column in zip(*shapes)]
        result = max_shape(shapes)
        self.assertEqual(result.dtype.kind, 'i')
        self.assertEqual(result.tolist(), expected)


if __name__ == '__main__':
    unittest.main()
