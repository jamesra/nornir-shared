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


def format_downsample_level(level: int | str) -> str:
    """Render a downsample level as a directory name, accepting int or numeric string.

    ``DownsampleFormat % level`` alone raises ``TypeError: %d format: a real number is
    required, not str`` for string levels. That mattered because callers are documented to
    pass ``frozenset[str]``, and ``ensure_string_set`` preserves non-string members
    (ints stay ints) while lowercasing strings only when ``caseInsensitive`` is true.
    Numeric strings are accepted in either spelling, so ``1``, ``'1'`` and ``'001'`` all
    render as ``'001'``.
    """
    try:
        return DownsampleFormat % int(level)
    except (TypeError, ValueError) as e:
        raise ValueError(
            f"Downsample level {level!r} is not a number. Levels name pyramid "
            f"directories such as '001', so they must be integers or numeric strings."
        ) from e


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


#: Ceiling on the unlink futures :func:`rmtree` keeps in flight. Bounds memory on trees
#: holding millions of files while still keeping the executor's queue fed.
_RMTREE_MAX_PENDING_UNLINKS = 1024


#: A subtree with fewer entries than this is handed to a worker whole rather than
#: walked. Matches the threshold the whole-call shortcut uses.
_RMTREE_SMALL_SUBTREE_ENTRIES = 50


def _entry_is_link(entry: os.DirEntry) -> bool:
    """True when a scandir entry is a link rather than the thing it points at.

    Reads the DirEntry's cached lstat, so this costs no extra syscalls. That matters:
    a path-based check using ``os.path.ismount`` is expensive enough on Windows to
    dominate the whole call when run once per entry.

    Windows junctions need naming explicitly. They report False from ``is_symlink``
    yet directory walks descend into them, so treating only symlinks as links walks
    straight out of the tree and deletes the target's contents. ``DirEntry.is_junction``
    arrived in Python 3.12; on older interpreters a junction is indistinguishable from a
    directory here, as it is to ``shutil.rmtree``.
    """
    if entry.is_symlink():
        return True

    is_junction = getattr(entry, 'is_junction', None)
    return False if is_junction is None else is_junction()


def _remove_link(path: str):
    """Remove a link without touching whatever it points at.

    POSIX wants unlink for a directory symlink, Windows wants rmdir for a junction.
    Neither is portable alone.
    """
    try:
        os.unlink(path)
    except OSError:
        os.rmdir(path)


def _remove_subtree_if_small(path: str, ignore_errors: bool) -> bool:
    """Remove path entirely if it is small, reporting whether it was handled.

    Runs on a worker thread and is deliberately self-contained: it never touches the
    executor that is running it, which is the whole difference from the recursive
    rmtree this replaced. Counting the entries here rather than on the calling thread
    keeps that scan parallel, which is where most of the old code's speed on trees of
    many small directories came from.

    :return: True if the subtree is gone, False if it is too large and the caller
             should walk it instead.
    """
    if path_entry_count(path, max_count=_RMTREE_SMALL_SUBTREE_ENTRIES) < _RMTREE_SMALL_SUBTREE_ENTRIES:
        shutil.rmtree(path, ignore_errors=ignore_errors)
        return True

    return False


