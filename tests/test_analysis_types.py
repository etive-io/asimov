"""
Analysis types (#238): a plugin can provide the type of an analysis, and a type
is chosen for an analysis by ``type:``, then by its pipeline, then by default.
"""
import os
import shutil
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

from asimov import analysis_types, features
from asimov.analysis import GravitationalWaveTransient, SimpleAnalysis
from asimov.analysis_types import (
    DEFAULT_TYPE,
    AnalysisTypeError,
    analysis_class_for,
    analysis_types as installed,
    build_analysis,
    declared_type,
    get_analysis_type,
    reset_analysis_types,
)
from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.event import Production
from asimov.ledger import DatabaseLedger, YAMLLedger
from asimov.needs_check import features_of
from asimov.pipeline import Pipeline
from asimov.pipelines import PipelineNotInstalled, get_pipeline_class, known_pipelines
from asimov.pipelines.testing import SimpleTestPipeline

EVENT = "kind: event\nname: E\ninterferometers: [H1]\n"


class FitComponent(SimpleAnalysis):
    """A type of a plugin's: a generic analysis with typed fields over its metadata."""

    @property
    def round(self):
        return int(self.meta["round"])


class FitStep(GravitationalWaveTransient):
    """A type which builds on the gravitational-wave one."""


def entries(**found):
    """``entry_points`` for the analysis-type group, finding these classes by name."""
    points = [types.SimpleNamespace(name=n, load=lambda c=c: c) for n, c in found.items()]
    return patch("asimov.analysis_types.entry_points", return_value=points)


class RegistryCase(unittest.TestCase):
    def setUp(self):
        reset_analysis_types()
        self.addCleanup(reset_analysis_types)


class RegistryTests(RegistryCase):
    def test_the_two_which_asimov_provides(self):
        found = installed()
        self.assertIs(found["simple"], SimpleAnalysis)
        self.assertIs(found["gravitational-wave-transient"], GravitationalWaveTransient)

    def test_a_plugin_registers_a_type_by_name(self):
        with entries(**{"fit-component": FitComponent}):
            self.assertIs(get_analysis_type("fit-component"), FitComponent)
        self.assertIn("simple", installed())  # (and the others are still there)

    def test_a_plugin_cannot_replace_one_which_asimov_provides(self):
        with entries(simple=FitComponent):
            self.assertIs(get_analysis_type("simple"), SimpleAnalysis)

    def test_a_plugin_which_fails_to_load_is_reported_and_left_out(self):
        def broken():
            raise ImportError("no module named gwaith")

        points = [types.SimpleNamespace(name="broken", load=broken)]
        with patch("asimov.analysis_types.entry_points", return_value=points):
            with self.assertLogs("asimov.analysis_types", level="WARNING") as logs:
                found = installed()
        self.assertNotIn("broken", found)
        self.assertIn("broken", "\n".join(logs.output))
        self.assertIn("no module named gwaith", "\n".join(logs.output))

    def test_the_types_are_read_once(self):
        with entries(**{"fit-component": FitComponent}) as points:
            installed()
            installed()
            get_analysis_type("simple")
        self.assertEqual(points.call_count, 1)

    def test_a_type_which_is_not_installed_says_which_are(self):
        with self.assertRaises(AnalysisTypeError) as caught:
            get_analysis_type("fit-component")
        message = str(caught.exception)
        self.assertIn("'fit-component' is not installed", message)
        self.assertIn("simple", message)
        self.assertIn("gravitational-wave-transient", message)
        self.assertIn("plugin", message)

    def test_the_error_is_a_value_error(self):
        self.assertTrue(issubclass(AnalysisTypeError, ValueError))


