"""
A vertical slice (#241): a generated, cross-subject graph, run to the end.

``toy-rounds`` (a strategy which exists only under ``ASIMOV_TESTING``) makes
rounds of steps in two components and a ``shared`` subject which combines them,
so needs cross subjects in both directions. The graph is made by ``asimov
apply`` and run by ``asimov monitor --chain --until-idle`` on the local
scheduler; this checks that the features which each have their own tests work
together.
"""
import json
import os
import subprocess
import sys
import unittest

from tests.test_chain_until_idle_e2e import CLI, EndToEndCase

BLUEPRINT = """kind: analysis
name: toy
strategy:
  type: toy-rounds
  components: [A, B]
  rounds: {rounds}
{extra}"""

STEPS = ("component-A", "component-B")


def names(rounds):
    return {
        (subject, name)
        for r in range(1, rounds + 1)
        for subject, name in (
            [(s, f"step-r{r}") for s in STEPS] + [("shared", f"combine-r{r}")]
        )
    }


DUMP = """
import json
from asimov.context import active_ledger as ledger
from asimov.strategies import read_group
found = {}
for subject in ledger.subject_names():
    for analysis in ledger.get_event(subject)[0].productions:
        found[subject + "/" + analysis.name] = {
            "strategy": analysis.meta.get("strategy"),
            "needs": analysis.meta.get("needs"),
        }
print(json.dumps({"analyses": found, "group": read_group(ledger, "toy")}, sort_keys=True))
"""


@unittest.skipUnless(os.path.exists(CLI), "the asimov command is not installed")
class SliceCase(EndToEndCase):
    @classmethod
    def setUpClass(cls):
        os.environ["ASIMOV_TOY_STRATEGY"] = "1"  # (read by the commands run below)
        super().setUpClass()
        cls.env["ASIMOV_TOY_STRATEGY"] = "1"

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("ASIMOV_TOY_STRATEGY", None)
        super().tearDownClass()

    def dump(self):
        result = subprocess.run(
            [sys.executable, "-c", DUMP], cwd=self.root, env=self.env, capture_output=True,
            text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-1500:])
        return json.loads(result.stdout.strip().splitlines()[-1])

    def applied(self):
        return {tuple(key.split("/")) for key in self.dump()["analyses"]}

    def blueprint(self, rounds=3, extra=""):
        return BLUEPRINT.format(rounds=rounds, extra=extra)


class RunToTheEndTests(SliceCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.apply(cls.blueprint(cls, 3))
        cls.monitor = cls.run_cli(
            "monitor", "--chain", "--until-idle", "--interval", "1", "--timeout", "150",
            check=False,
        )

    def test_the_graph_is_what_the_strategy_made(self):
        self.assertEqual(set(self.applied()), names(3))

    def test_it_finishes_everything(self):
        self.assertEqual(self.monitor.returncode, 0, self.monitor.stdout[-2000:] + self.monitor.stderr[-1000:])
        self.assertEqual(
            set(self.statuses().values()), {"complete"}, self.statuses()
        )
        self.assertEqual(len(self.statuses()), len(names(3)))

    def test_a_round_never_starts_before_the_combination_before_it(self):
        mtime = lambda subject, name: os.path.getmtime(self.results(subject, name))
        for r in (2, 3):
            combined = mtime("shared", f"combine-r{r - 1}")
            for subject in STEPS:
                self.assertGreater(mtime(subject, f"step-r{r}"), combined, f"{subject} r{r}")
        for r in (1, 2, 3):
            for subject in STEPS:
                self.assertGreater(mtime("shared", f"combine-r{r}"), mtime(subject, f"step-r{r}"))

    def test_every_analysis_is_stamped_with_the_group_and_it_survives_a_round_trip(self):
        for key, analysis in self.dump()["analyses"].items():
            self.assertEqual(analysis["strategy"], {"type": "toy-rounds", "id": "toy"}, key)

    def test_the_group_is_recorded(self):
        self.assertEqual(self.dump()["group"]["type"], "toy-rounds")


class ApplyingAgainTests(SliceCase):
    def snapshot(self):
        return self.dump()

    def test_the_same_blueprint_changes_nothing_and_more_rounds_add_only_the_new_ones(self):
        self.apply(self.blueprint(2))
        before = self.snapshot()
        self.apply(self.blueprint(2))
        self.assertEqual(self.snapshot(), before)

        self.apply(self.blueprint(3))
        self.assertEqual(set(self.applied()), names(3))

    def test_a_dry_run_creates_nothing(self):
        before = self.snapshot()
        path = os.path.join(self.root, "dry.yaml")
        with open(path, "w") as handle:
            handle.write(BLUEPRINT.format(rounds=5, extra="").replace("name: toy", "name: dry"))
        self.run_cli("apply", "--dry-run", "-f", path)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(any(subject == "shared" and name.endswith("r5") for subject, name in self.applied()))


class BadGraphTests(SliceCase):
    def test_a_cycle_in_the_emitted_documents_is_reported_and_never_runs(self):
        """Applying reports a cycle as an error (#231) and does not refuse it; nothing in it can start."""
        path = os.path.join(self.root, "cycle.yaml")
        with open(path, "w") as handle:
            handle.write(BLUEPRINT.format(rounds=2, extra="  cycle: true\n").replace("name: toy", "name: cyclic"))
        result = self.run_cli("apply", "-f", path, check=False)
        self.assertIn("cycle", result.stdout + result.stderr)
        monitor = self.run_cli(
            "monitor", "--chain", "--until-idle", "--interval", "1", "--timeout", "30", check=False
        )
        self.assertEqual(monitor.returncode, 1)
        self.assertFalse(os.path.exists(self.results("shared", "combine-r1")))
        self.assertFalse(os.path.exists(self.results("component-A", "step-r2")))

    def test_a_dangling_reference_waits_and_says_so(self):
        text = (
            "kind: analysis\nname: lost\npipeline: simpletestpipeline\nstatus: ready\n"
            "needs:\n  - shared/combine-r99\n"
        )
        path = os.path.join(self.root, "lost.yaml")
        with open(path, "w") as handle:
            handle.write(text)
        self.run_cli("apply", "-f", path, "-e", "shared")
        monitor = self.run_cli(
            "monitor", "--chain", "--until-idle", "--interval", "1", "--timeout", "60", check=False
        )
        self.assertEqual(monitor.returncode, 1)
        self.assertFalse(os.path.exists(self.results("shared", "lost")))


if __name__ == "__main__":
    unittest.main()
