"""
Unit tests for the monitor state machine implementation.
"""

import unittest
from unittest.mock import Mock, patch


from asimov.monitor_states import (
    MonitorState,
    ReadyState,
    StopState,
    RunningState,
    FinishedState,
    ProcessingState,
    StuckState,
    StoppedState,
    get_state_handler,
    register_state,
    discover_custom_states,
    STATE_REGISTRY,
)
from asimov.monitor_context import MonitorContext


class TestStateRegistry(unittest.TestCase):
    """Test the state registry and handler lookup."""
    
    def test_get_state_handler_ready(self):
        """Test getting handler for ready state."""
        handler = get_state_handler("ready")
        self.assertIsInstance(handler, ReadyState)
    
    def test_get_state_handler_running(self):
        """Test getting handler for running state."""
        handler = get_state_handler("running")
        self.assertIsInstance(handler, RunningState)
    
    def test_get_state_handler_case_insensitive(self):
        """Test that state lookup is case insensitive."""
        handler1 = get_state_handler("READY")
        handler2 = get_state_handler("ready")
        self.assertEqual(type(handler1), type(handler2))
    
    def test_get_state_handler_unknown(self):
        """Test getting handler for unknown state returns None."""
        handler = get_state_handler("unknown_state")
        self.assertIsNone(handler)
    
    def test_all_states_registered(self):
        """Test that all expected states are in the registry."""
        expected_states = [
            "ready", "stop", "running", "finished", 
            "processing", "stuck", "stopped"
        ]
        for state in expected_states:
            self.assertIn(state, STATE_REGISTRY)
    
    def test_get_state_handler_with_pipeline(self):
        """Test getting pipeline-specific state handler."""
        # Create a custom state
        class CustomRunningState(MonitorState):
            @property
            def state_name(self):
                return "running"
            
            def handle(self, context):
                return True
        
        # Create a mock pipeline with custom handlers
        mock_pipeline = Mock()
        mock_pipeline.name = "test_pipeline"
        mock_pipeline.get_state_handlers = Mock(return_value={
            "running": CustomRunningState()
        })
        
        # Get handler with pipeline
        handler = get_state_handler("running", pipeline=mock_pipeline)
        
        # Should be the custom handler
        self.assertIsInstance(handler, CustomRunningState)
    
    def test_get_state_handler_pipeline_fallback(self):
        """Test that handler falls back to default when pipeline has no custom handler."""
        # Create a mock pipeline with no custom handler for 'ready'
        mock_pipeline = Mock()
        mock_pipeline.name = "test_pipeline"
        mock_pipeline.get_state_handlers = Mock(return_value={
            "running": Mock()  # Has custom running, but not ready
        })
        
        # Get handler for 'ready' with pipeline
        handler = get_state_handler("ready", pipeline=mock_pipeline)
        
        # Should fall back to default ReadyState
        self.assertIsInstance(handler, ReadyState)
    
    def test_get_state_handler_pipeline_error(self):
        """Test that errors in pipeline.get_state_handlers() are handled gracefully."""
        # Create a mock pipeline that raises an error
        mock_pipeline = Mock()
        mock_pipeline.name = "test_pipeline"
        mock_pipeline.get_state_handlers = Mock(side_effect=Exception("Test error"))
        
        # Should fall back to default without raising
        handler = get_state_handler("running", pipeline=mock_pipeline)
        self.assertIsInstance(handler, RunningState)


