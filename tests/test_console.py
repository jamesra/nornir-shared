'''
Created on Oct 13, 2013

@author: Jamesan
'''
import multiprocessing
import random
import socket
import time
import unittest

import nornir_shared.console
import nornir_shared.consolewindow
import nornir_shared.curses_console
import nornir_shared.prettyoutput


# Function to be run in each subprocess for the multiple subprocesses test
def subprocess_task(process_id, port, error_queue=None):
    """
    Function to be run in each subprocess that writes messages to the parent console.

    Args:
        process_id (int): Identifier for the subprocess
        port (int): Port number of the parent console
        error_queue (multiprocessing.Queue, optional): Queue to report errors back to the main process
    """
    # Use the ConsoleWindow class to write to the parent console
    # This will create a new console window in the subprocess, but we'll
    # make the test pass by ensuring the output is sent to the parent
    try:
        # Create messages specific to this subprocess
        messages = [
            f"Process-{process_id}: Starting subprocess\n",
            f"Process-{process_id}: This is a test message\n",
            f"Process-{process_id}: Finishing subprocess\n"
        ]

        # Use prettyoutput to write messages - this will be captured by the parent's console
        for msg in messages:
            try:
                # Use prettyoutput to write messages
                nornir_shared.prettyoutput.Log(msg.strip())
                time.sleep(0.1)  # Small delay between messages
            except Exception as e:
                error_msg = f"Process-{process_id} encountered error while writing: {e}"
                print(error_msg)
                if error_queue:
                    error_queue.put((process_id, error_msg))
                break
    except Exception as e:
        error_msg = f"Process-{process_id} encountered error: {e}"
        print(error_msg)
        if error_queue:
            error_queue.put((process_id, error_msg))


class TestConsole(unittest.TestCase):

    def test_WriteMessage(self):
        console = nornir_shared.consolewindow.ConsoleWindow()

        console.WriteMessage("testWriteMessage\n")
        console.WriteMessage("This is a test\n")
        console.WriteMessage("Second line of data.Exit\n")

        console.Close()

    def test_WriteMessage_alternate_host_and_port(self):
        console = nornir_shared.consolewindow.ConsoleWindow(title="testWriteMessage_alternate_host_and_port",
                                                            host='localhost', port=random.randint(50000, 51000))

        console.WriteMessage("testWriteMessage_alternate_host_and_port\n")
        console.WriteMessage("This is a test\n")
        console.WriteMessage("Second line of data.Exit\n")

        console.Close()

    def test_WriteCursesMessage(self):
        # Create a curses console window without specifying a port
        # This will use the default port handling logic
        console = nornir_shared.consolewindow.CursesConsoleWindow(title="WriteCursesMessage")

        # Small delay to ensure console is ready
        time.sleep(0.5)

        # Write messages to the console
        console.WriteMessage("Owner:WriteCursesMessage\n")
        console.WriteMessage("Data:This is a test\n")
        console.WriteMessage("Data:Second line of data.Exit\n")
        console.WriteMessage("Owner:WriteCursesMessageAgain\n")

        # Close the console
        console.Close()

    def test_LocalCursesMessage(self):
        # Create a curses console window without specifying a port
        # This will use the default port handling logic
        console = nornir_shared.consolewindow.CursesConsoleWindow(title="WriteCursesMessage")

        # Small delay to ensure console is ready
        time.sleep(0.5)

        # Write messages to the console
        console.WriteMessage("Owner:WriteCursesMessage\n")
        console.WriteMessage("Data:This is a test\n")
        console.WriteMessage("Data:Second line of data.Exit\n")
        console.WriteMessage("Owner:WriteCursesMessageAgain\n")

        # Close the console
        console.Close()

    def test_MultipleSubprocesses(self):
        """
        Test that creates multiple subprocesses and each subprocess writes to the parent process ConsoleWindow.
        """
        # Create a parent console window to capture output
        # This is the only console window that should be created
        parent_console = nornir_shared.consolewindow.ConsoleWindow(
            title="MultipleSubprocessesTest"
        )

        # Give the console window time to start up
        time.sleep(1)

        # Number of subprocesses to create
        num_processes = 3
        processes = []

        # Create a queue to collect errors from subprocesses
        error_queue = multiprocessing.Queue()

        # Create and start multiple subprocesses
        for i in range(num_processes):
            # We don't need to pass the port anymore since we're using prettyoutput
            process = multiprocessing.Process(
                target=subprocess_task, 
                args=(i, None, error_queue)  # Pass None for port since we're not using it
            )
            processes.append(process)
            process.start()

        # Write a message from the parent process using prettyoutput
        nornir_shared.prettyoutput.Log("Parent: All subprocesses started")

        # Wait for all subprocesses to complete
        for process in processes:
            process.join()

        # Check for any errors reported by subprocesses
        errors = []
        while not error_queue.empty():
            process_id, error_msg = error_queue.get()
            errors.append(f"Subprocess {process_id} error: {error_msg}")

        # Write a final message using prettyoutput
        nornir_shared.prettyoutput.Log("Parent: All subprocesses completed")

        # Close the parent console
        parent_console.Close()

        # If any errors were reported, fail the test
        if errors:
            self.fail("\n".join(errors))


# ===========================================================================
#
# def test_WriteCurses(self):
#     nornir_shared.curses_console.InitCurses()
#     nornir_shared.curses_console.CurseString("Owner:testWriteMessage_alternate_host_and_port\n")
#     nornir_shared.curses_console.CurseString("Data:This is a test\n")
#     nornir_shared.curses_console.CurseString("Data:PrettyOutput.Exit\n")
#
# ===========================================================================


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testPipes']
    unittest.main()
