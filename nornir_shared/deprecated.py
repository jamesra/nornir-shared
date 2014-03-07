'''
Created on Jul 11, 2012

@author: Jamesan

Functions that were used in the past but should no longer be used.  Mostly replaced by thread and cluster pools.

'''
import platform
from . import PrettyOutput
import os
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
    PrettyOutput.Log(outStr);

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
            PrettyOutput.Log("Elapsed: " + str(Elapsed));
            PrettyOutput.Log("Elapsed Hours: " + str(Elapsed / (60 * 60)));
            if((Elapsed / (60 * 60)) > 48):
                PrettyOutput.Log("Removing stale lock file: " + LockFile);
                try:
                    os.remove(LockFile);
                except:
                    PrettyOutput.Log("Exception removing: " + LockFile);
        except:
            PrettyOutput.CurseString('Lock', 'Exception');
            return False;

    # Read the file and see if it is ours, just in case it was recreated
    if(os.path.exists(LockFile)):
        try:
            hLockFile = open(LockFile, 'r');
            LockingParty = hLockFile.readline().rstrip('\n');
            PrettyOutput.Log(LockFile + " locked by: " + LockingParty + " I am: " + MyID);
            if(LockingParty == MyID):
                PrettyOutput.CurseString('Lock', LockFile);
                return True;
            else:
                PrettyOutput.CurseString('Lock', 'None');
                return False;
        except:
            PrettyOutput.CurseString('Lock', 'Exception');
            return False;


    # Try to create the file
    try:
        hLockFile = open(LockFile, 'w+');
        hLockFile.write(MyID);
        hLockFile.write('\n');
        hLockFile.write(time.ctime(time.time()));
        hLockFile.close();

    except:
        PrettyOutput.Log("Could not create lock file: " + LockFile)
        return False;

    # Try to open the file we just created, if it has our ID we got the lock
    try:
        hLockFile = open(LockFile, 'r');
        LockingParty = hLockFile.readline().rstrip('\n');
        hLockFile.close();


        if(LockingParty == MyID):
            PrettyOutput.Log("Successful lock")
            return True;
        else:
            PrettyOutput.Log("Failed Lock: " + LockingParty + " got the lock on: " + LockFile);
            return False;
    except:
        PrettyOutput.Log("Exception opening lock file we just created")
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
            PrettyOutput.Log(MyID + " removed lock on " + LockFile)
            PrettyOutput.CurseString('Lock', 'Released ' + LockFile);
            os.remove(LockFile);
        else:
            PrettyOutput.Log("Tried to remove another processes lock " + LockFile);

    except:
        PrettyOutput.Log("Exception releasing Lock File: " + LockFile);
        PrettyOutput.CurseString('Lock', 'Release Exception ' + LockFile);
        return;



def ProcessThrottleCheck(Procs, maxProcs, SleepTime):
    '''
    Waits until the number of processes in the Procs list is less than the maxProcs value.
    The SleepTime is the value passed to sleep calls
    Function returns a new suggested sleep time
    '''

    CompletedProcs = [];
    while(len(Procs) >= maxProcs):
        # Check for openings and wait if none found
        TestProcList = Procs
        NumCompleted = 0;
        for proc in TestProcList:
            if proc.poll() is not None:
                NumCompleted += 1;
                Procs.remove(proc)
                CompletedProcs.append(proc);
                # PrettyOutput.Log( "PID " + str(proc.pid) + " Terminated"

        # Change the sleep time 2% if we waited too long or not long enough
        if(NumCompleted == 0):
            time.sleep(SleepTime);
            SleepTime = SleepTime * (100.0 / 99.0);
        elif (NumCompleted >= 1):
            SleepTime = SleepTime * (50.0 / 100.0) ** NumCompleted;

        if(SleepTime > 5):
            SleepTime = 5;

        if(len(Procs) >= maxProcs):
            time.sleep(SleepTime);

    Procs.sort();
    PIDList = [str(p.pid) + ' ' for p in Procs]

    PrettyOutput.CurseString('PIDs', ' %s ' % ''.join(PIDList));

    return [SleepTime, CompletedProcs];

def WaitForAllProcesses(Procs, SleepTime=None, Progress=None, Total=None):
    '''
    Waits until all processes in the Procs list have completed
    The SleepTime is the value passed to sleep calls
    Function returns no value
    '''

    if Progress is None:
        Progress = 0;

    if Total is None:
        Total = len(Procs);

    CompletedProcs = [];

    # Keep waiting until all processes are finished
    while(len(Procs) > 0):
        TestProcList = Procs;

        for proc in TestProcList:
            PrettyOutput.Log("Waiting on process " + str(proc.pid))
            proc.communicate();
            Procs.remove(proc);

            Progress += 1
            PrettyOutput.CurseProgress(None, Progress, Total)

            Procs.sort();
            PIDList = [' ' + str(p.pid) for p in Procs]
            PrettyOutput.CurseString('PIDs', ' %s ' % ''.join(PIDList));
            CompletedProcs.append(proc);

        if(SleepTime > 5):
            SleepTime = 5;

        # Wait 10 seconds and check for openings again
        if(SleepTime is not None and len(Procs) > 0):
            time.sleep(SleepTime);

    return CompletedProcs;

if __name__ == '__main__':
    pass