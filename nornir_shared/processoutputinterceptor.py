'''
Created on Dec 29, 2011

@author: Jamesan
'''
import prettyoutput
import os
import shutil
import random
import subprocess
# import nornir_pools as pools

class ProcessOutputInterceptor(object):
    '''
    Examines the output of the process in real time and calls lineparsefunc passing each line of output.
    lineparsefunc is called at least once with None input when the process terminates.
    lineparsefunc should be implemented by derived classes
    '''

    ProcessData = None  # An arbitrary object containing data about the process we are monitoring.
    Proc = None  # The process we are tracking


    def __init__(self, proc, processData=None):
        '''
        Constructor
        '''
        self.Proc = proc
        self.ProcessData = processData

    def Parse(self, line=None):
        '''Parse line of input from the process.  Should be overridden by a derived class'''
        raise Exception("No method defined for abstract class ProcessOutputInterceptor")

    @classmethod
    def Intercept(self, lineparseobj):
        '''Examines the output of the process in real time and calls lineparsefunc passing each line of output.
        lineparsefunc is called at least once with None input when the process terminates'''

        proc = lineparseobj.Proc

        if proc is None:
            return

        if proc.stdout is None:
            prettyoutput.Log("No stdout on process")
            return


        while True:

            line = proc.stdout.readline()
            if not line:
                break
            else:
                lineparseobj.Parse(line)

            # Break the loop if the process already terminated


        # This makes sure we call the lineparsefunc at least once
        lineparseobj.Parse(None)

class ProgressOutputInterceptor(ProcessOutputInterceptor):

    def Parse(self, line):
        '''Parse a line of output from a process looking for "percentage:".  Update the progress bar if found.
           ir-tools output progress info in this format:
           Task Percentage: 6.667e-001 until 9.000e-001
           '''

        if(line is None):
            prettyoutput.CurseProgress(None, 1, 1)
            return

        '''Processes a single line of output from the provided process and updates status as needed'''
        line = line.lower()
        if(line.find("percentage:") < 0):
            prettyoutput.Log(line)
            return

        try:
            parts = line.split(':')
            if(len(parts) < 2):
                return

            ProgressString = parts[1].strip()

            parts = ProgressString.split()

            Progress = float(parts[0].strip())

            prettyoutput.CurseProgress(None, Progress, 1)
        except:
            pass

        return

class StomOutputInterceptor(ProgressOutputInterceptor):

    def __init__(self, proc, processData=None, TargetDir=None, FilePrefix=None):
        self.Proc = proc
        self.FilePrefix = FilePrefix  # Prefix to add to files when we rename them
        if(self.FilePrefix is None):
            self.FilePrefix = ""

        self.ProcessData = processData
        self.Output = list()  # List of output lines
        self.LastLoadedFile = None  # Last file loaded by stom, used to rename the output
        self.TargetDir = TargetDir
        return

    def Parse(self, line):
        '''Parse a line of output from stom so we can figure out how to correctly name the output files.
           sample input: 
            Tool Percentage: 5.000000e-002
            loading 0009_ShadingCorrected-dapi_blob_1.png
            saving BruteResults/008.tif
            Tool Percentage: 5.000000e-002
            loading 0010_ShadingCorrected-dapi_blob_1.png
            saving BruteResults/009.tif
            Tool Percentage: 5.000000e-002'''

        # Line is called with None when the process has terminated which means it is safe to rename the created files
        if line is not None:
            # Let base class handle a progress percentage message
            ProgressOutputInterceptor.Parse(self, line)
            prettyoutput.Log(line)
            self.Output.append(line)
        else:
            for line in self.Output:




                '''Processes a single line of output from the provided process and updates status as needed'''
                try:
                    line = line.lower()
                    if(line.find("loading") >= 0):
                        parts = line.split()
                        FileName = os.path.basename(parts[1])
                        [name, ext] = os.path.splitext(FileName)
                        self.LastLoadedFile = name
                    elif(line.find("saving") >= 0):
                        parts = line.split()
                        outputFile = parts[1]

                        # Figure out if the output file has a different path
                        path = os.path.dirname(outputFile)

                        [name, ext] = os.path.splitext(outputFile)
                        if(ext is None):
                            ext = '.tif'

                        if(len(ext) <= 0):
                            ext = '.tif'

                        DestinationFile = os.path.join(path, self.FilePrefix + self.LastLoadedFile + ext)
                        if(self.TargetDir is not None):
                            DestinationFile = os.path.join(self.TargetDir, os.path.basename(self.FilePrefix + self.LastLoadedFile) + ext)

                        prettyoutput.Log("Renaming " + outputFile + " to " + DestinationFile)

                        shutil.move(outputFile, DestinationFile)
                except:
                    pass

        return

class IdentifyOutputInterceptor(ProcessOutputInterceptor):

    class Category:

        def __init__(self, Field, Value=None):
            self.name = Field
            self.value = Value


    def __init__(self, proc, processData=None):
        self.Proc = proc
        self.ProcessData = processData
        self.Output = list()  # List of output lines

        # Category to use for a given indentation level
        self.LastKeyForLevel = {0: None, 1: None}
        self.CategoryForLevel = {0: self, 1: self}

        self.LastIndentLevel = None

    @classmethod
    def indentCount(cls, line):
        '''Returns how many whitespace characters are at the beginning of the string'''
        if line is None:
            return 0

        count = 0

        for i in range(0, len(line)):
            if line[i].isspace():
                count = count + 1
            else:
                break

        return count / 2

    def Parse(self, line):

        if line is not None:
            indentLevel = IdentifyOutputInterceptor.indentCount(line)

            if(self.LastIndentLevel is None):
                self.LastIndentLevel = indentLevel

            line = line.strip()

            # Let base class handle a progress percentage message
            # prettyoutput.Log(line)
            self.Output.append(line)

            if(len(line) == 0):
                return

            parts = line.split(':', 1)
            if len(parts) <= 1:
                return

            if len(parts[0]) <= 0:
                return

            parts[0] = parts[0].replace(' ', '_')

            # If we increased indent level start a new category
            if indentLevel > self.LastIndentLevel and indentLevel > 1:
                key = self.LastKeyForLevel[self.LastIndentLevel]
                c = None
                if key in self.CategoryForLevel[self.LastIndentLevel].__dict__:
                    c = IdentifyOutputInterceptor.Category(key , self.CategoryForLevel[self.LastIndentLevel].__dict__[key])
                else:
                    c = IdentifyOutputInterceptor.Category(key)

                self.CategoryForLevel[indentLevel] = c
                self.CategoryForLevel[self.LastIndentLevel].__dict__[key] = c

            parts[0] = parts[0].strip().lower()
            parts[1] = parts[1].strip().lower()

            self.LastIndentLevel = indentLevel
            self.LastKeyForLevel[indentLevel] = parts[0]

            if parts[0] == 'geometry':
                dims = parts[1].split('x')
                layers = dims[1].split('+', 1)
                try:
                    self.TextureWidth = int(dims[0])
                    self.TextureHeight = int(layers[0])
                    self.layers = layers[1]
                except:
                    pass
            else:
                try:
                    self.CategoryForLevel[indentLevel].__dict__[parts[0]] = int(parts[1].split(' ')[0])
                    return
                except:
                    pass

                try:
                    self.CategoryForLevel[indentLevel].__dict__[parts[0]] = float(parts[1].split(' ')[0])
                    return
                except:
                    pass

                # prettyoutput.Log(parts[0] + ' : ' + parts[1])
                self.CategoryForLevel[indentLevel].__dict__[parts[0]] = parts[1]


