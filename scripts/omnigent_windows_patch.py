"""
Quick import helper for omnigent on Windows.
Use this at the top of your scripts before importing omnigent.
"""
import signal
import sys

if sys.platform == 'win32':
    signal.SIGUSR1 = 10
    signal.SIGUSR2 = 12

import omnigent  # noqa: F401  # intentional: this module exists to import/patch omnigent

