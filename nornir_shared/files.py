"""
Created on Jul 11, 2012

@author: Jamesan
"""
import asyncio
import collections.abc
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import errno
import glob
import functools
import math
import os
import re
import sys
import time
import typing
import shutil
import logging
import tempfile
from enum import IntEnum, auto
from typing import Any, Sequence, cast

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


def file_mtime_ns(path: str, comparison: FileTimeComparison = FileTimeComparison.MODIFIED) -> int:
    """Return the file modified or creation time in nanoseconds since the Unix epoch."""
    if comparison != FileTimeComparison.MODIFIED and comparison != FileTimeComparison.CREATION:
        raise ValueError('Unknown comparison')

    stats = os.stat(path)
    if comparison == FileTimeComparison.MODIFIED:
        return stats.st_mtime_ns
    return stats.st_ctime_ns


def path_list_to_mtime_ns_map(paths: Sequence[str],
                              comparison: FileTimeComparison = FileTimeComparison.MODIFIED) -> dict[str, int]:
    """Map each path to its modified or creation time in nanoseconds."""
    return {file_path: file_mtime_ns(file_path, comparison=comparison) for file_path in paths}


def format_mtime_ns(mtime_ns: int) -> str:
    """Format a nanosecond mtime for log and assertion messages."""
    seconds, remainder_ns = divmod(mtime_ns, 1_000_000_000)
    timestamp = datetime.datetime.fromtimestamp(seconds)
    return f"{timestamp.isoformat(sep=' ')} ({mtime_ns} ns, +{remainder_ns} ns within second)"


def _directory_listable(path: str) -> bool:
    """Return True when *path* is a directory the client can list (CIFS cache refresh)."""
    if not os.path.isdir(path):
        return False
    try:
        os.listdir(path)
        return True
    except OSError:
        return False


def _directory_writable(path: str) -> bool:
    """Return True when *path* accepts a create-and-delete probe file."""
    if not _directory_listable(path):
        return False
    try:
        with tempfile.NamedTemporaryFile(dir=path, prefix='.nornir_probe_', delete=True):
            pass
        return True
    except OSError:
        return False


def _path_components(path: str) -> list[str]:
    """Return absolute path components from root to leaf."""
    abspath = os.path.abspath(path)
    parts: list[str] = []
    cur = abspath
    while True:
        parts.append(cur)
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    parts.reverse()
    return parts


def ensure_directory(path: str, *, retries: int = 8, base_delay_s: float = 0.05) -> str:
    """Create *path* (and parents), blocking until visible; tolerant of CIFS/NFS races.

    ``os.makedirs`` can fail with ``FileNotFoundError`` on network shares when a parent
    is briefly missing from the client cache. Walk and create each path component with
    retries instead of assuming ``makedirs`` visibility is immediate.

    Success requires the final directory to be listable and accept a short-lived probe
    file so callers do not proceed while the share still rejects writes.
    """
    path = os.path.abspath(path)
    if _directory_writable(path):
        _flush_directory_tree_visibility(_path_components(path))
        return path

    parts: list[str] = _path_components(path)

    last_error: OSError | None = None
    for attempt in range(retries):
        try:
            for component in parts:
                if _directory_listable(component):
                    continue
                if os.path.exists(component) and not os.path.isdir(component):
                    raise ValueError(
                        f"Cannot create directory {path}: {component} exists and is not a directory")
                try:
                    os.mkdir(component)
                except FileExistsError:
                    if not os.path.isdir(component):
                        raise
                except FileNotFoundError as e:
                    last_error = e
                    parent = os.path.dirname(component)
                    if parent and os.path.isdir(parent):
                        try:
                            os.listdir(parent)
                        except OSError:
                            pass
                    break
            else:
                if _directory_writable(path):
                    _flush_directory_tree_visibility(parts)
                    return path
        except OSError as e:
            last_error = e

        time.sleep(base_delay_s * (attempt + 1))

    if _directory_writable(path):
        _flush_directory_tree_visibility(parts)
        return path

    detail = f"\n{last_error}" if last_error is not None else ""
    raise FileNotFoundError(
        f"Unable to create directory after {retries} attempts: {path}{detail}")


