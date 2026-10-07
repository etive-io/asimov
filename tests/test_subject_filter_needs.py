"""
``subject:`` is a filter in ``needs:`` and ``analyses:`` (#231).

Without it the pool is the analysis's own subject. Naming a subject, with
``subject: name``, makes the pool that subject; ``subject: "*"`` or a negated
one (``"!noise"``) makes it every subject. Every other condition still applies
inside the pool, and ``subject:`` narrows, as the others do, inside a
``ProjectAnalysis``'s subjects.
"""
import logging
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from asimov.analysis import ProjectAnalysis, SubjectAnalysis
from asimov.cli.application import apply_page
from asimov.cli.manage import report_unresolved_needs
from asimov.cli.project import make_project
from asimov.ledger import YAMLLedger

EVENT = "kind: event\nname: {name}\ninterferometers: [H1]\n"


def analysis(name, status="finished", needs=None, analyses=None, pipeline="simpletestpipeline"):
    text = f"kind: analysis\nname: {name}\npipeline: {pipeline}\nstatus: {status}\n"
    for key, entries in (("needs", needs), ("analyses", analyses)):
        if entries is not None:
            text += f"{key}:\n" + "".join(f"  - {entry}\n" for entry in entries)
    return text


def group(*conditions):
    """An AND group, as the text of one entry of a list."""
    return "- " + "\n    - ".join(f"'{condition}'" for condition in conditions)


class SubjectFilterCase(unittest.TestCase):
    """``central`` and three streams, each with a fit in two rounds."""

    def setUp(self):
        self.cwd = os.getcwd()
        self.root = tempfile.mkdtemp()
        os.chdir(self.root)
        make_project(name="Test project", root=self.root, engine="yamlfile")
        self.ledger = YAMLLedger(".asimov/ledger.yml")
        for name in ("central", "s1", "s2", "noise"):
            self.write("event.yaml", EVENT.format(name=name))
            apply_page("event.yaml", ledger=self.ledger)
        for stream in ("s1", "s2", "noise"):
            self.apply(stream, analysis("fit-r1"), analysis("fit-r2", status="running"))
        self.apply("central", analysis("prep"))
        self.logger = logging.getLogger("test_subject_filter_needs")

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, name, text):
        with open(name, "w") as handle:
            handle.write(text)

    def apply(self, event, *blueprints):
        self.write("blueprint.yaml", "---\n".join(blueprints))
        apply_page("blueprint.yaml", event=event, ledger=self.ledger)

    def event(self, name):
        return YAMLLedger(".asimov/ledger.yml").get_event(name)[0]

    def needs(self, *entries, event="central"):
        """The dependencies of a new analysis with these ``needs``."""
        self.write(
            "blueprint.yaml",
            analysis("consumer", status="ready") + "needs:\n" + "".join(f"  - {e}\n" for e in entries),
        )
        apply_page("blueprint.yaml", event=event, ledger=self.ledger)
        return self.event(event).analysis_by_name("consumer")


class SubjectFilterTests(SubjectFilterCase):
    def test_a_named_subject_is_the_pool(self):
        consumer = self.needs("subject: s1")
        self.assertEqual(consumer.dependencies, ["s1/fit-r1", "s1/fit-r2"])

    def test_the_other_conditions_apply_inside_it(self):
        consumer = self.needs(group("subject: s1", "status: finished"))
        self.assertEqual(consumer.dependencies, ["s1/fit-r1"])

    def test_a_star_is_every_subject(self):
        consumer = self.needs(group("subject: *", "name: fit-r1"))
        self.assertEqual(
            consumer.dependencies, ["noise/fit-r1", "s1/fit-r1", "s2/fit-r1"]
        )

    def test_a_negation_is_every_other_subject_this_one_included(self):
        consumer = self.needs(group("subject: !noise", "status: finished"))
        # ``prep`` is in this subject (central), so is a bare name.
        self.assertEqual(consumer.dependencies, ["prep", "s1/fit-r1", "s2/fit-r1"])

    def test_a_negation_leaves_out_this_subject_if_it_is_named(self):
        # ``central`` is in the pool, but nothing in it is finished and named fit.
        consumer = self.needs(group("subject: !s1", "status: running", "name: fit-r2"))
        self.assertEqual(consumer.dependencies, ["noise/fit-r2", "s2/fit-r2"])

    def test_the_subject_of_the_analysis_itself_is_a_name_like_any_other(self):
        self.apply("central", analysis("prep-2"))
        consumer = self.needs(group("subject: central", "name: prep"))
        # In its own subject, so a bare name.
        self.assertEqual(consumer.dependencies, ["prep"])

    def test_several_subject_conditions_narrow(self):
        consumer = self.needs(group("subject: s1", "subject: !s1"))
        self.assertEqual(consumer.dependencies, [])

    def test_without_it_the_pool_is_still_its_own_subject(self):
        consumer = self.needs("'status: finished'")
        self.assertEqual(consumer.dependencies, ["prep"])

    def test_a_property_in_the_metadata_still_works_across_subjects(self):
        self.apply("s2", analysis("tagged"))
        consumer = self.needs(group("subject: *", "name: tagged"))
        self.assertEqual(consumer.dependencies, ["s2/tagged"])

    def test_it_waits_for_what_it_matches(self):
        consumer = self.needs(group("subject: s1", "status: running"))
        self.assertEqual(consumer.foreign_dependencies_unfinished, ["s1/fit-r2"])
        self.assertNotIn("consumer", {a.name for a in self.event("central").get_all_latest()})

    def test_it_runs_when_all_of_them_have_finished(self):
        consumer = self.needs(group("subject: s1", "status: finished"))
        self.assertIn("consumer", {a.name for a in self.event("central").get_all_latest()})

    def test_it_is_stored_as_written(self):
        consumer = self.needs(group("subject: s1", "status: finished"))
        self.assertEqual(
            consumer.to_dict()["consumer"]["needs"], [["subject: s1", "status: finished"]]
        )

    def test_it_matches_nothing_and_holds_the_analysis_back(self):
        consumer = self.needs("- subject: nowhere")
        self.assertEqual(consumer.dependencies, [])
        with patch("asimov.cli.manage.click.echo") as echo:
            held = report_unresolved_needs(consumer, self.logger)
        self.assertTrue(held)
        self.assertIn("not ready", echo.call_args_list[0].args[0])

    def test_an_optional_one_which_matches_nothing_does_not(self):
        self.write(
            "blueprint.yaml",
            analysis("consumer", status="ready")
            + "needs:\n  - optional: true\n    subject: nowhere\n",
        )
        apply_page("blueprint.yaml", event="central", ledger=self.ledger)
        consumer = self.event("central").analysis_by_name("consumer")
        self.assertFalse(report_unresolved_needs(consumer, self.logger))


