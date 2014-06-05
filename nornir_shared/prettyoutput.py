import time
import sys
import os
import logging
import subprocess
import socket
import traceback
import inspect

ECLIPSE = 'ECLIPSE' in os.environ
CURSES = 'CURSES' in os.environ

LastReportedProgress = 100

__IndentLevel = 0

def IncreaseIndent():
	global __IndentLevel
	__IndentLevel = __IndentLevel + 1

def DecreaseIndent():
	global __IndentLevel
	__IndentLevel = __IndentLevel - 1

def ResetIndent():
	global __IndentLevel
	__IndentLevel = 0

if os.path.exists('Logs') == False:
	try:
		os.mkdir('Logs')
	except OSError as E:
		if E.errno == 17:
			# Log("Log dir already exists: " + 'Logs')
			pass


if CURSES:
	import curses
	import curses.wrapper
	import atexit

	global stdscr

	def __EndCurses__():
		curses.endwin()

	stdscr = curses.initscr()

	statusWindow = []
	logWindow = []


	cursesCoords = {"Cores" : 1,
					"Section" : 2,
					"Stage": 3,
					"Task": 4,
					"Progress": 5,
					"PIDs" : 6,
					"Lock": 7,
					"Path": 8,
					"Cmd" : 9
					}



	# sys.stdout = logFile

	try:
		(maxY, maxX) = stdscr.getmaxyx()
		LogStartY = 16
		ScreenWidth = maxX

		statusWindow = curses.newwin(15, maxX, 0, 0)
		logWindow = curses.newpad(9999, ScreenWidth)

		stdscr.erase()
		stdscr.refresh()

		logWindow.move(0, 0)
		logWindow.standout()
		statusWindow.standend()

		atexit.register(__EndCurses__)
	except Exception as e:
		curses.endwin()
		raise e

def CurseString(topic, text):


	if CURSES:
		y = 0
		x = 0

		if(cursesCoords.has_key(topic)):
			y = cursesCoords[topic]

		(yMax, xMax) = statusWindow.getmaxyx()

		outStr = topic + " : " + text
		# Log(outStr)
		statusWindow.addstr(y, x, outStr)
		statusWindow.clrtoeol()
		statusWindow.move(yMax - 1, 0)
		statusWindow.refresh()
	else:
		# print(topic + ": " + text)
		return

def CurseProgress(text, Progress, Total=None):
	'''If Total is specified we display a percentage, otherwise
       a number'''

	# This is used to calculate an ETA for completion
	global LastReportedProgress
	global ProgressStartTime
	if(Progress < LastReportedProgress):
		ProgressStartTime = float(time.time())

	LastReportedProgress = Progress
	if Total is None:
		Total = Progress
		if(Total == 0):
			Total = 1

	ProgressY = 0
	ProgressX = 0

	TaskX = 0
	TaskY = 0

	# Estimate how long until we reach total
	ETASec = 0
	tstruct = None
	ETAString = ""
	fraction = float(Progress / float(Total))
	if fraction > 0:
		elapsedSec = float(time.time() - ProgressStartTime)
		ETASec = (elapsedSec / fraction) * (1.0 - fraction)
		tstruct = time.gmtime(ETASec)
		ETAString = "ETA: " + time.strftime("%H:%M:%S", tstruct)

	if CURSES:
		(yMax, xMax) = statusWindow.getmaxyx()

		if(cursesCoords.has_key("Task")):
			TaskY = cursesCoords["Task"]

		if(cursesCoords.has_key("Progress")):
			ProgressY = cursesCoords["Progress"]


		if text is not None:
			# TaskStr = "Task: " + text
			# Log(TaskStr)
			statusWindow.addnstr(TaskY, TaskX, "Task: " + text, 80)
			statusWindow.clrtoeol()

		ProgressStr = "Progress : %4.2f%%" % ((Progress / float(Total)) * 100)
		if not tstruct is None:
			ProgressStr = ProgressStr + "        " + ETAString


		# Log(ProgressStr)

		statusWindow.addnstr(ProgressY, ProgressX, ProgressStr, 80)
		statusWindow.clrtoeol()
		statusWindow.move(yMax - 1, 0)
		statusWindow.refresh()
	elif ECLIPSE:
		if (Total is not None):
			if(Progress is not None):
				if(text is not None):
					# print('\b' * 80)
					progText = text + " %0.3g%%" % ((float(Progress) / float(Total)) * 100)
					progText = progText + ' ' + ETAString
					# progText = progText + ' ' * (80 - len(progText))
					# print(progText)
	else:
		if (Total is not None):
			if(Progress is not None):
				if(text is not None):
					text = ('\b' * 80) + text
					progText = text + " %0.3g%%" % ((float(Progress) / float(Total)) * 100)
					progText = progText + ' ' + ETAString
					progText = progText + ' ' * (80 - len(progText))
					print(progText)



