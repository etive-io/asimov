"""Test that yaml event formats are parsed and written correctly."""

import unittest
import os
import shutil
import git
import asimov.event
from asimov.cli.project import make_project
from asimov.cli.application import apply_page
from asimov.ledger import YAMLLedger

TEST_YAML = """
name: S000000xx
data: 
  channels:
    L1: /this/is/fake
  calibration: 
    L1: Fake
working directory: {0}/tests/tmp/
repository: {0}/tests/test_data/s000000xx/
interferometers: 
- L1
quality: {{}}
productions:
  - name: Prod0
    pipeline: lalinference
    comment: PSD production
    status: wait
"""

BAD_YAML = """
repository: {0}/tests/test_data/s000000xx/
working directory: {0}/tests/tmp/
interferometers: [L1]
data:
  calibration:
    L1: Fake
quality: {{}}
productions:
  - name: Prod0
    comment: PSD production
    status: wait

"""

BAD_YAML_2 = """
name: S200311bg
interferometers: [L1]
data:
  calibration:
  - L1: Fake
working directory: {0}/tests/tmp/
productions:
  - name: Prod0
    comment: PSD production
    status: wait

"""

class EventTests(unittest.TestCase):
    """All tests of the YAML event format."""
    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()
        #git.Repo.init(cls.cwd+"/tests/test_data/s000000xx/")

    @classmethod
    def tearDownClass(cls):
        """Destroy all the products of this test."""
        pass
        
    def setUp(self):
        os.makedirs(f"{self.cwd}/tests/tmp/project")
        os.chdir(f"{self.cwd}/tests/tmp/project")
        make_project(name="Test project", root=f"{self.cwd}/tests/tmp/project")
        self.ledger = YAMLLedger(f".asimov/ledger.yml")
        apply_page(file = "https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe.yaml", event=None, ledger=self.ledger)
        apply_page(file = "https://git.ligo.org/asimov/data/-/raw/main/events/gwtc-2-1/GW150914_095045.yaml", event=None, ledger=self.ledger)

        self.event = asimov.event.Event.from_yaml(TEST_YAML.format(self.cwd), ledger=self.ledger)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(f"{self.cwd}/tests/tmp/project")
        
    def test_name(self):
        """Check the name is loaded correctly."""
        self.assertEqual(self.event.name, "S000000xx")

    # def test_no_name_error(self):
    #     """Check an exception is raised if the event name is missing."""
    #     with self.assertRaises(asimov.event.DescriptionException):
    #         asimov.event.Event.from_yaml(BAD_YAML.format(self.cwd))

class ProductionTests(unittest.TestCase):
    """Tests of the YAML Production format."""

    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()

    @classmethod
    def tearDownClass(cls):
        """Destroy all the products of this test."""
        pass
            
    def setUp(self):
        os.makedirs(f"{self.cwd}/tests/tmp/project")
        os.chdir(f"{self.cwd}/tests/tmp/project")
        make_project(name="Test project", root=f"{self.cwd}/tests/tmp/project")
        self.ledger = YAMLLedger(f".asimov/ledger.yml")
        apply_page(file = "https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe.yaml", event=None, ledger=self.ledger)
        apply_page(file = "https://git.ligo.org/asimov/data/-/raw/main/events/gwtc-2-1/GW150914_095045.yaml", event=None, ledger=self.ledger)
        self.event = asimov.event.Event("S000000xx", ledger=self.ledger)

    def tearDown(self):
        shutil.rmtree(f"{self.cwd}/tests/tmp/project")
        os.chdir(self.cwd)

    def test_missing_name(self):
        """Check that an exception is raised if the production has no name."""
        production = dict(status="wait", pipeline="lalinference")
        with self.assertRaises(ValueError):
            asimov.event.Production.from_dict(production, subject=self.event)
        
    def test_missing_pipeline(self):
        """Check that an exception is raised if the production has no pipeline."""
        production = {"S000000x": dict(status="wait")}
        with self.assertRaises(ValueError):
            asimov.event.Production.from_dict(production, subject=self.event)
        
    def test_missing_status(self):
        """Check that an exception is raised if the production has no status."""
        production = {"S000000x": dict(pipeline="lalinference")}
        with self.assertRaises(ValueError):
            asimov.event.Production.from_dict(production, subject=self.event)

    def test_production_prior_read(self):
            """Check that per-production priors get read."""
            YAML_WITH_PRODUCTION_PRIORS = """
            name: S200311bg
            interferometers: [L1]
            data:
              calibration: {{}}
              channels:
                L1: /this/is/fake
            working directory: {0}/tests/tmp/
            priors:
              q: [0, 1]
            productions:
              - name: Prod0
                comment: PSD production
                pipeline: lalinference
                priors:
                  q: [0.0, 0.05]
                status: wait
              - name: Prod1
                comment: PSD production
                pipeline: lalinference
                priors:
                  q: [0.0, 0.8]
                status: wait
            """
            event = asimov.event.Event.from_yaml(
                YAML_WITH_PRODUCTION_PRIORS.format(self.cwd),
                ledger=self.ledger)
            prod0 = event.productions[0]
            prod1 = event.productions[1]
            self.assertEqual(prod0.priors['q'][1], 0.05)
            self.assertEqual(prod0.meta['priors']['q'][1], 0.05)
            self.assertEqual(prod1.priors['q'][1], 0.8)
            self.assertEqual(prod1.meta['priors']['q'][1], 0.8)

    def test_production_prior_preserved(self):
        """Check that per-production priors get preserved when saved to yaml."""
        YAML_WITH_PRODUCTION_PRIORS = """
        name: S200311bg
        interferometers: [L1]
        data:
          calibration: {{}}
          channels:
            L1: /this/is/fake
        working directory: {0}/tests/tmp/
        priors:
          q: [0, 1]
        productions:
        - name: Prod0
          comment: PSD production
          pipeline: lalinference
          priors:
                q: [0.0, 0.05]
          status: wait
        - name: Prod1
          comment: PSD production
          pipeline: lalinference
          priors:
                q: [0.0, 1.0]
          status: wait
        """
        event = asimov.event.Event.from_yaml(
            YAML_WITH_PRODUCTION_PRIORS.format(self.cwd),
            ledger=self.ledger)

        event_YAML = event.to_yaml()
        
        event2 = asimov.event.Event.from_yaml(event_YAML, ledger=self.ledger)
        prod0 = event.productions[0]
        prod1 = event.productions[1]

        prod01 = event2.productions[0]
        prod11 = event2.productions[1]
        self.assertEqual(prod0.priors, prod01.priors)
        
