"""
Characterisation tests for how analyses are constructed today (#238).

#238 makes the *type* of an analysis selectable. Before that changes how every
analysis is built, these tests pin what construction does now: which class each
way of building one produces, what the gravitational-wave class adds, what is
stored and reloaded, and what happens when a pipeline is not installed.

They describe present behaviour, including some which is awkward. If one fails
after a change, that change altered what an existing ledger loads as, and the
failure is the thing to look at, not the test. The few which are *meant* to
change when types arrive are in :class:`WillChangeWithTypes`, and say so.

Each test which loads a ledger runs against both the YAML ledger and the
database ledger, which build analyses in different places.
"""
import copy
import os
import shutil
import tempfile
import unittest

import asimov.event
from asimov import config
from asimov.analysis import (
    GravitationalWaveTransient,
    SimpleAnalysis,
    SubjectAnalysis,
)
from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.event import Event, Production, Subject
from asimov.ledger import DatabaseLedger, YAMLLedger

EVENT = "kind: event\nname: E\ninterferometers: [H1]\n"


def analysis(name, extra="", pipeline="simpletestpipeline"):
    return f"kind: analysis\nname: {name}\npipeline: {pipeline}\n{extra}"


class ConstructionCase(unittest.TestCase):
    """A scratch project with one subject, ``E``."""

    def setUp(self):
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
        apply_page("blueprint.yaml", event=subject, ledger=self.ledger)

    def loaded(self, name=None):
        """The analyses of ``E``, as a fresh ledger builds them."""
        found = {a.name: a for a in self.reopen().get_event("E")[0].productions}
        return found if name is None else found[name]

    def add_ghost(self):
        """Store an analysis whose pipeline is not installed."""
        ledger = self.reopen()
        ledger.events["E"]["productions"].append(
            {"ghost": {"name": "ghost", "pipeline": "nosuchpipeline", "status": "ready"}}
        )
        ledger.save()


class DatabaseCase(ConstructionCase):
    def make_ledger(self):
        self.location = f"sqlite:///{os.path.join(self.root, 'ledger.db')}"
        ledger = DatabaseLedger(engine="sqlalchemy", location=self.location)
        ledger.db.create_tables()
        return ledger

    def reopen(self):
        return DatabaseLedger(engine="sqlalchemy", location=self.location)

    def add_ghost(self):
        self.reopen().db.insert_production(
            {"name": "ghost", "pipeline": "nosuchpipeline", "status": "ready", "event_name": "E", "meta": {}}
        )


