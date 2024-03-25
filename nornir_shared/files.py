"""
Created on Jul 11, 2012

@author: Jamesan
"""
import collections.abc
import concurrent.futures
import datetime
import glob
import os
import re
import time
import typing
from enum import IntEnum, auto
from typing import Sequence

import nornir_shared
from nornir_shared import prettyoutput

DownsampleFormat = '%03d'
DefaultLevels = frozenset([1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024])
DefaultLevelStrings = frozenset([DownsampleFormat % lev for lev in DefaultLevels])
DefaultExcludeList = frozenset(
    ["clahe", "mbproj", "8-bit", "16-bit", "blob", "mosaic", "tem", "temp", "bruteresults", "gridresults", "results",
     "registered"])


class FileTimeComparison(IntEnum):
    MODIFIED = auto()
    CREATION = auto()


class FindFileResult(typing.NamedTuple):
    path: str  # Path that matched criteria
    matched_files: list[str] | None  # Files requested by the Match paramter


def rmtree(directory: str, ignore_errors: bool = False):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        for root, dirs, files in os.walk(directory, topdown=False):
            try:
                files_futures = executor.map(os.remove, [os.path.join(root, f) for f in files])
                t = list(files_futures)  # Force the map operation to complete
            except OSError as e:
                if ignore_errors is True:
                    prettyoutput.error(f'{e}')
                else:
                    raise e

            try:
                dir_futures = executor.map(os.rmdir, [os.path.join(root, d) for d in dirs])
                d = list(dir_futures)  # Force the map operation to complete
            except OSError as e:
                if ignore_errors is True:
                    prettyoutput.error(f'{e}')
                else:
                    raise e

    try:
        os.rmdir(directory)
    except OSError as e:
        if ignore_errors is True:
            # prettyoutput.error(f'{e}')
            pass
        else:
            raise e

    return


def NewestFile(fileA: str, fileB: str, comparison: FileTimeComparison = FileTimeComparison.MODIFIED) -> str | None:
    """:return: Newest file, or fileB in the case of a tie. Return None in case of an error."""

    if fileA is None:
        raise ValueError("fileA should not be None")

    if fileB is None:
        raise ValueError("fileB should not be None")

    if comparison != FileTimeComparison.MODIFIED and comparison != FileTimeComparison.CREATION:
        raise ValueError('Unknown comparison')

    AStats = None
    try:
        AStats = os.stat(fileA)
    except FileNotFoundError:
        prettyoutput.Log(f"NewestFile: File not found {fileA}")
        return None

    BStats = None
    try:
        BStats = os.stat(fileB)
    except FileNotFoundError:
        prettyoutput.Log(f"NewestFile: File not found {fileB}")
        return None

    atime = AStats.st_mtime_ns if comparison == FileTimeComparison.MODIFIED else AStats.st_ctime_ns
    btime = BStats.st_mtime_ns if comparison == FileTimeComparison.MODIFIED else BStats.st_ctime_ns

    if atime > btime:
        return fileA
    elif atime < btime:
        return fileB
    else:
        return fileB


def IsOutdated(ReferenceFilename, TestFilename, comparison: FileTimeComparison = FileTimeComparison.MODIFIED) -> bool:
    """
    :return: True if TestFilename is older than ReferenceFilename
    """
    newestFile = NewestFile(ReferenceFilename, TestFilename)

    return newestFile is None or newestFile == ReferenceFilename


