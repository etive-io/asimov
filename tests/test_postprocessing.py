# """These tests are designed to be run on all pipelines to ensure that
# they are generally compliant within asimov's specifications.  They can
# include checking that ini files have the correct information and that
# the pipelines report information as expected.
# """

# import os
# import io
# import unittest
# from unittest.mock import patch
# import shutil
# import git
# import contextlib

# from click.testing import CliRunner
# from importlib import reload

# import asimov.event
# from asimov.cli.project import make_project
# from asimov.cli.application import apply_page
# from asimov.ledger import YAMLLedger
# from asimov.pipelines import known_pipelines

# from asimov.testing import AsimovTestCase
# from asimov import config
# from asimov.utils import set_directory

# from asimov.cli import monitor

# class TestSimplePostProcessing(AsimovTestCase):

#     def event_setup(self):
#         f = io.StringIO()
#         with contextlib.redirect_stdout(f):

#             apply_page(
#                 f"{self.cwd}/tests/test_data/testing_pe.yaml",
#                 event=None,
#                 ledger=self.ledger,
#             )
#             apply_page(
#                 file=f"{self.cwd}/tests/test_data/testing_events.yaml",
#                 ledger=self.ledger,
#             )
#             apply_page(
#                 file=f"{self.cwd}/tests/test_data/test_analyses.yaml",
#                 ledger=self.ledger,
#             )
#             apply_page(
#                 file=f"{self.cwd}/tests/test_data/test_postprocessing.yaml",
#                 ledger=self.ledger,
#             )

#     def test_analysis_has_postprocesses(self):
#         self.event_setup()
#         post = self.ledger.get_event("GW150914_095045")[0].analyses[-1].postprocessing
#         self.assertEqual(len(post), 1)
            
#     def test_analysis_postprocess_stages(self):
#         self.event_setup()
#         post = self.ledger.get_event("GW150914_095045")[0].analyses[-1].postprocessing
#         self.assertEqual(len(post[0].stages), 2)

#     def test_analysis_postprocess_stages_into_pipelines(self):
#         self.event_setup()
#         post = self.ledger.get_event("GW150914_095045")[0].analyses[-1].postprocessing
#         self.assertEqual(post[0].stages[0].pipeline.name.lower(), "pesummary")

#     def test_analysis_postprocess_dag(self):
#         """Test that the DAG of analysis stages is created"""
#         self.event_setup()
#         # Mark the analysis as finished
#         os.chdir(f"{self.cwd}/tests/tmp/project")
#         reload(asimov)
#         analysis = asimov.current_ledger.get_event("GW150914_095045")[0].analyses[-1]
#         analysis.status = "finished"
#         asimov.current_ledger.update_event(analysis.event)
#         reload(asimov)
#         post = asimov.current_ledger.get_event("GW150914_095045")[0].analyses[-1].postprocessing
#         self.assertEqual(len(post[0]._stages_dag), 2)
#         self.assertEqual(len(post[0].next), 1)
#         self.assertEqual(post[0].next[0], "simple PE summary")
#         os.chdir(self.cwd)

#     @patch('asimov.pipelines.bilby.Bilby.samples')
#     def test_analysis_postprocess_run_next(self, mock_samples):
#         mock_samples.return_value = ["/home/test/samples"]
#         self.event_setup()
#         os.chdir(f"{self.cwd}/tests/tmp/project")
#         reload(asimov)
#         analysis = asimov.current_ledger.get_event("GW150914_095045")[0].analyses[-1]
#         analysis.status = "finished"
#         asimov.current_ledger.update_event(analysis.event)
#         reload(asimov)

#         post = asimov.current_ledger.get_event("GW150914_095045")[0].analyses[-1].postprocessing
#         f = io.StringIO()
#         with contextlib.redirect_stdout(f):

#             string = """'output': 'working/GW150914_095045/pesummary.out', 'error': 'working/GW150914_095045/pesummary.err', 'log': 'working/GW150914_095045/pesummary.log', 'request_cpus': 4, 'getenv': 'true', 'batch_name': 'Summary Pages/GW150914_095045', 'request_memory': '8192MB', 'should_transfer_files': 'YES', 'request_disk': '8192MB'"""

#             post[0].run_next(dryrun=True)
#             self.assertTrue(string in f.getvalue())
#         os.chdir(self.cwd)
        
#     @patch('asimov.pipelines.bilby.Bilby.samples')
#     def test_analysis_postprocess_run_mocked_samples(self, mock_samples):
#         mock_samples.return_value = ["/home/test/samples"]
#         self.event_setup()
#         os.chdir(f"{self.cwd}/tests/tmp/project")
#         reload(asimov)
#         analysis = asimov.current_ledger.get_event("GW150914_095045")[0].analyses[-1]
#         analysis.status = "finished"
#         asimov.current_ledger.update_event(analysis.event)
#         reload(asimov)

#         post = asimov.current_ledger.get_event("GW150914_095045")[0].analyses[-1].postprocessing
#         f = io.StringIO()
#         with contextlib.redirect_stdout(f):
#             post[0].run_next(dryrun=True)
#             self.assertTrue("--samples /home/test/samples" in f.getvalue())
#         os.chdir(self.cwd)

        
#     # Next we need to test that asimov monitor will actually start a post-processing job correctly.
#     @patch('asimov.condor.CondorJobList')
#     @patch('asimov.pipelines.bilby.Bilby.detect_completion')
#     @patch('asimov.pipelines.bilby.Bilby.collect_assets')
#     @patch('asimov.pipelines.bilby.Bilby.samples')
#     def test_analysis_postprocess_monitor_mocked_samples(self, mock_samples, mock_assets, mock_complete, mock_condor):
#         """Check that asimov monitor attempts to start a post-processing job"""