class Tests:
    """What construction does, for each ledger."""

    # Which class

    def test_every_analysis_a_ledger_loads_is_a_gravitational_wave_analysis(self):
        self.apply(analysis("a") + "---\n" + analysis("b"), "E")
        for name in ("a", "b"):
            self.assertIs(type(self.loaded(name)), GravitationalWaveTransient, name)

    def test_what_is_applied_is_built_as_one_too(self):
        self.apply(analysis("a"), "E")
        event = self.ledger.get_event("E")[0]
        self.assertIs(type(next(p for p in event.productions if p.name == "a")), GravitationalWaveTransient)

    def test_an_analysis_which_combines_others_is_a_subject_analysis(self):
        self.apply(analysis("a") + "---\n" + analysis("sub", "analyses:\n- - 'pipeline: simpletestpipeline'\n"), "E")
        self.assertIs(type(self.loaded("sub")), SubjectAnalysis)
        self.assertIs(type(self.loaded("a")), GravitationalWaveTransient)

    def test_the_pipeline_name_is_not_case_sensitive(self):
        self.apply(analysis("a", pipeline="SimpleTestPipeline"), "E")
        self.assertEqual(type(self.loaded("a").pipeline).__name__, "SimpleTestPipeline")

    def test_a_command_analysis_is_built_as_one_too(self):
        self.apply("kind: analysis\nname: c\ncommand: [true]\n", "E")
        self.assertIs(type(self.loaded("c")), GravitationalWaveTransient)
        self.assertEqual(self.loaded("c").pipeline.name, "command")

    # What the gravitational-wave class adds

    def test_the_metadata_it_adds(self):
        self.apply(analysis("a"), "E")
        meta = self.loaded("a").meta
        self.assertEqual(meta["scheduler"], {})
        self.assertEqual(meta["likelihood"], {"marginalization": {}})
        self.assertEqual(meta["data"], {"data files": {}})
        self.assertIn("sampler", meta)
        self.assertIn("waveform", meta)

    def test_the_category_is_the_calibration_directory_of_the_configuration(self):
        self.apply(analysis("a"), "E")
        self.assertEqual(self.loaded("a").category, config.get("general", "calibration_directory"))

    def test_the_psds_are_resolved_and_empty_when_there_are_none(self):
        self.apply(analysis("a"), "E")
        found = self.loaded("a")
        self.assertEqual(found.psds, {})
        self.assertEqual(found.xml_psds, {})
        self.assertEqual(found._psd_errors, {})

    def test_quality_is_migrated_to_likelihood_and_left_in_place(self):
        self.apply(analysis("a", "quality:\n  minimum frequency: {H1: 20}\n"), "E")
        meta = self.loaded("a").meta
        self.assertEqual(meta["likelihood"]["minimum frequency"], {"H1": 20})
        self.assertIn("quality", meta)

    # PSD resolution: the analysis's own, then a dependency's, then the subject's

    def psd_subject(self):
        """A subject with PSDs of its own, ``P``."""
        self.apply("kind: event\nname: P\ninterferometers: [H1]\npsds:\n  H1: /x/event_psd.dat\n")

    def psds_of(self, name):
        event = self.reopen().get_event("P")[0]
        return next(p for p in event.productions if p.name == name).psds

    def test_the_psds_of_the_subject_are_used_when_the_analysis_sets_none(self):
        self.psd_subject()
        self.apply(analysis("a"), "P")
        self.assertEqual(self.psds_of("a"), {"H1": "/x/event_psd.dat"})

    def test_the_psds_of_the_analysis_win_over_the_subjects(self):
        self.psd_subject()
        self.apply(analysis("a", "psds:\n  H1: /x/own_psd.dat\n"), "P")
        self.assertEqual(self.psds_of("a"), {"H1": "/x/own_psd.dat"})

    def test_the_psds_of_what_is_needed_win_over_the_subjects(self):
        from unittest.mock import patch

        from asimov.pipelines.testing import SimpleTestPipeline

        self.psd_subject()
        self.apply(analysis("a") + "---\n" + analysis("b", "needs: [a]\n"), "P")
        with patch.object(SimpleTestPipeline, "collect_assets", return_value={"psds": {"H1": "/x/dep_psd.dat"}}):
            self.assertEqual(self.psds_of("b"), {"H1": "/x/dep_psd.dat"})

    # What is stored and reloaded

    def test_what_a_blueprint_says_is_kept_in_the_metadata(self):
        self.apply(analysis("a", "mything: {a: 1}\n"), "E")
        self.assertEqual(self.loaded("a").meta["mything"], {"a": 1})

    def test_it_is_serialised_with_its_name_pipeline_status_and_metadata_at_the_top_level(self):
        self.apply(analysis("a", "mything: {a: 1}\n"), "E")
        data = self.loaded("a").to_dict(event=False)
        for key in ("name", "pipeline", "status", "comment", "scheduler", "likelihood", "mything", "needs"):
            self.assertIn(key, data)
        self.assertEqual(data["name"], "a")

    def test_a_new_analysis_is_ready(self):
        self.apply(analysis("a"), "E")
        self.assertEqual(self.loaded("a").status, "ready")

    def test_what_is_saved_loads_back_the_same(self):
        self.apply(analysis("a", "mything: {a: 1}\nstatus: finished\n"), "E")
        again = self.loaded("a")
        self.assertEqual((again.name, again.status, again.meta["mything"]), ("a", "finished", {"a": 1}))

    # Building one directly

    def test_from_dict_leaves_its_argument_alone_and_ignores_the_event_key(self):
        event = self.ledger.get_event("E")[0]
        parameters = {"name": "x", "pipeline": "simpletestpipeline", "event": "ignored"}
        before = copy.deepcopy(parameters)
        built = Production.from_dict(parameters, subject=event, ledger=self.ledger)
        self.assertEqual(parameters, before)
        self.assertEqual(built.status, "ready")
        self.assertIs(type(built), GravitationalWaveTransient)

    def test_from_dict_needs_a_name_and_a_pipeline(self):
        event = self.ledger.get_event("E")[0]
        with self.assertRaisesRegex(ValueError, "required parameters are missing"):
            Production.from_dict({"name": "x"}, subject=event, ledger=self.ledger)

    def test_a_command_with_no_pipeline_is_given_the_command_pipeline(self):
        event = self.ledger.get_event("E")[0]
        built = Production.from_dict({"name": "x", "command": ["true"]}, subject=event, ledger=self.ledger)
        self.assertEqual(built.pipeline.name, "command")

    def test_it_can_be_built_by_calling_the_class_as_the_api_does(self):
        event = self.ledger.get_event("E")[0]
        built = Production(subject=event, name="direct", pipeline="simpletestpipeline", comment="c")
        self.assertIs(type(built), GravitationalWaveTransient)
        self.assertEqual(built.name, "direct")