def IsOlderThan(TestPath: str, DateTime: str | float | int | datetime.datetime | datetime.date | time.struct_time,
                DateTimeFormat: str | None = None,
                comparison: FileTimeComparison = FileTimeComparison.MODIFIED) -> bool:
    """Return true if the file is older than the specified date string
    :param str TestPath: Path we are using to retrieve the last modified time from
    :param str DateTime: Either a string in the specified format or a floating point number representing seconds past the Unix epoch.
    :param str DateTimeFormat: Optional, if a string is passed this parameter indicates the string format.  Defaults to "%d %b %Y %H:%M:%S"
    :returns: True if the file is older than the reference date
    """
    if comparison != FileTimeComparison.MODIFIED and comparison != FileTimeComparison.CREATION:
        raise ValueError('Unknown comparison')

    if DateTimeFormat is None:
        DateTimeFormat = "%d %b %Y %H:%M:%S"

    if isinstance(DateTime, float):
        DateTime = DateTime
    elif isinstance(DateTime, int):
        DateTime = float(DateTime)
    elif isinstance(DateTime, str):
        DateTime = datetime.datetime.strptime(DateTime, DateTimeFormat).timestamp()
    elif isinstance(DateTime, datetime.datetime):
        DateTime = DateTime.timestamp()
    elif isinstance(DateTime, datetime.date):
        DateTime = datetime.datetime.fromordinal(DateTime.toordinal()).timestamp()
    elif isinstance(DateTime, time.struct_time):
        DateTime = DateTime
    else:
        raise TypeError("IsOlderThan expects a string or floating parameter to compare against, got %s" % str(DateTime))

    # modified_time = datetime.datetime.fromtimestamp()
    file_time = os.path.getmtime(TestPath) if comparison == FileTimeComparison.MODIFIED else os.path.getctime(TestPath)
    return file_time < DateTime


def OutdatedFile(ReferenceFilename: str, TestFilename: str,
                 comparison: FileTimeComparison = FileTimeComparison.MODIFIED) -> bool:
    """Return true if ReferenceFilename modified time is newer than the TestFilename"""
    return NewestFile(ReferenceFilename, TestFilename, comparison) == ReferenceFilename


def RemoveOutdatedFile(ReferenceFilename: str,
                       remove_if_outdated: str | datetime.datetime | datetime.date | time.struct_time | float | int,
                       comparison: FileTimeComparison = FileTimeComparison.MODIFIED) -> bool:
    """
    Takes a ReferenceFilename and TestFilename.  Removes TestFilename if it is newer than the reference
    :return: True if the input parameter is outdated
    """
    needs_removing = False

    if ReferenceFilename is None:
        raise ValueError("Cannot compare to None")

    if isinstance(remove_if_outdated, str):
        needs_removing = OutdatedFile(ReferenceFilename, remove_if_outdated, comparison=comparison)
    elif isinstance(remove_if_outdated, datetime.datetime):
        needs_removing = IsOlderThan(ReferenceFilename, remove_if_outdated, comparison=comparison)
    elif isinstance(remove_if_outdated, datetime.date):
        needs_removing = IsOlderThan(ReferenceFilename, remove_if_outdated, comparison=comparison)
    elif isinstance(remove_if_outdated, time.struct_time):
        needs_removing = IsOlderThan(ReferenceFilename, remove_if_outdated, comparison=comparison)
    elif isinstance(remove_if_outdated, float):
        needs_removing = IsOlderThan(ReferenceFilename, remove_if_outdated, comparison=comparison)
    elif isinstance(remove_if_outdated, int):
        needs_removing = IsOlderThan(ReferenceFilename, remove_if_outdated, comparison=comparison)
    else:
        raise ValueError(f"Unexpected type to compare against {remove_if_outdated.__class__}")

    #   [name, ext] = os.path.splitext(TestFilename)

    if needs_removing:

        if isinstance(remove_if_outdated, str):
            try:
                prettyoutput.Log(
                    f'Removing outdated file: {remove_if_outdated}, outdated compared to {ReferenceFilename}')
                os.remove(remove_if_outdated)
                return True
            except Exception as e:
                prettyoutput.Log(f'Exception removing outdated file: {remove_if_outdated}\n{e}')
                pass

    return needs_removing


def RemoveInvalidImageFile(TestFilename: str) -> bool:
    """Takes a ReferenceFilename and TestFilename.  Removes TestFilename if it is newer than the reference"""
    if not nornir_shared.images.IsValidImage(TestFilename):
        try:
            prettyoutput.Log('Removing invalid image file: ' + TestFilename)
            os.remove(TestFilename)
            return True
        except Exception as e:
            prettyoutput.Log(f'Exception removing invalid image file: {TestFilename}\n{e}')
            return True

    #   [name, ext] = os.path.splitext(TestFilename)
    return False