class SubjectAnalysisFilterTests(SubjectFilterCase):
    def combine(self, *entries):
        self.write(
            "blueprint.yaml",
            analysis("combined", status="ready", pipeline="subjecttestpipeline")
            + "analyses:\n" + "".join(f"  - {e}\n" for e in entries),
        )
        apply_page("blueprint.yaml", event="central", ledger=self.ledger)
        found = self.event("central").analysis_by_name("combined")
        self.assertIsInstance(found, SubjectAnalysis)
        return found

    def test_it_combines_every_stream_which_exists(self):
        combined = self.combine(group("subject: *", "name: fit-r1"))
        self.assertEqual(
            sorted((a.event.name, a.name) for a in combined.analyses),
            [("noise", "fit-r1"), ("s1", "fit-r1"), ("s2", "fit-r1")],
        )
        self.assertTrue(combined.source_analyses_ready())

    def test_it_is_not_ready_while_one_is_running(self):
        combined = self.combine(group("subject: !noise", "name: fit-r2"))
        self.assertEqual(len(combined.analyses), 2)
        self.assertFalse(combined.source_analyses_ready())

    def test_a_new_stream_is_combined_and_makes_it_stale(self):
        combined = self.combine(group("subject: !noise", "name: fit-r1"))
        combined.resolved_dependencies = ["s1/fit-r1", "s2/fit-r1"]
        self.assertFalse(combined.is_stale)
        self.write("event.yaml", EVENT.format(name="s3"))
        apply_page("event.yaml", ledger=self.ledger)
        self.apply("s3", analysis("fit-r1"))
        combined = self.event("central").analysis_by_name("combined")
        combined.resolved_dependencies = ["s1/fit-r1", "s2/fit-r1"]
        self.assertTrue(combined.is_stale)
        self.assertEqual(
            sorted(combined._qualified_name(a) for a in combined.analyses),
            ["s1/fit-r1", "s2/fit-r1", "s3/fit-r1"],
        )


class ProjectAnalysisFilterTests(SubjectFilterCase):
    def project_analysis(self, subjects, *entries):
        self.write(
            "project.yaml",
            f"kind: projectanalysis\nname: pa\npipeline: simpletestpipeline\n"
            f"subjects: [{', '.join(subjects)}]\nstatus: ready\nneeds:\n"
            + "".join(f"  - {e}\n" for e in entries),
        )
        apply_page("project.yaml", ledger=self.ledger)
        found = [p for p in YAMLLedger(".asimov/ledger.yml").project_analyses if p.name == "pa"]
        self.assertIsInstance(found[0], ProjectAnalysis)
        return found[0]

    def test_it_narrows_within_the_declared_subjects(self):
        project = self.project_analysis(["s1", "s2"], "subject: s1")
        self.assertEqual(sorted(project.dependencies), ["fit-r1", "fit-r2"])

    def test_it_never_widens_them(self):
        project = self.project_analysis(["s1"], "subject: s2")
        self.assertEqual(project.dependencies, [])

    def test_a_star_is_all_of_its_subjects(self):
        project = self.project_analysis(["s1", "s2"], "subject: '*'")
        self.assertEqual(len(project.dependencies), 4)


if __name__ == "__main__":
    unittest.main()