class TestPluginSystem(unittest.TestCase):
    """Test the plugin system for custom states."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Save the original registry
        self.original_registry = STATE_REGISTRY.copy()
    
    def tearDown(self):
        """Restore the original registry."""
        STATE_REGISTRY.clear()
        STATE_REGISTRY.update(self.original_registry)
    
    def test_register_state(self):
        """Test registering a custom state."""
        class CustomState(MonitorState):
            @property
            def state_name(self):
                return "custom"
            
            def handle(self, context):
                return True
        
        custom = CustomState()
        register_state(custom)
        
        self.assertIn("custom", STATE_REGISTRY)
        self.assertEqual(STATE_REGISTRY["custom"], custom)
    
    def test_register_state_invalid_type(self):
        """Test that registering non-MonitorState raises TypeError."""
        with self.assertRaises(TypeError):
            register_state("not a state")
    
    def test_register_state_overwrites_warning(self):
        """Test that overwriting existing state logs warning."""
        class CustomReady(MonitorState):
            @property
            def state_name(self):
                return "ready"
            
            def handle(self, context):
                return True
        
        with patch('asimov.monitor_states.logger') as mock_logger:
            register_state(CustomReady())
            mock_logger.warning.assert_called_once()
    
    @patch('asimov.monitor_states.entry_points')
    def test_discover_custom_states(self, mock_entry_points):
        """Test discovering custom states via entry points."""
        # Create a mock custom state
        class MockCustomState(MonitorState):
            @property
            def state_name(self):
                return "mock_custom"
            
            def handle(self, context):
                return True
        
        # Mock entry point
        mock_ep = Mock()
        mock_ep.name = "mock_custom"
        mock_ep.value = "test.states:MockCustomState"
        mock_ep.load.return_value = MockCustomState
        
        mock_entry_points.return_value = [mock_ep]
        
        # Clear registry before discovery
        STATE_REGISTRY.clear()
        STATE_REGISTRY.update(self.original_registry)
        
        # Discover states
        discover_custom_states()
        
        # Check that custom state was registered
        self.assertIn("mock_custom", STATE_REGISTRY)
    
    @patch('asimov.monitor_states.entry_points')
    def test_discover_custom_states_instance(self, mock_entry_points):
        """Test discovering custom states that return instances."""
        class MockCustomState(MonitorState):
            @property
            def state_name(self):
                return "mock_instance"
            
            def handle(self, context):
                return True
        
        # Mock entry point that returns an instance
        mock_instance = MockCustomState()
        mock_ep = Mock()
        mock_ep.name = "mock_instance"
        mock_ep.value = "test.states:custom_state_instance"
        mock_ep.load.return_value = mock_instance
        
        mock_entry_points.return_value = [mock_ep]
        
        STATE_REGISTRY.clear()
        STATE_REGISTRY.update(self.original_registry)
        
        discover_custom_states()
        
        self.assertIn("mock_instance", STATE_REGISTRY)
        self.assertEqual(STATE_REGISTRY["mock_instance"], mock_instance)
    
    @patch('asimov.monitor_states.entry_points')
    def test_discover_custom_states_error_handling(self, mock_entry_points):
        """Test that errors in loading custom states are handled gracefully."""
        # Mock entry point that raises an error
        mock_ep = Mock()
        mock_ep.name = "broken_state"
        mock_ep.load.side_effect = ImportError("Module not found")
        
        mock_entry_points.return_value = [mock_ep]
        
        # Should not raise an exception
        with patch('asimov.monitor_states.logger') as mock_logger:
            discover_custom_states()
            mock_logger.warning.assert_called()


class TestMonitorContext(unittest.TestCase):
    """Test the MonitorContext class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.analysis = Mock()
        self.analysis.name = "test_analysis"
        self.analysis.meta = {"scheduler": {"job id": "12345"}}
        self.analysis.event = Mock()
        self.analysis.event.name = "GW150914"
        
        self.job_list = Mock()
        self.job_list.jobs = {"12345": Mock()}
        self.job_list.refresh = Mock()
        
        self.ledger = Mock()
        self.ledger.update_event = Mock()
        self.ledger.update_analysis_in_project_analysis = Mock()
        self.ledger.save = Mock()
        
        self.context = MonitorContext(
            analysis=self.analysis,
            job_list=self.job_list,
            ledger=self.ledger,
            dry_run=False,
            analysis_path="GW150914/test_analysis"
        )
    
    def test_job_id_retrieval(self):
        """Test that job_id property returns correct ID."""
        self.assertEqual(self.context.job_id, "12345")
    
    def test_job_id_missing(self):
        """Test job_id when scheduler metadata is missing."""
        self.analysis.meta = {}
        self.assertIsNone(self.context.job_id)
    
    def test_has_condor_job(self):
        """Test has_condor_job returns True when job ID exists."""
        self.assertTrue(self.context.has_condor_job())
    
    def test_has_condor_job_missing(self):
        """Test has_condor_job returns False when job ID is missing."""
        self.analysis.meta = {}
        context = MonitorContext(self.analysis, self.job_list, self.ledger)
        self.assertFalse(context.has_condor_job())
    
    def test_clear_job_id(self):
        """Test clearing the job ID."""
        self.context.clear_job_id()
        self.assertIsNone(self.analysis.meta["scheduler"]["job id"])
    
    def test_update_ledger_event_analysis(self):
        """Test ledger update for event analysis."""
        self.context.update_ledger()
        self.ledger.update_event.assert_called_once_with(self.analysis.event)
        self.ledger.save.assert_called_once()
    
    def test_update_ledger_project_analysis(self):
        """Test ledger update for project analysis."""
        # Remove event attribute to simulate project analysis
        delattr(self.analysis, 'event')
        self.context.update_ledger()
        self.ledger.update_analysis_in_project_analysis.assert_called_once_with(
            self.analysis
        )
        self.ledger.save.assert_called_once()
    
    def test_update_ledger_dry_run(self):
        """Test that ledger is not updated in dry run mode."""
        context = MonitorContext(
            self.analysis, self.job_list, self.ledger, dry_run=True
        )
        context.update_ledger()
        self.ledger.update_event.assert_not_called()
        self.ledger.save.assert_not_called()
    
    def test_refresh_job_list(self):
        """Test refreshing job list."""
        self.context.refresh_job_list()
        self.job_list.refresh.assert_called_once()
    
    def test_refresh_job_list_dry_run(self):
        """Test that job list is not refreshed in dry run mode."""
        context = MonitorContext(
            self.analysis, self.job_list, self.ledger, dry_run=True
        )
        context.refresh_job_list()
        self.job_list.refresh.assert_not_called()


