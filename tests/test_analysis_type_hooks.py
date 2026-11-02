"""
The hooks of an analysis type (#238): what a type can override, and what asimov
then does with it. ``toy-step`` (see ``asimov.pipelines.testing.types``) uses
each of them once, as a type for a real domain would.
"""
import contextlib
import io
import os
import shutil
import tempfile
import types
import unittest
from unittest.mock import patch

from asimov.analysis import GravitationalWaveTransient, SimpleAnalysis
from asimov.analysis_types import compare, reset_analysis_types
from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.event import Production
from asimov.ledger import DatabaseLedger, YAMLLedger
from asimov.pipelines.testing.types import ToyStep
from asimov.vocabulary import get_vocabulary

EVENT = "kind: event\nname: E\ninterferometers: [H1]\n"


def step(name, round_=1, stream="A", extra=""):
    return (
        f"kind: analysis\nname: {name}\npipeline: simpletestpipeline\ntype: toy-step\n"
        f"round: {round_}\nstream: {stream}\n{extra}"
    )


class ToyCase(unittest.TestCase):
    """A scratch project with one subject, ``E``, in which the toy type is installed."""

    def setUp(self):
        os.environ["ASIMOV_TOY_STRATEGY"] = "1"
        reset_analysis_types()
        self.cwd = os.getcwd()
        self.root = tempfile.mkdtemp()
        os.chdir(self.root)
        self.ledger = self.make_ledger()
        self.apply(EVENT)

    def tearDown(self):
        os.environ.pop("ASIMOV_TOY_STRATEGY", None)
        reset_analysis_types()
        get_vocabulary(refresh=True)
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
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            apply_page("blueprint.yaml", event=subject, ledger=self.ledger)
        return out.getvalue()

    def loaded(self):
        return {a.name: a for a in self.reopen().get_event("E")[0].productions}


class DatabaseToyCase(ToyCase):
    def make_ledger(self):
        self.location = f"sqlite:///{os.path.join(self.root, 'ledger.db')}"
        ledger = DatabaseLedger(engine="sqlalchemy", location=self.location)
        ledger.db.create_tables()
        return ledger

    def reopen(self):
        return DatabaseLedger(engine="sqlalchemy", location=self.location)


