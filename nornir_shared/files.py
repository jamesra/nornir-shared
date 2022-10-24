'''
Created on Jul 11, 2012

@author: Jamesan
'''
import glob
import os
import re
import time
import collections.abc

from nornir_shared import prettyoutput
import nornir_shared
import concurrent.futures
from datetime import datetime

DownsampleFormat = '%03d'
DefaultLevels = frozenset([1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024])
DefaultLevelStrings = frozenset([DownsampleFormat % l for l in DefaultLevels])
DefaultExcludeList = frozenset(["clahe", "mbproj", "8-bit", "16-bit", "blob", "mosaic", "tem", "temp", "bruteresults", "gridresults", "results", "registered"])


def rmtree(directory, ignore_errors=False): 
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
            prettyoutput.error(f'{e}')
        else:
            raise e
            
    return


def NewestFile(fileA, fileB):
    ''':return: Newest file, or fileB in the case of a tie. Return None in case of an error.'''
    
    if fileA is None:
        raise ValueError("fileA should not be None")

    if fileB is None:
        raise ValueError("fileB should not be None")

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

    if AStats.st_mtime > BStats.st_mtime:
        return fileA
    elif AStats.st_mtime < BStats.st_mtime:
        return fileB
    else:
        return fileB

    
def IsOutdated(ReferenceFilename, TestFilename):
    '''
    :return: True if TestFilename is older than ReferenceFilename
    '''
    newestFile = NewestFile(ReferenceFilename, TestFilename)
    
    return newestFile is None or newestFile == ReferenceFilename


def IsOlderThan(TestPath, DateTime, DateTimeFormat=None):
    '''Return true if the file is older than the specified date string
    :param str TestPath: Path we are using to retrieve the last modified time from
    :param str DateTime: Either a string in the specified format or a floating point number representing seconds past the Unix epoch.
    :param str DateTimeFormat: Optional, if a string is passed this parameter indicates the string format.  Defaults to "%d %b %Y %H:%M:%S"
    '''
    if isinstance(DateTime, float):
        DateTime = DateTime
    elif isinstance(DateTime, int):
        DateTime = float(DateTime)
    elif isinstance(DateTime, str):
        if DateTimeFormat is None:
            DateTimeFormat = "%d %b %Y %H:%M:%S"
            
        DateTime = time.mktime(time.strptime(DateTime, DateTimeFormat))
    else:
        raise TypeError("IsOlderThan expects a string or floating parameter to compare against, got %s" % str(DateTime))
    
    return os.path.getmtime(TestPath) < DateTime
        

def OutdatedFile(ReferenceFilename, TestFilename):
    '''Return true if ReferenceFilename modified time is newer than the TestFilename'''
    return NewestFile(ReferenceFilename, TestFilename) == ReferenceFilename


def RemoveOutdatedFile(ReferenceFilename, remove_if_outdated) -> bool:
    '''
    Takes a ReferenceFilename and TestFilename.  Removes TestFilename if it is newer than the reference
    :return: True if the input parameter is outdated
    '''
    needsRemoving = False
    
    if ReferenceFilename is None:
        raise ValueError("Cannot compare to None")
     
    if isinstance(remove_if_outdated, str):
        needsRemoving = OutdatedFile(ReferenceFilename, remove_if_outdated)
    elif isinstance(remove_if_outdated, datetime):
        needsRemoving = IsOlderThan(ReferenceFilename, remove_if_outdated)
    elif isinstance(remove_if_outdated, float):
        needsRemoving = IsOlderThan(ReferenceFilename, remove_if_outdated)
    elif isinstance(remove_if_outdated, int):
        needsRemoving = IsOlderThan(ReferenceFilename, remove_if_outdated)
    else:
        raise ValueError(f"Unexpected type to compare against {remove_if_outdated.__class__}")

 #   [name, ext] = os.path.splitext(TestFilename)
 
    if needsRemoving:
        
        if isinstance(remove_if_outdated, str):
            try:
                prettyoutput.Log(f'Removing outdated file: {remove_if_outdated}, outdated compared to {ReferenceFilename}')
                os.remove(remove_if_outdated)
                return True
            except Exception as e:
                prettyoutput.Log(f'Exception removing outdated file: {remove_if_outdated}\n{e}')
                pass 
        
    return needsRemoving


