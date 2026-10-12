"""
``asimov monitor --chain --until-idle`` runs a project to the end on its own (#233).

Nothing is faked: a real project is made with the command line, the local
scheduler runs the testing pipeline's jobs as processes (each takes a couple of
seconds), and one command carries a chain of dependent analyses, one of which is
in another subject, from ``ready`` to ``complete``. The command is the one which
a person without a scheduler would run, and each analysis is started when what
it needs has finished, not before.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CLI = os.path.join(os.path.dirname(sys.executable), "asimov")

EVENTS = """kind: event
name: EvA
interferometers: [H1]
---
kind: event
name: EvB
interferometers: [H1]
"""


def analysis(name, needs=()):
    text = f"kind: analysis\nname: {name}\npipeline: simpletestpipeline\nstatus: ready\n"
    if needs:
        text += "needs:\n" + "".join(f"  - {need}\n" for need in needs)
    return text


@unittest.skipUnless(os.path.exists(CLI), "the asimov command is not installed")
class EndToEndCase(unittest.TestCase):
    """A project, made with the command line and run by the local scheduler."""

    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()
        cls.root = tempfile.mkdtemp(prefix="asimov-e2e-")
        cls.env = dict(
            os.environ,
            GIT_AUTHOR_NAME="Test",
            GIT_AUTHOR_EMAIL="test@example.com",
            GIT_COMMITTER_NAME="Test",
            GIT_COMMITTER_EMAIL="test@example.com",
        )
        cls.run_cli("init", "End to end", "--root", cls.root)
        cls.run_cli("configuration", "update", "scheduler/type", "local")
        cls.run_cli("apply", "-f", os.path.join(HERE, "test_data", "testing_pe.yaml"))
        cls.apply(EVENTS)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    @classmethod
    def run_cli(cls, *arguments, timeout=240, check=True):
        result = subprocess.run(
            [CLI, *arguments], cwd=cls.root, env=cls.env, capture_output=True, text=True,
            timeout=timeout,
        )
        if check and result.returncode != 0:
            raise AssertionError(
                f"asimov {' '.join(arguments)} failed ({result.returncode}):\n"
                f"{result.stdout[-1500:]}\n{result.stderr[-1500:]}"
            )
        return result

    @classmethod
    def apply(cls, text, subject=None):
        path = os.path.join(cls.root, "blueprint.yaml")
        with open(path, "w") as handle:
            handle.write(text)
        arguments = ["apply", "-f", path] + (["-e", subject] if subject else [])
        cls.run_cli(*arguments)

    @classmethod
    def statuses(cls):
        script = (
            "import json; from asimov.monitor_api import get_analysis_status; "
            "print(json.dumps({k: str(v) for k, v in get_analysis_status().items()}))"
        )
        result = subprocess.run(
            [sys.executable, "-c", script], cwd=cls.root, env=cls.env, capture_output=True,
            text=True, timeout=120,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout.strip().splitlines()[-1])

    def results(self, subject, name):
        return os.path.join(self.root, "working", subject, name, "results.dat")


class ChainToTheEndTests(EndToEndCase):
    """a, then b, then c in one subject; d, in another subject, needs c."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.apply(analysis("a") + "---\n" + analysis("b", ["a"]) + "---\n" + analysis("c", ["b"]), "EvA")
        cls.apply(analysis("d", ["EvA/c"]), "EvB")
        cls.monitor = cls.run_cli(
            "monitor", "--chain", "--until-idle", "--interval", "1", "--timeout", "100",
            check=False,
        )

    def test_it_exits_cleanly_having_finished_everything(self):
        self.assertEqual(self.monitor.returncode, 0, self.monitor.stdout[-2000:] + self.monitor.stderr[-1000:])
        self.assertIn("everything finished", self.monitor.stdout)

    def test_every_analysis_is_complete(self):
        self.assertEqual(
            self.statuses(),
            {"EvA/a": "complete", "EvA/b": "complete", "EvA/c": "complete", "EvB/d": "complete"},
        )

    def test_every_job_ran(self):
        for subject, name in (("EvA", "a"), ("EvA", "b"), ("EvA", "c"), ("EvB", "d")):
            self.assertTrue(os.path.exists(self.results(subject, name)), f"{subject}/{name}")

    def test_each_job_ran_after_what_it_needs(self):
        """The jobs take a couple of seconds, so finishing in order is starting in order."""
        times = [
            os.path.getmtime(self.results(subject, name))
            for subject, name in (("EvA", "a"), ("EvA", "b"), ("EvA", "c"), ("EvB", "d"))
        ]
        self.assertEqual(times, sorted(times))
        # and not at once: each waited for the one before it to run (2 s)
        for earlier, later in zip(times, times[1:]):
            self.assertGreater(later - earlier, 1.0)

    def test_each_was_submitted_once(self):
        for name in ("EvA/a", "EvA/b", "EvA/c", "EvB/d"):
            self.assertEqual(self.monitor.stdout.count(f"Submitted {name}"), 1, name)

    def test_a_running_job_is_not_taken_for_an_evicted_one(self):
        """The list of jobs is read afresh on each pass; from the cache, what an
        earlier pass started was missing, and a pipeline would be resurrected."""
        self.assertNotIn("attempting a rescue", self.monitor.stdout)
        self.assertNotIn("is stuck", self.monitor.stdout)

    def test_the_passes_are_numbered(self):
        self.assertIn("Pass 1", self.monitor.stdout)
        self.assertIn("Idle after", self.monitor.stdout)


class BlockedTests(EndToEndCase):
    """What can never start is left, and said so."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.apply(analysis("ok"), "EvA")
        cls.apply(analysis("waits", ["EvA/no-such-analysis"]), "EvB")
        cls.monitor = cls.run_cli(
            "monitor", "--chain", "--until-idle", "--interval", "1", "--timeout", "100",
            check=False,
        )

    def test_it_exits_saying_not_everything_finished(self):
        self.assertEqual(self.monitor.returncode, 1, self.monitor.stdout[-2000:] + self.monitor.stderr[-1000:])
        self.assertIn("not everything finished", self.monitor.stdout)

    def test_what_could_run_did(self):
        statuses = self.statuses()
        self.assertEqual(statuses["EvA/ok"], "complete")
        self.assertNotEqual(statuses["EvB/waits"], "complete")
        self.assertFalse(os.path.exists(self.results("EvB", "waits")))


if __name__ == "__main__":
    unittest.main()