class YAMLTests(Tests, ConstructionCase):
    def test_an_analysis_whose_pipeline_is_not_installed_stops_its_subject_loading(self):
        """The YAML ledger does not skip it: getting the subject raises, so every command on it does."""
        self.apply(analysis("a"), "E")
        self.add_ghost()
        with self.assertRaises(KeyError) as caught:
            self.reopen().get_event("E")
        self.assertIn("nosuchpipeline", str(caught.exception))


class DatabaseTests(Tests, DatabaseCase):
    def test_an_analysis_whose_pipeline_is_not_installed_is_skipped_with_a_warning(self):
        self.apply(analysis("a") + "---\n" + analysis("b"), "E")
        self.add_ghost()
        with self.assertLogs("asimov.ledger", level="WARNING") as logs:
            found = self.loaded()
        self.assertEqual(sorted(found), ["a", "b"])
        message = "\n".join(logs.output)
        self.assertIn("Skipped loading production 'ghost' for event 'E'", message)
        self.assertIn("nosuchpipeline", message)

    def test_get_productions_builds_the_same_class(self):
        self.apply(analysis("a"), "E")
        found = self.reopen().get_productions("E")
        self.assertEqual([(p.name, type(p)) for p in found], [("a", GravitationalWaveTransient)])


class AliasTests(unittest.TestCase):
    """What other code imports."""

    def test_production_is_the_gravitational_wave_class(self):
        self.assertIs(Production, GravitationalWaveTransient)
        self.assertIs(asimov.event.Production, GravitationalWaveTransient)

    def test_subject_is_event(self):
        self.assertIs(Subject, Event)

    def test_the_gravitational_wave_class_is_a_simple_analysis(self):
        self.assertTrue(issubclass(GravitationalWaveTransient, SimpleAnalysis))


class WillChangeWithTypes(ConstructionCase):
    """
    What is true now and is meant to change when analysis types arrive (#238).

    These are the tests to update, deliberately and with the change which makes
    them fail; the rest of this file should pass unmodified.
    """

    def test_a_command_analysis_carries_the_gravitational_wave_metadata(self):
        """The command pipeline is generic: it will declare the generic type."""
        self.apply("kind: analysis\nname: c\ncommand: [true]\n", "E")
        meta = self.loaded("c").meta
        for key in ("data", "likelihood", "waveform", "sampler", "scheduler"):
            self.assertIn(key, meta)

    def test_a_generic_analysis_has_no_category_or_psds(self):
        event = self.ledger.get_event("E")[0]
        built = SimpleAnalysis.from_dict({"name": "plain", "pipeline": "simpletestpipeline"}, subject=event, ledger=self.ledger)
        self.assertFalse(hasattr(built, "category"))
        self.assertFalse(hasattr(built, "psds"))
        self.assertNotIn("data", built.meta)
        self.assertNotIn("waveform", built.meta)

    def test_the_yaml_ledger_stores_a_generic_analysis(self):
        event = self.ledger.get_event("E")[0]
        built = SimpleAnalysis.from_dict({"name": "plain", "pipeline": "simpletestpipeline"}, subject=event, ledger=self.ledger)
        self.ledger.add_analysis(built, event=event)  # (does not raise)

    def test_the_database_ledger_refuses_a_generic_analysis(self):
        """It dispatches on ``isinstance(payload, Production)``, which is the GW class."""
        ledger = DatabaseCase.make_ledger(self)
        event_file = os.path.join(self.root, "event.yaml")
        with open(event_file, "w") as handle:
            handle.write(EVENT.replace("name: E", "name: F"))
        apply_page(event_file, ledger=ledger)
        event = ledger.get_event("F")[0]
        built = SimpleAnalysis.from_dict({"name": "plain", "pipeline": "simpletestpipeline"}, subject=event, ledger=ledger)
        with self.assertRaisesRegex(ValueError, "Unknown payload type"):
            ledger._insert(built)


if __name__ == "__main__":
    unittest.main()
