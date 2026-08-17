"""
Integration tests for CBCFlow <-> Asimov interaction.

These tests cover the two integration paths:

1. Applicator  (cbcflow -> asimov):  ``asimov apply -p cbcflow --event <NAME>``
   Reads metadata from a cbcflow library and creates/updates an Asimov event.

2. Collector   (asimov -> cbcflow):  post-monitor hook run by ``asimov monitor``
   Reads analysis status from the asimov ledger and writes it back to the
   cbcflow library.

The tests create a lightweight, local-git-backed cbcflow library so that no
network access or real remote is required.  Git *remote* operations
(pull/push) are patched out; local add/commit operations are allowed to run
for realism.

These tests require cbcflow to be installed (``pip install cbcflow``).
If cbcflow is not available the whole module is skipped gracefully.  They
are run in a separate CI workflow with ``continue-on-error: true``.
"""

import copy
import json
import os
import shutil
import subprocess
import unittest
from unittest.mock import patch

try:
    import cbcflow
    import cbcflow.core.database
    import cbcflow.core.schema
    import cbcflow.core.parser
    from cbcflow.inputs.asimov import Collector
    from cbcflow.outputs.asimov import Applicator

    cbcflow_available = True
except ImportError:
    cbcflow_available = False

import git

from asimov.testing import AsimovTestCase
from asimov.cli.application import apply_page, apply_via_plugin
from asimov.ledger import YAMLLedger
from asimov.pipelines.testing.simple import SimpleTestPipeline


class _FakeBilbyPipeline(SimpleTestPipeline):
    """A testing pipeline registered as ``bilby`` for these tests only.

    cbcflow's own ``Collector`` hardcodes
    ``supported_pipelines = ["bayeswave", "bilby", "rift"]`` (independent of
    asimov's plugin registry), so exercising it requires a pipeline whose
    name resolves to one of those values. This is *not* registered as a
    real ``asimov.pipelines`` entry point - it's patched into
    ``known_pipelines`` only for the duration of ``TestCBCFlowCollector``.
    """

    name = "Bilby"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_SNAME = "S000000xx"

_EVENT_BLUEPRINT = f"""\
kind: event
name: {TEST_SNAME}
ligo:
  sname: {TEST_SNAME}
interferometers:
  - H1
  - L1
"""

_BILBY_ANALYSIS_BLUEPRINT = """\
kind: analysis
name: Prod0
pipeline: bilby
status: running
waveform:
  approximant: IMRPhenomXPHM
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LIBRARY_CFG = """\
[Library Info]
library-name = test-library

