'''
Created on Jul 11, 2012

@author: Jamesan
'''

if __name__ == '__main__':
    pass

import os
import platform
import time
 
# Attempt to create a file that tells other machines the directory is in use.
def TryEnterLockPath(Path):
    LockFile = os.path.join(Path, 'Path');
    return TryEnterLockFile(LockFile);

# Attempt to create a file that tells other machines the specified file is in use.
# If the lock is successful it returns true, otherwise false
def TryEnterLockFile(LockFile):
    LockFile = LockFile + '.lock';
    MyID = platform.node();

    outStr = MyID + " trying to take a lock on: " + LockFile;
    # PrettyOutput.CurseString("Lock", outStr);
    print(outStr)

    # If the file exists we can't take the lock
    if(os.path.exists(LockFile)):
        # CreationTime = os.path.getctime(LockFile);  #For some reason ctime is the creation date of the first lock file ever, misses deletes and recreations

        # Read the file and see if it is stale
        try:
            hLockFile = open(LockFile, 'r');
            LockingParty = hLockFile.readline().rstrip('\n');
            FileTimeString = hLockFile.readline();
            hLockFile.close();  # Could be updated between here and delete

            # Ignore the lock if it has been more than eighteen hours
            CreationTime = time.strptime(FileTimeString);
            CreationTimeSec = time.mktime(CreationTime);
            now = time.time();
            Elapsed = now - CreationTimeSec;
            print("Elapsed: " + str(Elapsed))
            print("Elapsed Hours: " + str(Elapsed / (60 * 60)))
            if((Elapsed / (60 * 60)) > 48):
                print("Removing stale lock file: " + LockFile)
                try:
                    os.remove(LockFile);
                except:
                    print("Exception removing: " + LockFile)
        except:
            return False;

    # Read the file and see if it is ours, just in case it was recreated
    if(os.path.exists(LockFile)):
        try:
            hLockFile = open(LockFile, 'r');
            LockingParty = hLockFile.readline().rstrip('\n');
            print(LockFile + " locked by: " + LockingParty + " I am: " + MyID)
            if(LockingParty == MyID):
                return True;
            else:
                return False;
        except:
            return False;


    # Try to create the file
    try:
        hLockFile = open(LockFile, 'w+');
        hLockFile.write(MyID);
        hLockFile.write('\n');
        hLockFile.write(time.ctime(time.time()));
        hLockFile.close();

    except:
        print("Could not create lock file: " + LockFile)
        return False;

    # Try to open the file we just created, if it has our ID we got the lock
    try:
        hLockFile = open(LockFile, 'r');
        LockingParty = hLockFile.readline().rstrip('\n');
        hLockFile.close();


        if(LockingParty == MyID):
            print("Successful lock")
            return True;
        else:
            print("Failed Lock: " + LockingParty + " got the lock on: " + LockFile)
            return False;
    except:
        print("Exception opening lock file we just created")
        return False;

# Deletes a lock file in the specified directory if we created it
def ReleaseLockPath(Path):
    LockFile = os.path.join(Path, 'Path');
    return ReleaseLockFile(LockFile);

def ReleaseLockFile(LockFile):

    LockFile = LockFile + '.lock';

    try:
        hLockFile = open(LockFile, 'r');
        LockingParty = hLockFile.readline().rstrip('\n');
        hLockFile.close();
        MyID = platform.node();
        if(LockingParty == MyID):
            print(MyID + " removed lock on " + LockFile)
            os.remove(LockFile);
        else:
            print("Tried to remove another processes lock " + LockFile)
    except:
        print("Exception releasing Lock File: " + LockFile)
        return;