class Tests:
    """Each hook, on each ledger."""

    # validate: when a blueprint is applied

    def test_a_valid_analysis_is_applied(self):
        out = self.apply(step("a", round_=2), "E")
        self.assertIn("Successfully applied a to E", out)
        self.assertIs(type(self.loaded()["a"]), ToyStep)

    def test_an_analysis_with_a_problem_is_refused_and_not_stored(self):
        out = self.apply(step("a", round_=0), "E")
        self.assertIn("Could not apply a to E", out)
        self.assertIn("'round' must be a whole number of at least 1", out)
        self.assertEqual(self.loaded(), {})

    def test_every_problem_is_said(self):
        out = self.apply("kind: analysis\nname: a\npipeline: simpletestpipeline\ntype: toy-step\nround: x\n", "E")
        self.assertIn("'round' must be", out)
        self.assertIn("'stream' is needed", out)

    def test_the_others_in_the_blueprint_are_applied_around_it(self):
        out = self.apply(step("good1") + "---\n" + step("bad", round_=-1) + "---\n" + step("good2"), "E")
        self.assertEqual(sorted(self.loaded()), ["good1", "good2"])
        self.assertIn("Could not apply bad", out)

    def test_a_dry_run_refuses_it_too_and_stores_nothing(self):
        with open("blueprint.yaml", "w") as handle:
            handle.write(step("a", round_=0))
        plan = apply_page("blueprint.yaml", event="E", ledger=self.ledger, dry_run=True)
        self.assertTrue(any("'round' must be" in r.message for r in plan.refused), plan.refused)
        self.assertEqual(self.loaded(), {})

    def test_what_is_stored_loads_whether_or_not_it_is_valid(self):
        """A ledger is built on every load, so validation is never part of loading."""
        self.apply(step("a"), "E")
        stored = self.loaded()["a"]
        invalid = Production.from_dict(
            {"name": "broken", "pipeline": "simpletestpipeline", "type": "toy-step", "round": 0},
            subject=self.reopen().get_event("E")[0], ledger=self.ledger,
        )
        self.assertEqual(stored.validate(), [])
        self.assertEqual(len(invalid.validate()), 2)  # (built without a word)

    # match_attribute: in filters

    def test_a_filter_on_the_types_own_attribute_compares_numbers(self):
        self.apply(step("a", round_=2), "E")
        found = self.loaded()["a"]
        for spec, expected in (("<3", True), (">=3", False), ("2", True), ("==2", True), ("!=2", False), (">1", True)):
            self.assertIs(found.matches_filter(["round"], spec), expected, spec)

    def test_negation_applies_to_it(self):
        self.apply(step("a", round_=2), "E")
        self.assertFalse(self.loaded()["a"].matches_filter(["round"], "<3", negate=True))

    def test_needs_can_select_by_the_attribute(self):
        self.apply(step("s1", 1) + "---\n" + step("s2", 2) + "---\n" + step("s3", 3), "E")
        self.apply('kind: analysis\nname: fin\npipeline: simpletestpipeline\nneeds:\n  - round: "<3"\n', "E")
        self.assertEqual(self.loaded()["fin"].dependencies, ["s1", "s2"])

    def test_a_filter_can_combine_the_attribute_with_others(self):
        self.apply(step("a1", 1, "A") + "---\n" + step("b1", 1, "B") + "---\n" + step("a2", 2, "A"), "E")
        self.apply(
            'kind: analysis\nname: fin\npipeline: simpletestpipeline\nneeds:\n  - - round: "<2"\n    - stream: A\n', "E"
        )
        self.assertEqual(self.loaded()["fin"].dependencies, ["a1"])

    def test_what_the_type_has_no_say_in_is_looked_up_as_it_always_was(self):
        self.apply(step("a", extra="other: {x: 1}\n"), "E")
        self.assertTrue(self.loaded()["a"].matches_filter(["other", "x"], "1"))
        self.assertTrue(self.loaded()["a"].matches_filter(["stream"], "a"))

    def test_an_analysis_of_another_type_has_no_such_attribute(self):
        self.apply("kind: analysis\nname: g\npipeline: simpletestpipeline\nround: 1\n", "E")
        self.assertTrue(self.loaded()["g"].matches_filter(["round"], "1"))  # (its metadata, as ever)
        self.assertFalse(self.loaded()["g"].matches_filter(["round"], "<3"))  # (no comparisons)

    # rundir_name: the layout

    def test_the_run_directory_is_where_the_type_says(self):
        self.apply(step("a", round_=2), "E")
        self.assertEqual(os.path.relpath(self.loaded()["a"].rundir, self.root), os.path.join("working", "E", "round-2", "a"))

    def test_the_layout_is_kept_when_it_is_first_worked_out(self):
        self.apply(step("a", round_=2), "E")
        first = self.loaded()["a"]
        first.rundir  # (worked out, and put in the metadata)
        self.assertEqual(first.meta["rundir"], os.path.join("working", "E", "round-2", "a"))

    def test_an_analysis_of_another_type_is_laid_out_as_ever(self):
        self.apply("kind: analysis\nname: g\npipeline: simpletestpipeline\n", "E")
        self.assertEqual(os.path.relpath(self.loaded()["g"].rundir, self.root), os.path.join("working", "E", "g"))

    # card_details: the report

    def test_the_card_has_what_the_type_shows(self):
        self.apply(step("a", round_=2, stream="north"), "E")
        found = self.loaded()["a"]
        self.assertEqual(found.card_details(), [("Round", 2), ("Stream", "north")])

    def test_the_modal_of_the_report_gets_them(self):
        self.apply(step("a", round_=2, stream="north"), "E")
        page = self.reopen().get_event("E")[0].html()
        self.assertIn("data-details=", page)
        self.assertIn("[[&quot;Round&quot;, &quot;2&quot;], [&quot;Stream&quot;, &quot;north&quot;]]", page)

    def test_an_analysis_with_nothing_to_show_has_an_empty_list(self):
        self.apply("kind: analysis\nname: g\npipeline: simpletestpipeline\n", "E")
        self.assertIn('data-details="[]"', self.reopen().get_event("E")[0].html())

    def test_a_card_which_fails_does_not_stop_the_report(self):
        self.apply(step("a"), "E")
        with patch.object(ToyStep, "card_details", side_effect=RuntimeError("boom")):
            page = self.reopen().get_event("E")[0].html()
        self.assertIn('data-details="[]"', page)


class YAMLTests(Tests, ToyCase):
    pass


class DatabaseTests(Tests, DatabaseToyCase):
    pass


class BuildHookTests(unittest.TestCase):
    """The three hooks which are called as an analysis is built."""

    def setUp(self):
        self.cwd = os.getcwd()
        self.root = tempfile.mkdtemp()
        os.chdir(self.root)
        make_project(name="Test project", root=self.root, engine="yamlfile")
        self.ledger = YAMLLedger(".asimov/ledger.yml")
        with open("event.yaml", "w") as handle:
            handle.write(EVENT)
        apply_page("event.yaml", ledger=self.ledger)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def build(self, cls):
        return cls.from_dict(
            {"name": "a", "pipeline": "simpletestpipeline", "given": 1},
            subject=self.ledger.get_event("E")[0], ledger=self.ledger,
        )

    def test_they_are_called_once_each_in_order_when_everything_else_is_built(self):
        seen = []

        class Recording(SimpleAnalysis):
            def set_defaults(self):
                seen.append(("set_defaults", self.meta.get("given"), hasattr(self, "pipeline")))
                self.meta.setdefault("added", True)

            def migrate(self):
                seen.append(("migrate", self.meta.get("added")))

            def after_build(self):
                seen.append(("after_build", self.meta.get("added"), type(self.pipeline).__name__))

        built = self.build(Recording)
        self.assertEqual(
            seen,
            [
                ("set_defaults", 1, True),  # (its own metadata is there, and its pipeline)
                ("migrate", True),  # (what set_defaults added)
                ("after_build", True, "SimpleTestPipeline"),
            ],
        )
        self.assertTrue(built.meta["added"])

    def test_by_default_they_do_nothing(self):
        before = self.build(SimpleAnalysis)
        self.assertEqual(sorted(before.meta), ["given", "interferometers", "ledger", "likelihood", "sampler", "scheduler", "working directory"])

    def test_the_gravitational_wave_type_is_made_of_them(self):
        for hook in ("set_defaults", "migrate", "after_build"):
            self.assertIsNot(getattr(GravitationalWaveTransient, hook), getattr(SimpleAnalysis, hook), hook)

    def test_every_hook_has_a_default_which_says_nothing(self):
        plain = self.build(SimpleAnalysis)
        self.assertEqual(plain.validate(), [])
        self.assertIsNone(plain.match_attribute(["x"], "y"))
        self.assertEqual(plain.card_details(), [])
        self.assertEqual(plain.rundir_name(), "a")


