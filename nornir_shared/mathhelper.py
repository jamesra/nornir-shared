'''
Created on Jul 11, 2012

@author: Jamesan
'''

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
    
def NearestPowerOfTwo(val: float | int):
    return math.pow(2, math.ceil(math.log(val, 2)))


if __name__ == '__main__':
    pass