class SelectionTests(RegistryCase):
    def test_a_document_which_says_nothing_is_a_gravitational_wave_analysis(self):
        self.assertIsNone(declared_type({"name": "a", "pipeline": "simpletestpipeline"}))
        self.assertIs(analysis_class_for({"name": "a", "pipeline": "simpletestpipeline"}), GravitationalWaveTransient)

    def test_a_pipeline_can_declare_its_type(self):
        with patch.object(SimpleTestPipeline, "analysis_type", "simple"):
            self.assertEqual(declared_type({"name": "a", "pipeline": "SimpleTestPipeline"}), "simple")
            self.assertIs(analysis_class_for({"name": "a", "pipeline": "simpletestpipeline"}), SimpleAnalysis)

    def test_a_pipeline_declares_nothing_by_default(self):
        self.assertIsNone(Pipeline.analysis_type)

    def test_the_type_of_the_document_wins_over_its_pipelines(self):
        with patch.object(SimpleTestPipeline, "analysis_type", "simple"):
            document = {"name": "a", "pipeline": "simpletestpipeline", "type": "gravitational-wave-transient"}
            self.assertIs(analysis_class_for(document), GravitationalWaveTransient)

    def test_a_type_can_be_mixed_with_any_pipeline(self):
        with entries(**{"fit-component": FitComponent}):
            document = {"name": "a", "command": ["true"], "type": "fit-component"}
            self.assertIs(analysis_class_for(document), FitComponent)

    def test_the_command_pipeline_declares_the_generic_type(self):
        self.assertEqual(known_pipelines["command"].analysis_type, "simple")
        self.assertIs(analysis_class_for({"name": "a", "command": ["true"]}), SimpleAnalysis)
        self.assertIs(analysis_class_for({"name": "a", "pipeline": "command", "command": ["true"]}), SimpleAnalysis)

    def test_a_pipeline_which_is_not_installed_declares_nothing(self):
        self.assertIs(analysis_class_for({"name": "a", "pipeline": "nosuchpipeline"}), GravitationalWaveTransient)

    def test_a_type_which_is_not_installed_is_an_error_naming_the_installed_ones(self):
        with self.assertRaisesRegex(AnalysisTypeError, "'gone' is not installed.*simple"):
            analysis_class_for({"name": "a", "pipeline": "simpletestpipeline", "type": "gone"})

    def test_a_type_which_a_pipeline_declares_and_is_not_installed_is_too(self):
        with patch.object(SimpleTestPipeline, "analysis_type", "gone"):
            with self.assertRaises(AnalysisTypeError):
                analysis_class_for({"name": "a", "pipeline": "simpletestpipeline"})

    def test_a_type_which_is_not_a_name_is_ignored(self):
        self.assertIsNone(declared_type({"name": "a", "pipeline": "simpletestpipeline", "type": 3}))


class PipelineLookupTests(unittest.TestCase):
    def test_it_is_not_case_sensitive(self):
        self.assertIs(get_pipeline_class("SimpleTestPipeline"), SimpleTestPipeline)

    def test_one_which_is_not_installed_says_which_are(self):
        with self.assertRaises(PipelineNotInstalled) as caught:
            get_pipeline_class("nosuchpipeline")
        message = str(caught.exception)
        self.assertIn("The pipeline 'nosuchpipeline' is not installed", message)
        self.assertIn("simpletestpipeline", message)
        self.assertIn("plugin", message)

    def test_it_is_still_a_key_error_for_what_catches_that(self):
        with self.assertRaises(KeyError):
            get_pipeline_class("nosuchpipeline")


class ProjectCase(RegistryCase):
    """A scratch project with one subject, ``E``, on each kind of ledger."""

    def setUp(self):
        super().setUp()
        self.cwd = os.getcwd()
        self.root = tempfile.mkdtemp()
        os.chdir(self.root)
        self.ledger = self.make_ledger()
        self.apply(EVENT)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def make_ledger(self):
        make_project(name="Test project", root=self.root, engine="yamlfile")
        return YAMLLedger(".asimov/ledger.yml")

    def reopen(self):
        return YAMLLedger(".asimov/ledger.yml")

    def apply(self, text, subject=None):
        with open("blueprint.yaml", "w") as handle:
            handle.write(text)
        return apply_page("blueprint.yaml", event=subject, ledger=self.ledger)

    def loaded(self):
        return {a.name: a for a in self.reopen().get_event("E")[0].productions}

    def event(self):
        return self.ledger.get_event("E")[0]


