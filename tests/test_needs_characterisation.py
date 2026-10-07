"""
Characterisation tests for how ``needs:`` resolves today (#231).

#231 lets ``needs:`` reach analyses in other subjects of the same project. Its
compatibility rules say that every existing ledger must keep its meaning, so
these tests pin what resolution does *before* that change: which analyses are
candidates for each kind of analysis, which forms of entry parse, what an entry
which matches nothing does, and what is stored and serialised.

They describe present behaviour, including some which is odd (a ``subject:``
key is a metadata lookup, an unresolvable name is silently dropped). If one of
them fails after a change, that change altered an existing ledger's meaning and
the failure is the thing to look at, not the test.
"""
import os
import shutil
import tempfile
import unittest

import yaml

from asimov.analysis import ProjectAnalysis, SimpleAnalysis, SubjectAnalysis
from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.ledger import YAMLLedger

EVENT = "kind: event\nname: {name}\ninterferometers: [H1]\n"


def analysis(name, pipeline="simpletestpipeline", status="finished", needs=None, extra=""):
    text = f"kind: analysis\nname: {name}\npipeline: {pipeline}\nstatus: {status}\n"
    if needs is not None:
        text += "needs:\n" + "".join(f"  - {need}\n" for need in needs)
    return text + extra


class CharacterisationCase(unittest.TestCase):
    """A scratch project with two subjects, ``EvA`` and ``EvB``."""

    def setUp(self):
        self.cwd = os.getcwd()
        self.root = tempfile.mkdtemp()
        os.chdir(self.root)
        make_project(name="Test project", root=self.root, engine="yamlfile")
        self.ledger = YAMLLedger(".asimov/ledger.yml")
        for name in ("EvA", "EvB"):
            self.write("event.yaml", EVENT.format(name=name))
            apply_page("event.yaml", ledger=self.ledger)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, name, text):
        with open(name, "w") as handle:
            handle.write(text)

    def apply(self, event, *blueprints):
        self.write("blueprint.yaml", "---\n".join(blueprints))
        apply_page("blueprint.yaml", event=event, ledger=self.ledger)

    def apply_project(self, text):
        self.write("project.yaml", text)
        apply_page("project.yaml", ledger=self.ledger)

    def get(self, event, name):
        """One analysis, read fresh from the ledger."""
        found = [
            a for a in YAMLLedger(".asimov/ledger.yml").get_event(event)[0].analyses
            if a.name == name
        ]
        self.assertEqual(len(found), 1, f"{event}/{name}")
        return found[0]

    def project_analysis(self, name):
        return [
            a for a in YAMLLedger(".asimov/ledger.yml").project_analyses if a.name == name
        ][0]


