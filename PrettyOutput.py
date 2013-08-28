import time
import sys
import os
import logging

ECLIPSE = 'ECLIPSE' in os.environ;
CURSES = 'CURSES' in os.environ;

LastReportedProgress = 100;

__IndentLevel = 0;

def IncreaseIndent():
	global __IndentLevel
	__IndentLevel = __IndentLevel + 1;

def DecreaseIndent():
	global __IndentLevel
	__IndentLevel = __IndentLevel - 1;

def ResetIndent():
	global __IndentLevel
	__IndentLevel = 0;

if os.path.exists('Logs') == False:
	try:
		os.mkdir('Logs');
	except OSError as E:
		if E.errno == 17:
			# Log("Log dir already exists: " + 'Logs');
			pass 
	

if CURSES:
	import curses
	import curses.wrapper
	import atexit

	global stdscr

	def __EndCurses__():
		curses.endwin()

	stdscr = curses.initscr()

	statusWindow = [];
	logWindow = [];


	cursesCoords = {"Cores" : 1,
					"Section" : 2,
					"Stage": 3,
					"Task": 4,
					"Progress": 5,
					"PIDs" : 6,
					"Lock": 7,
					"Path": 8,
					"Cmd" : 9
					};



	# sys.stdout = logFile

	try:
		(maxY, maxX) = stdscr.getmaxyx()
		LogStartY = 16;
		ScreenWidth = maxX

		statusWindow = curses.newwin(15, maxX, 0, 0)
		logWindow = curses.newpad(9999, ScreenWidth)

		stdscr.erase();
		stdscr.refresh();

		logWindow.move(0, 0);
		logWindow.standout();
		statusWindow.standend();
		
		atexit.register(__EndCurses__)
	except Exception as e:
		curses.endwin();
		raise e;

def CurseString(topic, text):


	if CURSES:
		y = 0;
		x = 0;

		if(cursesCoords.has_key(topic)):
			y = cursesCoords[topic];

		(yMax, xMax) = statusWindow.getmaxyx()

		outStr = topic + " : " + text;
		# Log(outStr);
		statusWindow.addstr(y, x, outStr);
		statusWindow.clrtoeol()
		statusWindow.move(yMax - 1, 0);
		statusWindow.refresh();
	else:
		#print(topic + ": " + text);
		return

def CurseProgress(text, Progress, Total = None):
	'''If Total is specified we display a percentage, otherwise
       a number'''

	# This is used to calculate an ETA for completion;
	global LastReportedProgress
	global ProgressStartTime
	if(Progress < LastReportedProgress):
		ProgressStartTime = float(time.time());

	LastReportedProgress = Progress;
	if Total is None:
		Total = Progress;
		if(Total == 0):
			Total = 1

	ProgressY = 0;
	ProgressX = 0;

	TaskX = 0;
	TaskY = 0;

	# Estimate how long until we reach total
	ETASec = 0;
	tstruct = None;
	ETAString = "";
	fraction = float(Progress / float(Total));
	if fraction > 0:
		elapsedSec = float(time.time() - ProgressStartTime);
		ETASec = (elapsedSec / fraction) * (1.0 - fraction);
		tstruct = time.gmtime(ETASec);
		ETAString = "ETA: " + time.strftime("%H:%M:%S", tstruct);

	if CURSES:
		(yMax, xMax) = statusWindow.getmaxyx()

		if(cursesCoords.has_key("Task")):
			TaskY = cursesCoords["Task"];

		if(cursesCoords.has_key("Progress")):
			ProgressY = cursesCoords["Progress"];


		if text is not None:
			# TaskStr = "Task: " + text;
			# Log(TaskStr)
			statusWindow.addnstr(TaskY, TaskX, "Task: " + text, 80);
			statusWindow.clrtoeol()

		ProgressStr = "Progress : %4.2f%%" % ((Progress / float(Total)) * 100);
		if not tstruct is None:
			ProgressStr = ProgressStr + "        " + ETAString;


		# Log(ProgressStr)

		statusWindow.addnstr(ProgressY, ProgressX, ProgressStr, 80);
		statusWindow.clrtoeol()
		statusWindow.move(yMax - 1, 0);
		statusWindow.refresh();
	elif ECLIPSE:
		if (Total is not None):
			if(Progress is not None):
				if(text is not None):
					# print('\b' * 80);
					progText = text + " %0.3g%%" % ((float(Progress) / float(Total)) * 100)
					progText = progText + ' ' + ETAString
					# progText = progText + ' ' * (80 - len(progText));
					# print(progText);
	else:
		if (Total is not None):
			if(Progress is not None):
				if(text is not None):
					text = ('\b' * 80) + text;
					progText = text + " %0.3g%%" % ((float(Progress) / float(Total)) * 100) ;
					progText = progText + ' ' + ETAString
					progText = progText + ' ' * (80 - len(progText));
					print(progText);

def Log(text = None):

	if text is None or len(text) == 0:
		text = os.linesep;
	elif not isinstance(text, str):
		text = str(text);

	tabs = ''.join(['  ' for x in range(__IndentLevel)]);

	text = tabs + text;
	text.replace('\n', '\n' + tabs);

	logging.info(text);

	if CURSES:
		text = text + os.linesep;

		sys.stdout.write(text);
		sys.stdout.flush();

		numChars = len(text);

		(yMax, xMax) = stdscr.getmaxyx()

		numLines = (numChars / xMax) + 1;

		logWindow.move(0, 0);

		for i in range(numLines):
			logWindow.insertln();

		logWindow.addstr(0, 0, text);
		logWindow.clrtoeol()
		logWindow.refresh(0, 0, LogStartY, 0, yMax - 1, xMax);
	elif ECLIPSE:
		text = text.replace('\b', '');
		print(text);
	else:
		print(text);


def LogErr(error_message = None):
	if error_message is None  or len(error_message) == 0:
		error_message = "\n";
	elif not isinstance(error_message, str):
		error_message = str(error_message);

	if(error_message[-1] != '\n'):
		error_message = error_message + '\n';

	sys.stderr.write(error_message);
	logging.error(error_message);

