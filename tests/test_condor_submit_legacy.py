"""
Regression tests for `asimov.condor._submit_job_legacy`.

When no schedd accepted the job (for example because a pool's submit
requirements rejected its accounting tag), the function returned an unbound
local, so the real reason was hidden behind an ``UnboundLocalError``.
"""

import configparser
import unittest
from unittest.mock import MagicMock, patch

from asimov import condor


class SubmitJobLegacyTests(unittest.TestCase):
    def setUp(self):
        # No condor/scheduler configured: go straight to the schedd search.
        config_patcher = patch.object(
            condor.config,
            "get",
            side_effect=configparser.NoOptionError("scheduler", "condor"),
        )
        config_patcher.start()
        self.addCleanup(config_patcher.stop)

    def _patch_htcondor(self, schedd):
        fake = MagicMock()
        fake.Submit.return_value = object()
        fake.Collector.return_value.locateAll.return_value = ["schedd-ad"]
        fake.Schedd.return_value = schedd
        patcher = patch.object(condor, "htcondor", fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_refusal_is_reported_not_hidden(self):
        schedd = MagicMock()
        schedd.submit.side_effect = condor._HTCondorIOError(
            "SCHEDD:2:Invalid value for search tag: ligo.dev.o4.cbc.pe.lalinference"
        )
        self._patch_htcondor(schedd)
        with self.assertRaises(RuntimeError) as raised:
            condor._submit_job_legacy({"executable": "/bin/true"})
        self.assertIn("Invalid value for search tag", str(raised.exception))

    def test_no_schedd_found_is_reported(self):
        self._patch_htcondor(MagicMock())
        condor.htcondor.Collector.return_value.locateAll.return_value = []
        with self.assertRaises(RuntimeError):
            condor._submit_job_legacy({"executable": "/bin/true"})

    def test_accepted_job_returns_cluster(self):
        schedd = MagicMock()
        schedd.submit.return_value.cluster.return_value = 1234
        self._patch_htcondor(schedd)
        self.assertEqual(condor._submit_job_legacy({"executable": "/bin/true"}), 1234)


if __name__ == "__main__":
    unittest.main()
