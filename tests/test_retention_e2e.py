"""
Retention, run for real (#237): a project is run to the end by the monitor on the
local scheduler, and then pruned with the command line.
"""
import os
import subprocess
import sys
import unittest

from tests.test_chain_until_idle_e2e import CLI, EndToEndCase

BLUEPRINT = """kind: analysis
name: gen
command: [{python}, -c, "open('big.dat','wb').write(b'x'*200000); open('final.txt','w').write('answer')"]
outputs:
  big: {{path: big.dat, retention: until_consumed}}
  final: {{path: final.txt, retention: keep}}
---
kind: analysis
name: use
command: [{python}, -c, "import sys; open(sys.argv[2],'w').write(str(len(open(sys.argv[1],'rb').read())))", "{{inputs.big}}", "{{outputs.size}}"]
outputs:
  size: size.txt
needs: [gen]
"""


@unittest.skipUnless(os.path.exists(CLI), "the asimov command is not installed")
class RetentionEndToEndTests(EndToEndCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.apply(BLUEPRINT.format(python=sys.executable.replace("\\", "/")), "EvA")
        cls.monitor = cls.run_cli(
            "monitor", "--chain", "--until-idle", "--interval", "1", "--timeout", "90", check=False
        )

    def gen(self, name):
        return os.path.join(self.root, "working", "EvA", "gen", name)

    def test_it_ran_to_the_end_and_the_consumer_read_the_output(self):
        self.assertEqual(self.monitor.returncode, 0, self.monitor.stdout[-1500:])
        with open(os.path.join(self.root, "working", "EvA", "use", "size.txt")) as handle:
            self.assertEqual(handle.read(), "200000")

    def test_the_sizes_were_recorded_when_it_finished(self):
        result = self.run_cli("analysis", "du")
        self.assertIn("EvA/gen", result.stdout)
        self.assertIn("200.0 kB outputs", result.stdout)

    def test_prune_releases_the_intermediate_and_keeps_the_rest(self):
        # (in order: what these tests do to the project is not independent)
        dry = self.run_cli("analysis", "prune", "--dry-run")
        self.assertIn("Release 1 outputs", dry.stdout)
        self.assertTrue(os.path.exists(self.gen("big.dat")))

        real = self.run_cli("analysis", "prune", "--yes")
        self.assertIn("Released 1 outputs", real.stdout)
        self.assertFalse(os.path.exists(self.gen("big.dat")))
        self.assertTrue(os.path.exists(self.gen("final.txt")))

        again = self.run_cli("analysis", "prune", "--yes")
        self.assertIn("Nothing to release", again.stdout)

        refused = self.run_cli("analysis", "rerun", "EvA", "use", "--yes", check=False)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("EvA/use needs big of EvA/gen", refused.stderr + refused.stdout)

        after = self.run_cli("analysis", "du")
        self.assertIn("200.0 kB released", after.stdout)
        self.assertEqual(self.statuses()["EvA/gen"], "complete")


if __name__ == "__main__":
    unittest.main()
