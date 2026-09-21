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

import importlib
import json
import os
import shutil
import unittest
from unittest.mock import patch

from click.testing import CliRunner

import asimov
from asimov import config
from asimov.cli import provenance as provenance_cli
from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.ledger import DatabaseLedger, YAMLLedger
from asimov.pipelines.testing.simple import SimpleTestPipeline
from asimov.provenance import PROV_CONTEXT, ProvenanceError, _entity_id, build_provenance
from asimov.rocrate import RO_CRATE_CONTEXT, package_analysis
from asimov.storage import Store

EVENT_BLUEPRINT = """
kind: event
name: GW150914_095045
interferometers:
- H1
- L1
quality:
  state vector:
    H1: H1:DCS-CALIB_STATE_VECTOR_C01
"""

ANALYSIS_BLUEPRINT = """
kind: analysis
name: TestAnalysis
pipeline: simpletestpipeline
comment: A test analysis
event: GW150914_095045
status: ready
"""


class EntityIdTests(unittest.TestCase):
    """`_entity_id` must produce valid, collision-safe URIs from arbitrary
    asimov names, which aren't restricted to URI-safe characters."""

    def test_names_with_spaces_and_colons_are_percent_encoded(self):
        entity_id = _entity_id("config", "GW 150914", "Prod:1")
        self.assertNotIn(" ", entity_id)
        self.assertEqual(
            entity_id, "urn:asimov:config:GW%20150914:Prod%3A1"
        )

    def test_a_colon_inside_a_name_cannot_collide_with_the_separator(self):
        # Without encoding, ("a:b", "c") and ("a", "b:c") would produce the
        # same joined string; each component must stay distinguishable.
        first = _entity_id("kind", "a:b", "c")
        second = _entity_id("kind", "a", "b:c")
        self.assertNotEqual(first, second)


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

    def _invoke_cli(self, command_name, args):
        """
        Invoke a command from asimov.cli.provenance against this fixture's
        ledger.

        The CLI module binds `ledger = asimov.current_ledger` at import
        time, so the module has to be reloaded with `asimov.current_ledger`
        patched to the ledger this test fixture already built, rather than
        letting asimov's own startup probe try to rediscover it from disk.
        """
        with patch.object(asimov, "current_ledger", self.ledger):
            importlib.reload(provenance_cli)
            try:
                command = getattr(provenance_cli, command_name)
                runner = CliRunner()
                return runner.invoke(command, args)
            finally:
                importlib.reload(provenance_cli)


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

    def test_config_entity_includes_inherited_event_level_defaults(self):
        # TestAnalysis doesn't set `quality` itself - it inherits it
        # unchanged from the event (see EVENT_BLUEPRINT). `Analysis.to_dict()`
        # would diff this back out as "just a default"; a standalone
        # provenance/crate export has nowhere else to record it, so it must
        # be included here for the export to be self-contained.
        document = build_provenance(
            self.ledger, "GW150914_095045", "TestAnalysis", store=self.store
        )
        config_entities = [
            node for node in document["@graph"] if node.get("asimov:kind") == "configuration"
        ]
        self.assertEqual(
            config_entities[0]["asimov:value"]["quality"]["state vector"]["H1"],
            "H1:DCS-CALIB_STATE_VECTOR_C01",
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

    def test_dependencies_use_wasinformedby_not_used(self):
        # A dependency is another *activity* (an upstream analysis), so it
        # must relate via `prov:wasInformedBy` (activity-to-activity), never
        # via `prov:used` (whose range is `prov:Entity`).
        self.analysis.resolved_dependencies = ["UpstreamAnalysis"]
        # build_provenance() re-fetches the analysis from the ledger rather
        # than reusing this in-memory object, so the change must be
        # persisted first - the setter itself only mutates `.meta`.
        self.ledger.update_event(self.analysis.event)
        document = build_provenance(
            self.ledger, "GW150914_095045", "TestAnalysis", store=self.store
        )
        activities = [node for node in document["@graph"] if node["@type"] == "prov:Activity"]
        self.assertEqual(len(activities), 1)
        activity = activities[0]

        upstream_activity_id = "urn:asimov:activity:GW150914_095045:UpstreamAnalysis"
        self.assertIn(
            {"@id": upstream_activity_id}, activity["prov:wasInformedBy"]
        )
        used_ids = {entity["@id"] for entity in activity["prov:used"]}
        self.assertNotIn(upstream_activity_id, used_ids)

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

    def test_crate_context_resolves_both_ro_crate_and_prov_terms(self):
        # The embedded provenance nodes use `prov:`/`asimov:` terms that the
        # RO-Crate context alone doesn't define; `@context` must extend
        # (not replace) it with those, or a JSON-LD processor can't expand
        # them against the intended vocabularies.
        destination = self._crate_path()
        package_analysis(
            self.ledger, "GW150914_095045", "TestAnalysis", destination, store=self.store
        )
        with open(os.path.join(destination, "ro-crate-metadata.json")) as metadata_file:
            metadata = json.load(metadata_file)

        self.assertEqual(metadata["@context"], [RO_CRATE_CONTEXT, PROV_CONTEXT])

    def test_refuses_to_overwrite_existing_directory(self):
        destination = self._crate_path()
        os.makedirs(destination)
        with self.assertRaises(FileExistsError):
            package_analysis(
                self.ledger, "GW150914_095045", "TestAnalysis", destination, store=self.store
            )


class ProvenanceCommandTests(ProvenanceTestBase):
    """
    CLI-level tests for `asimov provenance` (asimov/cli/provenance.py),
    which previously had no test coverage at all - only the underlying
    `build_provenance()` function was tested, not the command's argument
    handling, error formatting, or stdout/file output paths.
    """

    def test_prints_document_to_stdout_by_default(self):
        result = self._invoke_cli(
            "provenance", ["GW150914_095045", "TestAnalysis"]
        )
        self.assertEqual(result.exit_code, 0, result.output)
        document = json.loads(result.output)
        self.assertIn("@graph", document)

    def test_writes_document_to_file_when_output_given(self):
        destination = os.path.join(
            self.cwd, f"tests/tmp/{self.PROJECT_DIR}", "prov.json"
        )
        result = self._invoke_cli(
            "provenance",
            ["GW150914_095045", "TestAnalysis", "--output", destination],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn(f"Provenance written to {destination}", result.output)
        with open(destination) as handle:
            document = json.load(handle)
        self.assertIn("@graph", document)

    def test_unknown_subject_reports_a_click_exception_not_a_traceback(self):
        result = self._invoke_cli(
            "provenance", ["NoSuchEvent", "TestAnalysis"]
        )
        # click.ClickException exits with code 1 and prints "Error: ...";
        # an *unhandled* ProvenanceError would instead propagate as a
        # traceback and a different exit code.
        self.assertEqual(result.exit_code, 1)
        self.assertNotIn("Traceback", result.output)
        self.assertIn("NoSuchEvent", result.output)

    def test_unknown_analysis_reports_a_click_exception_not_a_traceback(self):
        result = self._invoke_cli(
            "provenance", ["GW150914_095045", "NoSuchAnalysis"]
        )
        self.assertEqual(result.exit_code, 1)
        self.assertNotIn("Traceback", result.output)
        self.assertIn("NoSuchAnalysis", result.output)


class PackageCommandTests(ProvenanceTestBase):
    """CLI-level tests for `asimov package` (asimov/cli/provenance.py)."""

    def _crate_path(self):
        return os.path.join(self.cwd, f"tests/tmp/{self.PROJECT_DIR}", "out.crate")

    def test_creates_a_crate_at_the_requested_destination(self):
        destination = self._crate_path()
        result = self._invoke_cli(
            "package",
            ["GW150914_095045", "TestAnalysis", "--output", destination],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn(f"RO-Crate written to {destination}", result.output)
        self.assertTrue(
            os.path.isfile(os.path.join(destination, "ro-crate-metadata.json"))
        )

    def test_default_destination_is_derived_from_subject_and_analysis(self):
        result = self._invoke_cli("package", ["GW150914_095045", "TestAnalysis"])
        self.assertEqual(result.exit_code, 0, result.output)
        default_destination = "GW150914_095045-TestAnalysis.crate"
        self.assertTrue(os.path.isdir(default_destination))

    def test_refuses_to_overwrite_an_existing_destination(self):
        destination = self._crate_path()
        os.makedirs(destination)
        result = self._invoke_cli(
            "package",
            ["GW150914_095045", "TestAnalysis", "--output", destination],
        )
        self.assertEqual(result.exit_code, 1)
        self.assertIn("already exists", result.output)
        # And it must not have touched the pre-existing directory's contents.
        self.assertEqual(os.listdir(destination), [])

    def test_unknown_analysis_reports_a_click_exception_not_a_traceback(self):
        destination = self._crate_path()
        result = self._invoke_cli(
            "package",
            ["GW150914_095045", "NoSuchAnalysis", "--output", destination],
        )
        self.assertEqual(result.exit_code, 1)
        self.assertNotIn("Traceback", result.output)
        self.assertIn("NoSuchAnalysis", result.output)
        self.assertFalse(os.path.exists(destination))