def rmtree(directory: str, ignore_errors: bool = False, executor: concurrent.futures.ThreadPoolExecutor | None = None,
           wait: bool = True):
    """Recursively remove a directory and all its contents.  Uses multithreading for large directories.

    Everything handed to the executor can finish without the executor: file unlinks,
    link removals, and small subtrees removed whole by ``shutil.rmtree``. Only
    directories too large for that are walked, and that happens on the calling thread.

    This function used to submit *itself* into the same executor for each subdirectory
    and then block on ``as_completed`` for the results, which deadlocks: once every
    worker holds a directory and waits on a subdirectory queued behind it, no queued
    work can ever start. Measured on the default 32-worker pool, a tree of 34 top-level
    directories with substantial subdirectories hung permanently, and a chain of 200
    nested directories holding one file each hung as well.

    Do not pass an `executor` that the calling thread is itself a worker of. This call
    blocks until the unlinks it submitted have finished, so a thread waiting on its own
    pool can still starve it. That hazard belongs to the caller now: nothing inside here
    submits work that in turn waits on this executor.
    """
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

        def report_or_raise(exception: BaseException, description: str):
            if isinstance(exception, FileNotFoundError):
                return

            if ignore_errors is True:
                prettyoutput.error(f'Error removing {description}: {exception}')
            else:
                raise exception

        # Directories this thread has to walk itself, parents before children. Walking
        # them here is what breaks the deadlock: everything submitted to the executor
        # below is self-contained and never waits on the executor.
        large_directories = [directory]

        pending: collections.deque[tuple[concurrent.futures.Future, str, str | None]] = collections.deque()

        def drain_one():
            future, description, subtree = pending.popleft()
            try:
                handled = future.result()
            except Exception as e:
                report_or_raise(e, description)
                return

            # A subtree the worker found too large to remove whole comes back here to
            # be walked. Unlink futures return None, which is not False.
            if handled is False and subtree is not None:
                large_directories.append(subtree)

        def track(future: concurrent.futures.Future, description: str,
                  subtree: str | None = None):
            if len(pending) >= _RMTREE_MAX_PENDING_UNLINKS:
                drain_one()

            pending.append((future, description, subtree))

        index = 0
        while index < len(large_directories):
            current = large_directories[index]
            index += 1

            try:
                entries = list(os.scandir(current))
            except OSError as e:
                report_or_raise(e, current)
                continue

            for entry in entries:
                # A link is dropped as a link, never followed. shutil.rmtree, which the
                # branch above delegates to, refuses to follow them, while the code this
                # replaced used entry.is_dir() and did follow them, so the same tree
                # deleted data outside itself or not depending only on its entry count.
                if _entry_is_link(entry):
                    track(executor.submit(_remove_link, entry.path),
                          f'link {entry.path}')
                elif entry.is_dir(follow_symlinks=False):
                    track(executor.submit(_remove_subtree_if_small, entry.path,
                                          ignore_errors),
                          f'directory {entry.path}', entry.path)
                else:
                    track(executor.submit(os.remove, entry.path),
                          f'file entry {entry.path}')

            # Drain before moving on only if nothing is left to walk, so that
            # subtrees rejected by workers are picked up without idling the pool.
            while index >= len(large_directories) and len(pending) > 0:
                drain_one()

        while len(pending) > 0:
            drain_one()

        # Whatever is left is empty now. Children come after parents in the list, so
        # reversing removes the deepest first and `directory` last.
        for current in reversed(large_directories):
            try:
                os.rmdir(current)
            except OSError as e:
                report_or_raise(e, current)

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
    """Normalize *param* to a ``frozenset`` for name/level matching.

    When ``caseInsensitive`` is true, string members are lowercased. Non-string
    members (e.g. integer downsample levels) are preserved. A caller ``set`` /
    ``frozenset`` is rebuilt when lowercasing is required so identity is not
    relied upon; otherwise an existing ``frozenset`` may be returned unchanged.
    """
    if param is None:
        return None

    if isinstance(param, str):
        return frozenset([param.lower() if caseInsensitive else param])

    if isinstance(param, (frozenset, set)):
        if caseInsensitive:
            return frozenset(n.lower() if isinstance(n, str) else n for n in param)
        return frozenset(param) if isinstance(param, set) else param  # type: ignore[return-value]

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


#: Workers overlapping directory scans for the whole of one
#: :func:`RecurseSubdirectoriesGenerator` call. This used to be a fresh
#: ``min(len(dirs), 8)`` pool per recursion level, which compounded: a 780-directory
#: tree five wide and four deep peaked at 227 live threads.
_RECURSE_SCAN_WORKERS = 16

#: Directory scans allowed in flight. Bounds how far ahead of the consumer the walk
#: runs, so a huge tree does not queue a future per directory.
_RECURSE_MAX_PENDING_SCANS = 64

#: Pending directories at or below which a scan runs on the calling thread instead of
#: going through the pool. There is nothing to overlap it with at that point, so the
#: submit would be pure overhead.
_RECURSE_INLINE_WORKLIST = 1


class _DirectoryScan(typing.NamedTuple):
    results: list[FindFileResult]  # Ready to yield, in order
    children: list[str]  # Subdirectories still to visit


