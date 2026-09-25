"""Tests for the LALInference interface."""

import unittest
from unittest.mock import Mock, patch

import shutil
import os
import git
import tempfile

import io
import contextlib

import numpy as np


from click.testing import CliRunner

from asimov.utils import set_directory
from asimov import config

from asimov.cli import project, manage
from asimov.cli import configuration
from asimov.cli.application import apply_page
from asimov.ledger import YAMLLedger
from asimov.event import Event
from asimov.pipeline import PipelineException
from asimov.pipelines.bayeswave import BayesWave
from asimov.event import Event
from asimov.pipeline import PipelineException

TEST_YAML = """
name: S000000xx
repository: {0}/tests/test_data/s000000xx/
working_directory: {0}/tests/tmp/s000000xx/
webdir: ''
productions:
- Prod1:
    rundir: {0}/tests/tmp/s000000xx/C01_offline/Prod1
    pipeline: bayeswave
    comment: PSD production
    status: wait

"""

class BayeswaveTests(unittest.TestCase):
    """Test bayeswave interface.

    TODO
    ----
    Right now these feel a bit more like an expression of intention than actual tests, as we'll need to set the testing environment up better to make this work.

    The test_dag method will need to be updated.
"""

    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()

    def setUp(self):
        os.makedirs(f"{self.cwd}/tests/tmp/project")
        os.chdir(f"{self.cwd}/tests/tmp/project")
        runner = CliRunner()
        result = runner.invoke(project.init,
                               ['Test Project', '--root', f"{self.cwd}/tests/tmp/project"])
        assert result.exit_code == 0
        assert result.output == '● New project created successfully!\n'
        self.ledger = YAMLLedger(f".asimov/ledger.yml")

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(f"{self.cwd}/tests/tmp/project/")

    @unittest.skip("Skipped temporarily while RIFT is updated")
    def test_build_cli(self):
        """Check that a RIFT config file can be built."""
        apply_page(file = "https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe.yaml", event=None, ledger=self.ledger)
        apply_page(file = "https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe-priors.yaml", event=None, ledger=self.ledger)
        event = "GW150914_095045"
        pipeline = "bayeswave"
        apply_page(file = f"https://git.ligo.org/asimov/data/-/raw/main/tests/{event}.yaml", event=None, ledger=self.ledger)
        apply_page(file = f"https://git.ligo.org/asimov/data/-/raw/main/tests/{pipeline}.yaml", event=event, ledger=self.ledger)

        runner = CliRunner()
        result = runner.invoke(manage.build, "--dryrun")
        self.assertTrue("util_RIFT_pseudo_pipe.py" in result.output)

    def test_make_ini(self):
        """Check that a bayeswave config file can be built."""
        apply_page(file = "https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe.yaml", event=None, ledger=self.ledger)
        apply_page(file = "https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe-priors.yaml", event=None, ledger=self.ledger)
        event = "GW150914_095045"
        pipeline = "bayeswave"
        apply_page(file = f"https://git.ligo.org/asimov/data/-/raw/main/tests/{event}.yaml", event=None, ledger=self.ledger)
        apply_page(file = f"https://git.ligo.org/asimov/data/-/raw/main/tests/{pipeline}.yaml", event=event, ledger=self.ledger)

        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            production = self.ledger.get_event(event)[0].productions[0]
            with set_directory(os.path.join("checkouts", event, config.get("general", "calibration_directory"))):
                production.make_config(f"{production.name}.ini")
            self.assertTrue(os.path.exists(os.path.join(config.get("project", "root"),
                                                        "checkouts",
                                                        event,
                                                        config.get("general", "calibration_directory"),
                                                        f"{production.name}.ini")))

        
    def test_build_api(self):
        """Check that a bayeswave DAG can be built."""
        apply_page(file = "https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe.yaml", event=None, ledger=self.ledger)
        apply_page(file = "https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe-priors.yaml", event=None, ledger=self.ledger)
        event = "GW150914_095045"
        pipeline = "bayeswave"
        apply_page(file = f"https://git.ligo.org/asimov/data/-/raw/main/tests/{event}.yaml", event=None, ledger=self.ledger)
        apply_page(file = f"https://git.ligo.org/asimov/data/-/raw/main/tests/{pipeline}.yaml", event=event, ledger=self.ledger)

        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            production = self.ledger.get_event(event)[0].productions[0]
            with set_directory(os.path.join("checkouts", event, config.get("general", "calibration_directory"))):
                production.make_config(f"{production.name}.ini")
            production.pipeline.build_dag(dryrun=True)
            self.assertTrue("bayeswave_pipe" in f.getvalue())

