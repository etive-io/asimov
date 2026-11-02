"""
Retries and skipping, run for real (#240): ``asimov monitor --chain --until-idle``
with the local scheduler and commands which fail.
"""
import os
import sys
import unittest

from tests.test_chain_until_idle_e2e import CLI, EndToEndCase

FLAKY = """import os, sys
counter, output = sys.argv[1], sys.argv[2]
n = int(open(counter).read()) if os.path.exists(counter) else 0
open(counter, "w").write(str(n + 1))
if n < 2:
    sys.exit(1)
open(output, "w").write("worked after %d failures" % n)
"""

BLUEPRINT = """kind: analysis
name: flaky
command: [{python}, {script}, {counter}, "{{outputs.result}}"]
outputs:
  result: result.txt
retry:
  attempts: 4
  deterministic attempts: 4
---
kind: analysis
name: after-flaky
command: [cat, "{{inputs.result}}"]
needs: [flaky]
---
kind: analysis
name: doomed
command: [{python}, -c, "import sys; sys.exit(7)"]
outputs:
  never: never.txt
retry:
  attempts: 2
  deterministic attempts: 2
on failure: skip
---
kind: analysis
name: carries-on
command: [echo, carrying on]
needs: [doomed]
---
kind: analysis
name: stays-stuck
command: [{python}, -c, "import sys; sys.exit(9)"]
outputs:
  never: never.txt
---
kind: analysis
name: waits-for-it
command: [echo, never]
needs: [stays-stuck]
"""


@unittest.skipUnless(os.path.exists(CLI), "the asimov command is not installed")
class RetryEndToEndTests(EndToEndCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        script = os.path.join(cls.root, "flaky.py")
        with open(script, "w") as handle:
            handle.write(FLAKY)
        counter = os.path.join(cls.root, "counter.txt")
        cls.apply(
            BLUEPRINT.format(python=sys.executable.replace("\\", "/"), script=script, counter=counter),
            "EvA",
        )
        cls.monitor = cls.run_cli(
            "monitor", "--chain", "--until-idle", "--interval", "1", "--timeout", "200",
            check=False,
        )
        cls.state = cls.statuses()

    def test_a_flaky_command_is_tried_again_until_it_works(self):
        self.assertEqual(self.state["EvA/flaky"], "complete")
        with open(os.path.join(self.root, "working", "EvA", "flaky", "result.txt")) as handle:
            self.assertEqual(handle.read(), "worked after 2 failures")

    def test_what_needs_it_runs_after_it_has_worked(self):
        self.assertEqual(self.state["EvA/after-flaky"], "complete")

    def test_a_command_which_always_fails_is_skipped_after_its_attempts(self):
        self.assertEqual(self.state["EvA/doomed"], "skipped")

    def test_what_needs_a_skipped_analysis_goes_ahead(self):
        self.assertEqual(self.state["EvA/carries-on"], "complete")
        self.assertIn("needs doomed, which was skipped", self.monitor.stdout)

    def test_with_no_policy_a_failure_is_stuck_and_what_needs_it_waits(self):
        self.assertEqual(self.state["EvA/stays-stuck"], "stuck")
        self.assertEqual(self.state["EvA/waits-for-it"], "ready")
        self.assertFalse(os.path.exists(os.path.join(self.root, "working", "EvA", "waits-for-it", ".asimov-exit-status")))

    def test_the_run_says_not_everything_finished(self):
        self.assertEqual(self.monitor.returncode, 1, self.monitor.stdout[-2000:])
        self.assertIn("not everything finished", self.monitor.stdout)

    def test_each_attempt_was_started_once(self):
        self.assertEqual(self.monitor.stdout.count("Submitted EvA/flaky"), 3)
        self.assertEqual(self.monitor.stdout.count("Submitted EvA/doomed"), 2)
        self.assertEqual(self.monitor.stdout.count("Submitted EvA/stays-stuck"), 1)

    def test_the_failures_are_recorded(self):
        import subprocess, json

        script = (
            "import json; from asimov.context import active_ledger as l;"
            "print(json.dumps({p.name: p.meta.get('attempts', []) for p in l.get_event('EvA')[0].productions}))"
        )
        result = subprocess.run(
            [sys.executable, "-c", script], cwd=self.root, env=self.env, capture_output=True, text=True, timeout=120
        )
        attempts = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(len(attempts["flaky"]), 2)
        self.assertEqual(len(attempts["doomed"]), 2)
        self.assertEqual(attempts["stays-stuck"], [])
        self.assertEqual(attempts["flaky"][0]["kind"], "deterministic")


if __name__ == "__main__":
    unittest.main()
