'''
Created on Jul 11, 2012

@author: Jamesan
'''
import os
import six
import subprocess

import logging
import math
import shutil
import nornir_pools as Pools

import numpy as np

from . import prettyoutput
from . import processoutputinterceptor


def GetImageBpp(path):
    '''Returns how many bits per pixel the image at the provided path uses'''

    if not os.path.exists(path):
        raise ValueError('GetImageBpp File not found ' + path)

    cmd = 'identify -format "%z" ' + path
    proc = subprocess.Popen(cmd + " && exit", shell=True, stdout=subprocess.PIPE)
    proc.wait()

    [stdoutdata, stderrdata] = proc.communicate()

    bppStr = stdoutdata.strip()
    if len(bppStr) <= 0:
        return None

    bpp = int(stdoutdata.strip())

    return bpp

def GetImageColorspace(path):
    cmd = 'identify -format "colorspace:%[colorspace]\\n" ' + path
    colorspace = None
    try:
        proc = subprocess.Popen(cmd + " && exit", shell=True, stdout=subprocess.PIPE)
        [stdoutdata, stderrdata] = proc.communicate()

        lines = stdoutdata.splitlines()
        for line in lines:
            Parts = line.split(':')
            Header = Parts[0].strip()
            if Header == 'colorspace':
                colorspace = Parts[1]

    except:
        pass

    return colorspace


def GetImageStats(path):
    '''Returns [Min, Mean, Max, StdDev] of an image via ImageMagick'''

    cmd = 'identify -format "min:%[min]\\nmean:%[mean]\\nmax:%[max]\\nstandard deviation:%[standard-deviation]\\n" ' + path

    StdDev = None
    Mean = None
    Min = None
    Max = None

    try:
        proc = subprocess.Popen(cmd + " && exit", shell=True, stdout=subprocess.PIPE)
        [stdoutdata, stderrdata] = proc.communicate()

        lines = stdoutdata.splitlines()

        for line in lines:
            Parts = line.split(':')
            Header = Parts[0].strip()

            if Header == 'min':
                Min = float(Parts[1].strip('()'))

            if Header == 'max':
                Max = float(Parts[1].strip('()'))

            if Header == 'mean':
                Mean = float(Parts[1].strip('()'))

            if Header == 'standard deviation':
                StdDev = float(Parts[1].strip('()'))

    except:
        pass

    return [Min, Mean, Max, StdDev]



def IdentifyImage(ImageFilePath):
    '''Returns all output from identify as a dictionary'''
    cmd = 'identify -verbose ' + ImageFilePath
    try:
        NewP = subprocess.Popen(cmd + " && exit", shell=True, stdout=subprocess.PIPE)
    except:
        prettyoutput.Log('Eror calling ' + cmd)
        pass

    interceptor = processoutputinterceptor.ProcessOutputInterceptor.IdentifyOutputInterceptor(NewP, ImageFilePath)
    processoutputinterceptor.ProcessOutputInterceptor.IdentifyOutputInterceptor.Intercept(interceptor)

    return interceptor

def IsImageNumpyFormat(path):
    (root, ext) = os.path.splitext(path)
    return '.npy' == ext

def GetImageSize(path):
    '''
    :param str path: An image path or ndarray
    Returns size of image, [Width,Height]'''
    
    if isinstance(path, str):
        if not os.path.exists(path):
            return None        
               
        cmd = 'identify -format %G "' + path + '" '
        proc = subprocess.Popen(cmd + " && exit", shell=True, stdout=subprocess.PIPE)
        proc.wait()
    
        [stdoutdata, stderrdata] = proc.communicate()
    
        Output = stdoutdata.strip()
    
        if six.PY3:
            Output = Output.decode()
    
        Parts = Output.split('x')
        if len(Parts) < 2:
            raise ValueError("Invalid image file passed to GetImageSize: " + path)
    
        Width = int(Parts[0])
        Height = int(Parts[1])
    
        return (Width, Height)      
        