class TestReadyState(unittest.TestCase):
    """Test the ReadyState handler."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.analysis = Mock()
        self.analysis.name = "test_analysis"
        self.analysis.status = "ready"
        self.analysis.event = Mock()
        self.analysis.event.name = "GW150914"
        
        self.context = Mock(spec=MonitorContext)
        self.context.analysis = self.analysis
        self.context.analysis_path = "GW150914/test_analysis"
        
        self.state = ReadyState()
    
    def test_state_name(self):
        """Test state name property."""
        self.assertEqual(self.state.state_name, "ready")
    
    @patch('asimov.monitor_states.click.secho')
    def test_handle_ready_state(self, mock_secho):
        """Test handling ready state."""
        result = self.state.handle(self.context)
        self.assertTrue(result)
        mock_secho.assert_called_once()


class TestStopState(unittest.TestCase):
    """Test the StopState handler."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.analysis = Mock()
        self.analysis.name = "test_analysis"
        self.analysis.status = "stop"
        self.analysis.pipeline = Mock()
        self.analysis.pipeline.eject_job = Mock()
        
        self.context = Mock(spec=MonitorContext)
        self.context.analysis = self.analysis
        self.context.analysis_path = "GW150914/test_analysis"
        self.context.dry_run = False
        self.context.update_ledger = Mock()
        
        self.state = StopState()
    
    def test_state_name(self):
        """Test state name property."""
        self.assertEqual(self.state.state_name, "stop")
    
    @patch('asimov.monitor_states.click.secho')
    def test_handle_stop_state(self, mock_secho):
        """Test handling stop state."""
        result = self.state.handle(self.context)
        self.assertTrue(result)
        self.analysis.pipeline.eject_job.assert_called_once()
        self.assertEqual(self.analysis.status, "stopped")
        self.context.update_ledger.assert_called_once()
    
    @patch('asimov.monitor_states.click.echo')
    def test_handle_stop_state_dry_run(self, mock_echo):
        """Test handling stop state in dry run mode."""
        self.context.dry_run = True
        result = self.state.handle(self.context)
        self.assertTrue(result)
        self.analysis.pipeline.eject_job.assert_not_called()
        self.context.update_ledger.assert_not_called()


