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
            except ValueError:
                raise argparse.ArgumentTypeError("NumberList function could not convert %s to integer value" % entry)

    return listNums

def NumberPair(argstr):
    '''Return a pair of numbers based on a comma delimited string
    :param argstr:  A string defining one or two numbers.  If only one number is defined it is returned twice.  Commas separate values. Ex: 1,3
    :rtype: tuple of 2 integers
    '''
    
    listNums = []
    argstr = argstr.replace(' ', '')
    
    arg_values = argstr.strip().split(',')
    if len(arg_values) > 2 or len(arg_values) <= 0:
        raise  argparse.ArgumentTypeError("Number pair expects one number or two comma delimited numbers without spaces.  For example 1,3.  Passed value %s was invalid" % argstr)
    
    try:
        if len(arg_values) == 1:
            val = int(arg_values[0])
            return (val, val)
        else:
            return (int(arg_values[0]), int(arg_values[1]))
    except ValueError:
        raise argparse.ArgumentTypeError("NumberPair function could not convert %s to integer value(s)" % argstr)