def RecurseSubdirectories(Path: str,
                          RequiredFiles: str | Sequence[str] | re.Pattern | None = None,
                          ExcludedFiles: str | Sequence[str] | re.Pattern | None = None,
                          MatchNames: str | Sequence[str] | re.Pattern | None = None,
                          ExcludeNames: Sequence[str] | None = None,
                          ExcludedDownsampleLevels: list[int] | None = None,
                          caseInsensitive: bool = True) -> list[FindFileResult]:
    """Recurse Subdirectories adds Path and every subdirectory to a list
       If MatchNames is not null we yield the matching directory, but do not recurse subdirectories underneath.  A directory name matching this parameter will always be included, overriding the RequiredFiles or ExcludeFiles restrictions.
       If ExcludeNames  is not null we do not add the directory to the list and do not recurse subdirectories/
       if RequiredFiles is not null the directory must contain the required file before we add it.  No subdirectories are searched.
       if ExcludeFiles is not null and the directory contains a matching file we do not add it or search subdirectories
       ExcludedDownsampleLevels and ExcludeNames must be an empty list to avoid population with default values.
       RequiredFiles and ExcludeFiles can be either a regular expression string or a list of specific filenames.
       Excluded files take priority over RequiredFiles
       """

    generator = RecurseSubdirectoriesGenerator(Path=Path, RequiredFiles=RequiredFiles, ExcludedFiles=ExcludedFiles,
                                               MatchNames=MatchNames, ExcludeNames=ExcludeNames,
                                               ExcludedDownsampleLevels=ExcludedDownsampleLevels,
                                               caseInsensitive=caseInsensitive)
    return list(generator)


def ensure_regex_or_set(param: str | re.Pattern | Sequence[str] | None, caseInsensitive: bool = False) -> re.Pattern[
                                                                                                              typing.AnyStr] | \
                                                                                                          frozenset[
                                                                                                              str] | None:
    if param is None:
        return None
    elif isinstance(param, re.Pattern):
        return param
    elif isinstance(param, str):
        # helper change, if it starts with a *, then assume it is a file expression and convert it crudely
        if param[0] == '*':
            param = param.replace('.', '\.')
            param = param.replace('*', '.*')
            param += '$'
        return re.compile(param, re.IGNORECASE if caseInsensitive else 0)
    else:
        return ensure_string_set(param, caseInsensitive)


def ensure_string_set(param: str | Sequence[str] | None, caseInsensitive: bool = False) -> frozenset[str] | None:
    """Ensure the input is a set of lowercase strings.  If input is none use defaultValue if provided"""
    if param is None:
        return None

    if isinstance(param, str):
        return frozenset([param.lower() if caseInsensitive else param])

    if (isinstance(param, frozenset) or isinstance(param, set)) is False:
        if not isinstance(param, collections.abc.Iterable):
            param = [param]

        if caseInsensitive:
            param = [n.lower() if isinstance(n, str) else n for n in param]

        param = frozenset(param)

    return param


def RecurseSubdirectoriesGenerator(Path: str,
                                   RequiredFiles: str | Sequence[str] | re.Pattern | None = None,
                                   ExcludedFiles: str | Sequence[str] | re.Pattern | None = None,
                                   MatchNames: str | Sequence[str] | re.Pattern | None = None,
                                   ExcludeNames: Sequence[str] | None = None,
                                   ExcludedDownsampleLevels: list[int] | None = None,
                                   caseInsensitive: bool = True) -> typing.Generator[FindFileResult, None, None]:
    """
    Same as RecurseSubdirectories, but returns a generator
    :param str Path: Path to search
    :param RequiredFiles: A regular expression or list of files which must be present in the directory
    :param ExcludedFiles: A regular expression or list of files which must not be present in the directory
    :param MatchNames: A list of directory names which will be included in the output.
    :param ExcludeNames: A list of directory names which will be excluded from the output
    :param ExcludedDownsampleLevels: A list of downsample levels which will be excluded from the output
    :param bool caseInsensitive: If true then directory names are compared in a case-insensitive manner
    :return: A tuple with (directory, [files]) where files match the filter criteria if specified, otherwise an empty list
    """

    yield from _RecurseSubdirectoriesGeneratorTask(
        Path,
        RequiredFiles=RequiredFiles,
        ExcludedFiles=ExcludedFiles,
        MatchNames=MatchNames,
        ExcludeNames=ExcludeNames,
        ExcludedDownsampleLevels=ExcludedDownsampleLevels,
        caseInsensitive=caseInsensitive)