def _flush_directory_tree_visibility(parts: Sequence[str]) -> None:
    """Require every component in *parts* to be listable in the calling thread."""
    for component in parts:
        if not _directory_listable(component):
            raise FileNotFoundError(f"Directory not visible after creation: {component}")


def pin_directory_for_worker(path: str) -> None:
    """Make *path* visible in the current thread after stage-level ``ensure_directory``."""
    abspath = os.path.abspath(path)
    if _directory_listable(abspath):
        return

    parts = _path_components(abspath)

    for component in parts:
        try:
            os.listdir(component)
        except OSError:
            pass

    if not _directory_listable(abspath):
        ensure_directory(abspath)


def copy_file(
    src: str,
    dst: str,
    *,
    retries: int = 16,
    base_delay_s: float = 0.1,
) -> None:
    """Copy *src* to *dst* with CIFS/NFS retries (atomic replace in dest dir).

    Stage-level ``ensure_directory`` should create *parent* once.  On failure this
    re-pins directory visibility in the worker thread and retries with backoff.
    """
    src = os.path.abspath(src)
    dst = os.path.abspath(dst)
    parent = os.path.dirname(dst) or None
    if parent:
        parent = os.path.abspath(parent)

    last_error: OSError | None = None
    for attempt in range(retries):
        try:
            if not os.path.isfile(src):
                raise FileNotFoundError(f"Source file does not exist: {src}")
            if parent is None:
                shutil.copyfile(src, dst)
            else:
                _copy_file_atomic(src, dst, parent)
            return
        except FileNotFoundError as e:
            last_error = e
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise
            last_error = e

        if parent:
            pin_directory_for_worker(parent)
        time.sleep(base_delay_s * (attempt + 1))

    if last_error is not None:
        raise last_error
    raise FileNotFoundError(f"Unable to copy {src!r} to {dst!r}")


def _copy_file_atomic(src: str, dst: str, parent: str) -> None:
    """Write via a temp file in *parent* and atomically replace *dst*."""
    fd, tmp_path = tempfile.mkstemp(prefix='.nornir_copy_', dir=parent)
    try:
        with os.fdopen(fd, 'wb') as out_f:
            with open(src, 'rb') as in_f:
                shutil.copyfileobj(in_f, out_f)
        os.replace(tmp_path, dst)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _reference_timestamp_to_ns(
        date_time: str | float | int | datetime.datetime | datetime.date | time.struct_time,
        date_time_format: str | None = None) -> int:
    """Convert a reference date/time value to nanoseconds since the Unix epoch."""
    if isinstance(date_time, float):
        timestamp = date_time
    elif isinstance(date_time, int):
        timestamp = float(date_time)
    elif isinstance(date_time, str):
        if date_time_format is None:
            date_time_format = "%d %b %Y %H:%M:%S"
        timestamp = datetime.datetime.strptime(date_time, date_time_format).timestamp()
    elif isinstance(date_time, datetime.datetime):
        timestamp = date_time.timestamp()
    elif isinstance(date_time, datetime.date):
        timestamp = datetime.datetime.fromordinal(date_time.toordinal()).timestamp()
    elif isinstance(date_time, time.struct_time):
        timestamp = time.mktime(date_time)
    else:
        raise TypeError("Expected a string or numeric time value, got %s" % str(date_time))

    return _float_timestamp_to_ns(timestamp)


def _float_timestamp_to_ns(timestamp: float) -> int:
    """Convert a floating-point Unix timestamp to integer nanoseconds."""
    seconds = math.floor(timestamp)
    remainder_ns = int(round((timestamp - seconds) * 1_000_000_000))
    return (seconds * 1_000_000_000) + remainder_ns


class FindFileResult(typing.NamedTuple):
    path: str  # Path that matched criteria
    matched_files: list[str] | None  # Files requested by the Match paramter


