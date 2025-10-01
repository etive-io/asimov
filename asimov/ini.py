"""
Handle run configuration files.

This module is inteded to read and manipulate the run configuration
files which are used by ``LALInferencePipe`` to design a parameter estimation run.


"""

import ast
import getpass
import os
from configparser import ConfigParser, NoOptionError


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

    def check_fakecache(self):
        """
        Check to see if this file contains a fake-cache.

        This can be used to determine whether the ini file sets up a configuration which
        uses e.g. deglitched frames.

        Returns
        -------
        bool
           Returns true if a fake cache has been used for this file.
        """
        try:
            if len(self.ini.get("lalinference", "fake-cache")) > 0:
                return True
            else:
                return False
        except NoOptionError:
            return False

    def set_lalinference(self, **kwargs):
        """
        Set the values of LALInference configuration variables.

        Parameters
        ----------
        kwargs :
           Set a variety of parameters.

        """
        for key, value in kwargs:
            self.ini.set("lalinference", key, value)

    def get_psds(self):
        """
        Check if PSDs have been set in the ini file,
        and return them if they have.
        """
        psds = {}
        for det in self.get_ifos():
            try:
                psds[det] = self.ini.get("engine", f"{det}-psd")
            except NoOptionError:
                pass
        return psds

    def get_calibration(self):
        """
        Retrieve the calibration envelope locations.
        """
        calibration = {}
        for det in self.get_ifos():
            try:
                calibration[det] = self.ini.get("engine", f"{det}-spcal-envelope")
            except NoOptionError:
                pass
        return calibration

    def update_psds(self, psds, clobber=False):
        """
        Update the locations of the PSDs in the ini file.

        Parameters
        ----------
        psds : dict
           A dictionary of the various PSDs.
        """
        for det, location in psds.items():
            needs_psd = True
            try:
                self.ini.get("engine", f"{det}-psd")
                needs_psd = False
            except NoOptionError:
                needs_psd = True

            if needs_psd or clobber:
                self.ini.set("engine", f"{det}-psd", location)

    def run_bayeswave(self, status=True):
        """
        Ensure that Bayeswave is run for this job.

        This should be run in order to add Bayeswave to produce PSDs for an event.

        Parameters
        ----------
        status : bool, optional
           If set to true (the default) then a line will be added to ensure that
           Bayeswave is run to generate PSDs. If False then this line will be
           removed from the ini file if it exists.
        """
        if status:
            self.ini.set("condor", "bayeswave", "%(lalsuite-install)s/bin/BayesWave")
        else:
            try:
                self.ini.remove_option("condor", "bayeswave")
            except NoOptionError:
                pass

    def get_engine(self):
        """
        Fetch all of the Lalinference engine data.
        """
        return dict(self.ini.items("engine"))

    def get_ifos(self):
        return ast.literal_eval(self.ini.get("analysis", "ifos"))

    def get_channels(self):
        return ast.literal_eval(self.ini.get("data", "channels"))

    def set_approximant(self, approximant, amporder, fref):
        self.ini.set("engine", "approx", approximant)
        self.ini.set("engine", "amporder", amporder)
        self.ini.set("engine", "fref", fref)

    def set_queue(self, queue="Priority_PE"):
        self.ini.set("condor", "queue", queue)

    def update_accounting(self, user=None):
        """
        Update the accounting tag for this job.
        Defaults to the user account running the supervisor.

        Parameters
        ----------
        user : str
           The accounting user to be added to the ini file.
        """

        if not user:
            user = self._get_user()
        self.ini.set("condor", "accounting_group_user", user)

    def update_webdir(self, event, prod, rootdir="public_html/LVC/projects/O3/C01/"):
        """
        Update the web directory in the ini file.
        """

        web_path = os.path.join(
            os.path.expanduser("~"), *rootdir.split("/"), event, prod
        )  # TODO Make this generic
        self.ini.set("paths", "webdir", web_path)

    def _get_user(self):
        user = getpass.getuser()
        return user

    def save(self):
        with open(self.ini_loc, "w") as fp:
            self.ini.write(fp)
