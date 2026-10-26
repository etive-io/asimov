"""
A dataset step and a consumer step, both command analyses, run to the end by
``asimov monitor --chain --until-idle`` and the local scheduler (#236).

Nothing is faked: the first copies a file, the second reads what the first
declared through ``{inputs.data}`` and writes its own output.
"""
import os
import sys
import unittest

from tests.test_chain_until_idle_e2e import CLI, EndToEndCase

STEPS = """kind: analysis
name: raw-data
command: [cp, "{source}", data.txt]
outputs:
  data: data.txt
---
kind: analysis
name: fit
command:
  - {python}
  - -c
  - "import sys; open(sys.argv[2], 'w').write(open(sys.argv[1]).read().upper())"
  - "{{inputs.data}}"
  - "{{outputs.result}}"
outputs:
  result:
    path: result.txt
needs: [raw-data]
---
kind: analysis
name: broken
command: [{python}, -c, "import sys; sys.exit(3)"]
outputs:
  never: never.txt
"""


@unittest.skipUnless(os.path.exists(CLI), "the asimov command is not installed")
class CommandChainTests(EndToEndCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        source = os.path.join(cls.root, "source.txt")
        with open(source, "w") as handle:
            handle.write("raw data")
        cls.apply("kind: event\nname: EvA\ninterferometers: [H1]\n")
        # python is on the PATH of the environment which runs the tests
        cls.apply(STEPS.format(source=source, python=sys.executable.replace("\\", "/")), "EvA")
        cls.monitor = cls.run_cli(
            "monitor", "--chain", "--until-idle", "--interval", "1", "--timeout", "60",
            check=False,
        )

    def rundir(self, name):
        return os.path.join(self.root, "working", "EvA", name)

    def test_the_consumer_read_what_the_dataset_step_made(self):
        with open(os.path.join(self.rundir("fit"), "result.txt")) as handle:
            self.assertEqual(handle.read(), "RAW DATA")

    def test_both_are_complete(self):
        statuses = self.statuses()
        self.assertEqual(statuses["EvA/raw-data"], "complete")
        self.assertEqual(statuses["EvA/fit"], "complete")

    def test_a_command_which_fails_is_not_complete(self):
        self.assertNotEqual(self.statuses()["EvA/broken"], "complete")
        self.assertFalse(os.path.exists(os.path.join(self.rundir("broken"), "never.txt")))

    def test_the_wrapper_is_in_the_run_directory(self):
        self.assertTrue(os.path.exists(os.path.join(self.rundir("fit"), "command.sh")))
        with open(os.path.join(self.rundir("broken"), ".asimov-exit-status")) as handle:
            self.assertEqual(handle.read().strip(), "3")

    def test_the_build_did_not_log_an_error(self):
        self.assertNotIn("Traceback", self.monitor.stdout + self.monitor.stderr)
        self.assertNotIn("TemplateNotFound", self.monitor.stdout + self.monitor.stderr)


if __name__ == "__main__":
    unittest.main()