class PoolSelectionTests(CharacterisationCase):
    """Which analyses a ``needs:`` entry is matched against."""

    def setUp(self):
        super().setUp()
        self.apply("EvA", analysis("shared"), analysis("only-a"))
        self.apply("EvB", analysis("shared"), analysis("only-b"))

    def test_simple_analysis_matches_in_its_own_subject_only(self):
        self.apply(
            "EvA",
            analysis("consumer", needs=["shared", "only-a", "only-b"], status="ready"),
        )
        consumer = self.get("EvA", "consumer")
        self.assertIsInstance(consumer, SimpleAnalysis)
        self.assertEqual(consumer.dependencies, ["only-a", "shared"])
        # ``shared`` exists in both subjects and ``only-b`` only in EvB, which is
        # not a candidate.
        self.assertEqual(consumer.unresolved_needs, ["no analysis is named 'only-b'"])

    def test_a_filter_is_matched_in_its_own_subject_only(self):
        self.apply("EvA", analysis("consumer", needs=["'pipeline: simpletestpipeline'"], status="ready"))
        consumer = self.get("EvA", "consumer")
        # EvB's two analyses use the same pipeline and are not included.
        self.assertEqual(consumer.dependencies, ["only-a", "shared"])

    def subject_analysis(self, **spec):
        """A subject analysis (made by giving ``analyses:``) in EvA."""
        extra = "".join(
            f"{key}:\n" + "".join(f"  - 'name: {name}'\n" for name in names)
            for key, names in spec.items()
        )
        self.apply(
            "EvA",
            analysis("combined", pipeline="subjecttestpipeline", status="ready", extra=extra),
        )
        combined = self.get("EvA", "combined")
        self.assertIsInstance(combined, SubjectAnalysis)
        return combined

    def test_subject_analysis_resolves_its_spec_in_its_own_subject_only(self):
        combined = self.subject_analysis(analyses=["only-a", "only-b", "shared"])
        self.assertEqual(sorted(a.name for a in combined.analyses), ["only-a", "shared"])
        self.assertEqual({a.event.name for a in combined.analyses}, {"EvA"})

    def test_subject_analysis_has_no_needs_of_its_own(self):
        """Its ``needs`` is its ``analyses:`` spec, and takes precedence over it,
        and it has no graph dependencies."""
        combined = self.subject_analysis(needs=["only-a"], analyses=["shared"])
        self.assertEqual([a.name for a in combined.analyses], ["only-a"])
        self.assertEqual(combined.dependencies, [])
        self.assertEqual(combined._needs, [])

    def test_project_analysis_matches_in_its_declared_subjects(self):
        self.apply_project(
            "kind: projectanalysis\nname: both\npipeline: simpletestpipeline\n"
            "subjects: [EvA, EvB]\nneeds:\n  - only-a\n  - only-b\n  - shared\nstatus: ready\n"
        )
        project = self.project_analysis("both")
        self.assertIsInstance(project, ProjectAnalysis)
        # A name which is in both subjects appears once for each of them, so
        # the list holds names rather than analyses, and cannot say which is which.
        self.assertEqual(sorted(project.dependencies), ["only-a", "only-b", "shared", "shared"])

    def test_project_analysis_does_not_look_outside_its_declared_subjects(self):
        self.apply_project(
            "kind: projectanalysis\nname: just-a\npipeline: simpletestpipeline\n"
            "subjects: [EvA]\nneeds:\n  - only-a\n  - only-b\nstatus: ready\n"
        )
        self.assertEqual(self.project_analysis("just-a").dependencies, ["only-a"])


class ParsingFormTests(CharacterisationCase):
    """The forms of entry which ``needs:`` accepts."""

    def setUp(self):
        super().setUp()
        self.apply(
            "EvA",
            analysis("fit-1", status="finished", extra="comment: first\n"),
            analysis("fit-2", status="running"),
            analysis("fit-3", pipeline="simpletestpipelineb", status="finished"),
        )

    def needs(self, entries):
        """The dependencies of an analysis in EvA with this ``needs`` list."""
        self.apply("EvA", analysis("consumer", needs=entries, status="ready"))
        return self.get("EvA", "consumer").dependencies

    def test_plain_name(self):
        self.assertEqual(self.needs(["fit-2"]), ["fit-2"])

    def test_attribute_and_value_in_a_string(self):
        self.assertEqual(self.needs(["'status: finished'"]), ["fit-1", "fit-3"])

    def test_single_key_dict(self):
        self.assertEqual(self.needs(["status: finished"]), ["fit-1", "fit-3"])

    def test_negation(self):
        self.assertEqual(self.needs(["'status: !finished'"]), ["fit-2"])

    def test_top_level_entries_are_or_ed(self):
        self.assertEqual(self.needs(["fit-1", "fit-2"]), ["fit-1", "fit-2"])

    def test_a_nested_list_is_and_ed(self):
        self.write(
            "blueprint.yaml",
            analysis("consumer", status="ready")
            + "needs:\n  - - 'status: finished'\n    - 'pipeline: simpletestpipeline'\n",
        )
        apply_page("blueprint.yaml", event="EvA", ledger=self.ledger)
        self.assertEqual(self.get("EvA", "consumer").dependencies, ["fit-1"])

    def test_optional_entries_still_resolve(self):
        self.write(
            "blueprint.yaml",
            analysis("consumer", status="ready")
            + "needs:\n  - optional: true\n    name: fit-2\n  - fit-1\n",
        )
        apply_page("blueprint.yaml", event="EvA", ledger=self.ledger)
        consumer = self.get("EvA", "consumer")
        self.assertEqual(consumer.dependencies, ["fit-1", "fit-2"])
        # But an optional entry is not a *required* one.
        self.assertEqual(len(consumer.required_dependencies), 1)

    def test_an_analysis_does_not_depend_on_itself(self):
        self.assertEqual(self.needs(["consumer", "fit-1"]), ["fit-1"])


