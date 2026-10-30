'''
Created on Jul 11, 2012

@author: Jamesan
'''
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray, DTypeLike


def ListMedian(items):
    '''Return the center item from a sorted list'''
    if items is None:
        return None

    if not isinstance(items, list):
        return None

    if len(items) == 0:
        return None

    if len(items) == 1:
        return items[0]

    tempList = sorted(items)
    length = len(tempList)

    if length % 2 == 1:
        return tempList[int((length - 1) / 2)]
    else:
        return (tempList[int(length / 2 - 1)] + tempList[int(length / 2)]) / 2


def NearestPowerOfTwo(val: float | int | NDArray[np.floating] | NDArray[np.integer]) -> NDArray[np.integer]:
    """Return the nearest power of two greater than or equal to val"""
    return np.power(2, np.ceil(np.log2(val))).astype(int, copy=False)


def RoundingPrecision(dtype: DTypeLike) -> int:
    """Determine how many digits of precision we can get from a value at most"""
    np_dtype = np.dtype(dtype)  # type: ignore[call-overload]
    if not np_dtype.kind == 'f':
        raise ValueError(f"Expected floating dtype, got {dtype}")

    return int(np.abs(np.log10(np.finfo(np_dtype).eps)))  # type: ignore[call-overload]


def max_shape(shapes: Sequence[Sequence[int] | NDArray[np.integer]]) -> NDArray[np.integer]:
    """Return the elementwise maximum of shapes that share one number of dimensions.

    Callers pass array ``.shape`` tuples (or integer arrays); an empty sequence returns an
    empty integer array.
    """
    if len(shapes) == 0:
        return np.zeros(0, dtype=int)

    stacked: NDArray[np.integer] = np.vstack(shapes)
    return np.max(stacked, axis=0)


if __name__ == '__main__':
    pass
