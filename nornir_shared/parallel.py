'''
Created on Jul 11, 2012

@author: Jamesan
'''

if __name__ == '__main__':
    pass

import os
import platform
import time

#: A lock older than this is treated as abandoned and removed. The original comment
#: here said "eighteen hours" while the code compared against 48; 48 is what shipped,
#: so that is what is kept.
STALE_LOCK_HOURS = 48


def _LockAgeHours(LockFile, FileTimeString):
    """Age of a lock in hours, falling back to the file's mtime.

    The creation time is written as the lock's second line, but a process that dies
    mid-write leaves that line absent or truncated. ``time.strptime`` then raises, and
    the bare ``except`` this replaced turned that into "cannot lock" permanently: the
    stale-removal path was never reached, so a zero-byte lock file never cleared.
    Judging an undatable lock by its mtime lets it age out like any other.

    Returns None only when the age cannot be established at all.
    """
    try:
        return (time.time() - time.mktime(time.strptime(FileTimeString))) / (60 * 60)
    except (ValueError, OverflowError):
        pass

    try:
        return (time.time() - os.path.getmtime(LockFile)) / (60 * 60)
    except OSError:
        return None


# Attempt to create a file that tells other machines the directory is in use.
def TryEnterLockPath(Path):
    LockFile = os.path.join(Path, 'Path')
    return TryEnterLockFile(LockFile)


# Attempt to create a file that tells other machines the specified file is in use.
# If the lock is successful it returns true, otherwise false
def TryEnterLockFile(LockFile):
    LockFile = LockFile + '.lock'
    MyID = platform.node()

    outStr = MyID + " trying to take a lock on: " + LockFile
    # PrettyOutput.CurseString("Lock", outStr);
    print(outStr)

    # If the file exists we can't take the lock
    if os.path.exists(LockFile):
        # CreationTime = os.path.getctime(LockFile);  #For some reason ctime is the creation date of the first lock file ever, misses deletes and recreations

        # Read the file and see if it is stale
        FileTimeString = ''
        try:
            with open(LockFile, 'r') as hLockFile:
                LockingParty = hLockFile.readline().rstrip('\n')
                FileTimeString = hLockFile.readline()  # Could be updated before delete
        except OSError as e:
            # A genuine I/O failure is not evidence of a stale lock, so do not delete
            # on a guess. Previously indistinguishable from an unparseable timestamp.
            print("Could not read lock file " + LockFile + ": " + str(e))
            return False
        except UnicodeDecodeError:
            # Corrupt content: there is nothing in it to trust, so let mtime decide.
            print("Lock file is not readable text, judging age by mtime: " + LockFile)

        ElapsedHours = _LockAgeHours(LockFile, FileTimeString)
        if ElapsedHours is None:
            print("Could not determine the age of lock file: " + LockFile)
            return False

        print("Elapsed Hours: " + str(ElapsedHours))
        if ElapsedHours > STALE_LOCK_HOURS:
            print("Removing stale lock file: " + LockFile)
            try:
                os.remove(LockFile)
            except OSError as e:
                print("Exception removing " + LockFile + ": " + str(e))

    # Read the file and see if it is ours, just in case it was recreated
    if os.path.exists(LockFile):
        try:
            with open(LockFile, 'r') as hLockFile:
                LockingParty = hLockFile.readline().rstrip('\n')
            print(LockFile + " locked by: " + LockingParty + " I am: " + MyID)
            if LockingParty == MyID:
                return True
            else:
                return False
        except (OSError, UnicodeDecodeError):
            # UnicodeDecodeError has to be caught here too. The stale check above used
            # to swallow it and return, so a lock file holding non-text never reached
            # this read; now that a corrupt lock is allowed to age out instead, it does.
            return False

    # Try to create the file atomically (O_EXCL) so two hosts cannot both win.
    try:
        fd = os.open(LockFile, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, 'w') as hLockFile:
            hLockFile.write(MyID)
            hLockFile.write('\n')
            hLockFile.write(time.ctime(time.time()))
    except FileExistsError:
        print("Could not create lock file (already exists): " + LockFile)
        return False
    except OSError:
        print("Could not create lock file: " + LockFile)
        try:
            os.remove(LockFile)
        except OSError:
            pass
        return False

    # Try to open the file we just created, if it has our ID we got the lock
    try:
        with open(LockFile, 'r') as hLockFile:
            LockingParty = hLockFile.readline().rstrip('\n')

        if LockingParty == MyID:
            print("Successful lock")
            return True
        else:
            print("Failed Lock: " + LockingParty + " got the lock on: " + LockFile)
            return False
    except OSError:
        print("Exception opening lock file we just created")
        return False


# Deletes a lock file in the specified directory if we created it
def ReleaseLockPath(Path):
    LockFile = os.path.join(Path, 'Path')
    return ReleaseLockFile(LockFile)


def ReleaseLockFile(LockFile):
    LockFile = LockFile + '.lock'

    try:
        with open(LockFile, 'r') as hLockFile:
            LockingParty = hLockFile.readline().rstrip('\n')
    except FileNotFoundError:
        # Nothing to release, which is not an error: the lock may have aged out as
        # stale or never been taken. The bare except this replaced reported it with
        # the same message as a genuine I/O failure.
        print("No lock file to release: " + LockFile)
        return
    except (OSError, UnicodeDecodeError) as e:
        print("Could not read lock file " + LockFile + ": " + str(e))
        return

    MyID = platform.node()
    if LockingParty == MyID:
        print(MyID + " removed lock on " + LockFile)
        try:
            os.remove(LockFile)
        except OSError as e:
            print("Could not remove our own lock " + LockFile + ": " + str(e))
    else:
        print("Tried to remove another processes lock " + LockFile)
