'''
Created on Jul 11, 2012

@author: Jamesan
'''
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


def NearestPowerOfTwo(val: float | int | NDArray[float] | NDArray[int]) -> NDArray[int]:
    return np.power(2, np.ceil(np.log2(val))).astype(int, copy=False)


def RoundingPrecision(dtype: DTypeLike) -> int:
    """Determine how many digits of precision we can get from a value at most"""
    if not dtype.kind == 'f':
        raise ValueError(f"Expected floating dtype, got {dtype}")

    return int(np.abs(np.log10(np.finfo(dtype).eps)))


if __name__ == '__main__':
    pass