def _SeparateFilesAndDirs(entries) -> tuple[list[os.DirEntry], list[os.DirEntry]]:
    files = []
    dirs = []
    for e in entries:
        if e.is_file():
            files.append(e)
        elif e.is_dir():
            dirs.append(e)

    return files, dirs


def _RecurseSubdirectoriesGeneratorTask(
        Path: str,
        RequiredFiles: str | Sequence[str] | re.Pattern | None = None,
        ExcludedFiles: str | Sequence[str] | re.Pattern | None = None,
        MatchNames: str | Sequence[str] | re.Pattern | None = None,
        ExcludeNames: str | Sequence[str] | None = None,
        ExcludedDownsampleLevels: list[int] | None = None,
        caseInsensitive: bool = True,
) -> typing.Generator[FindFileResult, None, None]:
    """Same as RecurseSubdirectories, but returns a generator
    :param str Path: Path to search
    :param RequiredFiles: A regular expression or list of files which must be present in the directory
    :param ExcludedFiles: A regular expression or list of files which must not be present in the directory
    :param MatchNames: A list of directory names which will be included in the output.
    :param ExcludeNames: A list of directory names which will be excluded from the output
    :param ExcludedDownsampleLevels: A list of downsample levels which will be excluded from the output
    :param bool caseInsensitive: If true then directory names are compared in a case-insensitive manner
    :return: A tuple with (directory, [files]) where files match the filter criteria if specified, otherwise an empty list
    """
    RequiredFiles = ensure_regex_or_set(RequiredFiles, caseInsensitive=caseInsensitive)
    ExcludedFiles = ensure_regex_or_set(ExcludedFiles, caseInsensitive=caseInsensitive)
    MatchNames = ensure_regex_or_set(MatchNames, caseInsensitive=caseInsensitive)
    ExcludedDownsampleLevels = DefaultLevels if ExcludedDownsampleLevels is None else ensure_string_set(
        ExcludedDownsampleLevels, caseInsensitive=caseInsensitive)
    ExcludeNames = DefaultExcludeList if ExcludeNames is None else ensure_string_set(ExcludeNames,
                                                                                     caseInsensitive=caseInsensitive)

    if ExcludeNames is not None and ExcludedDownsampleLevels is not None:
        ExcludeNames = ExcludeNames.union([DownsampleFormat % level for level in ExcludedDownsampleLevels])
    elif ExcludedDownsampleLevels is not None:
        ExcludeNames = frozenset([DownsampleFormat % level for level in ExcludedDownsampleLevels])

    # If we made it this far we did not match either Required or Excluded Files

    # Recursively list the subdirectories, catch any exceptions.  This can occur if we don't have permissions
    try:
        with os.scandir(Path) as Path_iter:
            files, dirs = _SeparateFilesAndDirs(Path_iter)
        # entries = list(Path_iter)
        # files = filter(lambda e: e.is_file, entries)
        # dirs = filter(lambda e: e.is_dir, entries)

        excluded = False
        known_required_files = []

        # First, check if our root directory (Path) contains any required or excluded files, and if it meets criteria yield the root directory
        if (RequiredFiles is None or not RequiredFiles) and \
                (ExcludedFiles is None or not ExcludedFiles):
            # Automatically pass the test of whether the directory contains or does not have certain files
            excluded = False
        else:
            excluded = False
            for file in files:
                # Check if the directory is excluded
                if not excluded and ExcludedFiles is not None:
                    excluded = excluded or check_if_str_matches(file.name, ExcludedFiles)
                    if excluded:
                        break

                if RequiredFiles is not None and check_if_str_matches(file.name, RequiredFiles):
                    known_required_files.append(file.name)
                    # has_required_files = has_required_files or 

        # Do not yield the directory since it contains an excluded file
        if excluded:
            return

        # Yield the directory if it has a required file or if there are no requirements
        if len(known_required_files) > 0:
            yield Path, known_required_files
        elif (RequiredFiles is None or not RequiredFiles) and \
                (MatchNames is None or not MatchNames):
            yield FindFileResult(path=Path, matched_files=[])

        dir_search_tasks = []

        # Filter out directories we do not want to recurse into
        dirs = set(dirs)

        dirs_with_dots = list(filter(lambda d: d.path.find('.') > -1, dirs))
        dirs = dirs.difference(dirs_with_dots)

        # Skip if it contains words from the exclude list
        if ExcludeNames is not None:
            excluded_dir_names = filter(lambda d: d.name.lower() in ExcludeNames, dirs)
            dirs = dirs.difference(excluded_dir_names)

        if len(dirs) > 3:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(dirs), 8),
                                                       thread_name_prefix=Path + '_') as executor:
                for d in dirs:
                    fullpath = os.path.join(Path, d.path)
                    if check_if_str_matches(d.name, MatchNames, caseInsensitive):
                        yield FindFileResult(path=fullpath, matched_files=[])
                        continue  # We do not iterate the subdirectories of MatchNames

                    # If we are not matching names or requiring files then return the path
                    # if MatchNames is None and RequiredFiles is None:
                    # yield fullpath

                    # Add directory tree to list and keep looking

                    # yield from RecurseSubdirectoriesGenerator(fullpath,
                    #                        RequiredFiles=RequiredFiles,
                    #                        ExcludedFiles=ExcludedFiles,
                    #                        MatchNames=MatchNames,
                    #                        ExcludeNames=ExcludeNames,
                    #                        ExcludedDownsampleLevels=ExcludedDownsampleLevels)

                    task = executor.submit(_RecurseSubdirectoriesListTask,
                                           Path=fullpath,
                                           RequiredFiles=RequiredFiles,
                                           ExcludedFiles=ExcludedFiles,
                                           MatchNames=MatchNames,
                                           ExcludeNames=ExcludeNames,
                                           ExcludedDownsampleLevels=ExcludedDownsampleLevels)
                    dir_search_tasks.append(task)

                    # for subd in RecurseSubdirectoriesGenerator(fullpath,
                    #                       RequiredFiles=RequiredFiles,
                    #                       ExcludedFiles=ExcludedFiles,
                    #                       MatchNames=MatchNames,
                    #                       ExcludeNames=ExcludeNames,
                    #                       ExcludedDownsampleLevels=ExcludedDownsampleLevels):
                    #     yield subd

                for t in concurrent.futures.as_completed(dir_search_tasks):
                    output = t.result()
                    if output is not None:
                        yield from output
        else:
            # Do not create threads, just run the IO on this thread
            for d in dirs:
                fullpath = os.path.join(Path, d.path)
                if MatchNames is not None and check_if_str_matches(d.name, MatchNames, caseInsensitive):
                    yield FindFileResult(path=fullpath, matched_files=[])
                    continue  # We do not iterate the subdirectories of MatchNames

                # If we are not matching names or requiring files then return the path
                # if MatchNames is None and RequiredFiles is None:
                # yield fullpath

                # Add directory tree to list and keep looking

                yield from RecurseSubdirectoriesGenerator(fullpath,
                                                          RequiredFiles=RequiredFiles,
                                                          ExcludedFiles=ExcludedFiles,
                                                          MatchNames=MatchNames,
                                                          ExcludeNames=ExcludeNames,
                                                          ExcludedDownsampleLevels=ExcludedDownsampleLevels)

        # for t in dir_search_tasks:
        # output = t.result()
        # if output is not None:
        #   yield from output

    except IOError:
        prettyoutput.LogErr("RecurseSubdirectories could not enumerate " + str(Path))
        pass
    except FileNotFoundError:
        prettyoutput.LogErr("RecurseSubdirectories passed path parameter which does not exist: " + Path)

    return