def RemoveInvalidImageFile(TestFilename):
    '''Takes a ReferenceFilename and TestFilename.  Removes TestFilename if it is newer than the reference'''
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


def RecurseSubdirectories(Path,
                          RequiredFiles=None,
                          ExcludedFiles=None,
                          MatchNames=None,
                          ExcludeNames=None,
                          ExcludedDownsampleLevels=None,
                          caseInsensitive=True):
    '''Recurse Subdirectories adds Path and every subdirectory to a list
       If MatchNames is not null we yield the matching directory, but do not recurse subdirectories underneath.  A directory name matching this parameter will always be included, overriding the RequiredFiles or ExcludeFiles restrictions.
       If ExcludeNames  is not null we do not add the directory to the list and do not recurse subdirectories/
       if RequiredFiles is not null the directory must contain the required file before we add it.  No subdirectories are searched.
       if ExcludeFiles is not null and the directory contains the a matching file we do not add it or search subdirectories
       ExcludedDownsampleLevels and ExcludeNames must be an empty list to avoid population with default values.
       RequiredFiles and ExcludeFiles can be either a regular expression string or a list of specific filenames.
       Excluded files take priority over RequiredFiles
       '''

    generator = RecurseSubdirectoriesGenerator(Path=Path, RequiredFiles=RequiredFiles, ExcludedFiles=ExcludedFiles, MatchNames=MatchNames, ExcludeNames=ExcludeNames, ExcludedDownsampleLevels=ExcludedDownsampleLevels, caseInsensitive=caseInsensitive)
    return list(generator)


def _ensure_regex_or_set(param, defaultValue, caseInsensitive=False):
    if isinstance(param, re.Pattern):
        return param
    elif isinstance(param, str):
        # helper change, if it starts with a *, then assume it is a file expression and convert it crudely
        if param[0] == '*':
            param = param.replace('.', '\.')
            param = param.replace('*', '.*')
            param = param + '$'
        return re.compile(param, re.IGNORECASE if caseInsensitive else 0)
    else:
        return _ensure_string_set(param, defaultValue, caseInsensitive)


def _ensure_string_set(param, defaultValue, caseInsensitive=False):
    '''Ensure the input is a set of lowercase strings.  If input is none use defaultValue if provided'''
    if param is None:
        param = defaultValue
        
    if param is None:
        return None
    
    output = param
    
    if False == isinstance(param, frozenset) and False == isinstance(param, set):
        if not isinstance(param, collections.abc.Iterable):
            param = [param]

        if caseInsensitive:
            output = [n.lower() if isinstance(n, str) else n for n in param]
        
        output = frozenset(param)
    
    return output


def RecurseSubdirectoriesGenerator(Path,
                          RequiredFiles=None,
                          ExcludedFiles=None,
                          MatchNames=None,
                          ExcludeNames=None,
                          ExcludedDownsampleLevels=None,
                          caseInsensitive=True):
    '''Same as RecurseSubdirectories, but returns a generator
    :return: A tuple with (directory, [files]) where files match the filter criteria if specified, otherwise an empty list
    '''
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        yield from _RecurseSubdirectoriesGeneratorTask(executor,
                          Path,
                          RequiredFiles=RequiredFiles,
                          ExcludedFiles=ExcludedFiles,
                          MatchNames=MatchNames,
                          ExcludeNames=ExcludeNames,
                          ExcludedDownsampleLevels=ExcludedDownsampleLevels,
                          caseInsensitive=caseInsensitive)

    
