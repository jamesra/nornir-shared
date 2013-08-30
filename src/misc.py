'''
Created on Jul 11, 2012

@author: Jamesan

Functions that are broadly used in Python programs but don't have a specific category
'''
import os
import logging
import time
import atexit

def RunWithProfiler(functionStr, outputpath = None):
    import cProfile
    import pstats
    import sys

    if outputpath is None:
        outputpath = "C:\\Temp"

    ProfilePath = os.path.join(outputpath, 'BuildProfile.pr')

    ProfileDir = os.path.dirname(ProfilePath)
    if not os.path.exists(ProfileDir):
        os.makedirs(ProfileDir)

    logger = logging.getLogger('RunWithProfiler')

    
    logger.info("Profiling: " + functionStr)

    try:
        cProfile.run(functionStr, ProfilePath)
    finally:
        if not os.path.exists(ProfilePath):
            logger.error("No profile file found" + ProfilePath)
            sys.exit()

        pr = pstats.Stats(ProfilePath)
        if not pr is None:
            pr.sort_stats('time')
            print str(pr.print_stats(.1))
            logger.info(str(pr.print_stats(0.1)))

    pr.print_callers(.1)

def SetupLogging(OutputPath = None, Level = None):

    if(Level is None):
        Level = logging.WARNING

    if OutputPath is None:
        OutputPath = "C:\\Temp"

    LogPath = os.path.join(OutputPath, 'Logs')

    if not os.path.exists(LogPath):
        os.makedirs(LogPath)

    formatter = logging.Formatter('%(levelname)s - %(name)s - %(message)s')

    logFileName = time.strftime('log-%M.%d.%y_%H.%M.txt', time.localtime())
    logFileName = os.path.join(LogPath, logFileName)
    errlogFileName = time.strftime('log-%M.%d.%y_%H.%M-Errors.txt', time.localtime())
    errlogFileName = os.path.join(LogPath, errlogFileName)
    logging.basicConfig(filename = logFileName, level = 'DEBUG', format = '%(levelname)s - %(name)s - %(message)s')

    eh = logging.FileHandler(errlogFileName)
    eh.setLevel(logging.WARNING)
    eh.setFormatter(formatter)

    ch = logging.StreamHandler()
    ch.setLevel(Level)
    ch.setFormatter(formatter)

    logger = logging.getLogger()
    logger.addHandler(eh)
    logger.addHandler(ch)

    eh.setFormatter(formatter)

    # Automatically shutdown logging when our process ends
    atexit.register(logging.shutdown)

def enum(*sequential, **named):
    '''Generates a dictionary of names to number values used as an enumeration'''
    enums = dict(zip(sequential, range(len(sequential))), **named)
    return type('Enum', (), enums)


def ArgumentsFromDict(dictObj):
    '''Generates an argument string for a command line program from a dictionary
    Takes a dictionary and returns a string with '-' prepended to the entry name, a space, and the entry string verbatim'''

    outstr = " "

    for entry in dictObj.iteritems():
        assert(isinstance(entry[0], str))
        outstr = outstr + " -" + entry[0] + " " + str(entry[1]) + " "

    return outstr

def GenNameFromDict(dictObj):
    '''Creates a mangled name unique to the contents of a dictionary.
       Take the first three letters from each entry name, append the value, and build a mangled name'''
    outstr = ""

    for entry in dictObj.items():
        assert(isinstance(entry[0], str))
        nameMangle = entry[0]
        if(len(nameMangle) > 3):
            nameMangle = nameMangle[0:3]

        ValueStr = ""
        if entry[1] is None:
            ValueStr = "None"
        elif(isinstance(entry[1], list)):
            ValueStr = str(entry[1][0])
            for e in entry[1][1:-1]:
                ValueStr = 'x' + str(e)
        else:
            ValueStr = str(entry[1])

        outstr = outstr + "_" + nameMangle + ValueStr

    return outstr


def SortedListFromDelimited(value, delimiter = None):
    if delimiter is None:
        delimiter = ','

    ValueList = value
    if isinstance(value, str):
        ValueList = []
        Values = str(value).strip().split(delimiter)
        ValueList = list()
        for Value in  Values:
            try:
                floatVal = float(Value)
                try:
                    intVal = int(Value)
                    ValueList.append(intVal)
                except:
                    ValueList.append(floatVal)
            except:
                ValueList.append(Value)
    elif not isinstance(value, list):
        ValueList = [value]

    ValueList.sort()
    return ValueList

def ListFromAttribute(attrib):
    return SortedListFromDelimited(attrib, delimiter = ',')


if __name__ == '__main__':
    pass