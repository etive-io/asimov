"""
Test suite for HTML report generation improvements.
"""

import unittest
from unittest.mock import Mock, MagicMock
from asimov.analysis import SubjectAnalysis
from asimov.event import Event


class TestHTMLReporting(unittest.TestCase):
    """Test the HTML generation features for reports."""

    def test_analysis_html_contains_status_class(self):
        """Test that analysis HTML includes status-specific CSS class."""
        # Create a mock analysis
        analysis = SubjectAnalysis()
        analysis.name = "TestAnalysis"
        analysis.status = "running"
        analysis.comment = "Test comment"
        analysis.pipeline = Mock()
        analysis.pipeline.name = "TestPipeline"
        analysis.pipeline.html = Mock(return_value="")
        analysis.rundir = "/test/rundir"
        analysis.meta = {}
        analysis._reviews = Mock()
        analysis._reviews.__len__ = Mock(return_value=0)
        
        html = analysis.html()
        
        # Check for status-specific class
        self.assertIn("asimov-analysis-running", html)
        # Check for running indicator
        self.assertIn("running-indicator", html)
        # Check for the analysis name
        self.assertIn("TestAnalysis", html)

    def test_analysis_html_collapsible_details(self):
        """Test that analysis HTML includes collapsible details section."""
        analysis = SubjectAnalysis()
        analysis.name = "TestAnalysis"
        analysis.status = "finished"
        analysis.comment = None
        analysis.pipeline = Mock()
        analysis.pipeline.name = "TestPipeline"
        analysis.pipeline.html = Mock(return_value="")
        analysis.rundir = "/test/rundir"
        analysis.meta = {"approximant": "IMRPhenomPv2"}
        analysis._reviews = Mock()
        analysis._reviews.__len__ = Mock(return_value=0)
        
        html = analysis.html()
        
        # Check for collapsible toggle
        self.assertIn("toggle-details", html)
        # Check for details content div
        self.assertIn("details-content", html)
        # Check that approximant is in details
        self.assertIn("IMRPhenomPv2", html)

    def test_analysis_html_with_metadata(self):
        """Test that analysis HTML displays metadata correctly."""
        analysis = SubjectAnalysis()
        analysis.name = "TestAnalysis"
        analysis.status = "finished"
        analysis.comment = None
        analysis.pipeline = Mock()
        analysis.pipeline.name = "TestPipeline"
        analysis.pipeline.html = Mock(return_value="")
        analysis.rundir = "/test/rundir"
        analysis.meta = {
            "approximant": "IMRPhenomPv2",
            "quality": "high",
            "sampler": {"nsamples": 1000}
        }
        analysis._reviews = Mock()
        analysis._reviews.__len__ = Mock(return_value=0)
        
        html = analysis.html()
        
        # Check for metadata fields
        self.assertIn("Waveform approximant", html)
        self.assertIn("IMRPhenomPv2", html)
        self.assertIn("Quality", html)
        self.assertIn("high", html)

    def test_event_html_basic_structure(self):
        """Test that event HTML has basic structure."""
        event = Event(name="GW150914_095045")
        event.productions = []
        event.meta = {"gps": 1126259462.4}
        event.graph = MagicMock()
        event.graph.nodes = Mock(return_value=[])
        
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
        event = Event(name="GW150914_095045")
        event.productions = []
        event.meta = {
            "gps": 1126259462.4,
            "interferometers": ["H1", "L1"]
        }
        event.graph = MagicMock()
        event.graph.nodes = Mock(return_value=[])
        
        html = event.html()
        
        # Check for interferometers
        self.assertIn("Interferometers", html)
        # Should contain both IFOs
        self.assertIn("H1", html)
        self.assertIn("L1", html)


if __name__ == '__main__':
    unittest.main()
