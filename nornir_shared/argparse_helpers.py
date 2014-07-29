import re
import argparse

def _IsNumberRange(argstr):
    '''Return true if the string has a hypen with two numbers between'''
    match = re.match(r'\d+\-\d+', argstr)
    return match

def _NumberRangeToList(argstr):
    '''
    :param argstr: Pair of number seperated by a hyphen defining a range, inclusive.  Example: 1-3 = [1,2,3]
    '''

    numbers = []
    try:
        (start, delimiter, end) = argstr.partition('-')
        start_int = int(start)
        end_int = int(end)

        numbers = range(start_int, end_int + 1)

    except ValueError as ve:
        raise argparse.ArgumentTypeError()

    return numbers

def NumberList(argstr):
    '''Return a list of numbers based on a range defined by a string 
       :param argstr:  A string defining a list of numbers.  Commas seperate values and hyphens define ranges.  Ex: 1, 3, 5-8, 11 = [1,3,5,6,7,8,11]
       :rtype: List of integers
    '''

    listNums = []
    argstr = argstr.replace(' ', '')

    for entry in argstr.strip().split(','):
        entry = entry.strip()

        if(_IsNumberRange(entry)):
            addedIntRange = _NumberRangeToList(entry)
            listNums.extend(addedIntRange)
        else:
            try:
                val = int(entry)
                listNums.append(val)
            except ValueError as ve:
                raise argparse.ArgumentTypeError()

    return listNums