def path_entry_count(directory: str, max_count: int = 1000) -> int:
    """
    Count path files and directories up to max_count and return True if count is less than max_count.
    Short-circuits as soon as count exceeds max_count.
    """
    count = 0
    with os.scandir(directory) as it:
        try:
            for item in it:
                if item.is_file():
                    count += 1
                    if count > max_count:
                        return count
                elif item.is_dir():
                    count += path_entry_count(item.path, max_count - count)
                    if count > max_count:
                        return count

        except OSError as e:
            prettyoutput.error(f"Error reading directory {directory}: {e}")
            return max_count + 1

    return count


def rmtree(directory: str, ignore_errors: bool = False, executor: concurrent.futures.ThreadPoolExecutor | None = None,
           wait: bool = True):
    """Recursively remove a directory and all its contents.  Uses multithreading for large directories."""
    cleanup_executor = executor is None

    if not os.path.exists(directory):
        return

    if sys.is_finalizing():
        prettyoutput.Log(
            "Python is shutting down. Waiting for rmtree operation to complete contradicting passed wait parameter.")
        wait = True

    try:

        try:
            # For small directories, use shutil.rmtree directly
            # Short-circuit as soon as we exceed 1000 entries
            if path_entry_count(directory, max_count=50) < 50:
                shutil.rmtree(directory, ignore_errors=ignore_errors)
                return
        except IOError as e:
            if not ignore_errors:
                raise

        executor = concurrent.futures.ThreadPoolExecutor() if executor is None else executor

        folders = []
        files = []

        directory_remover = functools.partial(rmtree, executor=executor, ignore_errors=ignore_errors, wait=wait)

        for entry in os.scandir(directory):
            if entry.is_file():
                files.append(entry.path)
            elif entry.is_dir():
                folders.append(entry.path)

        folder_futures = []
        files_futures = []

        for folder in folders:
            folder_futures.append(executor.submit(directory_remover, folder))

        for file in files:
            files_futures.append(executor.submit(os.remove, file))

        for f in as_completed(folder_futures):
            try:
                f.result()  # This will raise an exception if the task failed
            except FileNotFoundError:
                pass
            except Exception as e:
                if ignore_errors is True:
                    prettyoutput.error(f'Error removing directory entry: {e}')
                else:
                    raise

        del folder_futures  # Clear the list to free memory

        for f in as_completed(files_futures):
            try:
                f.result()  # This will raise an exception if the task failed
            except FileNotFoundError:
                pass
            except Exception as e:
                if ignore_errors is True:
                    prettyoutput.error(f'Error removing file entry: {e}')
                else:
                    raise

        del files_futures

        try:
            os.rmdir(directory)
        except FileNotFoundError:
            pass
        except OSError as e:
            if ignore_errors is True:
                prettyoutput.error(f'Error removing {directory}: {e}')
                pass
            else:
                raise

        return
    finally:
        if cleanup_executor and executor is not None:
            # Test if python is in shutdown

            executor.shutdown(wait=wait)
            # If we created the executor, we should clean it up
            # This is to avoid leaving threads running in the background
            # when this function is called from a thread pool.


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
        # prettyoutput.Log(f"NewestFile: File not found {fileA}")
        return None

    BStats = None
    try:
        BStats = os.stat(fileB)
    except FileNotFoundError:
        # prettyoutput.Log(f"NewestFile: File not found {fileB}")
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
    newestFile = NewestFile(ReferenceFilename, TestFilename, comparison=comparison)

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

    reference_ns = _reference_timestamp_to_ns(DateTime, DateTimeFormat)
    file_time_ns = file_mtime_ns(TestPath, comparison=comparison)
    return file_time_ns < reference_ns


def OutdatedFile(ReferenceFilename: str, TestFilename: str,
                 comparison: FileTimeComparison = FileTimeComparison.MODIFIED) -> bool | None:
    """

    :param ReferenceFilename: File to compare against
    :param TestFilename: File to compare
    :param comparison: Which timestamp to use for comparison. Defaults to FileTimeComparison.MODIFIED
    :return: True if TestFilename is older than ReferenceFilename, None if one of the files did not exist"""
    result = NewestFile(ReferenceFilename, TestFilename, comparison)
    return None if result is None else result == ReferenceFilename


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

    if needs_removing is None:
        # One of the files did not exist
        if not os.path.exists(ReferenceFilename):
            prettyoutput.LogErr(f'Reference file does not exist: {ReferenceFilename}')
            return False
        elif not os.path.exists(remove_if_outdated):  # type: ignore[arg-type]
            prettyoutput.Log(f'File being checked does not exist: {remove_if_outdated}')
            return True
    elif needs_removing:
        if isinstance(remove_if_outdated, str):
            try:
                prettyoutput.Log(
                    f'Removing outdated file: {remove_if_outdated}, outdated compared to {ReferenceFilename}')
                os.remove(remove_if_outdated)
                return True
            except Exception as e:
                prettyoutput.Log(f'Exception removing outdated file: {remove_if_outdated}\n{e}')
                pass

    return False


