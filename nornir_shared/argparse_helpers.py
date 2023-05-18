import argparse
import re

from nornir_shared.misc import ListFromDelimited


def _IsNumberRange(argstr):
    '''Return true if the string has a hypen with two numbers between'''
    match = re.match(r'\d+\-\d+', argstr)
    return match


def _IntegerRangeToList(argstr: str) -> list[int]:
    '''
    :param argstr: Pair of integers separated by a hyphen defining a range, inclusive.  Example: 1-3 = [1,2,3]
    '''

    numbers = []
    try:
        (start, delimiter, end) = argstr.partition('-')
        start_int = int(start)
        end_int = int(end)

        numbers = range(start_int, end_int + 1)

    except ValueError as e:
        raise argparse.ArgumentTypeError()

    return numbers


def StringList(argstr):
    list_strs = ListFromDelimited(argstr)
    return list_strs


def IntegerList(argstr: str) -> list[int]:
    '''Return a list of integers based on a range defined by a string 
       :param argstr:  A string defining a list of numbers.  Commas separate values and hyphens define ranges.  Ex: 1, 3, 5-8, 11 = [1,3,5,6,7,8,11]
       :rtype: List of integers
    '''

    listNums = []
    argstr = argstr.replace(' ', '')

    for entry in argstr.strip().split(','):
        entry = entry.strip()

        if _IsNumberRange(entry):
            addedIntRange = _IntegerRangeToList(entry)
            listNums.extend(addedIntRange)
        else:
            try:
                val = int(entry)
                listNums.append(val)
            except ValueError:
                raise argparse.ArgumentTypeError("IntegerList function could not convert %s to integer value" % entry)

    return listNums


def IntegerPair(argstr: str) -> tuple[int, int]:
    '''Return a pair of integers based on a comma delimited string
    :param argstr:  A string defining one or two integers.  If only one integer is defined it is returned twice.  Commas separate values. Ex: 1,3
    :rtype: tuple of 2 integers
    '''

    argstr = argstr.replace(' ', '')

    arg_values = argstr.strip().split(',')
    if len(arg_values) > 2 or len(arg_values) <= 0:
        raise argparse.ArgumentTypeError(
            "Integer pair expects one number or two comma delimited numbers without spaces.  For example 1,3.  Passed value %s was invalid" % argstr)

    try:
        if len(arg_values) == 1:
            val = int(arg_values[0])
            return val, val
        else:
            return int(arg_values[0]), int(arg_values[1])
    except ValueError:
        raise argparse.ArgumentTypeError(f"IntegerPair function could not convert {argstr} to integer value(s)")


def Tuple(argstr: str) -> list[int]:
    if len(argstr) == 0:
        return None

    argstr = argstr.replace(' ', '')

    arg_values = argstr.strip().split(',')
    if len(arg_values) != 2:
        raise argparse.ArgumentTypeError(
            "Number of arguments to rectangle is incorrect.  Must be four numbers seperated by commas.  For example: MinX, MinY, MaxX, MaxY\nInput was: %s " % argstr)

    return IntegerList(argstr)


def Triple(argstr) -> list[int]:
    if len(argstr) == 0:
        return None

    argstr = argstr.replace(' ', '')

    arg_values = argstr.strip().split(',')
    if len(arg_values) != 3:
        raise argparse.ArgumentTypeError(
            "Number of arguments to rectangle is incorrect.  Must be four numbers seperated by commas.  For example: MinX, MinY, MaxX, MaxY\nInput was: %s " % argstr)

    return IntegerList(argstr)


def Quadruple(argstr) -> list[int]:
    if len(argstr) == 0:
        return None

    argstr = argstr.replace(' ', '')

    arg_values = argstr.strip().split(',')
    if len(arg_values) != 4:
        raise argparse.ArgumentTypeError(
            "Number of arguments to rectangle is incorrect.  Must be four numbers seperated by commas.  For example: MinX, MinY, MaxX, MaxY\nInput was: %s " % argstr)

    return IntegerList(argstr)


def FloatPair(argstr) -> tuple[int]:
    '''Return a pair of floats based on a comma delimited string
    :param argstr:  A string defining one or two floats.  If only one float is defined it is returned twice.  Commas separate values. Ex: 1,3
    :rtype: tuple of 2 integers
    '''

    argstr = argstr.replace(' ', '')

    arg_values = argstr.strip().split(',')
    if len(arg_values) > 2 or len(arg_values) <= 0:
        raise argparse.ArgumentTypeError(
            "Integer pair expects one number or two comma delimited numbers without spaces.  For example 1,3.  Passed value %s was invalid" % argstr)

    try:
        if len(arg_values) == 1:
            val = float(arg_values[0])
            return val, val
        else:
            return float(arg_values[0]), float(arg_values[1])
    except ValueError:
        raise argparse.ArgumentTypeError("FloatPair function could not convert %s to float value(s)" % argstr)


def FloatRange(argstr) -> list[float]:
    '''Return a pair of numbers based on a comma delimited string
    :param argstr:  A string defining either: A single number or a pair of hyphen delimited numbers indicating a range.
                    A trailing comma indicates the step size for the floating point values. Ex: 0:0.5:2 -> [0, 0.5, 1, 1.5, 2] 
    :rtype: list of floats
    '''

    listNums = []
    argstr = argstr.replace(' ', '')

    if argstr is None or len(argstr) == 0:
        return None

    arg_values = argstr.strip().split(':')
    if len(arg_values) > 3 or len(arg_values) <= 0:
        raise argparse.ArgumentTypeError(
            "Number pair expects at most one step size argument.  For example '0:0.5:2'. Passed value %s was invalid" % argstr)

    step_size = 1.0
    start_val = None
    end_val = None

    try:
        if len(arg_values) == 1:
            start_val = float(arg_values[0])
            end_val = float(arg_values[0])
        elif len(arg_values) == 2:
            start_val = float(arg_values[0])
            end_val = float(arg_values[1])
        elif len(arg_values) == 3:
            start_val = float(arg_values[0])
            step_size = float(arg_values[1])
            end_val = float(arg_values[2])
    except ValueError:
        raise argparse.ArgumentTypeError("FloatRange function could not convert %s to integer value(s)" % argstr)

    NextVal = start_val
    while NextVal <= end_val:
        listNums.append(NextVal)
        NextVal += step_size

    return listNums
