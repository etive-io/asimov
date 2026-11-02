"""
Subject types (#238): a plugin can provide the type of a subject, which for now
says what its subjects are called. A subject asks for one with ``type:``.
"""
import os
import shutil
import tempfile
import types
import unittest
from unittest.mock import patch

from click.testing import CliRunner

from asimov import subject_types
from asimov.analysis import GravitationalWaveTransient
from asimov.cli import manage
from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.event import Event, Subject
from asimov.ledger import DatabaseLedger, YAMLLedger
from asimov.pipelines.testing.types import ToyComponent
from asimov.subject_types import (
    SubjectTypeError,
    check,
    class_for,
    declared_type,
    get_subject_type,
    noun_of,
    reset_subject_types,
    subject_types as installed,
)
from tests.test_chain_until_idle_e2e import CLI, EndToEndCase


class Component(Event):
    """A plugin's subject type, with a plural which is not just an 's'."""

    subject_noun = "stratum"
    subject_noun_plural = "strata"


def entries(**found):
    points = [types.SimpleNamespace(name=n, load=lambda c=c: c) for n, c in found.items()]
    return patch("asimov.subject_types.entry_points", return_value=points)


class RegistryCase(unittest.TestCase):
    def setUp(self):
        reset_subject_types()
        self.addCleanup(reset_subject_types)


class RegistryTests(RegistryCase):
    def test_the_default_is_the_event(self):
        self.assertIs(installed()["event"], Event)
        self.assertIs(get_subject_type("event"), Event)

    def test_a_plugin_registers_a_type_by_name(self):
        with entries(stratum=Component):
            self.assertIs(get_subject_type("stratum"), Component)
        self.assertIn("event", installed())

    def test_a_plugin_cannot_replace_the_event(self):
        with entries(event=Component):
            self.assertIs(get_subject_type("event"), Event)

    def test_a_plugin_which_fails_to_load_is_reported_and_left_out(self):
        def broken():
            raise ImportError("no module named gwaith")

        with patch("asimov.subject_types.entry_points", return_value=[types.SimpleNamespace(name="broken", load=broken)]):
            with self.assertLogs("asimov.subject_types", level="WARNING") as logs:
                found = installed()
        self.assertNotIn("broken", found)
        self.assertIn("no module named gwaith", "\n".join(logs.output))

    def test_the_types_are_read_once(self):
        with entries(stratum=Component) as points:
            installed()
            get_subject_type("event")
        self.assertEqual(points.call_count, 1)

    def test_a_type_which_is_not_installed_says_which_are(self):
        with self.assertRaises(SubjectTypeError) as caught:
            get_subject_type("stratum")
        message = str(caught.exception)
        self.assertIn("'stratum' is not installed", message)
        self.assertIn("event", message)
        self.assertIn("plugin", message)

    def test_a_document_says_its_type_with_a_name(self):
        self.assertEqual(declared_type({"name": "a", "type": "stratum"}), "stratum")
        self.assertIsNone(declared_type({"name": "a"}))
        self.assertIsNone(declared_type({"name": "a", "type": 3}))
        self.assertIsNone(declared_type({"name": "a", "type": ""}))

    def test_checking_a_document_raises_only_for_a_type_which_is_not_installed(self):
        check({"name": "a"})
        check({"name": "a", "type": "event"})
        reset_subject_types()  # (the registry is read once: look again, with the plugin)
        with entries(stratum=Component):
            check({"name": "a", "type": "stratum"})
        reset_subject_types()
        with self.assertRaises(SubjectTypeError):
            check({"name": "a", "type": "stratum"})

    def test_a_type_which_is_not_installed_is_an_ordinary_subject_when_loading_with_one_warning(self):
        with self.assertLogs("asimov.subject_types", level="WARNING") as logs:
            self.assertIs(class_for({"name": "a", "type": "stratum"}), Event)
            self.assertIs(class_for({"name": "b", "type": "stratum"}), Event)
        self.assertEqual(len(logs.output), 1)
        self.assertIn("'stratum' is not installed", logs.output[0])
        self.assertIn("loaded as ordinary subjects", logs.output[0])


class NounTests(unittest.TestCase):
    def of(self, *classes):
        return [object.__new__(c) for c in classes]

    def test_what_a_type_calls_its_subjects(self):
        self.assertEqual(noun_of(self.of(ToyComponent, ToyComponent)), ("component", "components"))

    def test_the_plural_can_be_given(self):
        self.assertEqual(noun_of(self.of(Component)), ("stratum", "strata"))

    def test_an_event_says_nothing_so_callers_say_what_they_always_did(self):
        self.assertIsNone(noun_of(self.of(Event)))
        self.assertIsNone(Event.subject_noun)

    def test_subjects_which_do_not_agree_say_nothing(self):
        self.assertIsNone(noun_of(self.of(ToyComponent, Event)))
        self.assertIsNone(noun_of(self.of(ToyComponent, Component)))

    def test_no_subjects_say_nothing(self):
        self.assertIsNone(noun_of([]))


