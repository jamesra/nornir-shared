#!/usr/bin/env python3
"""
Example script demonstrating MQTT functionality in nornir_shared

This script shows how to use the modified nornir_shared.prettyoutput functions
that now publish messages to MQTT topics based on severity.

To test this:
1. Run this script in one terminal - it will start publishing log messages
2. Run the console subscriber in another terminal:
   python -m nornir_shared.console

The console will automatically start mosquitto broker if needed and display
all log messages with timestamps and severity levels.
"""

import time
import sys
import os

# Add the nornir_shared directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'nornir_shared'))

import nornir_shared.prettyoutput as pretty


def demo_logging():
    """Demonstrate different types of logging that will be published via MQTT"""
    
    print("Starting MQTT logging demo...")
    print("Make sure to run 'python -m nornir_shared.console' in another terminal to see the messages")
    print()
    
    # Give time for user to start console
    for i in range(5, 0, -1):
        print(f"Starting in {i} seconds...")
        time.sleep(1)
    
    print("Demo starting!")
    print()
    
    # Test basic logging
    pretty.Log("This is a basic log message")
    time.sleep(1)
    
    pretty.Log("This is another info message with some details")
    time.sleep(1)
    
    # Test error logging
    pretty.LogErr("This is an error message - should appear on error topic")
    time.sleep(1)
    
    # Test progress reporting
    print("Testing progress reporting...")
    for i in range(0, 101, 20):
        pretty.CurseProgress(f"Processing step {i//20 + 1}", i, 100)
        time.sleep(2)
    
    # Test status updates
    print("Testing status updates...")
    pretty.CurseString("Stage", "Data Processing")
    time.sleep(1)
    
    pretty.CurseString("Task", "Loading input files")
    time.sleep(1)
    
    pretty.CurseString("Status", "Processing complete")
    time.sleep(1)
    
    # Test more complex messages
    pretty.Log(["Multiple", "items", "in", "a", "list"])
    time.sleep(1)
    
    pretty.Log("Final log message - demo complete!")
    
    print()
    print("Demo complete! Check your console window for MQTT messages.")
    print("The console should show all messages with timestamps and severity levels.")


if __name__ == "__main__":
    try:
        demo_logging()
    except KeyboardInterrupt:
        print("\nDemo interrupted by user")
    except Exception as e:
        print(f"Demo error: {e}")
        import traceback
        traceback.print_exc() 