def RemoveInvalidImageFile(TestFilename: str) -> bool:
    """Takes a ReferenceFilename and TestFilename.  Removes TestFilename if it is newer than the reference"""
    if not nornir_shared.images.IsValidImage(TestFilename):
        try:
            prettyoutput.Log('Removing invalid image file: ' + TestFilename)
            os.remove(TestFilename)
            return True
        except Exception as e:
            prettyoutput.Log(f'Exception removing invalid image file: {TestFilename}\n{e}')
            return False

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


def ensure_regex_or_set(param: str | re.Pattern | Sequence[str] | frozenset[str] | None,
                        caseInsensitive: bool = False) -> re.Pattern[str] | frozenset[str] | None:
    if param is None:
        return None
    elif isinstance(param, re.Pattern):
        return param
    elif isinstance(param, str):
        # helper change, if it starts with a *, then assume it is a file expression and convert it crudely
        if param[0] == '*':
            param = param.replace('.', r'\.')
            param = param.replace('*', '.*')
            param += '$'
        return re.compile(param, re.IGNORECASE if caseInsensitive else 0)
    else:
        return ensure_string_set(param, caseInsensitive)


def ensure_string_set(param: str | Sequence[Any] | frozenset[Any] | None, caseInsensitive: bool = False) -> frozenset[str] | None:
    """Ensure the input is a set of lowercase strings.  If input is none use defaultValue if provided"""
    if param is None:
        return None

    if isinstance(param, str):
        return frozenset([param.lower() if caseInsensitive else param])

    if isinstance(param, (frozenset, set)):
        return param  # type: ignore[return-value]

    items: list[Any] = list(param) if isinstance(param, collections.abc.Iterable) else [param]

    if caseInsensitive:
        items = [n.lower() if isinstance(n, str) else n for n in items]

    return frozenset(items)


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
        RequiredFiles: str | Sequence[str] | re.Pattern | frozenset[str] | None = None,
        ExcludedFiles: str | Sequence[str] | re.Pattern | frozenset[str] | None = None,
        MatchNames: str | Sequence[str] | re.Pattern | frozenset[str] | None = None,
        ExcludeNames: str | Sequence[str] | frozenset[str] | None = None,
        ExcludedDownsampleLevels: Sequence[int] | frozenset[str] | None = None,
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
    RequiredFiles = ensure_regex_or_set(RequiredFiles, caseInsensitive=caseInsensitive)  # type: ignore[reportAssignmentType]
    ExcludedFiles = ensure_regex_or_set(ExcludedFiles, caseInsensitive=caseInsensitive)  # type: ignore[reportAssignmentType]
    MatchNames = ensure_regex_or_set(MatchNames, caseInsensitive=caseInsensitive)  # type: ignore[reportAssignmentType]
    ExcludeNames_set: frozenset[str] | None = cast(
        frozenset[str] | None,
        DefaultExcludeList if ExcludeNames is None else ensure_string_set(ExcludeNames,
                                                                           caseInsensitive=caseInsensitive))
    ExcludedDownsampleLevels_set: frozenset[str] | None = cast(
        frozenset[str] | None,
        DefaultLevels if ExcludedDownsampleLevels is None else ensure_string_set(
            ExcludedDownsampleLevels, caseInsensitive=caseInsensitive))

    if ExcludeNames_set is not None and ExcludedDownsampleLevels_set is not None:
        ExcludeNames_set = ExcludeNames_set.union([DownsampleFormat % level for level in ExcludedDownsampleLevels_set])
    elif ExcludedDownsampleLevels_set is not None:
        ExcludeNames_set = frozenset([DownsampleFormat % level for level in ExcludedDownsampleLevels_set])

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
        if not isinstance(RequiredFiles, re.Pattern) and (RequiredFiles is None or len(RequiredFiles) == 0) and \
                not isinstance(ExcludedFiles, re.Pattern) and (ExcludedFiles is None or len(ExcludedFiles) == 0):
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
            yield FindFileResult(path=Path, matched_files=known_required_files)
        elif (RequiredFiles is None or not RequiredFiles) and \
                (MatchNames is None or not MatchNames):
            yield FindFileResult(path=Path, matched_files=[])

        dir_search_tasks = []

        # Filter out directories we do not want to recurse into
        dirs = set(dirs)

        # Test the directory's own name, not its full path.  Using the path meant
        # a single dotted ancestor -- a volume directory named RC3.v2, or any
        # scan rooted under one -- matched every subdirectory and pruned the
        # entire search after the root.
        dirs_with_dots = list(filter(lambda d: d.name.find('.') > -1, dirs))
        dirs = dirs.difference(dirs_with_dots)

        # Skip if it contains words from the exclude list
        if ExcludeNames_set is not None:
            excluded_dir_names = filter(lambda d: d.name.lower() in ExcludeNames_set, dirs)  # type: ignore[reportArgumentType]
            dirs = dirs.difference(excluded_dir_names)

        if len(dirs) > 3:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(dirs), 8),
                                                       thread_name_prefix=Path + '_') as executor:
                for d in dirs:
                    fullpath = d.path
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
                                           ExcludeNames=ExcludeNames_set,
                                           ExcludedDownsampleLevels=ExcludedDownsampleLevels_set)
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
                fullpath = d.path
                if MatchNames is not None and check_if_str_matches(d.name, MatchNames, caseInsensitive):
                    yield FindFileResult(path=fullpath, matched_files=[])
                    continue  # We do not iterate the subdirectories of MatchNames

                # If we are not matching names or requiring files then return the path
                # if MatchNames is None and RequiredFiles is None:
                # yield fullpath

                # Add directory tree to list and keep looking

                yield from _RecurseSubdirectoriesGeneratorTask(fullpath,
                                                              RequiredFiles=RequiredFiles,
                                                              ExcludedFiles=ExcludedFiles,
                                                              MatchNames=MatchNames,
                                                              ExcludeNames=ExcludeNames_set,
                                                              ExcludedDownsampleLevels=ExcludedDownsampleLevels_set,
                                                              caseInsensitive=caseInsensitive)

        # for t in dir_search_tasks:
        # output = t.result()
        # if output is not None:
        #   yield from output

    except FileNotFoundError:
        prettyoutput.LogErr("RecurseSubdirectories passed path parameter which does not exist: " + Path)
    except IOError:
        prettyoutput.LogErr("RecurseSubdirectories could not enumerate " + str(Path))
        pass

    return


def _RecurseSubdirectoriesListTask(
        Path: str,
        RequiredFiles: str | Sequence[str] | re.Pattern | frozenset[str] | None = None,
        ExcludedFiles: str | Sequence[str] | re.Pattern | frozenset[str] | None = None,
        MatchNames: str | Sequence[str] | re.Pattern | frozenset[str] | None = None,
        ExcludeNames: str | Sequence[str] | frozenset[str] | None = None,
        ExcludedDownsampleLevels: Sequence[int] | frozenset[str] | None = None,
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


def check_if_str_matches(file: str, matchCriteria: re.Pattern | collections.abc.Iterable | None,
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
    except OSError:
        prettyoutput.Log("RecurseSubdirectories could not enumerate " + path)
        return []

    for d in dirs:
        if os.path.isfile(d):
            continue

        # Skip if the directory's own name contains a '.'.  d is a full glob
        # path, so testing it directly skipped every subdirectory whenever the
        # parent path happened to contain a dot.
        name = os.path.basename(d)
        if name.find('.') > -1:
            continue

        # Skip if it contains words from the exclude list
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


def try_locate_file(ImageFullPath: str, listAltDirs: list[str]):
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
