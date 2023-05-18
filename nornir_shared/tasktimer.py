import datetime
import math
import time

from . import prettyoutput


class TaskTimer:
    '''Helper class that allows us to manually record how long a given section of code took to execute'''

    def __init__(self):
        # Dictionary of start times
        self._TaskStartTime = dict()

        # Dictionary of elapsed times
        self._TaskDeltaTime = dict()

        # If a task isn't explicitely started we compare to when this class was created.
        self.DefaultStartTime = time.perf_counter()

        self.CreationDateTime = datetime.datetime.now(datetime.timezone.utc)

    def Start(self, task):
        self._TaskStartTime[task] = time.perf_counter()

    def End(self, task, print_elapsed=True):
        '''Stop a timer for a task, print output if PrintElapsed is not explicitely set to False'''
        tend = time.perf_counter()

        tstart = self.DefaultStartTime
        if task in self._TaskStartTime:
            tstart = self._TaskStartTime.pop(task, self.DefaultStartTime)
        else:
            prettyoutput.Log(f'No timer started for task {task} using default value')

        tdelta = tend - tstart
        if task in self._TaskDeltaTime:
            self._TaskDeltaTime[task] = self._TaskDeltaTime[task] + tdelta
        else:
            self._TaskDeltaTime[task] = tdelta

        if print_elapsed:
            prettyoutput.Log(self.ElapsedString(task))

    def ElapsedString(self, task):
        if task in self._TaskDeltaTime:
            tdelta = self._TaskDeltaTime[task]
            [ms, sec] = math.modf(tdelta)
            [garbage, ms] = math.modf(ms * 1000)
            return task + ' : %2d days %s' % (
            tdelta / (60 * 60 * 24), time.strftime('%H:%M:%S', time.gmtime(tdelta))) + '.' + ('%d' % ms)

        return ''

    def __str__(self):
        s = self.CreationDateTime.strftime("%Y-%m-%d %H:%M:%S")
        localTime = self.CreationDateTime.astimezone()
        s += localTime.strftime("\t(%a %x %I:%M%p %Z)")

        for task in self._TaskDeltaTime.keys():
            outstr = self.ElapsedString(task)
            s += f'\n\t{outstr}'

        return s
