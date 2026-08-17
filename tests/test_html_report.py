"""
Test suite for HTML report generation improvements.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch


class TestHTMLReporting(unittest.TestCase):
    """Test the HTML generation features for reports."""

    def _create_mock_analysis(self, status="running", name="TestAnalysis", 
                              rundir="/test/rundir", meta=None):
        """Helper to create a mock analysis object."""
        analysis = Mock()
        analysis.name = name
        analysis.status = status
        analysis.comment = None
        analysis.pipeline = Mock()
        analysis.pipeline.name = "TestPipeline"
        analysis.pipeline.html = Mock(return_value="")
        analysis.rundir = rundir
        analysis.meta = meta or {}
        analysis._reviews = Mock()
        analysis._reviews.__len__ = Mock(return_value=0)
        
        # Import the html method from analysis module and bind it
        from asimov.analysis import SubjectAnalysis
        analysis.html = lambda: SubjectAnalysis.html(analysis)
        
        return analysis

    def test_analysis_html_contains_status_class(self):
        """Test that analysis HTML includes status-specific CSS class."""
        analysis = self._create_mock_analysis(status="running")
        
        html = analysis.html()
        
        # Check for status-specific class
        self.assertIn("asimov-analysis-running", html)
        # Check for running indicator
        self.assertIn("running-indicator", html)
        # Check for the analysis name
        self.assertIn("TestAnalysis", html)

    def test_analysis_html_collapsible_details(self):
        """Test that analysis HTML includes collapsible details section."""
        analysis = self._create_mock_analysis(
            status="finished",
            meta={"approximant": "IMRPhenomPv2"}
        )
        
        html = analysis.html()
        
        # Check for collapsible toggle
        self.assertIn("toggle-details", html)
        # Check for details content div
        self.assertIn("details-content", html)
        # Check that approximant is in details
        self.assertIn("IMRPhenomPv2", html)

    def test_analysis_html_with_metadata(self):
        """Test that analysis HTML displays metadata correctly."""
        analysis = self._create_mock_analysis(
            status="finished",
            meta={
                "approximant": "IMRPhenomPv2",
                "quality": "high",
                "sampler": {"nsamples": 1000}
            }
        )
        
        html = analysis.html()
        
        # Check for metadata fields
        self.assertIn("Waveform approximant", html)
        self.assertIn("IMRPhenomPv2", html)
        self.assertIn("Quality", html)
        self.assertIn("high", html)

    def test_event_html_basic_structure(self):
        """Test that event HTML has basic structure."""
        from asimov.event import Event
        
        event = Mock(spec=Event)
        event.name = "GW150914_095045"
        event.productions = []
        event.meta = {"gps": 1126259462.4}
        event.graph = MagicMock()
        event.graph.nodes = Mock(return_value=[])
        
        # Import and bind the html method
        from asimov.event import Event as RealEvent
        event.html = lambda: RealEvent.html(event)
        
        html = event.html()
        
        # Check for event name
        self.assertIn("GW150914_095045", html)
        # Check for GPS time
        self.assertIn("GPS Time", html)
        self.assertIn("1126259462.4", html)
        # Check for card structure
        self.assertIn("event-data", html)

    def test_event_html_with_interferometers(self):
        """Test that event HTML displays interferometer information."""
        from asimov.event import Event
        
        event = Mock(spec=Event)
        event.name = "GW150914_095045"
        event.productions = []
        event.meta = {
            "gps": 1126259462.4,
            "interferometers": ["H1", "L1"]
        }
        event.graph = MagicMock()
        event.graph.nodes = Mock(return_value=[])
        
        # Import and bind the html method
        from asimov.event import Event as RealEvent
        event.html = lambda: RealEvent.html(event)
        
        html = event.html()
        
        # Check for interferometers
        self.assertIn("Interferometers", html)
        # Should contain both IFOs
        self.assertIn("H1", html)
        self.assertIn("L1", html)


if __name__ == '__main__':
    unittest.main()