class UnmatchedEntryTests(CharacterisationCase):
    """An entry which matches nothing is silently no dependency at all."""

    def setUp(self):
        super().setUp()
        self.apply("EvA", analysis("fit-1"), analysis("consumer", needs=["fit-1", "no-such-name"], status="ready"))
        self.event = YAMLLedger(".asimov/ledger.yml").get_event("EvA")[0]
        self.consumer = [a for a in self.event.analyses if a.name == "consumer"][0]

    def test_it_is_no_dependency(self):
        self.assertEqual(self.consumer.dependencies, ["fit-1"])

    def test_it_is_no_graph_edge(self):
        self.event.update_graph()
        edges = {(a.name, b.name) for a, b in self.event.graph.edges}
        self.assertEqual(edges, {("fit-1", "consumer")})

    def test_an_analysis_whose_only_need_is_unmatched_has_no_dependency(self):
        self.apply("EvA", analysis("lonely", needs=["no-such-name"], status="ready"))
        lonely = self.get("EvA", "lonely")
        self.assertEqual(lonely.dependencies, [])
        self.assertEqual(lonely.unresolved_needs, ["no analysis is named 'no-such-name'"])
        # ...and so nothing in the graph holds it back.
        self.assertEqual(list(lonely.event.graph.predecessors(lonely)), [])

    def test_a_property_filter_matching_nothing_is_the_same(self):
        self.apply("EvA", analysis("filtered", needs=["'pipeline: nosuchpipeline'"], status="ready"))
        self.assertEqual(self.get("EvA", "filtered").dependencies, [])


class SlashInNameTests(CharacterisationCase):
    """A name containing ``/`` is just a name today."""

    def setUp(self):
        super().setUp()
        self.apply("EvA", analysis("EvB/fit"), analysis("consumer", needs=["EvB/fit"], status="ready"))
        self.apply("EvB", analysis("fit"))

    def test_it_resolves_as_a_literal_name_in_the_subject(self):
        self.assertEqual(self.get("EvA", "consumer").dependencies, ["EvB/fit"])

    def test_it_is_not_read_as_subject_and_name(self):
        # EvB has an analysis called ``fit``; the entry does not reach it.
        self.assertNotIn("fit", self.get("EvA", "consumer").dependencies)

    def test_without_the_literal_name_it_matches_nothing(self):
        self.apply("EvA", analysis("other", needs=["EvB/fit-missing"], status="ready"))
        self.assertEqual(self.get("EvA", "other").dependencies, [])


class SubjectKeyTests(CharacterisationCase):
    """``subject:`` is not a keyword today; it is a lookup in the analysis metadata.

    A blueprint cannot set it (``subject`` is already an argument when an
    analysis is built, so the blueprint is refused), so these set it on the
    objects directly.
    """

    def setUp(self):
        super().setUp()
        self.apply("EvA", analysis("tagged"), analysis("untagged"))
        self.apply("EvB", analysis("tagged-b"))
        self.apply("EvA", analysis("consumer", needs=["'subject: central'"], status="ready"))
        self.consumer = self.get("EvA", "consumer")
        for name in ("tagged", "untagged"):
            self.consumer.event.analysis_by_name(name)
        self.consumer.event.analysis_by_name("tagged").meta["subject"] = "central"

    def test_a_blueprint_cannot_set_it(self):
        with self.assertRaises(TypeError):
            self.apply("EvA", analysis("bad", extra="subject: central\n"))

    def test_it_matches_a_metadata_key_of_that_name(self):
        self.assertEqual(self.consumer.dependencies, ["tagged"])

    def test_it_does_not_match_the_name_of_the_subject(self):
        self.consumer.event.analysis_by_name("untagged").meta["subject"] = "other"
        self.consumer._needs = ["subject: EvA"]
        self.assertEqual(self.consumer.dependencies, [])

    def test_it_does_not_reach_other_subjects(self):
        other = YAMLLedger(".asimov/ledger.yml").get_event("EvB")[0].analysis_by_name("tagged-b")
        other.meta["subject"] = "central"
        self.assertEqual(self.consumer.dependencies, ["tagged"])


