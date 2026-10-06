"""
Test package initialization.

This module sets up the test environment before any tests run.
"""
import os

# Enable testing mode for all tests
# This must be set before asimov modules are imported
os.environ['ASIMOV_TESTING'] = '1'