#    @unittest.skipIf(not os.path.exists(os.path.join(config.get("pipelines", "environment"), "bin", "bayeswave_pipe")),
#                    "Bayeswave Pipe isnt installed on the test system")
    @patch('subprocess.Popen')
    def test_submit_api(self, mock_popen):
        """Check that a bayeswave config file can be submitted."""
        apply_page(file = "https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe.yaml", event=None, ledger=self.ledger)
        apply_page(file = "https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe-priors.yaml", event=None, ledger=self.ledger)
        event = "GW150914_095045"
        pipeline = "bayeswave"
        apply_page(file = f"https://git.ligo.org/asimov/data/-/raw/main/tests/{event}.yaml", event=None, ledger=self.ledger)
        apply_page(file = f"https://git.ligo.org/asimov/data/-/raw/main/tests/{pipeline}.yaml", event=event, ledger=self.ledger)
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            production = self.ledger.get_event(event)[0].productions[0]
            with set_directory(os.path.join("checkouts", event, config.get("general", "calibration_directory"))):
                production.make_config(f"{production.name}.ini")
            # We need to make the workdir as this ought to be done by bayeswave_pipe
            os.makedirs(os.path.join("working", event, production.name))

            mock_popen.returncode=0
            mock_popen.return_value.communicate.return_value=(b"Blah blah blah To submit: just run this", b"Lots of stuff on stderr")

            production.pipeline.build_dag(dryrun=False)

        with contextlib.redirect_stdout(f):

            mock_popen.returncode=0
            mock_popen.return_value.communicate.return_value=(b"submitted to cluster 999", b"Lots of stuff on stderr")

            
            production.pipeline.submit_dag(dryrun=False)
            self.ledger.update_event(production.event)
        
        self.assertEqual(production.job_id, 999)
        self.assertEqual(self.ledger.get_event(event)[0].productions[0].job_id, 999)

    def test_presubmit_mocked(self):
        """Check that a bayeswave submit file should be altered"""
        apply_page(file = "https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe.yaml", event=None, ledger=self.ledger)
        apply_page(file = "https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe-priors.yaml", event=None, ledger=self.ledger)
        event = "GW150914_095045"
        pipeline = "bayeswave"
        apply_page(file = f"https://git.ligo.org/asimov/data/-/raw/main/tests/{event}.yaml", event=None, ledger=self.ledger)
        apply_page(file = f"https://git.ligo.org/asimov/data/-/raw/main/tests/{pipeline}.yaml", event=event, ledger=self.ledger)

        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            production = self.ledger.get_event(event)[0].productions[0]
            with set_directory(os.path.join("checkouts", event, config.get("general", "calibration_directory"))):
                production.make_config(f"{production.name}.ini")
            production.pipeline.build_dag(dryrun=True)
            self.assertTrue("bayeswave_pipe" in f.getvalue())
        # We need to make the workdir as this ought to be done by bayeswave_pipe
        os.makedirs(os.path.join("working", event, production.name))
        with set_directory(os.path.join(config.get("general", "rundir_default"), event, production.name)):
            with open("bayeswave_post.sub", "w") as submit_file:
                submit_file.write("This is some test text and is just garbage")

        production.pipeline.before_submit()

        with set_directory(os.path.join(config.get("general", "rundir_default"), event, production.name)):
            with open("bayeswave_post.sub", "r") as submit_file:
                self.assertTrue("request_disk" in submit_file.read())

    @patch('subprocess.Popen.communicate')
    @patch('subprocess.Popen')
    def test_bad_dag_build(self, mock_popen, mock_pcomm):
        """Check that things behave as expected if the DAG file can't be build."""
        apply_page(file = "https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe.yaml", event=None, ledger=self.ledger)
        apply_page(file = "https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe-priors.yaml", event=None, ledger=self.ledger)
        event = "GW150914_095045"
        pipeline = "bayeswave"
        apply_page(file = f"https://git.ligo.org/asimov/data/-/raw/main/tests/{event}.yaml", event=None, ledger=self.ledger)
        apply_page(file = f"https://git.ligo.org/asimov/data/-/raw/main/tests/{pipeline}.yaml", event=event, ledger=self.ledger)

        mock_popen.returncode=1 #"Could not build the DAG file"
        mock_popen.return_value.communicate.return_value=(b"Could not be created", b"Lots of stuff on stderr")
        
        production = self.ledger.get_event(event)[0].productions[0]
        with set_directory(os.path.join("checkouts", event, config.get("general", "calibration_directory"))):
            production.make_config(f"{production.name}.ini")
        
        with self.assertRaises(PipelineException):
            production.pipeline.build_dag(dryrun=False)


