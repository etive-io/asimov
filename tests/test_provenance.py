"""
Tests for asimov.provenance and asimov.rocrate (#154).

These follow the style of tests/test_multiple_psds.py: drive the real
ledger/apply_page code paths with a lightweight fixture pipeline, rather
than mocking the ledger away, so the tests exercise the same public
Ledger/Store interfaces asimov.provenance is built on.

BuildProvenanceTests runs against the YAML ledger; BuildProvenanceDatabaseLedgerTests
re-runs the same cases against the database ledger, to demonstrate that
asimov.provenance is generic across ledger backends (see the design note in
asimov/provenance.py) rather than tied to one.
"""

import json
import os
import shutil
import unittest

from asimov import config
from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.ledger import DatabaseLedger, YAMLLedger
from asimov.pipelines.testing.simple import SimpleTestPipeline
from asimov.provenance import ProvenanceError, build_provenance
from asimov.rocrate import package_analysis
from asimov.storage import Store

EVENT_BLUEPRINT = """
kind: event
name: GW150914_095045
interferometers:
- H1
- L1
"""

ANALYSIS_BLUEPRINT = """
kind: analysis
name: TestAnalysis
pipeline: simpletestpipeline
comment: A test analysis
event: GW150914_095045
status: ready
"""


class ProvenanceTestBase(unittest.TestCase):
    """Sets up a small project with one event and one completed analysis."""

    ENGINE = "yamlfile"
    PROJECT_DIR = "provenance_project"

    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.cwd)

    def _apply(self, contents, name):
        path = f"tests/tmp/{self.PROJECT_DIR}/{name}.yaml"
        with open(f"{self.cwd}/{path}", "w") as blueprint_file:
            blueprint_file.write(contents)
        apply_page(file=f"{self.cwd}/{path}", ledger=self.ledger)

    def setUp(self):
        project_root = f"{self.cwd}/tests/tmp/{self.PROJECT_DIR}"
        os.makedirs(project_root)
        os.chdir(project_root)
        make_project(name="Provenance test project", root=project_root, engine=self.ENGINE)

        if self.ENGINE == "yamlfile":
            self.ledger = YAMLLedger(".asimov/ledger.yml")
        else:
            self.ledger = DatabaseLedger(engine=self.ENGINE)

        self._apply(EVENT_BLUEPRINT, "event")
        self._apply(ANALYSIS_BLUEPRINT, "analysis")

        subject = self.ledger.get_subject("GW150914_095045")[0]
        self.analysis = next(p for p in subject.productions if p.name == "TestAnalysis")
        self.pipeline = SimpleTestPipeline(self.analysis)

        # Capture the software environment (#88), as `asimov manage build` would.
        self.pipeline.before_config(dryrun=False)
        # SimpleTestPipeline's after_completion() doesn't upload environment
        # files itself (only the PESummary-postprocessing path in the base
        # Pipeline class does) - call the upload step directly, as it would
        # be reached for a pipeline that does wire it in.
        self.pipeline._store_environment_files()

        self.store = Store(root=config.get("storage", "directory"))
        os.makedirs(self.analysis.rundir, exist_ok=True)
        results_file = os.path.join(self.analysis.rundir, "posterior_samples.dat")
        with open(results_file, "w") as samples_file:
            samples_file.write("# parameter1 parameter2\n1.0 2.0\n")
        self.store.add_file("GW150914_095045", "TestAnalysis", results_file)

    def tearDown(self):
        del self.ledger
        os.chdir(self.cwd)
        shutil.rmtree(f"{self.cwd}/tests/tmp/{self.PROJECT_DIR}")