def IsValidImage(filename, ImageDir=None, Pool=None):
    ''':return: true/false if passed a single image.  Returns a list of bad images if passed a list.  Return empty list if filename is an empty list'''

    filenamelist = filename
    if not isinstance(filename, list):
        filenamelist = [filename]
     
    if len(filenamelist) == 0:
        return []
        
    IsSingleImage = len(filenamelist) == 1

    if Pool is None and not IsSingleImage:
        Pool = Pools.GetGlobalClusterPool()

    if ImageDir is None:
        ImageDir = ""

    TaskList = []
    SingleParameterProc = None

    InvalidImageList = []

    for filename in filenamelist:
        ImageFullPath = os.path.join(ImageDir, filename)
        if not os.path.exists(ImageFullPath):
            InvalidImageList.append(filename)
            continue
        
        (root, ext) = os.path.splitext(filename)
        if ext == '.npy':
            continue

        cmd = 'identify -format "  %f %G %b" ' + ImageFullPath

        try:
            if IsSingleImage:
                SingleParameterProc = subprocess.check_call(cmd + " && exit", shell=True)
            else:
                TaskList.append(Pool.add_process(filename, cmd + " && exit", shell=True))
        except subprocess.CalledProcessError as CPE:
            # Identify returned an error, so the file is bad
            InvalidImageList.append(filename) 
            continue
        
    if not Pool is None:
        Pool.wait_completion()

    # If check_call succeeded then we know the file is good and we can return
    if IsSingleImage:
        return len(InvalidImageList) == 0

    for Task in TaskList:
        if Task.returncode > 0:
            InvalidImageList.append(Task.name)

    return InvalidImageList


def Shrink(InFile, OutFile, ShrinkFactor):
    '''Shrinks the passed image file, return procedure handle of invoked command
       Quality follows image magick documentation for -quality flag.  Here are some
       test results from 774 1024x1024 images.  We had issues with ir-tools reading
       images compressed with 106.  Going to 0 resolved the issue.
       0: 614,393KB
       75: 614,393KB
       106: 475,508KB
       '''
    Percentage = (1 / float(ShrinkFactor)) * 100.0
    cmd = "Convert " + InFile + " -scale \"" + str(Percentage) + "%\" -quality 75  -colorspace gray " + OutFile
    prettyoutput.CurseString('Cmd', cmd)
    NewP = subprocess.Popen(cmd + " && exit", shell=True)
    return NewP


def __Fix_sRGB_String(path):
    '''Generate a string which will correctly convert an image from either linear or sRGB colorspaces to grayscale'''

    colorspace = GetImageColorspace(path)
    if colorspace is None:
        return " -colorspace Gray "

    if colorspace == "sRGB":
        return " -colorspace Gray " #" -set colorspace RGB -colorspace Gray " # I removed this on 1/29/2016.  Image magick was telling me a BMP image was an sRGB colorspace.  When I converted to RGB the conversion to PNG grayscale was shifting the image.

    return " -colorspace Gray "

def ConvertImagesInDict(ImagesToConvertDict, Flip=False, Flop=False, Bpp=8, Invert=False, bDeleteOriginal=False, RightLeftShift=None, AndValue=None, MinMax=None, Async=False):
    '''
    
    The key and value in the dictionary have the full path of an image to convert.
    MinMax is a tuple [Min,Max] passed to the -level parameter if it is not None
    RightLeftShift is a tuple containing a right then left then return to center shift which should be done to remove useless bits from the data
    I do not use an and because I do not calculate ImageMagick's quantum size yet.
    Every image must share the same colorspace
    '''

    if len(ImagesToConvertDict) == 0:
        return

    prettyoutput.CurseString('Stage', "ConvertImagesInDict")
    # numProcs = Config.NumProcs * 1.25 #ir-flip spends about half the time loading from disk...
                                        # doubling the number of procs should keep the CPU busy

    ProcPool = Pools.GetGlobalClusterPool()

    if not MinMax is None:
        if(MinMax[0] > MinMax[1]):
            prettyoutput.Log("Invalid MinMax parameter passed to ConvertImagesInDict")
            MinMax = None

    originalFileName = ""
    targetFileName = ""

    DepthStr = ' -depth ' + str(Bpp) + ' '

    InvertStr = ''
    if Invert:
        InvertStr = ' -negate '

#    LeftShiftStr = ''
    # if LeftShift > 0:
#        LeftShiftStr = " -evaluate leftshift " + str(LeftShift) + " "

    AndStr = ""
    if not AndValue is None:
        AndStr = " -evaluate And " + str(AndValue) + " "

    RightLeftShiftStr = ''
    if not RightLeftShift is  None:
        # This would be much clearer simply using an AND operation, but the ImageMagick output depends on the
        # bpp a particular build of IM was compiled for

        # Track the shift required to return to center


        if(RightLeftShift[0] > 0):
            RightLeftShiftStr = " -evaluate rightshift " + str(RightLeftShift[0]) + ' '

        if(RightLeftShift[1] > 0):
            RightLeftShiftStr = RightLeftShiftStr + " -evaluate leftshift " + str(RightLeftShift[0] + RightLeftShift[1])
        else:
            RightLeftShiftStr = RightLeftShiftStr + " -evaluate leftshift " + str(RightLeftShift[0])

        # " -evaluate rightshift " + str(RightLeftShift[1])

    MinMaxStr = ''
    if MinMax is not None and RightLeftShift is None:
        MinMaxStr = ' -level ' + str(MinMax[0]) + ',' + str(MinMax[1]) + ' '

    flipStr = ""
    if Flip:
        flipStr = " -flip "

    flopStr = ""
    if Flop:
        flopStr = " -flop "


    QualityStr = ''
    if Bpp <= 8:
        QualityStr = ' -quality 106 '

    SampleCmdPrinted = False

    colorspaceString = __Fix_sRGB_String(ImagesToConvertDict.keys()[0])

    tasks = []

    for f in ImagesToConvertDict.keys():
        OpNameStr = f + ' -> ' + ImagesToConvertDict[f]


        originalFileName = '"' + f + '"'

        # I move images to a temporary file, then rename at the end to prevent half-written files when the user uses CTRL+C
        temptargetFileName = '"' + ImagesToConvertDict[f] + '"'
        targetFileName = '"' + ImagesToConvertDict[f] + '"'

        if(os.path.exists(targetFileName)):
            prettyoutput.Log('Skipping existing file: ' + str(targetFileName))
            continue

        # prettyoutput.Log(f + ' -> ' + ImagesToConvertDict[f])



        # Find out if we need to flip the image
        if(originalFileName != targetFileName) or Flip or Flop:
            cmd = "convert " + originalFileName + InvertStr + AndStr + RightLeftShiftStr + MinMaxStr + colorspaceString + DepthStr + " -type optimize " + flipStr + flopStr + QualityStr + targetFileName
        else:
            # Nothing to do, source and target names match and no flipping required, skip everything
            return

        if not SampleCmdPrinted:
            SampleCmdPrinted = True
            prettyoutput.Log('Converting images, example command:')
            prettyoutput.CurseString('Cmd', cmd)
        # prettyoutput.CurseString('Cmd', cmd)
        tasks.append(ProcPool.add_process(OpNameStr, cmd, shell=True))

    # Keep waiting until all processes are finished
    # WaitForAllProcesses(Procs)
    if not Async:
        ProcPool.wait_completion()

    for t in tasks:
        if not t.returncode == 0:
            prettyoutput.LogErr("Failed to convert " + t.name)

    if bDeleteOriginal and (originalFileName != targetFileName):
        for f in ImagesToConvertDict.keys():
            # Don't delete unless the target file was created
            if(os.path.exists(ImagesToConvertDict[f])):
                prettyoutput.Log("Deleting: " + f)
                os.remove(f)