#         class MockJobList:
#             def __init__(self):
#                 pass
#             def refresh(self):
#                 return []
        
#         mock_samples.return_value = ["/home/test/samples"]
#         mock_assets.return_value = {"samples": "/home/test/samples"}
#         mock_complete.return_value = True
#         mock_condor.return_value = MockJobList()
#         self.event_setup()
#         os.chdir(f"{self.cwd}/tests/tmp/project")
#         runner = CliRunner()

#         reload(asimov)
#         reload(monitor)
#         # Mark the analysis as running
#         analysis = asimov.current_ledger.get_event("GW150914_095045")[0].analyses[-1]
#         analysis.status = "finished"
#         asimov.current_ledger.update_event(analysis.event)
#         reload(asimov)
#         analysis = asimov.current_ledger.get_event("GW150914_095045")[0].analyses[-1]

#         # Run the monitor
#         result = runner.invoke(monitor.monitor, "--dry-run")

#         os.chdir(self.cwd)
#         self.assertTrue("--samples /home/test/samples" in result.output)


# class TestEventPostProcessing(AsimovTestCase):

#     def event_setup(self):
# #        f = io.StringIO()
#  #       with contextlib.redirect_stdout(f):

#         apply_page(
#              f"{self.cwd}/tests/test_data/testing_pe.yaml",
#              event=None,
#              ledger=self.ledger,
#          )
#         apply_page(
#             file=f"{self.cwd}/tests/test_data/testing_events.yaml",
#             ledger=self.ledger,
#         )
#         apply_page(
#             file=f"{self.cwd}/tests/test_data/test_analyses.yaml",
#             ledger=self.ledger,
#         )
#         apply_page(
#             file=f"{self.cwd}/tests/test_data/test_postprocessing.yaml",
#             ledger=self.ledger,
#         )

#     def test_subject_has_postprocesses(self):
#         self.event_setup()
#         post = self.ledger.get_event("GW150914_095045")[0].postprocessing
#         self.assertEqual(len(post), 1)
        
#     def test_correct_analyses(self):
#         """Test that the correct analyses are returned."""
#         self.event_setup()
#         post = self.ledger.get_event("GW150914_095045")[0].postprocessing
#         self.assertEqual(str(list(post[0].analyses)[0].pipeline), "bilby")

#     def test_fresh_is_true_no_finished_analyses(self):
#         """Test that when no analyses are finished the job is not fresh"""
#         self.event_setup()
#         post_job = self.ledger.get_event("GW150914_095045")[0].postprocessing[0]
#         self.assertEqual(post_job.fresh, True)

#     # Next we need to test that asimov monitor will actually start a post-processing job correctly.
#     @patch('asimov.condor.CondorJobList')
#     @patch('asimov.pipelines.bilby.Bilby.detect_completion')
#     @patch('asimov.pipelines.bilby.Bilby.collect_assets')
#     @patch('asimov.pipelines.bilby.Bilby.samples')
#     def test_analysis_postprocess_monitor_mocked_samples(self, mock_samples, mock_assets, mock_complete, mock_condor):
#         """Check that asimov monitor attempts to start a post-processing job"""

#         class MockJobList:
#             def __init__(self):
#                 pass
#             def refresh(self):
#                 return []
        
#         mock_samples.return_value = ["/home/test/samples"]
#         mock_complete.return_value = True
#         mock_condor.return_value = MockJobList()
#         self.event_setup()
#         os.chdir(f"{self.cwd}/tests/tmp/project")
#         runner = CliRunner()

#         reload(asimov)
#         reload(monitor)
#         # Mark the analysis as running
#         analysis = asimov.current_ledger.get_event("GW150914_095045")[0].analyses[-1]
#         analysis.status = "finished"
#         asimov.current_ledger.get_event("GW150914_095045")[0].analyses[-1].status = "finished"
#         asimov.current_ledger.update_event(analysis.event)

#         reload(asimov)
#         reload(monitor)
                
#         # Run the monitor
#         result = runner.invoke(monitor.monitor, "--dry-run")
#         os.chdir(self.cwd)
#         self.assertTrue("--samples /home/test/samples /home/test/samples" in result.output) 

#     # Next we need to test that asimov monitor will actually start a post-processing job correctly.
#     @patch('asimov.condor.CondorJobList')
#     @patch('asimov.pipelines.bilby.Bilby.detect_completion')
#     @patch('asimov.pipelines.bilby.Bilby.collect_assets')
#     @patch('asimov.pipelines.bilby.Bilby.samples')
#     def test_analysis_postprocess_only_ready(self, mock_samples, mock_assets, mock_complete, mock_condor):
#         """Check that asimov monitor attempts to start a post-processing job only if one of the analyses is ready"""

#         class MockJobList:
#             def __init__(self):
#                 pass
#             def refresh(self):
#                 return []
        
#         mock_samples.return_value = ["/home/test/samples"]
#         #mock_assets.return_value = {"samples": "/home/test/samples"}
#         mock_complete.return_value = True
#         mock_condor.return_value = MockJobList()
#         self.event_setup()
#         os.chdir(f"{self.cwd}/tests/tmp/project")
#         runner = CliRunner()

#         reload(asimov)
#         reload(monitor)
#         # Mark the analysis as running
#         analysis = asimov.current_ledger.get_event("GW150914_095045")[0].analyses[-1]
#         analysis.status = "finished"
#         asimov.current_ledger.get_event("GW150914_095045")[0].analyses[-1].status = "finished"
#         asimov.current_ledger.update_event(analysis.event)

#         reload(asimov)
#         reload(monitor)
#         result = runner.invoke(monitor.monitor, "--dry-run")
#         os.chdir(self.cwd)
#         self.assertTrue("--samples /home/test/samples /home/test/samples" in result.output) 