class BuildProvenanceTests(ProvenanceTestBase):
    def test_config_entity_present(self):
        document = build_provenance(
            self.ledger, "GW150914_095045", "TestAnalysis", store=self.store
        )
        config_entities = [
            node for node in document["@graph"] if node.get("asimov:kind") == "configuration"
        ]
        self.assertEqual(len(config_entities), 1)
        self.assertEqual(
            config_entities[0]["asimov:value"]["pipeline"], "simpletestpipeline"
        )

    def test_environment_entity_present(self):
        document = build_provenance(
            self.ledger, "GW150914_095045", "TestAnalysis", store=self.store
        )
        env_entities = [
            node
            for node in document["@graph"]
            if node.get("asimov:kind") == "software-environment"
        ]
        self.assertEqual(len(env_entities), 1)
        self.assertIsNotNone(env_entities[0]["asimov:pythonVersion"])

    def test_output_entity_present_with_hash_and_uuid(self):
        document = build_provenance(
            self.ledger, "GW150914_095045", "TestAnalysis", store=self.store
        )
        output_entities = [
            node for node in document["@graph"] if node.get("asimov:kind") == "output-file"
        ]
        self.assertEqual(len(output_entities), 1)
        self.assertEqual(output_entities[0]["asimov:filename"], "posterior_samples.dat")
        self.assertTrue(output_entities[0]["asimov:hash"])
        self.assertTrue(output_entities[0]["asimov:uuid"])
        self.assertEqual(
            output_entities[0]["prov:wasGeneratedBy"]["@id"],
            "urn:asimov:activity:GW150914_095045:TestAnalysis",
        )

    def test_activity_and_agents_present(self):
        document = build_provenance(
            self.ledger, "GW150914_095045", "TestAnalysis", store=self.store
        )
        activities = [node for node in document["@graph"] if node["@type"] == "prov:Activity"]
        self.assertEqual(len(activities), 1)
        self.assertEqual(activities[0]["asimov:pipeline"], "SimpleTestPipeline")

        agents = [
            node for node in document["@graph"] if node["@type"] == "prov:SoftwareAgent"
        ]
        agent_names = {agent["asimov:name"] for agent in agents}
        self.assertIn("asimov", agent_names)
        self.assertIn("SimpleTestPipeline", agent_names)

    def test_document_is_json_serialisable(self):
        document = build_provenance(
            self.ledger, "GW150914_095045", "TestAnalysis", store=self.store
        )
        json.dumps(document)  # should not raise

    def test_unknown_subject_raises(self):
        with self.assertRaises(ProvenanceError):
            build_provenance(self.ledger, "NoSuchEvent", "TestAnalysis", store=self.store)

    def test_unknown_analysis_raises(self):
        with self.assertRaises(ProvenanceError):
            build_provenance(
                self.ledger, "GW150914_095045", "NoSuchAnalysis", store=self.store
            )


class BuildProvenanceDatabaseLedgerTests(BuildProvenanceTests):
    """Re-runs BuildProvenanceTests against the database ledger backend."""

    ENGINE = "sqlite"
    PROJECT_DIR = "provenance_project_db"


class PackageAnalysisTests(ProvenanceTestBase):
    def _crate_path(self):
        return os.path.join(self.cwd, f"tests/tmp/{self.PROJECT_DIR}/out.crate")

    def test_crate_contains_expected_files(self):
        destination = self._crate_path()
        package_analysis(
            self.ledger, "GW150914_095045", "TestAnalysis", destination, store=self.store
        )

        self.assertTrue(os.path.isfile(os.path.join(destination, "ro-crate-metadata.json")))
        self.assertTrue(os.path.isfile(os.path.join(destination, "provenance.json")))
        self.assertTrue(os.path.isfile(os.path.join(destination, "config.json")))
        self.assertTrue(
            os.path.isfile(os.path.join(destination, "environment", "environment.json"))
        )

    def test_output_files_are_referenced_not_copied(self):
        destination = self._crate_path()
        package_analysis(
            self.ledger, "GW150914_095045", "TestAnalysis", destination, store=self.store
        )

        self.assertFalse(os.path.exists(os.path.join(destination, "posterior_samples.dat")))

        with open(os.path.join(destination, "ro-crate-metadata.json")) as metadata_file:
            metadata = json.load(metadata_file)
        referenced = [
            node for node in metadata["@graph"] if node.get("name") == "posterior_samples.dat"
        ]
        self.assertEqual(len(referenced), 1)
        self.assertTrue(referenced[0]["asimov:externallyStored"])

    def test_refuses_to_overwrite_existing_directory(self):
        destination = self._crate_path()
        os.makedirs(destination)
        with self.assertRaises(FileExistsError):
            package_analysis(
                self.ledger, "GW150914_095045", "TestAnalysis", destination, store=self.store
            )