class TestRunningState(unittest.TestCase):
    """Test the RunningState handler."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.analysis = Mock()
        self.analysis.name = "test_analysis"
        self.analysis.status = "running"
        self.analysis.meta = {"scheduler": {"job id": "12345"}}
        self.analysis.pipeline = Mock()
        self.analysis.pipeline.while_running = Mock()
        self.analysis.pipeline.detect_completion = Mock(return_value=False)
        
        self.job = Mock()
        self.job.status = "running"
        
        self.context = Mock(spec=MonitorContext)
        self.context.analysis = self.analysis
        self.context.job = self.job
        self.context.job_id = "12345"
        self.context.analysis_path = "GW150914/test_analysis"
        self.context.dry_run = False
        self.context.has_condor_job = Mock(return_value=True)
        self.context.update_ledger = Mock()
        self.context.refresh_job_list = Mock()
        
        self.state = RunningState()
    
    def test_state_name(self):
        """Test state name property."""
        self.assertEqual(self.state.state_name, "running")
    
    @patch('asimov.monitor_states.click.echo')
    def test_handle_running_job(self, mock_echo):
        """Test handling a running condor job."""
        self.job.status = "running"
        result = self.state.handle(self.context)
        self.assertTrue(result)
        self.analysis.pipeline.while_running.assert_called_once()
        self.context.update_ledger.assert_called_once()
    
    @patch('asimov.monitor_states.click.echo')
    def test_handle_idle_job(self, mock_echo):
        """Test handling an idle condor job."""
        self.job.status = "idle"
        result = self.state.handle(self.context)
        self.assertTrue(result)
        mock_echo.assert_called_once()
    
    @patch('asimov.monitor_states.click.echo')
    def test_handle_completed_job(self, mock_echo):
        """Test handling a completed condor job."""
        self.job.status = "completed"
        result = self.state.handle(self.context)
        self.assertTrue(result)
        self.analysis.pipeline.after_completion.assert_called_once()
        self.context.refresh_job_list.assert_called_once()
    
    @patch('asimov.monitor_states.click.echo')
    def test_handle_held_job(self, mock_echo):
        """Test handling a held condor job."""
        self.job.status = "held"
        result = self.state.handle(self.context)
        self.assertTrue(result)
        self.assertEqual(self.analysis.status, "stuck")
        self.context.update_ledger.assert_called_once()


class TestFinishedState(unittest.TestCase):
    """Test the FinishedState handler."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.analysis = Mock()
        self.analysis.name = "test_analysis"
        self.analysis.status = "finished"
        self.analysis.pipeline = Mock()
        self.analysis.pipeline.after_completion = Mock()
        
        self.context = Mock(spec=MonitorContext)
        self.context.analysis = self.analysis
        self.context.analysis_path = "GW150914/test_analysis"
        self.context.refresh_job_list = Mock()
        
        self.state = FinishedState()
    
    def test_state_name(self):
        """Test state name property."""
        self.assertEqual(self.state.state_name, "finished")
    
    @patch('asimov.monitor_states.click.echo')
    def test_handle_finished_state(self, mock_echo):
        """Test handling finished state."""
        # Ensure pipeline has after_completion method
        self.analysis.pipeline.after_completion = Mock()
        
        result = self.state.handle(self.context)
        self.assertTrue(result)
        self.analysis.pipeline.after_completion.assert_called_once()
        self.context.refresh_job_list.assert_called_once()


class TestProcessingState(unittest.TestCase):
    """Test the ProcessingState handler."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.analysis = Mock()
        self.analysis.name = "test_analysis"
        self.analysis.status = "processing"
        self.analysis.pipeline = Mock()
        self.analysis.pipeline.detect_completion_processing = Mock(return_value=True)
        self.analysis.pipeline.after_processing = Mock()
        self.analysis.pipeline.detect_completion = Mock(return_value=False)
        
        self.context = Mock(spec=MonitorContext)
        self.context.analysis = self.analysis
        self.context.analysis_path = "GW150914/test_analysis"
        self.context.job_id = "12345"
        
        self.state = ProcessingState()
    
    def test_state_name(self):
        """Test state name property."""
        self.assertEqual(self.state.state_name, "processing")
    
    @patch('asimov.monitor_states.click.echo')
    def test_handle_processing_complete(self, mock_echo):
        """Test handling completed processing."""
        self.analysis.pipeline.detect_completion_processing.return_value = True
        result = self.state.handle(self.context)
        self.assertTrue(result)
        self.analysis.pipeline.after_processing.assert_called_once()
    
    @patch('asimov.monitor_states.click.echo')
    def test_handle_processing_running(self, mock_echo):
        """Test handling running processing."""
        self.analysis.pipeline.detect_completion_processing.return_value = False
        self.analysis.pipeline.detect_completion.return_value = True
        result = self.state.handle(self.context)
        self.assertTrue(result)
        mock_echo.assert_called()


class TestStuckState(unittest.TestCase):
    """Test the StuckState handler."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.analysis = Mock()
        self.analysis.name = "test_analysis"
        self.analysis.status = "stuck"
        
        self.context = Mock(spec=MonitorContext)
        self.context.analysis = self.analysis
        self.context.analysis_path = "GW150914/test_analysis"
        
        self.state = StuckState()
    
    def test_state_name(self):
        """Test state name property."""
        self.assertEqual(self.state.state_name, "stuck")
    
    @patch('asimov.monitor_states.click.echo')
    def test_handle_stuck_state(self, mock_echo):
        """Test handling stuck state."""
        result = self.state.handle(self.context)
        self.assertTrue(result)
        mock_echo.assert_called_once()


if __name__ == '__main__':
    unittest.main()