class CompareTests(unittest.TestCase):
    def test_numbers_are_compared_as_numbers(self):
        self.assertTrue(compare(2, "<3"))
        self.assertTrue(compare(10, ">9"))  # (not as text, where "10" < "9")
        self.assertTrue(compare("2", ">=2"))
        self.assertTrue(compare(2.5, "<=2.5"))
        self.assertFalse(compare(3, "<3"))

    def test_a_value_alone_means_equal(self):
        self.assertTrue(compare(3, "3"))
        self.assertTrue(compare(3, "3.0"))
        self.assertFalse(compare(3, "4"))

    def test_text_is_compared_without_regard_to_case(self):
        self.assertTrue(compare("North", "north"))
        self.assertTrue(compare("North", "==north"))
        self.assertTrue(compare("North", "!=south"))

    def test_text_has_no_order(self):
        self.assertFalse(compare("b", ">a"))
        self.assertFalse(compare("a", "<b"))

    def test_whitespace_is_ignored(self):
        self.assertTrue(compare(2, " < 3 "))

    def test_something_which_is_not_a_number_does_not_match_a_number(self):
        self.assertFalse(compare(None, "<3"))
        self.assertFalse(compare("x", ">=1"))


class VocabularyTests(ToyCase):
    """A type brings its own terms (``vocabulary`` on its class)."""

    document = {"name": "a", "pipeline": "simpletestpipeline", "round": 3, "stream": "A"}

    def test_the_terms_of_the_type_are_known(self):
        found = get_vocabulary(refresh=True).check(self.document)
        self.assertEqual(found, [])

    def test_they_are_checked(self):
        found = get_vocabulary(refresh=True).check({**self.document, "round": "three"})
        self.assertEqual([f.kind for f in found], ["type"])

    def test_they_are_not_foreign_to_the_pipeline_of_the_document(self):
        found = get_vocabulary(refresh=True).check(self.document, pipeline="somepipeline")
        self.assertEqual([f for f in found if f.kind == "foreign"], [])

    def test_without_the_type_they_are_unknown(self):
        os.environ.pop("ASIMOV_TOY_STRATEGY")
        reset_analysis_types()
        found = get_vocabulary(refresh=True).check(self.document)
        self.assertEqual({f.kind for f in found}, {"unknown"})

    def test_a_type_whose_vocabulary_cannot_be_read_is_reported_and_the_rest_load(self):
        class Broken(SimpleAnalysis):
            vocabulary = 3  # (not a dict, a path or something which returns one)

        points = [types.SimpleNamespace(name="broken", load=lambda: Broken)]
        with patch("asimov.analysis_types.entry_points", return_value=points):
            reset_analysis_types()
            with self.assertLogs("asimov.vocabulary", level="WARNING") as logs:
                found = get_vocabulary(refresh=True).check(self.document)
        self.assertIn("'broken'", "\n".join(logs.output))
        self.assertEqual(found, [])  # (the toy type's terms are there)


class TypedStrategyTests(ToyCase):
    def test_the_toy_strategy_makes_typed_analyses_when_asked(self):
        self.apply("kind: analysis\nname: toy\nstrategy:\n  type: toy-rounds\n  rounds: 2\n  typed: true\n")
        found = {
            (s, a.name): a
            for s in self.reopen().subject_names()
            for a in self.reopen().get_event(s)[0].productions
        }
        self.assertEqual(len(found), 6)
        self.assertTrue(all(type(a) is ToyStep for a in found.values()), {k: type(a) for k, a in found.items()})
        self.assertEqual(found[("component-A", "step-r2")].round, 2)
        self.assertEqual(found[("shared", "combine-r1")].stream, "shared")

    def test_and_ordinary_ones_when_not(self):
        self.apply("kind: analysis\nname: toy\nstrategy:\n  type: toy-rounds\n  rounds: 1\n")
        analyses = [a for s in self.reopen().subject_names() for a in self.reopen().get_event(s)[0].productions]
        self.assertTrue(all(type(a) is GravitationalWaveTransient for a in analyses))


if __name__ == "__main__":
    unittest.main()