def get_calling_func_name():
   records = inspect.stack()[2]
   mod_name = inspect.getmodule(records[0]).__name__
   func_name = records[3]

   return mod_name + "." + func_name

#   stack = traceback.extract_stack()
#   filename, codeline, funcName, text = stack[-3]

#   return funcName


def Log(text=None):

	if text is None or len(text) == 0:
		text = os.linesep
	elif not isinstance(text, str):
		text = str(text)

	tabs = ''.join(['  ' for x in range(__IndentLevel)])

	text = tabs + text
	text.replace('\n', '\n' + tabs)

	logger = logging.getLogger(get_calling_func_name())
	logger.info(text)

	if CURSES:
		text = text + os.linesep

		sys.stdout.write(text)
		sys.stdout.flush()

		numChars = len(text)

		(yMax, xMax) = stdscr.getmaxyx()

		numLines = (numChars / xMax) + 1

		logWindow.move(0, 0)

		for i in range(numLines):
			logWindow.insertln()

		logWindow.addstr(0, 0, text)
		logWindow.clrtoeol()
		logWindow.refresh(0, 0, LogStartY, 0, yMax - 1, xMax)
	elif ECLIPSE:
		text = text.replace('\b', '')
		print(text)
	else:
		print(text)


def LogErr(error_message=None):
	if error_message is None  or len(error_message) == 0:
		error_message = "\n"
	elif not isinstance(error_message, str):
		error_message = str(error_message)

	if(error_message[-1] != '\n'):
		error_message = error_message + '\n'

	sys.stderr.write(error_message)
	logger = logging.getLogger(get_calling_func_name())
	logger.error(error_message)


def PrettyOutputModulePath():

    try:
        path = os.path.dirname(__file__)
    except:
        path = os.getcwd()

    return os.path.join(path, 'prettyoutput.py')


class Console(object):
	'''
	Creates a second window which recieves text output sent to the Console object
	'''
	HOST = '127.0.0.1'  # The remote host
	PORT = 50007  # The same port as used by the serve

	def __init__(self, *args, **kwargs):
		super(Console, self).__init__(*args, **kwargs)
		self._socket = None
		self._consoleProc = None

	@classmethod
	def CreateConsoleProc(cls):
		pycmd = "python -u " + PrettyOutputModulePath()
		return subprocess.Popen("start " + pycmd, stdin=subprocess.PIPE, shell=True)

	@property
	def socket(self):
		if self._consoleProc is None:
			self._consoleProc = Console.CreateConsoleProc()

		if self._socket is None:
			self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			self._socket.connect((Console.HOST, Console.PORT))

		return self._socket

	@property
	def ConsoleProc(self):
		return self._consoleProc

	def WriteMessage(self, text):
		self.socket.sendall(text.encode())

	def Close(self):

		if not self._socket is None:
			self._socket.sendall('PrettyOutput.Exit'.encode())
			self._socket.close()
			self._socket = None
#
#  		if not self._consoleProc is None:
#  			self._consoleProc.terminate()
#  			self._consoleProc = None

if __name__ == '__main__':
	import sys
	import time
	import socket

	sys.stdout.write("Starting second output window\n")
	HOST = '127.0.0.1'  # The remote host
	PORT = 50007  # The same port as used by the server

	while True:
		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		s.bind((HOST, PORT))
		s.listen(1)
		conn, addr = s.accept()
		# print 'Connected by', addr
		data = None

		while 1:
			data = conn.recv(1024)
			if not data: break

			sys.stdout.write(data)
			if 'PrettyOutput.Exit' in data:
				break

		conn.close()

		if 'PrettyOutput.Exit' in data:
			sys.stdout.write("Exit output process")
			break