class BayeswaveSupressionTests(unittest.TestCase):
    """Unit tests for BayesWave.supress_psd.

    These tests mock all file I/O and focus on verifying that the numpy
    suppression logic is correct for single-range, multi-range, and the
    backwards-compatible single-dict input forms.
    """

    def _make_pipeline(self, tmp_repo_dir, sample_rate=4096):
        """Return a BayesWave instance with all external dependencies mocked."""
        production = Mock()
        production.meta = {
            "likelihood": {"sample rate": sample_rate},
            "quality": {},
            "interferometers": ["H1", "L1"],
        }
        production.event.name = "S000000xx"
        production.name = "Prod0"
        production.event.repository.directory = tmp_repo_dir

        pipeline = BayesWave.__new__(BayesWave)
        pipeline.production = production
        pipeline.category = "C01_offline"
        pipeline.logger = Mock()
        return pipeline

    def _write_psd(self, repo_dir, ifo, sample_rate, freqs, values):
        """Write a fake ASCII PSD into the expected repository path."""
        psd_dir = os.path.join(repo_dir, "C01_offline", "psds", str(sample_rate))
        os.makedirs(psd_dir, exist_ok=True)
        path = os.path.join(psd_dir, f"{ifo}-psd.dat")
        np.savetxt(path, np.vstack([freqs, values]).T, fmt="%+.5e")
        return path

    def _read_saved_psd(self, tmp_dir, ifo):
        """Read the PSD written to the current working directory by supress_psd."""
        return np.genfromtxt(os.path.join(tmp_dir, f"{ifo}-psd.dat"))

    @patch("asimov.pipelines.bayeswave.Store")
    @patch("asimov.pipelines.bayeswave.config")
    def test_single_range_suppresses_correct_bins(self, mock_config, mock_store_cls):
        """Bins inside [fmin, fmax] are set to 1.0; others are unchanged."""
        mock_config.get.return_value = "/tmp/fake-store"
        mock_store_cls.return_value = Mock()

        with tempfile.TemporaryDirectory() as repo_dir:
            with tempfile.TemporaryDirectory() as work_dir:
                freqs = np.linspace(10, 200, 191)
                values = np.full_like(freqs, 1e-46)
                psd_file = self._write_psd(repo_dir, "H1", 4096, freqs, values)

                pipeline = self._make_pipeline(repo_dir)
                pipeline.production.event.repository.add_file = Mock()

                with set_directory(work_dir):
                    pipeline.supress_psd("H1", [{"lower": 59.0, "upper": 61.0}], psd_file)

                saved = self._read_saved_psd(work_dir, "H1")
                in_band = (saved[:, 0] >= 59.0) & (saved[:, 0] <= 61.0)
                self.assertTrue(np.all(saved[:, 1][in_band] == 1.0),
                                "Bins inside the notch should be 1.0")
                np.testing.assert_allclose(
                    saved[:, 1][~in_band], 1e-46,
                    err_msg="Bins outside the notch should be unchanged"
                )

    @patch("asimov.pipelines.bayeswave.Store")
    @patch("asimov.pipelines.bayeswave.config")
    def test_single_range_suppresses_outside_unchanged(self, mock_config, mock_store_cls):
        """Frequencies outside the suppression range keep their original value."""
        mock_config.get.return_value = "/tmp/fake-store"
        mock_store_cls.return_value = Mock()

        with tempfile.TemporaryDirectory() as repo_dir:
            with tempfile.TemporaryDirectory() as work_dir:
                freqs = np.array([10.0, 30.0, 60.0, 90.0, 120.0])
                values = np.array([1e-46, 2e-46, 3e-46, 4e-46, 5e-46])
                psd_file = self._write_psd(repo_dir, "L1", 4096, freqs, values)

                pipeline = self._make_pipeline(repo_dir)
                pipeline.production.event.repository.add_file = Mock()

                with set_directory(work_dir):
                    pipeline.supress_psd("L1", [{"lower": 55.0, "upper": 65.0}], psd_file)

                saved = self._read_saved_psd(work_dir, "L1")
                psd = saved[:, 1]

                np.testing.assert_allclose(psd[0], 1e-46)
                np.testing.assert_allclose(psd[1], 2e-46)
                self.assertAlmostEqual(psd[2], 1.0)   # 60 Hz — inside notch
                np.testing.assert_allclose(psd[3], 4e-46)
                np.testing.assert_allclose(psd[4], 5e-46)

    @patch("asimov.pipelines.bayeswave.Store")
    @patch("asimov.pipelines.bayeswave.config")
    def test_multiple_ranges_all_suppressed(self, mock_config, mock_store_cls):
        """All notch bands are suppressed in a single call, with one commit."""
        mock_config.get.return_value = "/tmp/fake-store"
        mock_store_cls.return_value = Mock()

        with tempfile.TemporaryDirectory() as repo_dir:
            with tempfile.TemporaryDirectory() as work_dir:
                freqs = np.array([10.0, 30.0, 60.0, 90.0, 120.0])
                values = np.array([1e-46, 2e-46, 3e-46, 4e-46, 5e-46])
                psd_file = self._write_psd(repo_dir, "H1", 4096, freqs, values)

                pipeline = self._make_pipeline(repo_dir)
                mock_add_file = Mock()
                pipeline.production.event.repository.add_file = mock_add_file

                with set_directory(work_dir):
                    pipeline.supress_psd("H1", [
                        {"lower": 55.0, "upper": 65.0},
                        {"lower": 115.0, "upper": 125.0},
                    ], psd_file)

                saved = self._read_saved_psd(work_dir, "H1")
                psd = saved[:, 1]

                self.assertAlmostEqual(psd[2], 1.0)   # 60 Hz — first notch
                self.assertAlmostEqual(psd[4], 1.0)   # 120 Hz — second notch
                np.testing.assert_allclose(psd[0], 1e-46)
                np.testing.assert_allclose(psd[1], 2e-46)
                np.testing.assert_allclose(psd[3], 4e-46)

                # Only one commit despite two notches
                mock_add_file.assert_called_once()

    @patch("asimov.pipelines.bayeswave.Store")
    @patch("asimov.pipelines.bayeswave.config")
    def test_backwards_compat_single_dict(self, mock_config, mock_store_cls):
        """Passing a bare dict (old call style) still suppresses the correct range."""
        mock_config.get.return_value = "/tmp/fake-store"
        mock_store_cls.return_value = Mock()

        with tempfile.TemporaryDirectory() as repo_dir:
            with tempfile.TemporaryDirectory() as work_dir:
                freqs = np.array([10.0, 60.0, 120.0])
                values = np.array([1e-46, 3e-46, 5e-46])
                psd_file = self._write_psd(repo_dir, "H1", 4096, freqs, values)

                pipeline = self._make_pipeline(repo_dir)
                pipeline.production.event.repository.add_file = Mock()

                with set_directory(work_dir):
                    # Passing a dict directly (backwards-compat path)
                    pipeline.supress_psd("H1", {"lower": 55.0, "upper": 65.0}, psd_file)

                saved = self._read_saved_psd(work_dir, "H1")
                psd = saved[:, 1]

                self.assertAlmostEqual(psd[1], 1.0)   # 60 Hz — inside notch
                np.testing.assert_allclose(psd[0], 1e-46)
                np.testing.assert_allclose(psd[2], 5e-46)

    @patch("asimov.pipelines.bayeswave.Store")
    @patch("asimov.pipelines.bayeswave.config")
    def test_call_site_normalises_single_dict_yaml(self, mock_config, mock_store_cls):
        """The upload() call site wraps a single-dict 'supress' value into a list."""
        mock_config.get.return_value = "/tmp/fake-store"
        mock_store_cls.return_value = Mock()

        with tempfile.TemporaryDirectory() as repo_dir:
            with tempfile.TemporaryDirectory() as work_dir:
                freqs = np.array([10.0, 60.0, 120.0])
                values = np.array([1e-46, 3e-46, 5e-46])
                psd_file = self._write_psd(repo_dir, "H1", 4096, freqs, values)

                pipeline = self._make_pipeline(repo_dir)
                pipeline.production.event.repository.add_file = Mock()
                pipeline.production.meta["quality"]["supress"] = {
                    "H1": {"lower": 55.0, "upper": 65.0}
                }

                # Simulate the call-site normalisation from upload()
                for ifo in pipeline.production.meta["quality"]["supress"]:
                    if ifo in pipeline.production.meta["interferometers"]:
                        ranges = pipeline.production.meta["quality"]["supress"][ifo]
                        if isinstance(ranges, dict):
                            ranges = [ranges]
                        with set_directory(work_dir):
                            pipeline.supress_psd(ifo, ranges, psd_file)

                saved = self._read_saved_psd(work_dir, "H1")
                self.assertAlmostEqual(saved[1, 1], 1.0)

    @patch("asimov.pipelines.bayeswave.Store")
    @patch("asimov.pipelines.bayeswave.config")
    def test_store_add_file_called_once_per_ifo(self, mock_config, mock_store_cls):
        """The results store receives exactly one add_file call per IFO regardless of notch count."""
        mock_config.get.return_value = "/tmp/fake-store"
        mock_store = Mock()
        mock_store_cls.return_value = mock_store

        with tempfile.TemporaryDirectory() as repo_dir:
            with tempfile.TemporaryDirectory() as work_dir:
                freqs = np.linspace(10, 200, 191)
                values = np.full_like(freqs, 1e-46)
                psd_file = self._write_psd(repo_dir, "H1", 4096, freqs, values)

                pipeline = self._make_pipeline(repo_dir)
                pipeline.production.event.repository.add_file = Mock()

                with set_directory(work_dir):
                    pipeline.supress_psd("H1", [
                        {"lower": 59.0, "upper": 61.0},
                        {"lower": 119.0, "upper": 121.0},
                        {"lower": 179.0, "upper": 181.0},
                    ], psd_file)

                mock_store.add_file.assert_called_once()
