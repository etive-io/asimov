"""Tests for the LALInference interface."""

import unittest
import shutil
import os
import git

from asimov.pipelines.lalinference import LALInference
from asimov.event import Event
from asimov.pipeline import PipelineException

TEST_YAML = """
name: S000000xx
working directory: {0}/tests/tmp/s000000xx/
repository: {0}/tests/test_data/s000000xx
webdir: ''
productions:
- Prod0:
    pipeline: lalinference
    comment: PSD production
    status: wait

"""

@unittest.skip("Skipped while unmaintained.")
class LALInferenceTests(unittest.TestCase):
    """Test lalinference interface"""

    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()
        repo = git.Repo.init(cls.cwd+"/tests/test_data/s000000xx/")
        os.chdir(cls.cwd+"/tests/test_data/s000000xx/")
        os.system("git add analyses/Prod0_test.ini analyses/s000000xx_gpsTime.txt")
        os.system("git commit -m 'test'")
        os.chdir(cls.cwd)


    @classmethod
    def tearDownClass(cls):
        """Destroy all the products of this test."""
        os.system(f"rm -rf {cls.cwd}/tests/tmp/")
        os.system(f"rm -rf {cls.cwd}/tests/test_data/s000000xx/.git")
        try:
            shutil.rmtree("/tmp/S000000xx")
        except:
            pass

    def tearDown(self):
        #os.system(f"{self.cwd}/tests/tmp/-rf")
        pass
        
    def setUp(self):
        """Create a pipeline."""
        self.event = Event.from_yaml(TEST_YAML.format(self.cwd))
        self.pipeline = LALInference(self.event.productions[0])
        out = self.pipeline.build_dag()

    def test_dag(self):
        """Check that a DAG is actually produced."""
        self.assertEqual(os.path.exists(f"{self.cwd}/tests/tmp/s000000xx/Prod0/lalinference_1248617392-1248617397.dag"), 1)
