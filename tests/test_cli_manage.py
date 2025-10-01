"""
Test the manage functions from the CLI
"""

from importlib import reload
import unittest
from unittest.mock import patch

import os
import io
import shutil
import contextlib

from click.testing import CliRunner
import asimov
from asimov.event import Production
from asimov.cli.application import apply_page
from asimov.cli import manage, project
from asimov.ledger import YAMLLedger
from asimov.pipeline import PipelineException

pipelines = {"bayeswave"}
EVENTS = ["GW150914_095045", "GW190924_021846", "GW190929_012149", "GW191109_010717"]


class TestBuild(unittest.TestCase):
    """
    Test the build process.
    """

    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(f"{self.cwd}/tests/tmp/")
    
    def setUp(self):
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

    def test_build_all_events(self):
        """Check that multiple events can be built at once"""
        with patch("asimov.current_ledger", new=YAMLLedger(".asimov/ledger.yml")):
            reload(asimov)
            reload(manage)
            runner = CliRunner()
            
            result = runner.invoke(manage.manage, ['build'])
            for event in EVENTS:
                self.assertTrue(f"Working on {event}" in result.output)
                self.assertTrue(f"Production config Prod0 created" in result.output)
                self.assertFalse(f"Production config Prod1 created" in result.output)
                self.assertTrue(os.path.exists(os.path.join(self.cwd, "tests", "tmp", "project", "checkouts", event, "C01_offline", "Prod0.ini")))
                    

    def test_build_dryruns(self):
        """Check that multiple events can be built at once"""
        with patch("asimov.current_ledger", new=YAMLLedger(".asimov/ledger.yml")):
            reload(asimov)
            reload(manage)
            runner = CliRunner()

            result = runner.invoke(manage.manage, ['build', '--dryrun'])
            for event in EVENTS:
                    self.assertTrue(f"Working on {event}" in result.output)
                    self.assertTrue(f"Will create Prod0" in result.output)

    def test_check_running_events_ignored(self):
        """Check that multiple events can be built at once"""
        with patch("asimov.current_ledger", new=YAMLLedger(".asimov/ledger.yml")):
            reload(asimov)
            reload(manage)
            runner = CliRunner()
            event = EVENTS[0]
            with open(os.path.join(self.cwd, "tests", "tmp", "project", "test_ledger_page.yaml"), "w") as ledger_page:
                ledger_page.write(f"""
kind: analysis
pipeline: bilby
event: {event}
name: Prod8
status: running
                """)
            apply_page(os.path.join(self.cwd, "tests", "tmp", "project", "test_ledger_page.yaml"), event=event, ledger=self.ledger)

            result = runner.invoke(manage.manage, ['build', '--dryrun'])
            self.assertTrue(f"Working on {event}" in result.output)
            self.assertFalse(f"Will create Prod8" in result.output)


class TestSubmit(unittest.TestCase):
    """
    Test the submit process.
    """

    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(f"{self.cwd}/tests/tmp/")
    
    def setUp(self):
        os.makedirs(f"{self.cwd}/tests/tmp/project")
        os.chdir(f"{self.cwd}/tests/tmp/project")
        runner = CliRunner()
        result = runner.invoke(project.init,
                               ['Test Project', '--root', f"{self.cwd}/tests/tmp/project"])
        assert result.exit_code == 0
        assert result.output == '● New project created successfully!\n'
        self.ledger = YAMLLedger(".asimov/ledger.yml")

        #f = io.StringIO()
        #with contextlib.redirect_stdout(f):
        apply_page(file = "https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe.yaml", event=None, ledger=self.ledger)
        apply_page(file = "https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe-priors.yaml", event=None, ledger=self.ledger)
        for event in EVENTS:
            for pipeline in pipelines:
                apply_page(file = f"https://git.ligo.org/asimov/data/-/raw/main/tests/{event}.yaml", event=None, ledger=self.ledger)
                apply_page(file = f"https://git.ligo.org/asimov/data/-/raw/main/tests/{pipeline}.yaml", event=event, ledger=self.ledger)

    def test_buildsubmit_all_events(self):
        """Check that multiple events can be built at once"""
        with patch("asimov.current_ledger", new=YAMLLedger(".asimov/ledger.yml")):
            reload(asimov)
            reload(manage)
            runner = CliRunner()

            result = runner.invoke(manage.manage, ['build', 'submit'])
            for event in EVENTS:
                self.assertTrue(f"Working on {event}" in result.output)
                self.assertTrue(f"Production config Prod0 created" in result.output)
                self.assertFalse(f"Production config Prod1 created" in result.output)
                self.assertTrue(os.path.exists(os.path.join(self.cwd, "tests", "tmp", "project", "checkouts", event, "C01_offline", "Prod0.ini")))
                    

    def test_build_submit_dryruns(self):
        """Check that multiple events can be built at once"""
        with patch("asimov.current_ledger", new=YAMLLedger(".asimov/ledger.yml")):
            reload(asimov)
            reload(manage)
            runner = CliRunner()

            result = runner.invoke(manage.manage, ['build', 'submit', '--dryrun'])
            for event in EVENTS:
                    output = """bayeswave_pipe --trigger-time=1126259462.391 --copy-frames --transfer-files -r """
                    self.assertTrue(output in result.output)

    def test_submit_no_build(self):
        """Check that the command fails as expected if the build has not been completed."""
        runner = CliRunner()
        result = runner.invoke(manage.manage, ['submit', '--dryrun'])
        self.assertTrue("as it hasn't been built yet" in result.output)
                    
    @unittest.skip("I can't get the mocking to work properly.")
    def test_submit_reset(self):
        """Check that an event analysis can be reset"""

        event = EVENTS[0]
        with open(os.path.join(self.cwd, "tests", "tmp", "project", "test_ledger_page.yaml"), "w") as ledger_page:
            ledger_page.write(f"""
kind: analysis
pipeline: bilby
event: {event}
name: Prod8
status: restart
                """)
        apply_page(os.path.join(self.cwd, "tests", "tmp", "project", "test_ledger_page.yaml"), event=event, ledger=self.ledger)

        with patch("asimov.current_ledger", new=YAMLLedger(".asimov/ledger.yml")):
            reload(asimov)
            reload(manage)
            
            runner = CliRunner()
            
            result = runner.invoke(manage.manage, ['submit', '--dryrun'])
            self.assertTrue(f"Resubmitted {event}/Prod8" in result.output)

    @unittest.skip("I can't get the mocking to work properly.")
    def test_submit_failure(self):
        """Check that failed submits are caught"""
        with patch("asimov.current_ledger", new=YAMLLedger(".asimov/ledger.yml")):
            reload(asimov)
            reload(manage)
            runner = CliRunner()

            with patch("asimov.event.Production", {"pipeline.submit_dag.side_effect": PipelineException}):
                result = runner.invoke(manage.manage, ['build', 'submit'])
                print(result.output)
                self.assertTrue(f"Unable to submit" in result.output)
            

