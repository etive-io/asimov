"""
Test configuration that runs before any test imports.

This file sets up the test environment, including enabling testing mode
for asimov pipelines.
"""
import os

# Enable testing mode before any asimov modules are imported
# This ensures testing pipelines are registered in known_pipelines
os.environ['ASIMOV_TESTING'] = '1'
