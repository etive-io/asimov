"""
Looking an analysis up by name uses an index on the event, not a scan (#242).

The index must never change what ``needs`` resolves to, so most of these tests
compare it with a plain scan of the subject.
"""
import copy
import os
import random
import shutil
import unittest
from unittest.mock import patch

from asimov.analysis import Analysis
from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.ledger import YAMLLedger

EVENT = "GW150914_095045"

BLUEPRINT = "---\n".join(
    f"""kind: analysis
name: a{n}
pipeline: {"simpletestpipeline" if n % 2 == 0 else "simpletestpipelineb"}
status: {["ready", "finished", "running"][n % 3]}
"""
    for n in range(8)
)


def scan(analysis, requirement):
    """The analyses matching one parsed requirement, found by scanning the subject."""
    conditions = requirement if isinstance(requirement, list) else [requirement]
    matches = list(analysis.event.analyses)
    for parsed in conditions:
        attribute, match, negate = parsed[:3]
        matches = [a for a in matches if a.matches_filter(attribute, match, negate)]
    return matches


def scanned_dependencies(analysis, needs):
    """What ``dependencies`` gave before there was an index."""
    found = set()
    for requirement in analysis._process_dependencies(copy.deepcopy(needs)):
        found |= set(scan(analysis, requirement))
    return [a.name for a in sorted(found, key=lambda a: a.name) if a.name != analysis.name]


class NameIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.cwd)

    def setUp(self):
        self.root = f"{self.cwd}/tests/tmp/name_index_project"
        os.makedirs(self.root)
        os.chdir(self.root)
        make_project(name="Test project", root=self.root, engine="yamlfile")
        self.ledger = YAMLLedger(".asimov/ledger.yml")
        apply_page(file=f"{self.cwd}/tests/test_data/testing_pe.yaml", event=None, ledger=self.ledger)
        apply_page(file=f"{self.cwd}/tests/test_data/events_blueprint.yaml", ledger=self.ledger)
        with open("blueprint.yaml", "w") as handle:
            handle.write(BLUEPRINT)
        apply_page(file="blueprint.yaml", event=EVENT, ledger=self.ledger)
        self.event = self.ledger.get_event(EVENT)[0]
        self.by_name = {p.name: p for p in self.event.productions}

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    # The index itself

    def test_it_finds_an_analysis_by_name(self):
        self.assertIs(self.event.analysis_by_name("a3"), self.by_name["a3"])

    def test_an_unknown_name_gives_none(self):
        self.assertIsNone(self.event.analysis_by_name("nothing"))

    def test_it_follows_add_production(self):
        self.event.analysis_by_name("a0")  # builds the index
        new = copy.copy(self.by_name["a0"])
        new.name = "added"
        self.event.add_production(new)
        self.assertIs(self.event.analysis_by_name("added"), new)

    def test_it_follows_remove_production(self):
        self.event.analysis_by_name("a0")
        self.event.remove_production(self.by_name["a0"])
        self.assertIsNone(self.event.analysis_by_name("a0"))
        self.assertNotIn(self.by_name["a0"], self.event.graph)
        self.assertIs(self.event.analysis_by_name("a1"), self.by_name["a1"])

    def test_it_notices_a_change_made_to_the_list_directly(self):
        self.event.analysis_by_name("a0")
        self.event.productions.remove(self.by_name["a0"])
        self.assertIsNone(self.event.analysis_by_name("a0"))

    # What needs resolves to

    def test_a_plain_name_does_not_scan_the_subject(self):
        analysis = self.by_name["a7"]
        analysis._needs = ["a2"]
        with patch.object(Analysis, "matches_filter", autospec=True,
                          side_effect=Analysis.matches_filter) as matches:
            self.assertEqual(analysis.dependencies, ["a2"])
        self.assertLessEqual(matches.call_count, 1)

    def test_an_unknown_name_is_still_no_dependency(self):
        analysis = self.by_name["a7"]
        analysis._needs = ["nothing"]
        self.assertEqual(analysis.dependencies, [])

    def test_a_dependency_on_itself_is_still_dropped(self):
        analysis = self.by_name["a7"]
        analysis._needs = ["a7", "a1"]
        self.assertEqual(analysis.dependencies, ["a1"])

    def test_a_name_in_an_and_group_still_has_the_other_conditions_applied(self):
        analysis = self.by_name["a7"]
        # a1 is "finished" and uses simpletestpipelineb
        analysis._needs = [[{"name": "a1"}, {"status": "ready"}]]
        self.assertEqual(analysis.dependencies, [])
        analysis._needs = [[{"name": "a1"}, {"status": "finished"}]]
        self.assertEqual(analysis.dependencies, ["a1"])

    def test_a_negated_name_is_not_looked_up(self):
        analysis = self.by_name["a7"]
        analysis._needs = [{"name": "!a1"}]
        self.assertEqual(analysis.dependencies, [f"a{n}" for n in (0, 2, 3, 4, 5, 6)])

    def test_the_index_agrees_with_a_scan_for_random_needs(self):
        names = [f"a{n}" for n in range(8)] + ["nothing", "A1"]
        pipelines = ["simpletestpipeline", "simpletestpipelineb", "bilby"]
        statuses = ["ready", "finished", "running", "stuck"]

        def condition(rng):
            kind = rng.choice(["name", "name", "pipeline", "status"])
            value = {"name": names, "pipeline": pipelines, "status": statuses}[kind]
            value = rng.choice(value)
            if rng.random() < 0.2:
                value = "!" + value
            return {kind: value}

        def entry(rng):
            shape = rng.random()
            if shape < 0.5:
                return condition(rng)
            if shape < 0.8:
                return [condition(rng) for _ in range(rng.randint(2, 3))]
            return {"optional": True, **condition(rng)}

        rng = random.Random(244)
        analysis = self.by_name["a7"]
        for _ in range(400):
            needs = [entry(rng) for _ in range(rng.randint(1, 4))]
            analysis._needs = needs
            self.assertEqual(analysis.dependencies, scanned_dependencies(analysis, needs), needs)
            for requirement in analysis._process_dependencies(copy.deepcopy(needs)):
                self.assertEqual(
                    {a.name for a in analysis._requirement_matches(requirement)},
                    {a.name for a in scan(analysis, requirement)},
                    needs,
                )


if __name__ == "__main__":
    unittest.main()
