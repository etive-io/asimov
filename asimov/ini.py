"""
Handle run configuration files.

This module provides a minimal wrapper around a pipeline's ini-style
run configuration file, used to locate and validate the file without
asimov needing to understand its pipeline-specific contents.
"""

from configparser import ConfigParser


class RunConfiguration(object):
    """A class to represent a run configuration."""

    def __init__(self, path):
        """
        Open the run configuration file.

        Parameters
        ----------
        path : str
           The path to a run configuration ini file.
        """
        self.ini_loc = path
        ini = ConfigParser()
        ini.optionxform = str

        if isinstance(path, dict):
            ini.read_dict(path)
        else:

            try:
                ini.read(path)
            except FileNotFoundError:
                raise ValueError("Could not open the ini file")

        self.ini = ini
