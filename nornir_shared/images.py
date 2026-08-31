"""
Created on Jul 11, 2012

@author: Jamesan
"""
import concurrent.futures
import logging
import math
import multiprocessing
import os
import shutil
import subprocess

import numpy as np
from numpy.typing import NDArray

from PIL import Image

# Disable decompression bomb protection since we are dealing with huge images on purpose
Image.MAX_IMAGE_PIXELS = None

import PIL.ImageOps
# import nornir_pools
import nornir_shared

from . import prettyoutput
from . import processoutputinterceptor


def GetImageBpp(path: str) -> int | None:
    """Return bits-per-pixel for the image at ``path`` via ImageMagick identify."""

    if not os.path.exists(path):
        raise ValueError('GetImageBpp File not found ' + path)

    # Quote the path so spaces/special chars do not break the shell command.
    cmd = f'magick identify -format "%z" -verbose "{path}"'
    # Use communicate() only — wait() before reading stdout can deadlock on a full pipe.
    proc = subprocess.Popen(cmd + " && exit", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdoutdata, _stderrdata = proc.communicate()

    bppStr = stdoutdata.strip()
    if len(bppStr) <= 0:
        return None

    try:
        return int(bppStr.decode('utf-8') if isinstance(bppStr, bytes) else bppStr)
    except (ValueError, UnicodeDecodeError):
        logging.getLogger(__name__).warning("GetImageBpp: could not parse bpp from %r for %s", bppStr, path)
        return None


def GetImageColorspace(path: str) -> str | None:
    """Return ImageMagick colorspace name for ``path``, or None on failure."""
    cmd = f'magick identify -verbose -format "colorspace:%[colorspace]\\n" "{path}"'
    colorspace = None
    try:
        proc = subprocess.Popen(cmd + " && exit", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdoutdata, _stderrdata = proc.communicate()

        lines = stdoutdata.decode('utf-8').splitlines()
        for line in lines:
            Parts = line.split(':')
            Header = Parts[0].strip()
            if Header == 'colorspace':
                colorspace = Parts[1]

    except (OSError, UnicodeDecodeError, IndexError) as e:
        logging.getLogger(__name__).debug("GetImageColorspace failed for %s: %s", path, e)

    return colorspace


def GetImageStats(path: str) -> tuple[float | None, float | None, float | None, float | None]:
    """Return (Min, Mean, Max, StdDev) of an image via ImageMagick, or Nones on failure."""

    cmd = (
        f'magick identify -verbose -format '
        f'"min:%[min]\\nmean:%[mean]\\nmax:%[max]\\nstandard deviation:%[standard-deviation]\\n" '
        f'"{path}"'
    )

    StdDev = None
    Mean = None
    Min = None
    Max = None

    try:
        proc = subprocess.Popen(cmd + " && exit", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdoutdata, _stderrdata = proc.communicate()

        lines = stdoutdata.decode('utf-8').splitlines()

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

    except (OSError, UnicodeDecodeError, ValueError, IndexError) as e:
        logging.getLogger(__name__).debug("GetImageStats failed for %s: %s", path, e)

    return Min, Mean, Max, StdDev


def IdentifyImage(ImageFilePath: str):
    """Run ImageMagick identify and return an IdentifyOutputInterceptor, or None on failure."""
    cmd = f'magick identify -verbose "{ImageFilePath}"'
    try:
        NewP = subprocess.Popen(cmd + " && exit", shell=True, stdout=subprocess.PIPE)
    except OSError as e:
        prettyoutput.Log(f'Error calling {cmd}: {e}')
        return None

    interceptor = processoutputinterceptor.IdentifyOutputInterceptor(NewP, ImageFilePath)
    processoutputinterceptor.IdentifyOutputInterceptor.Intercept(interceptor)

    return interceptor


def IsImageNumpyFormat(path: str):
    (root, ext) = os.path.splitext(path)
    return '.npy' == ext


def GetImageSize(image_param: str | NDArray) -> NDArray[np.integer]:
    """
    :param image_param:
    """

    # if not os.path.exists(ImageFullPath):
    # raise ValueError("%s does not exist" % (ImageFullPath))

    if isinstance(image_param, np.ndarray):
        return np.array(image_param.shape, dtype=np.int32)

    (root, ext) = os.path.splitext(image_param)

    im = None
    try:
        if ext == '.npy':
            im = np.load(image_param, 'c')
            return im.shape
        else:
            with Image.open(image_param) as im:
                shape = (im.size[1], im.size[0])
                return np.array(shape, dtype=np.int32)
    except IOError:
        raise IOError("Unable to read size from %s" % image_param)
    finally:
        del im


def _is_numpy_extension(filename: str):
    (root, ext) = os.path.splitext(filename)
    return ext == '.npy'


def IsValidImage(filename: str) -> bool:
    """:return: true/false if passed a single image."""
    if not os.path.exists(filename):
        return False

    try:
        with Image.open(filename) as im:
            im.verify()
    except OSError as os_e:
        prettyoutput.Log("{0} -> {1}".format(filename, os_e.strerror))
        return False

    return True


def IsValidImageReturnName(filename: str) -> tuple[bool, str]:
    """:return: A tuple of (true/false, filename). """
    return IsValidImage(filename), filename


def AreValidImages(filenames: list[str], ImageDir: str | None = None, Pool=None) -> list[str]:
    """Check a list of images and report which ones are *not* valid.

    Despite the name, the return value lists the failures, not the successes, so an empty
    result means every image was valid.

    Entries are returned exactly as the caller supplied them, whatever they were: bare
    filenames stay bare, absolute paths stay absolute. ``ImageDir`` is used to locate the
    files but never appears in the result, so ``os.path.join(ImageDir, entry)`` still
    reaches the file, and an entry can be compared against or looked up by whatever the
    caller passed in. This holds for a one-element list as well as a longer one, which it
    did not before review #230.

    :param filenames: image paths to check, or a single path
    :param ImageDir: directory to resolve *filenames* against, if they are relative
    :return: the subset of *filenames* that are not valid images; empty if all are valid,
        or if *filenames* is empty
    """

    filenamelist = filenames
    if not isinstance(filenames, list):
        filenamelist = [filenames]

    if len(filenamelist) == 0:
        return []

    # If there is only one entry in the list do not bother to multiprocess
    if len(filenamelist) == 1:
        if _is_numpy_extension(filenamelist[0]):
            return []
        ImageDir = "" if ImageDir is None else ImageDir
        full = os.path.join(ImageDir, filenamelist[0]) if ImageDir else filenamelist[0]
        return [] if IsValidImage(full) else [filenamelist[0]]

    num_threads = multiprocessing.cpu_count() * 2
    # if num_threads > len(filenames):
    #    num_threads = len(filenames) + 1

    # if Pool is None:
    #     # Pool = nornir_pools.GetThreadPool('IsValidImage {0}'.format(filenamelist[0]), multiprocessing.cpu_count() * 2)
    #     # Pool = nornir_pools.GetGlobalLocalMachinePool()
    #     Pool = nornir_pools.GetLocalMachinePool("IOBound", num_threads=num_threads)

    ImageDir = "" if ImageDir is None else ImageDir

    TaskList = []
    SingleParameterProc = None

    InvalidImageList = []

    testable_image_extensions = list(filter(lambda filename: not _is_numpy_extension(filename), filenamelist))
    image_full_paths = [os.path.join(ImageDir, filename) for filename in testable_image_extensions]

    max_workers = min((os.process_cpu_count() or 1) * 2, 60)

    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        chunksize = len(image_full_paths) // (max_workers * 8)
        if chunksize < 1:
            chunksize = 1

        image_iterator = executor.map(IsValidImageReturnName, image_full_paths,
                                      chunksize=chunksize)

        # executor.map preserves input order, so pair each verdict back to the entry the
        # caller passed. Appending os.path.basename of the *joined* path used to be close
        # enough whenever ImageDir was supplied and the entries were bare filenames, but it
        # silently diverged in two ways: with ImageDir=None and absolute paths it stripped
        # the directory, leaving a result the caller could not resolve, and with entries
        # containing a subdirectory it dropped that component, so
        # MosaicFile.RemoveInvalidMosaicImages' `if InvalidImage in
        # self.ImageToTransformString` stopped matching and quietly kept the bad image.
        # It also did not match the single-file branch, which returns filenamelist[0]
        # unchanged. See review #230.
        for original, (result, _full_path) in zip(testable_image_extensions,
                                                  image_iterator, strict=True):
            if not result:
                InvalidImageList.append(original)
        #
        # # while image_task is not None:
        # #     if not image_task:
        # #         InvalidImageList.append(image_task)
        # #
        # #     image_task = image_iterator.__next__()
        # #
        #
        # for i, ImageFullPath in enumerate(image_full_paths):
        #
        #     # cmd = 'magick identify -verbose -format "  %f %G %b" ' + ImageFullPath
        #     filename = testable_image_extensions[i]
        #     try:
        #         TaskList.append(Pool.add_task(filename, IsValidImage, ImageFullPath))
        #     except subprocess.CalledProcessError as CPE:
        #         # Identify returned an error, so the file is bad
        #         InvalidImageList.append(filename)
        #         continue
        #
        # if Pool is not None:
        #     Pool.wait_completion()
        #     # Pool.shutdown()
        #     Pool = None
        #
        # # If check_call succeeded then we know the file is good and we can return
        # while len(TaskList) > 0:
        #     Task = TaskList.pop(0)
        #     # if Task.returncode == False:
        #     if Task.wait_return() is False:
        #         InvalidImageList.append(Task.name)

    return InvalidImageList


def __Fix_sRGB_String(path: str):
    """Generate a string which will correctly convert an image from either linear or sRGB colorspaces to grayscale"""

    colorspace = GetImageColorspace(path)
    if colorspace is None:
        return " -colorspace Gray "

    if colorspace == "sRGB":
        # I removed this on 1/29/2016.  Image magick was telling me a BMP image was an sRGB colorspace.  When I converted to RGB the conversion to PNG grayscale was shifting the image.
        return " -colorspace Gray "  # " -set colorspace RGB -colorspace Gray " 

    return " -colorspace Gray "


def InvertImage(input_image_fullpath: str, output_image_fullpath: str):
    with Image.open(input_image_fullpath) as img:
        inverted_img = PIL.ImageOps.invert(img)
        inverted_img.save(output_image_fullpath)


#
# def ConvertImagesInDict(ImagesToConvertDict, Flip=False, Flop=False, Bpp=None, Invert=False, bDeleteOriginal=False,
#                         RightLeftShift=None, AndValue=None, MinMax=None, Async=False):
#     """
#     The key and value in the dictionary have the full path of an image to convert.
#     MinMax is a tuple [Min,Max] passed to the -level parameter if it is not None
#     RightLeftShift is a tuple containing a right then left then return to center shift which should be done to remove useless bits from the data
#     I do not use an and because I do not calculate ImageMagick's quantum size yet.
#     Every image must share the same colorspace
#
#     :return: True if images were converted
#     :rtype: bool
#     """
#
#     if len(ImagesToConvertDict) == 0:
#         return False
#
#     if Bpp is None:
#         Bpp = GetImageBpp(ImagesToConvertDict.keys[0])
#
#     prettyoutput.CurseString('Stage', "ConvertImagesInDict")
#     # numProcs = Config.NumProcs * 1.25 #ir-flip spends about half the time loading from disk...
#     # doubling the number of procs should keep the CPU busy
#
#     ProcPool = nornir_pools.GetGlobalClusterPool()
#
#     if not MinMax is None:
#         if MinMax[0] > MinMax[1]:
#             prettyoutput.Log("Invalid MinMax parameter passed to ConvertImagesInDict")
#             MinMax = None
#
#     originalFileName = ""
#     targetFileName = ""
#
#     DepthStr = ' -depth ' + str(Bpp) + ' '
#
#     InvertStr = ''
#     if Invert:
#         InvertStr = ' -negate '
#
#     #    LeftShiftStr = ''
#     # if LeftShift > 0:
#     #        LeftShiftStr = " -evaluate leftshift " + str(LeftShift) + " "
#
#     AndStr = ""
#     if not AndValue is None:
#         AndStr = " -evaluate And " + str(AndValue) + " "
#
#     RightLeftShiftStr = ''
#     if not RightLeftShift is None:
#         # This would be much clearer simply using an AND operation, but the ImageMagick output depends on the
#         # bpp a particular build of IM was compiled for
#
#         # Track the shift required to return to center
#
#         if RightLeftShift[0] > 0:
#             RightLeftShiftStr = " -evaluate rightshift " + str(RightLeftShift[0]) + ' '
#
#         if RightLeftShift[1] > 0:
#             RightLeftShiftStr = RightLeftShiftStr + " -evaluate leftshift " + str(RightLeftShift[0] + RightLeftShift[1])
#         else:
#             RightLeftShiftStr = RightLeftShiftStr + " -evaluate leftshift " + str(RightLeftShift[0])
#
#         # " -evaluate rightshift " + str(RightLeftShift[1])
#
#     MinMaxStr = ''
#     if MinMax is not None and RightLeftShift is None:
#         MinMaxStr = ' -level ' + str(MinMax[0]) + ',' + str(MinMax[1]) + ' '
#
#     flipStr = ""
#     if Flip:
#         flipStr = " -flip "
#
#     flopStr = ""
#     if Flop:
#         flopStr = " -flop "
#
#     QualityStr = ''
#     if Bpp <= 8:
#         QualityStr = ' -quality 106 '
#
#     SampleCmdPrinted = False
#
#     colorspaceString = __Fix_sRGB_String(list(ImagesToConvertDict.keys())[0])
#
#     tasks = []
#
#     for f in ImagesToConvertDict.keys():
#         OpNameStr = f + ' -> ' + ImagesToConvertDict[f]
#
#         originalFileName = '"' + f + '"'
#
#         # I move images to a temporary file, then rename at the end to prevent half-written files when the user uses CTRL+C
#         temptargetFileName = '"' + ImagesToConvertDict[f] + '"'
#         targetFileName = '"' + ImagesToConvertDict[f] + '"'
#
#         if os.path.exists(targetFileName):
#             prettyoutput.Log('Skipping existing file: ' + str(targetFileName))
#             continue
#
#         # prettyoutput.Log(f + ' -> ' + ImagesToConvertDict[f])
#
#         # Find out if we need to flip the image
#         if (originalFileName != targetFileName) or Flip or Flop:
#             cmd = "magick convert " + originalFileName + InvertStr + AndStr + RightLeftShiftStr + MinMaxStr + colorspaceString + DepthStr + " -type optimize " + flipStr + flopStr + QualityStr + targetFileName
#         else:
#             # Nothing to do, source and target names match and no flipping required, skip everything
#             return False
#
#         if not SampleCmdPrinted:
#             SampleCmdPrinted = True
#             prettyoutput.Log('Converting images, example command:')
#             prettyoutput.CurseString('Cmd', cmd)
#         # prettyoutput.CurseString('Cmd', cmd)
#         tasks.append(ProcPool.add_process(OpNameStr, cmd, shell=True))
#
#     # Keep waiting until all processes are finished
#     # WaitForAllProcesses(Procs)
#     if not Async:
#         ProcPool.wait_completion()
#
#     for t in tasks:
#         if not t.returncode == 0:
#             prettyoutput.LogErr("Failed to convert " + t.name)
#
#     if bDeleteOriginal and (originalFileName != targetFileName):
#         for f in ImagesToConvertDict.keys():
#             # Don't delete unless the target file was created
#             if os.path.exists(ImagesToConvertDict[f]):
#                 prettyoutput.Log("Deleting: " + f)
#                 os.remove(f)
#
#     return len(tasks) > 0


def TilesFromImage(ImageFullPath, OutputPath, ImageExt=None, TileSize=None, DownsampleList=None,
                   GridTileCoordFormat=None, Logger=None):
    """Create tiles for a single image"""

    if GridTileCoordFormat is None:
        GridTileCoordFormat = 'd'

    GridTileNameTemplate = '%(prefix)sX%(X)' + GridTileCoordFormat + '_Y%(Y)' + GridTileCoordFormat + '%(postfix)s.png'

    if Logger is None:
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
    Logger.info(
        "Assembling largest image using downsample " + str(Downsample) + " in directory " + str(DownSampleDirectory))

    os.makedirs(DownSampleDirectory, exist_ok=True)

    # path is an image name-
    [YDim, XDim] = GetImageSize(ImageFullPath)

    if XDim % TileSize[0] > 0:
        XDim = XDim + (TileSize[0] - (XDim % TileSize[0]))

    if YDim % TileSize[1] > 0:
        YDim = YDim + (TileSize[1] - (YDim % TileSize[1]))

    tilePrefix = 'tile_'

    XGridDim = int(math.ceil(float(XDim) / float(TileSize[0])))
    YGridDim = int(math.ceil(float(YDim) / float(TileSize[1])))

    tilePrefixPath = os.path.join(DownSampleDirectory, tilePrefix + '%d' + ImageExt)

    FilePostfix = ".png"

    XMLFilePath = os.path.join(DownSampleDirectory, str(Downsample) + ".xml")

    nornir_shared.files.RemoveOutdatedFile(ImageFullPath, XMLFilePath)

    if not os.path.exists(XMLFilePath):
        # Convert is going to create a list of names.
        cmd = 'magick convert ' + ImageFullPath + ' -crop ' + str(TileSize[0]) + 'x' + str(
            TileSize[1]) + ' -depth 8 -quality 106 -type Grayscale -extent ' + str(XDim) + 'x' + str(
            YDim) + ' ' + tilePrefixPath
        prettyoutput.CurseString('Cmd', cmd)
        subprocess.call(cmd + ' && exit', shell=True)

        iFile = 0
        for iY in range(0, YGridDim):
            for iX in range(0, XGridDim):
                tileFileName = os.path.join(DownSampleDirectory, tilePrefix + str(iFile) + '.png')
                gridTileFileName = GridTileNameTemplate % {'prefix': '', 'X': iX, 'Y': iY, 'postfix': FilePostfix}
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

    return XGridDim, YGridDim


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
    print(IsValidImage(' C:\\data\\rc2_mini_pipeline\\TEM\\0022\\TEM\\Raw8\\TilePyramid\\004\\007.png'))
    pass
