import unittest
import os
import shutil
import git

from importlib import reload
import contextlib
import io
from unittest.mock import patch

from click.testing import CliRunner

import asimov
from asimov.event import Production
from asimov.cli import review, project
from asimov.ledger import YAMLLedger
import asimov.event
from asimov.cli.project import make_project
from asimov.cli.application import apply_page
from asimov.ledger import YAMLLedger

EVENTS = ["GW150914_095045", "GW190924_021846", "GW190929_012149", "GW191109_010717"]
pipelines = {"bayeswave"}

TEST_YAML = """
name: S000000xx
working directory: {0}/tests/tmp/
repository: {0}/tests/test_data/s000000xx/
data: 
  channels:
    L1: /this/is/fake
  calibration: 
    L1: Fake
interferometers: 
- L1
quality: {{}}
productions:
  - name: Prod0
    pipeline: lalinference
    comment: PSD production
    status: wait
    review:
    - message: Second.
      status: APPROVED
      timestamp: 2021-03-17 21:58:05
    - message: This is a review message.
      status: REJECTED
      timestamp: 2021-03-17 20:58:05
    - message: Third.
      timestamp: 2021-03-18 20:58:05
"""
TEST_YAML_2 = """
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
class ReviewTests(unittest.TestCase):
    """All tests of the YAML event format."""
    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()
        git.Repo.init(cls.cwd+"/tests/test_data/s000000xx/")
        
    def setUp(self):
        os.makedirs(f"{self.cwd}/tests/tmp/project")
        os.chdir(f"{self.cwd}/tests/tmp/project")
        make_project(name="Test project", root=f"{self.cwd}/tests/tmp/project")
        self.ledger = YAMLLedger(f".asimov/ledger.yml")
        apply_page(file = "https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe.yaml", event=None, ledger=self.ledger)
        apply_page(file = "https://git.ligo.org/asimov/data/-/raw/main/events/gwtc-2-1/GW150914_095045.yaml", event=None, ledger=self.ledger)

        self.event = asimov.event.Event.from_yaml(TEST_YAML.format(self.cwd),
                                                  ledger=self.ledger)
        self.event_no_review = asimov.event.Event.from_yaml(TEST_YAML_2.format(self.cwd),
                                                            ledger=self.ledger)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(f"{self.cwd}/tests/tmp/project")
    
    def test_review_parsing(self):
        """Check that review messages get parsed correctly."""
        self.assertEqual(self.event.productions[0].review[0].status, "REJECTED")

    # def test_empty_register_creation(self):
    #     """Check that productions initialise an empty register if no review information attached."""
    #     self.assertEqual(len(self.event_no_review.productions[0].review), 0)

    def test_review_message_sort(self):
        """Check that messages are correctly sorted."""
        self.assertEqual(self.event.productions[0].review[-1].message, "Third.")
        self.assertEqual(self.event.productions[0].review[1].message, "Second.")

    def test_gets_latest_status(self):
        """Ensure latest status is reported."""
        self.assertEqual(self.event.productions[0].review.status, "APPROVED")
        
    def test_outputs_to_dict(self):
        """Check that dictionary output works"""
        self.assertEqual(self.event.productions[0].review.to_dicts()[0]['status'], 'REJECTED')


class ReviewCliTests(unittest.TestCase):
    """Test the CLI interfaces for review."""

    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(f"{self.cwd}/tests/tmp/")
    
    def setUp(self):
        project_dir = f"{self.cwd}/tests/tmp/"
        if os.path.exists(project_dir):
                    shutil.rmtree(project_dir)
        os.makedirs(f"{self.cwd}/tests/tmp/project")
        os.chdir(f"{self.cwd}/tests/tmp/project")
        runner = CliRunner()
        result = runner.invoke(project.init,
                               ['Test Project', '--root', f"{self.cwd}/tests/tmp/project"])
        assert result.exit_code == 0
        assert result.output == '● New project created successfully!\n'
        self.ledger = YAMLLedger(".asimov/ledger.yml")

        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            apply_page(file = "https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe.yaml", event=None, ledger=self.ledger)
            apply_page(file = "https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe-priors.yaml", event=None, ledger=self.ledger)
            for event in EVENTS:
                for pipeline in pipelines:
                    apply_page(file = f"https://git.ligo.org/asimov/data/-/raw/main/tests/{event}.yaml", event=None, ledger=self.ledger)
                    apply_page(file = f"https://git.ligo.org/asimov/data/-/raw/main/tests/{pipeline}.yaml", event=event, ledger=self.ledger)

    # def test_show_review_no_review(self):
    #     """Check that the CLI can show a review report with no reviews"""
    #     with patch("asimov.current_ledger", new=YAMLLedger(".asimov/ledger.yml")):
    #         reload(asimov)
    #         reload(review)
    #         runner = CliRunner()
    #         for event in EVENTS:
                
    #             result = runner.invoke(review.review,
    #                                    ['status', event])
    #             print(result.output)
    #             self.assertTrue(f"No review information exists for this production." in result.output)            

                    
    def test_add_review_to_event_reject(self):
        """Check that the CLI can add an event review"""
        with patch("asimov.current_ledger", new=YAMLLedger(".asimov/ledger.yml")):
            reload(asimov)
            reload(review)
            runner = CliRunner()

            for event in EVENTS:
                result = runner.invoke(review.review,
                                       ['add', event, "Prod0", "Rejected"])
                self.assertTrue(f"{event}/Prod0 rejected" in result.output)     

    def test_add_review_to_event_reject(self):
        """Check that the CLI can add an event review"""
        with patch("asimov.current_ledger", new=YAMLLedger(".asimov/ledger.yml")):
            reload(asimov)
            reload(review)
            runner = CliRunner()

            for event in EVENTS:
                result = runner.invoke(review.review,
                                       ['add', event, "Prod0", "Approved"])
                self.assertTrue(f"{event}/Prod0 approved" in result.output)          

    def test_add_review_to_event_unknown(self):
        """Check that the CLI rejects an unknown review status"""
        with patch("asimov.current_ledger", new=YAMLLedger(".asimov/ledger.yml")):
            reload(asimov)
            reload(review)
            runner = CliRunner()

            for event in EVENTS:
                result = runner.invoke(review.review,
                                       ['add', event, "Prod0", "Splorg"])
                self.assertTrue(f"Did not understand the review status splorg" in result.output)                          

    def test_show_review_with_review(self):
        """Check that the CLI can show a review report with no reviews"""
        with patch("asimov.current_ledger", new=YAMLLedger(".asimov/ledger.yml")):
            reload(asimov)
            reload(review)
            runner = CliRunner()

            for event in EVENTS:
                result = runner.invoke(review.review,
                                       ['add', event, "Prod0", "Approved"])                
                result = runner.invoke(review.review,
                                       ['status', event])
                self.assertTrue(f"approved" in result.output)       