def TilesFromImage(ImageFullPath, OutputPath, ImageExt=None, TileSize=None, DownsampleList=None, GridTileCoordFormat=None, Logger=None):
    '''Create tiles for a single image'''

    if(GridTileCoordFormat is None):
        GridTileCoordFormat = 'd'

    GridTileNameTemplate = '%(prefix)sX%(X)' + GridTileCoordFormat + '_Y%(Y)' + GridTileCoordFormat + '%(postfix)s.png'

    if(Logger is None):
        Logger = logging.getLogger(__name__)

    prettyoutput.CurseString('Stage', "Tiles from Image")
    if ImageExt is None:
        ImageExt = 'png'

    if TileSize is None:
        TileSize = [256, 256]

    if DownsampleList is None:
        DownsampleList = [1, 2, 4, 8, 16, 32, 64, 128, 256]

    DownsampleList.sort()

    # Determine name of pyramid level
    Downsample = DownsampleList[0]
    DownSampleDirectory = os.path.join(OutputPath, '%03d' % Downsample)
    Logger.info("Assembling largest image using downsample " + str(Downsample) + " in directory " + str(DownSampleDirectory))

    try:
        os.makedirs(DownSampleDirectory)
    except:
        pass

    # path is an image name-
    [XDim, YDim] = GetImageSize(ImageFullPath)

    if(XDim % TileSize[0] > 0):
        XDim = XDim + (TileSize[0] - (XDim % TileSize[0]))

    if(YDim % TileSize[1] > 0):
        YDim = YDim + (TileSize[1] - (YDim % TileSize[1]))

    tilePrefix = 'tile_'

    XGridDim = int(math.ceil(float(XDim) / float(TileSize[0])))
    YGridDim = int(math.ceil(float(YDim) / float(TileSize[1])))

    tilePrefixPath = os.path.join(DownSampleDirectory, tilePrefix + '%d' + ImageExt)

    FilePostfix = ".png"

    XMLFilePath = os.path.join(DownSampleDirectory, str(Downsample) + ".xml")

    utils.Files.RemoveOutdatedFile(ImageFullPath, XMLFilePath)

    if not os.path.exists(XMLFilePath):
        # Convert is going to create a list of names.
        cmd = 'convert -crop ' + str(TileSize[0]) + 'x' + str(TileSize[1]) + ' ' + ImageFullPath + ' -depth 8 -quality 106 -type Grayscale -extent ' + str(XDim) + 'x' + str(YDim) + ' ' + tilePrefixPath
        prettyoutput.CurseString('Cmd', cmd)
        subprocess.call(cmd + ' && exit', shell=True)

        iFile = 0
        for iY in range(0, YGridDim):
            for iX in range(0, XGridDim):
                tileFileName = os.path.join(DownSampleDirectory, tilePrefix + str(iFile) + '.png')
                gridTileFileName = GridTileNameTemplate % {'prefix' : '', 'X' : iX, 'Y' : iY, 'postfix' : FilePostfix}
                gridTileFileName = os.path.join(DownSampleDirectory, gridTileFileName)

                shutil.move(tileFileName, gridTileFileName)

                iFile = iFile + 1

        WriteTilesetXML(XMLFilePath, XGridDim, YGridDim, TileSize[0], TileSize[1], Downsample, "")

    # Go back and downsample results by combining adjacent tiles to maintain constant tile size
    # start combining tiles into the next level if they exist
#    BasePathName = os.path.join(Dir, SectionName)
#    for i in range(1, len(DownsampleList)):
#
#        SourceDownsample = DownsampleList[i - 1]
#        TargetDownsample = DownsampleList[i]
#
#        if(SourceDownsample < SectionDownsample):
#            continue
#
#        InputImageDir = os.path.join(BasePathName, Config.DownsampleFormat % SourceDownsample)
#        XmlFilePath = os.path.join(BasePathName, Config.DownsampleFormat % SourceDownsample, SectionName + '.xml')
#        OutputImageDir = os.path.join(BasePathName, Config.DownsampleFormat % TargetDownsample)
#        OutputXmlFilePath = os.path.join(BasePathName, Config.DownsampleFormat % TargetDownsample, SectionName + '.xml')
#
#        utils.Files.RemoveOutdatedFile(XmlFilePath, OutputXmlFilePath)
#
#        if(os.path.exists(OutputXmlFilePath) == False):
#            BuildTilePyramids(Dir, InputImageDir, XmlFilePath, OutputImageDir, TargetDownsample)


    return

def WriteTilesetXML(XMLOutputPath, XDim, YDim, TileXDim, TileYDim, DownsampleTarget, FilePrefix, FilePostfix=".png"):
    # Write a new XML file
    prettyoutput.CurseString('Stage', "WriteTilesetXML : " + XMLOutputPath)
    with  open(XMLOutputPath, 'w') as newXML:

        newXML.write('<?xml version="1.0" ?> \n')
        newXML.write('<Level GridDimX=\"' + '%d' % XDim + '\" GridDimY=\"' + '%d' % YDim +
                     '\" TileXDim=\"' + '%d' % TileXDim + '\" TileYDim=\"' + '%d' % TileYDim +
                     '\" Downsample=\"' + '%d' % DownsampleTarget + '\" FilePrefix=\"' +
                     FilePrefix + '\" FilePostfix=\"' + FilePostfix + '\" /> \n')
    return


if __name__ == '__main__':
    print(IsValidImage(' C:\data\\rc2_mini_pipeline\\TEM\\0022\TEM\Raw8\TilePyramid\\004\\007.png'))
    pass