def _scan_one_directory(
        Path: str,
        RequiredFiles: re.Pattern | frozenset[str] | None,
        ExcludedFiles: re.Pattern | frozenset[str] | None,
        MatchNames: re.Pattern | frozenset[str] | None,
        ExcludeNames_set: frozenset[str] | None,
        caseInsensitive: bool,
) -> _DirectoryScan:
    """Scan one directory, reporting what to yield and where to go next.

    Runs on a worker thread and deliberately never touches the executor running it, so
    it cannot wait on the pool it is queued in. The recursive version of this could:
    each level built its own pool and blocked on it, which is why thread counts
    multiplied with depth.

    Filters arrive already normalised, so this does no per-level renormalisation.
    """
    results: list[FindFileResult] = []
    children: list[str] = []

    try:
        with os.scandir(Path) as entries:
            files, dirs = _SeparateFilesAndDirs(entries)
    except FileNotFoundError:
        prettyoutput.LogErr("RecurseSubdirectories passed path parameter which does not exist: " + Path)
        return _DirectoryScan(results, children)
    except IOError:
        prettyoutput.LogErr("RecurseSubdirectories could not enumerate " + str(Path))
        return _DirectoryScan(results, children)

    excluded = False
    known_required_files: list[str] = []

    no_file_criteria = (not isinstance(RequiredFiles, re.Pattern)
                       and (RequiredFiles is None or len(RequiredFiles) == 0)
                       and not isinstance(ExcludedFiles, re.Pattern)
                       and (ExcludedFiles is None or len(ExcludedFiles) == 0))

    if not no_file_criteria:
        for file in files:
            if not excluded and ExcludedFiles is not None:
                excluded = excluded or check_if_str_matches(file.name, ExcludedFiles)
                if excluded:
                    break

            if RequiredFiles is not None and check_if_str_matches(file.name, RequiredFiles):
                known_required_files.append(file.name)

    # An excluded directory takes its whole subtree with it.
    if excluded:
        return _DirectoryScan(results, children)

    if len(known_required_files) > 0:
        results.append(FindFileResult(path=Path, matched_files=known_required_files))
    elif (RequiredFiles is None or not RequiredFiles) and \
            (MatchNames is None or not MatchNames):
        results.append(FindFileResult(path=Path, matched_files=[]))

    for d in dirs:
        # Test the directory's own name, not its full path.  Using the path meant
        # a single dotted ancestor -- a volume directory named RC3.v2, or any
        # scan rooted under one -- matched every subdirectory and pruned the
        # entire search after the root.
        if d.name.find('.') > -1:
            continue

        # Skip if it contains words from the exclude list
        if ExcludeNames_set is not None:
            dir_key = d.name.lower() if caseInsensitive else d.name
            if dir_key in ExcludeNames_set:
                continue

        if MatchNames is not None and check_if_str_matches(d.name, MatchNames, caseInsensitive):
            results.append(FindFileResult(path=d.path, matched_files=[]))
            continue  # We do not iterate the subdirectories of MatchNames

        children.append(d.path)

    return _DirectoryScan(results, children)


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

    One executor serves the whole traversal and results stream out as each directory's
    scan lands. This replaced a recursive walk that built a fresh ``min(len(dirs), 8)``
    pool at every level and materialised each subtree with ``return list(...)`` before
    the caller saw any of it. Both were measurable: a 780-directory tree five wide and
    four deep peaked at 227 live threads, and with ``RequiredFiles`` set -- how the
    importers call this -- 98% of the total runtime elapsed before the first result was
    yielded, which is the opposite of what a generator is for.
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
        ExcludeNames_set = ExcludeNames_set.union(
            [format_downsample_level(level) for level in ExcludedDownsampleLevels_set])
    elif ExcludedDownsampleLevels_set is not None:
        ExcludeNames_set = frozenset(
            [format_downsample_level(level) for level in ExcludedDownsampleLevels_set])

    # Directories still to scan, breadth first. Scans are handed to one pool and their
    # results streamed out in submission order, so a directory's own entry always
    # precedes its children and the caller sees matches as they are found.
    worklist: collections.deque[str] = collections.deque([Path])
    in_flight: collections.deque[concurrent.futures.Future] = collections.deque()

    executor: concurrent.futures.ThreadPoolExecutor | None = None
    try:
        while len(worklist) > 0 or len(in_flight) > 0:
            # One pending directory with nothing in flight offers no parallelism to
            # exploit, so scanning it here beats a submit-and-wait round trip. A tree
            # one directory wide never builds a pool at all, which is what the old
            # serial branch was for: measured over a 400-deep chain, always submitting
            # cost 52 ms against 37 ms inline.
            if len(in_flight) == 0 and len(worklist) <= _RECURSE_INLINE_WORKLIST:
                scan = _scan_one_directory(worklist.popleft(),
                                           RequiredFiles,
                                           ExcludedFiles,
                                           MatchNames,
                                           ExcludeNames_set,
                                           caseInsensitive)
                yield from scan.results
                worklist.extend(scan.children)
                continue

            if executor is None:
                executor = concurrent.futures.ThreadPoolExecutor(
                    max_workers=_RECURSE_SCAN_WORKERS,
                    thread_name_prefix='RecurseSubdirectories')

            while len(worklist) > 0 and len(in_flight) < _RECURSE_MAX_PENDING_SCANS:
                in_flight.append(executor.submit(_scan_one_directory,
                                                 worklist.popleft(),
                                                 RequiredFiles,
                                                 ExcludedFiles,
                                                 MatchNames,
                                                 ExcludeNames_set,
                                                 caseInsensitive))

            scan = in_flight.popleft().result()
            yield from scan.results
            worklist.extend(scan.children)
    finally:
        # Also runs on GeneratorExit, so abandoning the generator part-way tears the
        # pool down. The old code yielded from inside `with executor`, which left one
        # executor alive per suspended level for as long as the consumer took.
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)


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