class ResolvedDependenciesTests(CharacterisationCase):
    """What is stored as ``resolved_dependencies`` and what makes an analysis stale."""

    def setUp(self):
        super().setUp()
        self.apply(
            "EvA",
            analysis("fit-1"),
            analysis("fit-2"),
            analysis("consumer", needs=["fit-1", "fit-2"], status="ready"),
        )

    def test_it_holds_bare_names(self):
        consumer = self.get("EvA", "consumer")
        consumer.resolved_dependencies = consumer.dependencies
        self.assertEqual(consumer.resolved_dependencies, ["fit-1", "fit-2"])

    def test_not_stale_before_it_has_run(self):
        self.assertIsNone(self.get("EvA", "consumer").resolved_dependencies)
        self.assertFalse(self.get("EvA", "consumer").is_stale)

    def test_not_stale_while_the_names_are_unchanged(self):
        consumer = self.get("EvA", "consumer")
        consumer.resolved_dependencies = ["fit-1", "fit-2"]
        self.assertFalse(consumer.is_stale)

    def test_stale_when_the_dependencies_differ(self):
        consumer = self.get("EvA", "consumer")
        consumer.resolved_dependencies = ["fit-1"]
        self.assertTrue(consumer.is_stale)

    def test_the_order_does_not_matter(self):
        consumer = self.get("EvA", "consumer")
        consumer.resolved_dependencies = ["fit-2", "fit-1"]
        self.assertFalse(consumer.is_stale)


class RoundTripTests(CharacterisationCase):
    """``needs`` goes into the ledger as written, and comes back unchanged."""

    WRITTEN = ["fit-1", "status: finished", "review: !approved"]

    def setUp(self):
        super().setUp()
        self.apply(
            "EvA",
            analysis("fit-1"),
            analysis(
                "consumer",
                needs=["fit-1", "'status: finished'", "'review: !approved'"],
                status="ready",
            ),
        )

    def stored_needs(self, name):
        with open(".asimov/ledger.yml") as handle:
            stored = yaml.safe_load(handle)
        for event in stored["events"]:
            for production in event.get("productions", []):
                if name in production:
                    return production[name]["needs"]

    def test_to_dict_gives_the_needs_as_written(self):
        consumer = self.get("EvA", "consumer")
        self.assertEqual(consumer.to_dict()["consumer"]["needs"], self.WRITTEN)

    def test_a_nested_list_and_a_dict_are_kept(self):
        self.write(
            "blueprint.yaml",
            analysis("rich", status="ready")
            + "needs:\n  - - 'status: finished'\n    - 'pipeline: simpletestpipeline'\n"
            "  - optional: true\n    name: fit-1\n",
        )
        apply_page("blueprint.yaml", event="EvA", ledger=self.ledger)
        expected = [
            ["status: finished", "pipeline: simpletestpipeline"],
            {"optional": True, "name": "fit-1"},
        ]
        self.assertEqual(self.get("EvA", "rich").to_dict()["rich"]["needs"], expected)
        self.assertEqual(self.stored_needs("rich"), expected)

    def test_it_is_the_same_in_the_ledger_file(self):
        self.assertEqual(self.stored_needs("consumer"), self.WRITTEN)

    def test_writing_the_event_back_changes_nothing(self):
        ledger = YAMLLedger(".asimov/ledger.yml")
        ledger.update_event(ledger.get_event("EvA")[0])
        self.assertEqual(self.stored_needs("consumer"), self.WRITTEN)
        self.assertEqual(self.get("EvA", "consumer")._needs, self.WRITTEN)

    def test_a_project_analysis_keeps_its_needs_too(self):
        """``ProjectAnalysis.to_dict`` sets ``needs`` to the resolved names, then
        the copy of its metadata overwrites that with what was written."""
        self.apply_project(
            "kind: projectanalysis\nname: pa\npipeline: simpletestpipeline\n"
            "subjects: [EvA]\nneeds:\n  - 'status: finished'\nstatus: ready\n"
        )
        project = self.project_analysis("pa")
        self.assertEqual(project.dependencies, ["fit-1"])
        self.assertEqual(project.to_dict()["needs"], ["status: finished"])


if __name__ == "__main__":
    unittest.main()
