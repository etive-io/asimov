import unittest
from unittest.mock import MagicMock, patch

import asimov
import asimov.condor
from asimov.scheduler import HTCondor as HTCondorScheduler


class CondorTests(unittest.TestCase):

# @classmethod
#     def setUpClass(cls):
#         cls.app = app = asimov.server.create_app()
#         app.config.update({
#         "TESTING": True,
#         })
#         cls.client = cls.app.test_client()


    def test_job_from_dict(self):
        """Check that a CondorJob object can be created from a dictionary."""

        dictionary = {"id": 450,
                      "command": "test.sh",
                      "hosts": "test.test.com",
                      "status": 1}

        job = asimov.condor.CondorJob.from_dict(dictionary)

        self.assertEqual(job.idno, 450)

    def test_status(self):
        """Check that status codes get translated to a human-readable string."""
        dictionary = {"id": 450,
                      "command": "test.sh",
                      "hosts": "test.test.com",
                      "status": 1}

        job = asimov.condor.CondorJob.from_dict(dictionary)

        self.assertEqual(job.status, "Idle")


class CollectHistoryTests(unittest.TestCase):
    """Tests for the collect_history functionality."""

    def _make_job_ad(self, completion_date=1700000000, entered_status=1700000000,
                     cpus_provisioned=4.0, gpus_provisioned=2.0,
                     remote_wall_clock=7200.0, suspension_time=0.0):
        """Return a mock HTCondor ClassAd dict for a completed job."""
        ad = {
            "CompletionDate": completion_date,
            "EnteredCurrentStatus": entered_status,
            "CpusProvisioned": cpus_provisioned,
            "GpusProvisioned": gpus_provisioned,
            "RemoteWallClockTime": remote_wall_clock,
            "CumulativeSuspensionTime": suspension_time,
            "MaxHosts": 1,
        }
        # Simulate ClassAd __getitem__ / get behaviour with a dict subclass
        mock_ad = MagicMock()
        mock_ad.__getitem__ = MagicMock(side_effect=lambda k: ad[k])
        mock_ad.get = lambda k, default=None: ad.get(k, default)
        return mock_ad

    def test_collect_history_from_configured_schedd(self):
        """collect_history returns correct data when the configured schedd has history."""
        job_ad = self._make_job_ad(
            completion_date=1700000000,
            cpus_provisioned=4.0,
            gpus_provisioned=0.0,
            remote_wall_clock=3600.0,
            suspension_time=0.0,
        )

        scheduler = HTCondorScheduler(schedd_name=None)
        mock_schedd = MagicMock()
        mock_schedd.history.return_value = [job_ad]
        scheduler._schedd = mock_schedd

        result = scheduler.collect_history(12345)

        self.assertIn("runtime", result)
        self.assertAlmostEqual(result["runtime"], 3600.0)
        self.assertAlmostEqual(result["cpus"], 4.0)
        self.assertAlmostEqual(result["gpus"], 0.0)
        self.assertIn("end", result)

    def test_collect_history_falls_back_to_other_schedds(self):
        """collect_history searches other schedds when the primary returns nothing."""
        job_ad = self._make_job_ad(
            completion_date=1700000000,
            cpus_provisioned=2.0,
            gpus_provisioned=1.0,
            remote_wall_clock=1800.0,
            suspension_time=600.0,
        )

        scheduler = HTCondorScheduler(schedd_name=None)
        # Primary schedd returns empty list
        mock_primary_schedd = MagicMock()
        mock_primary_schedd.history.return_value = []
        scheduler._schedd = mock_primary_schedd

        # Fallback schedd returns the job
        mock_fallback_schedd = MagicMock()
        mock_fallback_schedd.history.return_value = [job_ad]

        with patch("asimov.scheduler.htcondor") as mock_htcondor:
            mock_htcondor.Collector.return_value.locateAll.return_value = [MagicMock()]
            mock_htcondor.Schedd.return_value = mock_fallback_schedd
            mock_htcondor.HTCondorLocateError = Exception
            mock_htcondor.HTCondorIOError = Exception

            result = scheduler.collect_history(12345)

        # runtime = 1800 - 600 = 1200
        self.assertAlmostEqual(result["runtime"], 1200.0)
        self.assertAlmostEqual(result["cpus"], 2.0)
        self.assertAlmostEqual(result["gpus"], 1.0)

    def test_collect_history_raises_when_no_history(self):
        """collect_history raises ValueError when no history is found anywhere."""
        scheduler = HTCondorScheduler(schedd_name=None)
        mock_schedd = MagicMock()
        mock_schedd.history.return_value = []
        scheduler._schedd = mock_schedd

        with patch("asimov.scheduler.htcondor") as mock_htcondor:
            mock_htcondor.Collector.return_value.locateAll.return_value = []
            mock_htcondor.HTCondorLocateError = Exception
            mock_htcondor.HTCondorIOError = Exception

            with self.assertRaises(ValueError):
                scheduler.collect_history(99999)

    def test_collect_history_uses_request_cpus_when_provisioned_missing(self):
        """collect_history falls back to RequestCpus when CpusProvisioned is absent."""
        ad = {
            "CompletionDate": 1700000000,
            "EnteredCurrentStatus": 1700000000,
            "RemoteWallClockTime": 900.0,
            "CumulativeSuspensionTime": 0.0,
            "RequestCpus": 8,
            "RequestGpus": 0,
        }
        mock_ad = MagicMock()
        mock_ad.get = lambda k, default=None: ad.get(k, default)

        # Raise KeyError for CpusProvisioned / GpusProvisioned, return dict values otherwise
        def getitem_missing_provisioned(k):
            if k in ("CpusProvisioned", "GpusProvisioned"):
                raise KeyError(k)
            return ad[k]

        mock_ad.__getitem__ = MagicMock(side_effect=getitem_missing_provisioned)

        scheduler = HTCondorScheduler(schedd_name=None)
        mock_schedd = MagicMock()
        mock_schedd.history.return_value = [mock_ad]
        scheduler._schedd = mock_schedd

        result = scheduler.collect_history(12345)
        self.assertAlmostEqual(result["cpus"], 8.0)
        self.assertAlmostEqual(result["gpus"], 0.0)

    def test_condor_collect_history_delegates_to_scheduler(self):
        """asimov.condor.collect_history delegates to the HTCondor scheduler."""
        expected = {"end": "2023-01-01", "cpus": 4.0, "gpus": 0.0, "runtime": 3600.0}

        with patch("asimov.condor.HTCondorScheduler") as MockScheduler:
            mock_instance = MagicMock()
            mock_instance.collect_history.return_value = expected
            MockScheduler.return_value = mock_instance

            result = asimov.condor.collect_history(12345)

        self.assertEqual(result, expected)
        mock_instance.collect_history.assert_called_once_with(12345)