def _RecurseSubdirectoriesListTask(
        Path: str,
        RequiredFiles: str | Sequence[str] | re.Pattern | None = None,
        ExcludedFiles: str | Sequence[str] | re.Pattern | None = None,
        MatchNames: str | Sequence[str] | None = None,
        ExcludeNames: str | Sequence[str] | None = None,
        ExcludedDownsampleLevels: Sequence[int] | None = None,
        caseInsensitive: bool = True,
):
    """
    This is called on another thread, we force the generator to return its items
    as a list so we can yield results from the main thread
    """
    return list(_RecurseSubdirectoriesGeneratorTask(
        Path=Path,
        RequiredFiles=RequiredFiles,
        ExcludedFiles=ExcludedFiles,
        MatchNames=MatchNames,
        ExcludeNames=ExcludeNames,
        ExcludedDownsampleLevels=ExcludedDownsampleLevels,
        caseInsensitive=caseInsensitive,
    ))


def check_if_str_matches(file: str, matchCriteria: re.Pattern | collections.abc.Iterable,
                         caseInsensitive: bool = True):
    # Exclude takes priority over included files
    if caseInsensitive:
        file = file.lower()

    if matchCriteria is None:
        return None
    elif isinstance(matchCriteria, re.Pattern):
        return matchCriteria.match(file) is not None
    elif isinstance(matchCriteria, collections.abc.Iterable):
        return file in matchCriteria
    else:
        raise ValueError("Unexpected matchCriteria")


