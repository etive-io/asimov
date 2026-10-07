"""
``needs:`` can name an analysis in another subject as ``subject/name`` (#231).

What it must not change is pinned by ``test_needs_characterisation.py``; these
are the new behaviour: resolving the name, holding an analysis back until what
it needs in another subject has finished, and what happens when the name does
not resolve.
"""
import logging
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from asimov.cli.application import apply_page
from asimov.cli.manage import report_unresolved_needs
from asimov.cli.project import make_project
from asimov.ledger import YAMLLedger

EVENT = "kind: event\nname: {name}\ninterferometers: [H1]\n"


def analysis(name, status="finished", needs=None, pipeline="simpletestpipeline"):
    text = f"kind: analysis\nname: {name}\npipeline: {pipeline}\nstatus: {status}\n"
    if needs is not None:
        text += "needs:\n" + "".join(f"  - {need}\n" for need in needs)
    return text


class CrossSubjectCase(unittest.TestCase):
    """Three subjects: ``central``, and two streams."""

    def setUp(self):
        self.cwd = os.getcwd()
        self.root = tempfile.mkdtemp()
        os.chdir(self.root)
        make_project(name="Test project", root=self.root, engine="yamlfile")
        self.ledger = YAMLLedger(".asimov/ledger.yml")
        for name in ("central", "s1", "s2"):
            self.write("event.yaml", EVENT.format(name=name))
            apply_page("event.yaml", ledger=self.ledger)
        self.logger = logging.getLogger("test_cross_subject_needs")

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, name, text):
        with open(name, "w") as handle:
            handle.write(text)

    def apply(self, event, *blueprints):
        self.write("blueprint.yaml", "---\n".join(blueprints))
        apply_page("blueprint.yaml", event=event, ledger=self.ledger)

    def get(self, event, name):
        """One analysis, from a ledger read afresh."""
        event = YAMLLedger(".asimov/ledger.yml").get_event(event)[0]
        return event.analysis_by_name(name)


class ResolutionTests(CrossSubjectCase):
    def setUp(self):
        super().setUp()
        self.apply("central", analysis("prep"), analysis("shared"))
        self.apply("s1", analysis("fit"), analysis("shared"))

    def test_a_qualified_name_reaches_another_subject(self):
        self.apply("s2", analysis("next", status="ready", needs=["central/prep"]))
        self.assertEqual(self.get("s2", "next").dependencies, ["central/prep"])

    def test_it_resolves_to_the_analysis_of_that_subject(self):
        self.apply("s2", analysis("next", status="ready", needs=["s1/shared"]))
        (found,) = self.get("s2", "next").dependency_objects
        self.assertEqual((found.event.name, found.name), ("s1", "shared"))

    def test_the_subjects_own_name_is_qualified_too(self):
        self.apply("s1", analysis("again", status="ready", needs=["s1/fit"]))
        again = self.get("s1", "again")
        # A name in its own subject stays a bare name.
        self.assertEqual(again.dependencies, ["fit"])
        self.assertEqual(again.unresolved_needs, [])

    def test_a_qualified_name_in_a_group_still_applies_the_other_conditions(self):
        self.write(
            "blueprint.yaml",
            analysis("next", status="ready")
            + "needs:\n  - - central/prep\n    - 'status: running'\n",
        )
        apply_page("blueprint.yaml", event="s2", ledger=self.ledger)
        # central/prep has finished, so does not match ``status: running``.
        self.assertEqual(self.get("s2", "next").dependencies, [])

    def test_negation_is_not_a_qualified_name(self):
        self.apply("s2", analysis("next", status="ready", needs=["'name: !central/prep'"]))
        self.assertEqual(self.get("s2", "next").dependencies, [])

    def test_three_parts_are_reserved(self):
        self.apply("s2", analysis("next", status="ready", needs=["project/central/prep"]))
        self.assertEqual(self.get("s2", "next").dependencies, [])

    def test_dependencies_in_several_subjects_are_in_name_order(self):
        self.apply("s2", analysis("next", status="ready", needs=["s1/fit", "central/prep", "s1/shared"]))
        self.assertEqual(
            self.get("s2", "next").dependencies, ["central/prep", "s1/fit", "s1/shared"]
        )

    def test_the_same_bare_name_in_two_subjects_is_two_dependencies(self):
        self.apply("s2", analysis("next", status="ready", needs=["central/shared", "s1/shared"]))
        self.assertEqual(
            self.get("s2", "next").dependencies, ["central/shared", "s1/shared"]
        )

    def test_a_literal_name_still_wins(self):
        self.apply("s2", analysis("central/prep"), analysis("next", status="ready", needs=["central/prep"]))
        (found,) = self.get("s2", "next").dependency_objects
        self.assertEqual(found.event.name, "s2")
        self.assertEqual(self.get("s2", "next").dependencies, ["central/prep"])