class DatabaseProjectCase(ProjectCase):
    def make_ledger(self):
        self.location = f"sqlite:///{os.path.join(self.root, 'ledger.db')}"
        ledger = DatabaseLedger(engine="sqlalchemy", location=self.location)
        ledger.db.create_tables()
        return ledger

    def reopen(self):
        return DatabaseLedger(engine="sqlalchemy", location=self.location)


class Tests:
    """Building, saving and loading analyses of a type, on each ledger."""

    # Building

    def test_production_builds_the_type_which_the_document_asks_for(self):
        with entries(**{"fit-component": FitComponent}):
            built = Production.from_dict(
                {"name": "a", "pipeline": "simpletestpipeline", "type": "fit-component", "round": 3},
                subject=self.event(), ledger=self.ledger,
            )
        self.assertIs(type(built), FitComponent)
        self.assertEqual(built.round, 3)

    def test_production_builds_what_the_pipeline_declares(self):
        with patch.object(SimpleTestPipeline, "analysis_type", "simple"):
            built = Production.from_dict({"name": "a", "pipeline": "simpletestpipeline"}, subject=self.event(), ledger=self.ledger)
        self.assertIs(type(built), SimpleAnalysis)

    def test_production_still_builds_a_gravitational_wave_analysis_when_nothing_is_said(self):
        built = Production.from_dict({"name": "a", "pipeline": "simpletestpipeline"}, subject=self.event(), ledger=self.ledger)
        self.assertIs(type(built), GravitationalWaveTransient)

    def test_a_type_which_builds_on_the_gravitational_wave_one_is_built_not_looped_over(self):
        with entries(**{"fit-step": FitStep}):
            built = Production.from_dict(
                {"name": "a", "pipeline": "simpletestpipeline", "type": "fit-step"}, subject=self.event(), ledger=self.ledger
            )
        self.assertIs(type(built), FitStep)
        self.assertEqual(built.psds, {})  # (it has what the gravitational-wave one has)

    def test_a_class_asked_directly_builds_itself_whatever_the_document_says(self):
        built = SimpleAnalysis.from_dict(
            {"name": "a", "pipeline": "simpletestpipeline", "type": "gravitational-wave-transient"},
            subject=self.event(), ledger=self.ledger,
        )
        self.assertIs(type(built), SimpleAnalysis)

    def test_build_analysis_is_the_same(self):
        with entries(**{"fit-component": FitComponent}):
            built = build_analysis(
                {"name": "a", "pipeline": "simpletestpipeline", "type": "fit-component", "round": 1},
                subject=self.event(), ledger=self.ledger,
            )
        self.assertIs(type(built), FitComponent)

    def test_a_document_of_an_uninstalled_type_is_an_error_when_it_is_applied(self):
        with self.assertRaises(AnalysisTypeError) as caught:
            Production.from_dict(
                {"name": "a", "pipeline": "simpletestpipeline", "type": "gone"}, subject=self.event(), ledger=self.ledger
            )
        self.assertIn("'gone' is not installed", str(caught.exception))

    def test_a_generic_analysis_resolves_no_psds(self):
        with patch.object(GravitationalWaveTransient, "_collect_psds", side_effect=AssertionError("resolved PSDs")):
            built = Production.from_dict({"name": "c", "command": ["true"]}, subject=self.event(), ledger=self.ledger)
        self.assertIs(type(built), SimpleAnalysis)

    # Saving and loading

    def test_an_explicit_type_is_kept_in_the_metadata_and_loads_as_that_type(self):
        with entries(**{"fit-component": FitComponent}):
            self.apply("kind: analysis\nname: a\npipeline: simpletestpipeline\ntype: fit-component\nround: 2\n", "E")
            loaded = self.loaded()["a"]
            self.assertIs(type(loaded), FitComponent)
            self.assertEqual(loaded.meta["type"], "fit-component")
            self.assertEqual(loaded.round, 2)

    def test_a_type_which_a_pipeline_declares_is_not_stored_and_loads_the_same(self):
        with patch.object(SimpleTestPipeline, "analysis_type", "simple"):
            self.apply("kind: analysis\nname: a\npipeline: simpletestpipeline\n", "E")
            loaded = self.loaded()["a"]
        self.assertIs(type(loaded), SimpleAnalysis)
        self.assertNotIn("type", loaded.meta)

    def test_a_command_analysis_loads_as_a_generic_one(self):
        self.apply("kind: analysis\nname: c\ncommand: [true]\n", "E")
        self.assertIs(type(self.loaded()["c"]), SimpleAnalysis)

    def test_what_the_type_does_not_use_is_still_in_the_metadata(self):
        with entries(**{"fit-component": FitComponent}):
            self.apply("kind: analysis\nname: a\npipeline: simpletestpipeline\ntype: fit-component\nround: 2\nother: {x: 1}\n", "E")
            self.assertEqual(self.loaded()["a"].meta["other"], {"x": 1})

    def test_what_loads_without_the_plugin_is_skipped_with_a_warning_naming_it(self):
        with entries(**{"fit-component": FitComponent}):
            self.apply(
                "kind: analysis\nname: a\npipeline: simpletestpipeline\ntype: fit-component\nround: 2\n---\n"
                "kind: analysis\nname: b\npipeline: simpletestpipeline\n",
                "E",
            )
        reset_analysis_types()  # (the plugin is not installed now)
        with self.assertLogs("asimov", level="WARNING") as logs:
            found = self.loaded()
        self.assertEqual(sorted(found), ["b"])
        message = "\n".join(logs.output)
        self.assertIn("Skipped loading production 'a' for event 'E'", message)
        self.assertIn("The analysis type 'fit-component' is not installed", message)

    def test_a_version_without_types_loads_a_typed_analysis_as_a_gravitational_wave_one(self):
        """It does not know ``type``, so it is one more key of metadata: what is stored is enough."""
        with entries(**{"fit-component": FitComponent}):
            self.apply("kind: analysis\nname: a\npipeline: simpletestpipeline\ntype: fit-component\nround: 2\n", "E")
            stored = self.loaded()["a"].to_dict(event=False)
        older = GravitationalWaveTransient(subject=self.event(), ledger=self.ledger, **stored)
        self.assertIs(type(older), GravitationalWaveTransient)
        self.assertEqual(older.meta["type"], "fit-component")
        self.assertEqual(older.meta["round"], 2)