def RemoveDirectorySpaces(path: str):
    """
    Remove spaces from the path and any immediate subdirectories under that path replacing spaces with '_'
    """
    import shutil

    if not os.path.exists(path):
        prettyoutput.Log("No valid path provided as first argument")
        return

    Dirlist = list()
    Dirlist.append(path)

    # Recursively list the subdirectories, catch any exceptions.  This can occur if we don't have permissions
    dirs = []
    try:
        #    prettyoutput.Log( os.path.join(Path, '*[!png]'))
        dirs = glob.glob(os.path.join(path, '*'))
    except:
        prettyoutput.Log("RecurseSubdirectories could not enumerate " + path)
        return []

    for d in dirs:
        if os.path.isfile(d):
            continue

        # Skip if it contains a .
        if d.find('.') > -1:
            continue

        # Skip if it contains words from the exclude list
        name = os.path.basename(d)
        parentDir = os.path.dirname(d)
        nameNoSpaces = name.replace(' ', '_')
        if name != nameNoSpaces:
            fullnameNoSpace = os.path.join(parentDir, nameNoSpaces)
            shutil.move(d, fullnameNoSpace)


def RemoveFilenameSpaces(path: str, ext: str):
    """Replaces spaces in filenames with _"""
    import shutil

    if not os.path.exists(path):
        prettyoutput.Log("No valid path provided as first argument")
        return

    if ext[0] != '.':
        ext = '.' + ext

    globext = '*' + ext

    prettyoutput.Log(os.path.join(path, ext))

    # List all of the .mrc files in the path
    files = glob.glob(os.path.join(path, globext))

    # We expect .mrc files to be named ####_string.mrc
    # #### is a section number
    # string is anything the users chooses to add

    prettyoutput.Log(files)
    for f in files:
        filename = os.path.basename(f)
        dirname = os.path.dirname(f)

        # Remove spaces if they are found
        filenameNoSpaces = filename.replace(' ', '_')
        filePathNoSpaces = os.path.join(dirname, filenameNoSpaces)
        shutil.move(f, filePathNoSpaces)


def try_locate_file(self, ImageFullPath: str, listAltDirs: list[str]):
    """
    Identify the path a file exists at.  If the path is absolute that will be
    returned.  If the path is relative it will be combined with the list of
    alternative paths to see if it can be found
    """
    if os.path.exists(ImageFullPath):
        return ImageFullPath
    else:

        filename = ImageFullPath

        # Do not use the base filename if the ImagePath is relative
        if os.path.isabs(ImageFullPath):
            filename = os.path.basename(ImageFullPath)

        for dirname in listAltDirs:
            nextPath = os.path.join(dirname, filename)
            if os.path.exists(nextPath):
                return nextPath

    return None


if __name__ == '__main__':
    output = RecurseSubdirectoriesGenerator("\\\\OpR-Marc-Syn3\\Data\\RawData\\RC3", RequiredFiles='*.idoc')
    for (path, files) in output:
        print(f'{path}:{files}')
    pass