def _RecurseSubdirectoriesGeneratorTask(executor,
                          Path,
                          RequiredFiles=None,
                          ExcludedFiles=None,
                          MatchNames=None,
                          ExcludeNames=None,
                          ExcludedDownsampleLevels=None,
                          caseInsensitive=True,
                          ):
    '''Same as RecurseSubdirectories, but returns a generator
    :return: A tuple with (directory, [files]) where files match the filter criteria if specified, otherwise an empty list
    '''
    RequiredFiles = _ensure_regex_or_set(RequiredFiles, None, caseInsensitive=caseInsensitive)
    ExcludedFiles = _ensure_regex_or_set(ExcludedFiles, None, caseInsensitive=caseInsensitive)
    MatchNames = _ensure_string_set(MatchNames, None, caseInsensitive=caseInsensitive)    
    ExcludedDownsampleLevels = _ensure_string_set(ExcludedDownsampleLevels, DefaultLevels)
    ExcludeNames = _ensure_string_set(ExcludeNames, DefaultExcludeList, caseInsensitive=caseInsensitive)
    
    if ExcludeNames is not None and ExcludedDownsampleLevels is not None:
        ExcludeNames = ExcludeNames.union([DownsampleFormat % level for level in ExcludedDownsampleLevels])
    elif ExcludedDownsampleLevels is not None:
        ExcludeNames = frozenset([DownsampleFormat % level for level in ExcludedDownsampleLevels])
    
    # If we made it this far we did not match either Required or Excluded Files

    # Recursively list the subdirectories, catch any exceptions.  This can occur if we don't have permissions
    try:
        with os.scandir(Path) as Path_iter:
            entries = list(Path_iter)
            files = filter(lambda e: e.is_file, entries)
            dirs = filter(lambda e: e.is_dir, entries)
            
            excluded = False
            required_files = []
            
            # First, check if our root directory (Path) contains any required or excluded files, and if it meets criteria yield the root directory
            if RequiredFiles is None and ExcludedFiles is None:
                # Automatically pass the test of whether the directory contains or does not have certain files
                excluded = False 
            else:
                excluded = False 
                for file in files:
                    # Check if the directory is excluded
                    if not excluded and ExcludedFiles is not None:
                        excluded = excluded or _check_if_file_matches(file.name, ExcludedFiles)
                        if excluded:
                            break
                    
                    if RequiredFiles is not None and _check_if_file_matches(file.name, RequiredFiles):
                        required_files.append(file.name)
                        # has_required_files = has_required_files or 
            
            # Do not yield the directory since it contains an excluded file
            if excluded:
                return
            
            # Yield the directory if it has a required file
            if len(required_files) > 0:
                yield Path, required_files
                
            dir_search_tasks = []
            
            for d in dirs:
                # Skip if it contains a .
                if d.path.find('.') > -1:
                    continue
                         
                # Skip if it contains words from the exclude list
                name = d.name.lower() if caseInsensitive else d.name
                
                if ExcludeNames is not None and name in ExcludeNames:
                    continue
                 
                fullpath = os.path.join(Path, d.path)
                if MatchNames is not None and name in MatchNames: 
                    yield fullpath, []
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
                
                task = executor.submit(_RecurseSubdirectoriesGeneratorTask, 
                                       executor=executor,
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
                    
            #for t in dir_search_tasks:
                #output = t.result()
                ##if output is not None:
                 #   yield from output
                  
    except IOError:
        prettyoutput.LogErr("RecurseSubdirectories could not enumerate " + str(Path))
        pass
    except FileNotFoundError:
        prettyoutput.LogErr("RecurseSubdirectories passed path parameter which does not exist: " + Path)
    
    return


def _check_if_file_matches(file, matchCriteria, caseInsensitive=True):
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
        
    return
 

def RemoveDirectorySpaces(Path):
    '''
    Remove spaces from the path and any immediate subdirectories under that path replacing spaces with '_'
    '''
    import shutil

    if os.path.exists(Path) == False:
        prettyoutput.Log("No valid path provided as first argument")
        return

    Dirlist = list()
    Dirlist.append(Path)

    # Recursively list the subdirectories, catch any exceptions.  This can occur if we don't have permissions
    dirs = []
    try:
    #    prettyoutput.Log( os.path.join(Path, '*[!png]'))
        dirs = glob.glob(os.path.join(Path, '*'))
    except:
        prettyoutput.Log("RecurseSubdirectories could not enumerate " + Path)
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


def RemoveFilenameSpaces(Path, ext):
    '''Replaces spaces in filenames with _'''
    import shutil

    if os.path.exists(Path) == False:
        prettyoutput.Log("No valid path provided as first argument")
        return

    if ext[0] != '.':
        ext = '.' + ext

    globext = '*' + ext

    prettyoutput.Log(os.path.join(Path, ext))

    # List all of the .mrc files in the path
    files = glob.glob(os.path.join(Path, globext))

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

        
def try_locate_file(self, ImageFullPath, listAltDirs):
        '''
        Identify the path a file exists at.  If the path is absolute that will be
        returned.  If the path is relative it will be combined with the list of 
        alternative paths to see if it can be found
        '''
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