class ProjectCase(RegistryCase):
    def setUp(self):
        super().setUp()
        os.environ["ASIMOV_TOY_STRATEGY"] = "1"
        reset_subject_types()
        self.cwd = os.getcwd()
        self.root = tempfile.mkdtemp()
        os.chdir(self.root)
        self.ledger = self.make_ledger()

    def tearDown(self):
        os.environ.pop("ASIMOV_TOY_STRATEGY", None)
        reset_subject_types()
        os.chdir(self.cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def make_ledger(self):
        make_project(name="Test project", root=self.root, engine="yamlfile")
        return YAMLLedger(".asimov/ledger.yml")

    def reopen(self):
        return YAMLLedger(".asimov/ledger.yml")

    def apply(self, text, subject=None, **kwargs):
        with open("blueprint.yaml", "w") as handle:
            handle.write(text)
        return apply_page("blueprint.yaml", event=subject, ledger=self.ledger, **kwargs)


class DatabaseProjectCase(ProjectCase):
    def make_ledger(self):
        self.location = f"sqlite:///{os.path.join(self.root, 'ledger.db')}"
        ledger = DatabaseLedger(engine="sqlalchemy", location=self.location)
        ledger.db.create_tables()
        return ledger

    def reopen(self):
        return DatabaseLedger(engine="sqlalchemy", location=self.location)


SUBJECT = "kind: event\nname: {name}\ninterferometers: [H1]\n{extra}"


class Tests:
    # Building one, whichever way

    def test_a_subject_which_says_its_type_is_built_as_it(self):
        built = Event(name="C", type="toy-component", ledger=self.ledger)
        self.assertIs(type(built), ToyComponent)
        self.assertIsInstance(built, Event)

    def test_a_subject_which_says_nothing_is_an_event(self):
        self.assertIs(type(Event(name="E", ledger=self.ledger)), Event)

    def test_the_event_type_is_an_event(self):
        self.assertIs(type(Event(name="E", type="event", ledger=self.ledger)), Event)

    def test_subject_is_event_and_builds_a_type_too(self):
        self.assertIs(Subject, Event)
        self.assertIs(type(Subject(name="C", type="toy-component", ledger=self.ledger)), ToyComponent)

    def test_from_yaml_builds_it(self):
        built = Event.from_yaml(SUBJECT.format(name="C", extra="type: toy-component\n"))
        self.assertIs(type(built), ToyComponent)

    def test_a_type_which_builds_on_the_event_has_what_it_has(self):
        built = Event(name="C", type="toy-component", ledger=self.ledger)
        self.assertEqual(built.productions, [])
        self.assertTrue(built.repository)

    def test_the_name_may_be_given_first(self):
        self.assertIs(type(Event("C", type="toy-component", ledger=self.ledger)), ToyComponent)

    # Applying, saving, loading

    def test_an_applied_subject_is_stored_with_its_type_and_loads_as_it(self):
        self.apply(SUBJECT.format(name="C", extra="type: toy-component\n"))
        found = self.reopen().get_event("C")[0]
        self.assertIs(type(found), ToyComponent)
        self.assertEqual(found.meta["type"], "toy-component")
        self.assertEqual(found.to_dict()["type"], "toy-component")

    def test_kind_subject_does_too(self):
        self.apply("kind: subject\nname: C\ninterferometers: [H1]\ntype: toy-component\n")
        self.assertIs(type(self.reopen().get_event("C")[0]), ToyComponent)

    def test_its_analyses_load_with_it(self):
        self.apply(SUBJECT.format(name="C", extra="type: toy-component\n"))
        self.apply("kind: analysis\nname: a\npipeline: simpletestpipeline\n", "C")
        found = self.reopen().get_event("C")[0]
        self.assertEqual([(a.name, type(a)) for a in found.productions], [("a", GravitationalWaveTransient)])

    def test_every_subject_of_a_project_loads_as_its_own_type(self):
        self.apply(SUBJECT.format(name="C", extra="type: toy-component\n") + "---\n" + SUBJECT.format(name="E", extra=""))
        kinds = {e.name: type(e) for e in self.reopen().get_event()}
        self.assertEqual(kinds, {"C": ToyComponent, "E": Event})

    def test_a_subject_of_a_type_which_is_not_installed_is_refused_and_not_stored(self):
        plan = self.apply(SUBJECT.format(name="X", extra="type: gone\n"), dry_run=True)
        self.assertTrue(any("'gone' is not installed" in r.message for r in plan.refused), plan.refused)
        self.apply(SUBJECT.format(name="X", extra="type: gone\n"))
        self.assertEqual([e.name for e in self.reopen().get_event()], [])

    def test_the_others_in_the_blueprint_are_applied_around_it(self):
        self.apply(
            SUBJECT.format(name="A", extra="") + "---\n" + SUBJECT.format(name="X", extra="type: gone\n")
            + "---\n" + SUBJECT.format(name="B", extra="")
        )
        self.assertEqual(sorted(e.name for e in self.reopen().get_event()), ["A", "B"])

    def test_what_loads_without_the_plugin_is_an_ordinary_subject_and_its_analyses_load(self):
        self.apply(SUBJECT.format(name="C", extra="type: toy-component\n"))
        self.apply("kind: analysis\nname: a\npipeline: simpletestpipeline\n", "C")
        os.environ.pop("ASIMOV_TOY_STRATEGY")
        reset_subject_types()  # (the plugin is not installed now)
        with self.assertLogs("asimov.subject_types", level="WARNING") as logs:
            found = self.reopen().get_event("C")[0]
        self.assertIs(type(found), Event)
        self.assertEqual(found.meta["type"], "toy-component")  # (kept, as plain metadata)
        self.assertEqual([a.name for a in found.productions], ["a"])
        self.assertIn("'toy-component' is not installed", "\n".join(logs.output))


class YAMLTests(Tests, ProjectCase):
    pass


class DatabaseTests(Tests, DatabaseProjectCase):
    pass


class ManageWordingTests(ProjectCase):
    def build(self):
        with patch("asimov.cli.manage.ledger", new=self.reopen()):
            return CliRunner().invoke(manage.build, []).output

    def test_what_the_type_calls_its_subjects_is_used(self):
        self.apply(SUBJECT.format(name="C1", extra="type: toy-component\n") + "---\n" + SUBJECT.format(name="C2", extra="type: toy-component\n"))
        self.assertIn("Building 2 component(s)", self.build())

    def test_events_are_what_they_always_were(self):
        self.apply(SUBJECT.format(name="E", extra=""))
        output = self.build()
        self.assertIn("Loading events...", output)
        self.assertIn("Building 1 event(s)", output)

    def test_mixed_subjects_say_what_they_always_did(self):
        self.apply(SUBJECT.format(name="C", extra="type: toy-component\n") + "---\n" + SUBJECT.format(name="E", extra=""))
        self.assertIn("Building 2 event(s)", self.build())


@unittest.skipUnless(os.path.exists(CLI), "the asimov command is not installed")
class ReportWordingTests(EndToEndCase):
    """The page which ``asimov report html`` writes."""

    @classmethod
    def setUpClass(cls):
        os.environ["ASIMOV_TOY_STRATEGY"] = "1"
        super().setUpClass()
        cls.env["ASIMOV_TOY_STRATEGY"] = "1"

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("ASIMOV_TOY_STRATEGY", None)
        super().tearDownClass()

    def page(self, subjects, name):
        text = "---\n".join(f"kind: event\nname: {n}\ninterferometers: [H1]\n{extra}" for n, extra in subjects)
        self.apply(text)
        out = os.path.join(self.root, name)
        self.run_cli("report", "html", "--location", out)
        with open(os.path.join(out, "index.html")) as handle:
            return handle.read()

    def test_the_report_calls_subjects_what_their_type_does_or_what_it_always_did(self):
        # (the project has EvA and EvB, ordinary events, from setUpClass of the helper)
        page = self.page([("C1", "type: toy-component\n")], "mixed")
        self.assertIn("<h6>Subjects</h6>", page)  # (mixed with the project's events: as ever)
        self.assertIn("Search events/subjects...", page)

    def test_a_report_of_one_typed_subject_uses_the_noun(self):
        self.apply("kind: event\nname: Only\ninterferometers: [H1]\ntype: toy-component\n")
        out = os.path.join(self.root, "only")
        self.run_cli("report", "html", "--location", out, "Only")
        with open(os.path.join(out, "index.html")) as handle:
            page = handle.read()
        self.assertIn("<h6>Components</h6>", page)
        self.assertIn("Search components...", page)
        self.assertNotIn("Search events/subjects...", page)


if __name__ == "__main__":
    unittest.main()