class OtherUsesOfNeedsTests(CrossSubjectCase):
    """What reads the dependencies must see the ones in other subjects."""

    def setUp(self):
        super().setUp()
        self.apply("central", analysis("prep"))
        self.apply("s2", analysis("next", status="ready", needs=["central/prep"]))
        self.next = self.get("s2", "next")

    def test_assets_are_collected_from_it(self):
        prep = self.next.dependency_objects[0]
        with patch.object(type(prep.pipeline), "collect_assets", return_value={"a": 1}):
            self.assertEqual(self.next._previous_assets(), {"a": 1})

    def test_validation_considers_it(self):
        self.assertEqual([a.name for a in self.next._dependency_analyses()], ["prep"])

    def test_it_is_stored_qualified_and_stale_when_it_changes(self):
        self.next.resolved_dependencies = self.next.dependencies
        self.assertEqual(self.next.resolved_dependencies, ["central/prep"])
        self.assertFalse(self.next.is_stale)
        self.next.resolved_dependencies = ["prep"]
        self.assertTrue(self.next.is_stale)

    def test_needs_is_stored_as_written(self):
        self.assertEqual(self.next.to_dict()["next"]["needs"], ["central/prep"])


class HoldingTests(CrossSubjectCase):
    def ready(self, event):
        ledger = YAMLLedger(".asimov/ledger.yml")
        return {a.name for a in ledger.get_event(event)[0].get_all_latest()}

    def test_it_waits_for_an_analysis_in_another_subject(self):
        self.apply("central", analysis("prep", status="running"))
        self.apply("s2", analysis("next", status="ready", needs=["central/prep"]))
        self.assertEqual(self.ready("s2"), set())

    def test_it_runs_once_that_has_finished(self):
        self.apply("central", analysis("prep", status="finished"))
        self.apply("s2", analysis("next", status="ready", needs=["central/prep"]))
        self.assertEqual(self.ready("s2"), {"next"})

    def test_an_unrelated_analysis_is_not_held(self):
        self.apply("central", analysis("prep", status="running"))
        self.apply(
            "s2",
            analysis("next", status="ready", needs=["central/prep"]),
            analysis("other", status="ready"),
        )
        self.assertEqual(self.ready("s2"), {"other"})

    def test_it_waits_in_either_direction(self):
        self.apply("s1", analysis("fit", status="ready"))
        self.apply("central", analysis("combine", status="ready", needs=["s1/fit"]))
        self.assertEqual(self.ready("s1"), {"fit"})
        self.assertEqual(self.ready("central"), set())

    def test_it_waits_for_a_filter_in_a_group_too(self):
        self.apply("central", analysis("prep", status="running"))
        self.write(
            "blueprint.yaml",
            analysis("next", status="ready")
            + "needs:\n  - - central/prep\n    - 'pipeline: simpletestpipeline'\n",
        )
        apply_page("blueprint.yaml", event="s2", ledger=self.ledger)
        self.assertEqual(self.ready("s2"), set())

    def test_a_cycle_between_subjects_does_not_hang_and_holds_both(self):
        self.apply("s1", analysis("a", status="ready", needs=["s2/b"]))
        self.apply("s2", analysis("b", status="ready", needs=["s1/a"]))
        self.assertEqual(self.ready("s1"), set())
        self.assertEqual(self.ready("s2"), set())


class UnresolvedTests(CrossSubjectCase):
    """A qualified name which does not resolve waits, and says so."""

    def setUp(self):
        super().setUp()
        self.apply("central", analysis("prep"))

    def held(self, need):
        self.apply("s2", analysis("next", status="ready", needs=[need]))
        production = self.get("s2", "next")
        with patch("asimov.cli.manage.click.echo") as echo:
            held = report_unresolved_needs(production, self.logger)
        return production, held, [call.args[0] for call in echo.call_args_list]

    def test_a_misspelt_name_holds_it_back_without_strict_needs(self):
        production, held, messages = self.held("central/prep-typo")
        self.assertTrue(held)
        self.assertFalse(production.strict_needs)
        self.assertEqual(production.dependencies, [])
        self.assertIn("no analysis is named 'central/prep-typo'", messages[0])
        self.assertIn("not ready", messages[0])

    def test_a_subject_which_does_not_exist_holds_it_back(self):
        _, held, _ = self.held("nowhere/prep")
        self.assertTrue(held)

    def test_an_optional_one_does_not(self):
        self.write(
            "blueprint.yaml",
            analysis("next", status="ready")
            + "needs:\n  - optional: true\n    name: central/typo\n",
        )
        apply_page("blueprint.yaml", event="s2", ledger=self.ledger)
        production = self.get("s2", "next")
        self.assertFalse(report_unresolved_needs(production, self.logger))

    def test_an_old_style_entry_is_still_only_a_warning(self):
        _, held, messages = self.held("prep-typo")
        self.assertFalse(held)
        self.assertNotIn("not ready", messages[0])

    def test_it_resolves_once_the_analysis_exists(self):
        self.apply("central", analysis("prep-typo"))
        production, held, _ = self.held("central/prep-typo")
        self.assertFalse(held)
        self.assertEqual(production.dependencies, ["central/prep-typo"])


if __name__ == "__main__":
    unittest.main()
