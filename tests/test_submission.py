"""Tests of asimov's ability to run pipeline generation tools to produce submission files."""

import hashlib
import unittest
import shutil, os
from configparser import ConfigParser, NoOptionError
import git
import asimov.git

class LALInferenceTests(unittest.TestCase):
    """Test lalinference_pipe related jobs."""

    @classmethod
    def setUpClass(self):
        self.cwd = os.getcwd()
        git.Repo.init("test_data/s000000xx/")


    @classmethod
    def tearDownClass(self):
        """Destroy all the products of this test."""
        shutil.rmtree("test_data/s000000xx/.git")


    def setUp(self):
        self.repo = repo = asimov.git.EventRepo("test_data/s000000xx")
        self.sample_hashes = {
            "lalinference_dag": self._get_hash("test_data/sample_files/lalinference_1248617392-1248617397.dag")
            }
        self.repo.build_dag("C01_offline", "Prod0")
        os.chdir(self.cwd)

    def _get_hash(self, filename):
        with open(filename, "r") as handle:
            return hashlib.md5(handle.read().encode()).hexdigest()

    def _get_config_ini(self):
        """Fetch the generated config.ini file."""
        ini = ConfigParser()
        ini.optionxform=str
        ini.read(self.cwd+"/test_data/s000000xx/C01_offline/Prod0/config.ini")
        return ini
    
    # def test_lalinference_dag(self):
    #     """Check that the generated lalinference DAG is correct."""
    #     self.assertEqual(self.sample_hashes["lalinference_dag"],
    #                      self._get_hash("test_data/s000000xx/C01_offline/Prod0/lalinference_1248617392-1248617397.dag"))

    def test_gpstime_insertion(self):
        """Check that the GPS time is picked-up from the time file."""
        ini = self._get_config_ini()
        start = float(ini.get("input", "gps-start-time"))
        end = float(ini.get("input", "gps-end-time"))
        with open("test_data/s000000xx/C01_offline/s000000xx_gpsTime.txt", "r") as f:
            event_time = float(f.read())

        assert(start < event_time)
        assert(end > event_time)

    def test_paths(self):
        """Check that the paths are set correctly."""
        ini = self._get_config_ini()
        basedir = ini.get("paths", "basedir")
        self.assertEqual(basedir, self.cwd+"/test_data/s000000xx/C01_offline/Prod0")

    def test_webdir(self):
        """Check that the web paths are set correctly."""
        ini = self._get_config_ini()
        self.assertEqual(self.repo.event, "s000000xx")
        webdir = ini.get("paths", "webdir")
        self.assertEqual(webdir,
                         os.path.join(os.path.expanduser("~"), *"public_html/LVC/projects/O3/C01/".split("/"), "s000000xx", "Prod0"))
        
    def test_bayeswave(self):
        """Check that Bayeswave is enabled."""
        ini = self._get_config_ini()
        assert(ini.has_option("condor", "bayeswave"))

    def test_bayeswave_disabled(self):
        """Check that Bayeswave is correctly disabled when PSDs provided."""
        shutil.rmtree("test_data/s000000xx/C01_offline/Prod0/")
        psds = {"L1": "fake.txt", "H1": "fake.txt"}
        self.repo.build_dag("C01_offline", "Prod0", psds=psds)
        os.chdir(self.cwd)
        ini = self._get_config_ini()
        assert(not ini.has_option("condor", "bayeswave"))

    def test_change_user(self):
        """Check that the ini is built for a specified accounting user."""
        shutil.rmtree("test_data/s000000xx/C01_offline/Prod0/")
        self.repo.build_dag("C01_offline", "Prod0", user = "hermann.minkowski")
        os.chdir(self.cwd)
        ini = self._get_config_ini()
        self.assertEqual(ini.get("condor", "accounting_group_user"), "hermann.minkowski")
        
    def test_queue(self):
        """Check that the Queue is correctly set."""
        ini = self._get_config_ini()
        self.assertEqual(ini.get("condor", "queue"), "Priority_PE")

        
    def tearDown(self):
        shutil.rmtree("test_data/s000000xx/C01_offline/Prod0/")
        