"""Tests for the RIFT interface."""

import unittest
import shutil
import os
import git

import io
import contextlib

from unittest.mock import patch
from importlib import reload

from click.testing import CliRunner

import asimov
from asimov.cli import project, manage
from asimov.cli import configuration
from asimov.cli.application import apply_page
from asimov.ledger import YAMLLedger
from asimov.pipelines.rift import Rift
from asimov.event import Event
from asimov.pipeline import PipelineException


# @unittest.skip("Skipped until RIFT is added to the testing environment correctly.")
class RiftTests(unittest.TestCase):
    """Test RIFT interface.

    The test_dag method will need to be updated.
"""

    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()

    def setUp(self):
        os.makedirs(f"{self.cwd}/tests/tmp/project")
        os.chdir(f"{self.cwd}/tests/tmp/project")
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
        
            runner = CliRunner()
            result = runner.invoke(project.init,
                                   ['Test Project', '--root', f"{self.cwd}/tests/tmp/project"])
            assert result.exit_code == 0
            assert result.output == '● New project created successfully!\n'
            self.ledger = YAMLLedger()

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(f"{self.cwd}/tests/tmp/project/")

    @unittest.skip("Skipped temporarily while RIFT is updated")
    def test_submit_cli(self):
        """Check that a RIFT config file can be built."""
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            apply_page(file = f"https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe.yaml", event=None, ledger=self.ledger)
            apply_page(file = "https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe-priors.yaml", event=None, ledger=self.ledger)
            event = "GW150914_095045"
            pipeline = "rift"
            apply_page(file = f"https://git.ligo.org/asimov/data/-/raw/main/tests/{event}.yaml", event=None, ledger=self.ledger)
            apply_page(file = f"{self.cwd}/tests/test_data/test_{pipeline}.yaml", event=event, ledger=self.ledger)
        with patch("asimov.current_ledger", new=YAMLLedger()):
            reload(asimov)
            reload(manage)
            runner = CliRunner()
            result = runner.invoke(manage.manage, ['build'])
            result = runner.invoke(manage.submit, "--dryrun")
            print(result.output)
        self.assertTrue("util_RIFT_pseudo_pipe.py" in result.output)

    @unittest.skip("Skipped temporarily while RIFT is updated")
    def test_build_api(self):
        """Check that a RIFT config file can be built."""
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            apply_page(file = "https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe.yaml", event=None, ledger=self.ledger)
            apply_page(file = "https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe-priors.yaml", event=None, ledger=self.ledger)
            event = "GW150914_095045"
            pipeline = "rift"
            apply_page(file = f"https://git.ligo.org/asimov/data/-/raw/main/tests/{event}.yaml", event=None, ledger=self.ledger)
            apply_page(file = f"{self.cwd}/tests/test_data/test_{pipeline}.yaml", event=event, ledger=self.ledger)
        with patch("asimov.current_ledger", new=YAMLLedger()):
            reload(asimov)
            reload(manage)
            runner = CliRunner()
            result = runner.invoke(manage.manage, ['build'])
            result = runner.invoke(manage.submit, "--dryrun")
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            result = self.ledger.get_event(event)[0].productions[0].pipeline.build_dag(dryrun=True)
            print("\n\nBUILDDAG ",f.getvalue())
            print("RESULT", result)
            self.assertTrue("util_RIFT_pseudo_pipe.py --assume-nospin --calibration C01 --approx IMRPhenomD" in f.getvalue())
            self.assertTrue("--ile-force-gpu " in f.getvalue())
        
    @unittest.skip("Skipped temporarily while RIFT is updated")
    def test_build_api_non_default_calibration(self):
        """Check that a RIFT correctly picks up non C01 calibration."""

        runner = CliRunner()
        result = runner.invoke(configuration.update,
                               ['--general/calibration_directory', f"C00_offline"])
        assert result.exit_code == 0
        result = runner.invoke(configuration.update,
                               ['--general/calibration', f"C00"])
        assert result.exit_code == 0

        f = io.StringIO()
        with contextlib.redirect_stdout(f):        
            apply_page(file = "https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe.yaml", event=None, ledger=self.ledger)
            apply_page(file = "https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe-priors.yaml", event=None, ledger=self.ledger)
            event = "GW150914_095045"
            pipeline = "rift"
            apply_page(file = f"https://git.ligo.org/asimov/data/-/raw/main/tests/{event}.yaml", event=None, ledger=self.ledger)
            apply_page(file = f"{self.cwd}/tests/test_data/test_{pipeline}.yaml", event=event, ledger=self.ledger)

        with patch("asimov.current_ledger", new=YAMLLedger()):
            reload(asimov)
            reload(manage)
            runner = CliRunner()
            result = runner.invoke(manage.manage, ['build'])
            result = runner.invoke(manage.submit, "--dryrun")
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            result = self.ledger.get_event(event)[0].productions[0].pipeline.build_dag(dryrun=True)
            print("\n\nBUILDDAG ",f.getvalue())
            print("RESULT", result)
            self.assertTrue("util_RIFT_pseudo_pipe.py --assume-nospin --calibration C00 --approx IMRPhenomD" in f.getvalue())
            self.assertTrue("--ile-force-gpu " in f.getvalue())