class YAMLTests(Tests, ProjectCase):
    pass


class DatabaseTests(Tests, DatabaseProjectCase):
    pass


class FeatureTests(ProjectCase):
    def analysis(self, **meta):
        return types.SimpleNamespace(meta=meta, pipeline=None, _needs=[])

    def test_an_explicit_type_is_a_feature_a_version_without_types_would_misread(self):
        self.assertIn("analysis-types", features_of(self.analysis(type="fit-component")))
        self.assertIn("analysis-types", features.FEATURES)

    def test_a_type_which_a_pipeline_declares_is_not(self):
        self.assertNotIn("analysis-types", features_of(self.analysis()))
        self.assertNotIn("analysis-types", features_of(self.analysis(type="")))

    def test_applying_one_records_it_and_says_so_once(self):
        with entries(**{"fit-component": FitComponent}):
            plan = self.apply("kind: analysis\nname: a\npipeline: simpletestpipeline\ntype: fit-component\nround: 1\n", "E")
            self.assertTrue(any("'type:'" in p.message for p in plan.problems))
            self.assertIn("analysis-types", features.recorded(self.reopen()))
            again = self.apply("kind: analysis\nname: b\npipeline: simpletestpipeline\ntype: fit-component\nround: 2\n", "E")
        self.assertFalse(any("'type:'" in p.message for p in again.problems))

    def test_an_ordinary_analysis_records_nothing(self):
        self.apply("kind: analysis\nname: a\npipeline: simpletestpipeline\n", "E")
        self.assertNotIn("analysis-types", features.recorded(self.reopen()))


if __name__ == "__main__":
    unittest.main()