[Events]
far-threshold = 1.0
"""

_MINIMAL_METADATA = {
    "Sname": TEST_SNAME,
    "Info": {"Notes": [], "Labels": []},
    "Publications": {"Papers": []},
    "GraceDB": {
        "Events": [
            {
                "State": "preferred",
                "UID": "G000001",
                "Pipeline": "gstlal",
                "GPSTime": 1000000000.0,
                "FAR": 1.0e-10,
                "NetworkSNR": 12.0,
                "Mass1": 30.0,
                "Mass2": 25.0,
            }
        ],
        "Instruments": "H1,L1",
        "LastUpdate": "2023-01-01 00:00:00.000000",
    },
    "ParameterEstimation": {
        "Analysts": [],
        "Reviewers": [],
        "Status": "ongoing",
        "Results": [],
        "Notes": [],
    },
    "ExtremeMatter": {"Analyses": []},
    "Cosmology": {"Counterparts": []},
    # cbcflow's v3 schema (its current default) replaced the flat "Analyses"
    # list with "MultipletAnalyses"/"SingletAnalyses"; an empty dict validates
    # since neither is required.
    "Lensing": {},
    "RatesAndPopulations": {"RnPRunsUsingThisSuperevent": []},
    "TestingGR": {
        "IMRCTAnalyses": [],
        "SSBAnalyses": [],
        "PSEOBRDAnalyses": [],
        "SIMAnalyses": [],
        "MDRAnalyses": [],
        "FTIAnalyses": [],
        "Notes": [],
    },
    "DetectorCharacterization": {
        "Analysts": [],
        "Reviewers": [],
        "ParticipatingDetectors": ["H1", "L1"],
        "Status": "complete",
        "RecommendedDetectors": [
            {
                "UID": "H1",
                "RecommendedMinimumFrequency": 20,
                "FrameType": "H1_HOFT_C00",
                "RecommendedChannel": "H1:GDS-CALIB_STRAIN_CLEAN",
                "GlitchMitigationStatus": "not required",
                "Notes": [],
            },
            {
                "UID": "L1",
                "RecommendedMinimumFrequency": 20,
                "FrameType": "L1_HOFT_C00",
                "RecommendedChannel": "L1:GDS-CALIB_STRAIN_CLEAN",
                "GlitchMitigationStatus": "not required",
                "Notes": [],
            },
        ],
        "DQRResults": [],
        "Notes": [],
        "RecommendedDuration": 8.0,
    },
}


def _init_library_repo(library_path):
    """
    Initialise a git repository at *library_path* with committer identity
    set.  Returns the Repo object.

    Note: branch renaming to 'main' must be done *after* the first commit
    because ``git branch -M`` requires at least one commit to exist.
    Call ``_ensure_main_branch(repo)`` once the initial commit is made.
    """
    # git init -b main  (git >= 2.28).  Fall back to plain init for older git.
    result = subprocess.run(
        ["git", "init", "-b", "main", library_path],
        capture_output=True,
    )
    if result.returncode != 0:
        subprocess.run(["git", "init", library_path], check=True, capture_output=True)

    repo = git.Repo(library_path)
    with repo.config_writer() as cfg:
        cfg.set_value("user", "name", "Asimov Test")
        cfg.set_value("user", "email", "test@asimov.test")
    return repo


def _ensure_main_branch(repo):
    """
    Rename the current branch to 'main' if it isn't already.

    Must be called *after* at least one commit exists in the repository,
    because ``git branch -M`` requires an existing commit.
    """
    try:
        repo.git.branch("-M", "main")
    except git.GitCommandError:
        pass  # already on 'main', or rename not supported


# ---------------------------------------------------------------------------
# Test: Applicator  (cbcflow -> asimov)
# ---------------------------------------------------------------------------


@unittest.skipUnless(cbcflow_available, "cbcflow not installed")
class TestCBCFlowApplicator(AsimovTestCase):
    """
    Tests for the cbcflow Applicator hook.

    The Applicator reads metadata from a cbcflow library and creates an
    event in the Asimov ledger.  This is the path exercised by::

        asimov apply -p cbcflow --event <EVENT_NAME>
    """

    def setUp(self):
        super().setUp()
        self.library_path = os.path.join(self.cwd, "tests", "tmp", "cbcflow_library")
        self._setup_library_with_event()
        self._configure_hooks()

    def _setup_library_with_event(self):
        """Create a cbcflow library containing metadata for TEST_SNAME."""
        os.makedirs(self.library_path, exist_ok=True)
        repo = _init_library_repo(self.library_path)

        with open(os.path.join(self.library_path, "library.cfg"), "w") as f:
            f.write(_LIBRARY_CFG)

        metadata = copy.deepcopy(_MINIMAL_METADATA)
        metadata_file = f"{TEST_SNAME}-cbc-metadata.json"
        with open(os.path.join(self.library_path, metadata_file), "w") as f:
            json.dump(metadata, f, indent=2)

        repo.index.add(["library.cfg", metadata_file])
        repo.index.commit("Initial test library")
        _ensure_main_branch(repo)

    def _configure_hooks(self):
        self.ledger.data["hooks"] = {
            "applicator": {
                "cbcflow": {"library location": self.library_path}
            }
        }
        self.ledger.save()

    # --- individual tests ---------------------------------------------------

    @patch("cbcflow.core.database.LocalLibraryDatabase.git_pull_from_remote")
    def test_applicator_adds_event_to_ledger(self, _mock_pull):
        """Applicator should create an event in the asimov ledger."""
        applicator = Applicator(self.ledger)
        applicator.run(sid=TEST_SNAME)

        events = self.ledger.get_event(TEST_SNAME)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].name, TEST_SNAME)

    @patch("cbcflow.core.database.LocalLibraryDatabase.git_pull_from_remote")
    def test_applicator_sets_minimum_frequency(self, _mock_pull):
        """Applicator should populate quality.minimum frequency from DetectorCharacterization."""
        applicator = Applicator(self.ledger)
        applicator.run(sid=TEST_SNAME)

        event = self.ledger.get_event(TEST_SNAME)[0]
        min_freq = event.meta.get("quality", {}).get("minimum frequency", {})
        self.assertEqual(min_freq.get("H1"), 20)
        self.assertEqual(min_freq.get("L1"), 20)

    @patch("cbcflow.core.database.LocalLibraryDatabase.git_pull_from_remote")
    def test_applicator_sets_data_channels(self, _mock_pull):
        """Applicator should populate data.channels from DetectorCharacterization."""
        applicator = Applicator(self.ledger)
        applicator.run(sid=TEST_SNAME)

        event = self.ledger.get_event(TEST_SNAME)[0]
        channels = event.meta.get("data", {}).get("channels", {})
        self.assertEqual(channels.get("H1"), "H1:GDS-CALIB_STRAIN_CLEAN")
        self.assertEqual(channels.get("L1"), "L1:GDS-CALIB_STRAIN_CLEAN")

    @patch("cbcflow.core.database.LocalLibraryDatabase.git_pull_from_remote")
    def test_applicator_sets_frame_types(self, _mock_pull):
        """Applicator should populate data.frame types from DetectorCharacterization."""
        applicator = Applicator(self.ledger)
        applicator.run(sid=TEST_SNAME)

        event = self.ledger.get_event(TEST_SNAME)[0]
        frame_types = event.meta.get("data", {}).get("frame types", {})
        self.assertEqual(frame_types.get("H1"), "H1_HOFT_C00")
        self.assertEqual(frame_types.get("L1"), "L1_HOFT_C00")

    @patch("cbcflow.core.database.LocalLibraryDatabase.git_pull_from_remote")
    def test_applicator_sets_ligo_sname(self, _mock_pull):
        """Applicator should store the sname and FAR under event.ligo."""
        applicator = Applicator(self.ledger)
        applicator.run(sid=TEST_SNAME)

        event = self.ledger.get_event(TEST_SNAME)[0]
        self.assertEqual(event.meta["ligo"]["sname"], TEST_SNAME)
        self.assertAlmostEqual(event.meta["ligo"]["false alarm rate"], 1.0e-10)

    @patch("cbcflow.core.database.LocalLibraryDatabase.git_pull_from_remote")
    def test_apply_via_plugin_adds_event(self, _mock_pull):
        """Full CLI path: apply_via_plugin should add the event via the cbcflow hook."""
        import sys
        if sys.version_info >= (3, 10):
            from importlib.metadata import entry_points as ep
        else:
            from importlib_metadata import entry_points as ep
        if not any(h.name == "cbcflow" for h in ep(group="asimov.hooks.applicator")):
            self.skipTest(
                "cbcflow applicator entry point not registered "
                "(install cbcflow from PyPI to enable this test)"
            )

        apply_via_plugin(TEST_SNAME, hookname="cbcflow")

        # Reload ledger from disk to pick up changes made by the plugin
        ledger = YAMLLedger(".asimov/ledger.yml")
        events = ledger.get_event(TEST_SNAME)
        self.assertEqual(len(events), 1)


# ---------------------------------------------------------------------------
# Test: Collector  (asimov -> cbcflow)
# ---------------------------------------------------------------------------


@unittest.skipUnless(cbcflow_available, "cbcflow not installed")
class TestCBCFlowCollector(AsimovTestCase):
    """
    Tests for the cbcflow Collector hook.

    The Collector runs as a post-monitor hook and writes analysis status
    from the asimov ledger back into the cbcflow library.  This is the
    path exercised by the ``asimov monitor`` command when the cbcflow
    postmonitor hook is configured.
    """

    def setUp(self):
        super().setUp()
        # See _FakeBilbyPipeline: cbcflow's Collector only recognizes
        # bayeswave/bilby/rift, independent of what's actually registered
        # in asimov's own plugin registry.
        import asimov.pipelines
        self._known_pipelines_patcher = patch.dict(
            asimov.pipelines.known_pipelines, {"bilby": _FakeBilbyPipeline}
        )
        self._known_pipelines_patcher.start()
        self.addCleanup(self._known_pipelines_patcher.stop)

        self.library_path = os.path.join(self.cwd, "tests", "tmp", "cbcflow_library")
        self._setup_empty_library()
        self._setup_asimov_event()
        self._configure_hooks()
        # YAMLLedger caches events in _all_events at __init__ time.  Reload
        # now that all events and analyses have been written to disk so that
        # ledger.get_event() (no-arg form used by the Collector) is populated.
        self.ledger = YAMLLedger(".asimov/ledger.yml")

    def _setup_empty_library(self):
        """Create an empty cbcflow library (no event files yet).

        A local bare repository is created alongside the working copy and added
        as the "origin" remote.  This is required because cbcflow's
        ``git_checkout_new_branch`` calls ``git push -u origin <branch>`` to
        set up tracking the first time it sees an untracked branch.  Without a
        real remote the push fails with "fatal: 'origin' does not appear to be
        a git repository".  The bare repo acts as that remote; the actual remote
        push at the end of ``Collector.run()`` (``git_push_to_remote``) is
        still mocked out so no real network I/O occurs.
        """
        if os.path.exists(self.library_path):
            shutil.rmtree(self.library_path)
        os.makedirs(self.library_path)
        repo = _init_library_repo(self.library_path)

        with open(os.path.join(self.library_path, "library.cfg"), "w") as f:
            f.write(_LIBRARY_CFG)
        repo.index.add(["library.cfg"])
        repo.index.commit("Initial empty library")
        _ensure_main_branch(repo)

        # Set up a local bare repo as "origin" so that git_checkout_new_branch
        # can successfully call "git push -u origin main" to register tracking.
        bare_path = self.library_path + "_origin"
        if os.path.exists(bare_path):
            shutil.rmtree(bare_path)
        git.Repo.init(bare_path, bare=True)
        repo.create_remote("origin", bare_path)
        repo.git.push("-u", "origin", "main")

    def _setup_asimov_event(self):
        """Add the test event and a simpletestpipeline analysis to the asimov ledger."""
        with open("test_event.yaml", "w") as f:
            f.write(_EVENT_BLUEPRINT)
        apply_page("test_event.yaml", ledger=self.ledger)

        with open("test_analysis.yaml", "w") as f:
            f.write(_BILBY_ANALYSIS_BLUEPRINT)
        apply_page("test_analysis.yaml", event=TEST_SNAME, ledger=self.ledger)

    def _configure_hooks(self):
        self.ledger.data["hooks"] = {
            "postmonitor": {
                "cbcflow": {
                    "library location": self.library_path,
                    "schema section": "ParameterEstimation",
                }
            }
        }
        self.ledger.save()

    def _set_analysis_status(self, status):
        """
        Update the status of 'Prod0' in the asimov ledger and save.

        Works by mutating the raw ledger dict so no assumptions need to be
        made about the public API for status updates.  Reloads self.ledger
        afterward so that _all_events reflects the new status.
        """
        for prod_entry in self.ledger.events[TEST_SNAME].get("productions", []):
            if isinstance(prod_entry, dict) and "Prod0" in prod_entry:
                prod_entry["Prod0"]["status"] = status
                break
        self.ledger.save()
        self.ledger = YAMLLedger(".asimov/ledger.yml")

    def _read_pe_results(self):
        """Return the ParameterEstimation.Results list from the library file."""
        metadata_file = os.path.join(
            self.library_path, f"{TEST_SNAME}-cbc-metadata.json"
        )
        with open(metadata_file) as f:
            data = json.load(f)
        return data.get("ParameterEstimation", {}).get("Results", [])

    # --- individual tests ---------------------------------------------------

    @patch("asimov.git.EventRepo.find_prods", return_value=[])
    @patch("cbcflow.core.database.LocalLibraryDatabase.git_push_to_remote")
    @patch("cbcflow.core.database.LocalLibraryDatabase.git_pull_from_remote")
    def test_collector_creates_metadata_file(self, _mock_pull, _mock_push, _mock_find):
        """Collector should create a cbcflow metadata file for the event."""
        collector = Collector(self.ledger)
        collector.run()

        metadata_file = os.path.join(
            self.library_path, f"{TEST_SNAME}-cbc-metadata.json"
        )
        self.assertTrue(
            os.path.exists(metadata_file),
            "Collector should write a cbcflow metadata file",
        )

    @patch("asimov.git.EventRepo.find_prods", return_value=[])
    @patch("cbcflow.core.database.LocalLibraryDatabase.git_push_to_remote")
    @patch("cbcflow.core.database.LocalLibraryDatabase.git_pull_from_remote")
    def test_collector_writes_analysis_uid_and_pipeline(self, _mock_pull, _mock_push, _mock_find):
        """Collector should write the analysis UID and InferenceSoftware."""
        collector = Collector(self.ledger)
        collector.run()

        results = self._read_pe_results()
        self.assertEqual(len(results), 1, "Expected exactly one result entry")
        self.assertEqual(results[0]["UID"], "Prod0")
        self.assertEqual(results[0]["InferenceSoftware"], "bilby")

    @patch("asimov.git.EventRepo.find_prods", return_value=[])
    @patch("cbcflow.core.database.LocalLibraryDatabase.git_push_to_remote")
    @patch("cbcflow.core.database.LocalLibraryDatabase.git_pull_from_remote")
    def test_collector_maps_running_status(self, _mock_pull, _mock_push, _mock_find):
        """'running' in asimov should map to 'running' in cbcflow."""
        collector = Collector(self.ledger)
        collector.run()

        results = self._read_pe_results()
        self.assertEqual(results[0]["RunStatus"], "running")

    @patch("asimov.pipelines.testing.simple.SimpleTestPipeline.collect_assets")
    @patch("asimov.git.EventRepo.find_prods", return_value=[])
    @patch("cbcflow.core.database.LocalLibraryDatabase.git_push_to_remote")
    @patch("cbcflow.core.database.LocalLibraryDatabase.git_pull_from_remote")
    def test_collector_maps_uploaded_status(self, _mock_pull, _mock_push, _mock_find, _mock_assets):
        """'uploaded' in asimov should map to 'complete' in cbcflow."""
        # A real (though empty) file is needed so cbcflow can compute its MD5
        # when validating the ResultFile entry against the schema.
        fake_sample = os.path.join(self.cwd, "tests", "tmp", "fake_result.hdf5")
        open(fake_sample, "w").close()
        _mock_assets.return_value = {"samples": [fake_sample], "config": fake_sample}

        self._set_analysis_status("uploaded")

        collector = Collector(self.ledger)
        collector.run()

        results = self._read_pe_results()
        self.assertEqual(results[0]["RunStatus"], "complete")

    @patch("asimov.git.EventRepo.find_prods", return_value=[])
    @patch("cbcflow.core.database.LocalLibraryDatabase.git_push_to_remote")
    @patch("cbcflow.core.database.LocalLibraryDatabase.git_pull_from_remote")
    def test_collector_writes_waveform_approximant(self, _mock_pull, _mock_push, _mock_find):
        """Collector should write the WaveformApproximant field."""
        collector = Collector(self.ledger)
        collector.run()

        results = self._read_pe_results()
        self.assertEqual(results[0].get("WaveformApproximant"), "IMRPhenomXPHM")

    @patch("asimov.pipelines.testing.simple.SimpleTestPipeline.collect_assets")
    @patch("asimov.git.EventRepo.find_prods", return_value=[])
    @patch("cbcflow.core.database.LocalLibraryDatabase.git_push_to_remote")
    @patch("cbcflow.core.database.LocalLibraryDatabase.git_pull_from_remote")
    def test_collector_updates_status_on_second_run(self, _mock_pull, _mock_push, _mock_find, _mock_assets):
        """
        Running the Collector twice should update the status, not duplicate entries.

        This is the key regression test for the bug where ledger updates were
        not being reflected back to cbcflow.
        """
        # First run: analysis is running — collect_assets is not called
        _mock_assets.return_value = {"samples": [], "config": None}
        collector = Collector(self.ledger)
        collector.run()
        results_after_first = self._read_pe_results()
        self.assertEqual(results_after_first[0]["RunStatus"], "running")

        # Simulate the analysis completing: update status to 'uploaded'
        self._set_analysis_status("uploaded")

        # A real (though empty) file is needed so cbcflow can compute its MD5
        # when validating the ResultFile entry against the schema.
        fake_sample = os.path.join(self.cwd, "tests", "tmp", "fake_result.hdf5")
        open(fake_sample, "w").close()
        _mock_assets.return_value = {"samples": [fake_sample], "config": fake_sample}

        # Second run: should update the existing entry to 'complete'
        ledger2 = YAMLLedger(".asimov/ledger.yml")
        collector2 = Collector(ledger2)
        collector2.run()

        results_after_second = self._read_pe_results()
        self.assertEqual(
            len(results_after_second),
            1,
            "Collector should update the existing entry, not create a duplicate",
        )
        self.assertEqual(
            results_after_second[0]["RunStatus"],
            "complete",
            "Status should be updated to 'complete' after the analysis is uploaded",
        )

    @patch("asimov.git.EventRepo.find_prods", return_value=[])
    @patch("cbcflow.core.database.LocalLibraryDatabase.git_push_to_remote")
    @patch("cbcflow.core.database.LocalLibraryDatabase.git_pull_from_remote")
    def test_collector_commits_changes_to_git(self, _mock_pull, _mock_push, _mock_find):
        """Collector should commit the updated metadata to the local git repo."""
        repo = git.Repo(self.library_path)
        commits_before = len(list(repo.iter_commits("main")))

        collector = Collector(self.ledger)
        collector.run()

        commits_after = len(list(repo.iter_commits("main")))
        self.assertGreater(
            commits_after,
            commits_before,
            "Collector should commit the metadata update to git",
        )
