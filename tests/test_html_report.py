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


class TestReportGraphClicks(unittest.TestCase):
    """Mermaid ignores `click` directives unless securityLevel is 'loose'."""

    def setUp(self):
        import inspect
        import asimov.cli.report as report

        self.source = inspect.getsource(report)

    def test_click_handlers_are_bound_to_rendered_nodes(self):
        if "securityLevel: 'loose'" not in self.source:
            self.assertNotIn("'    click ' + n.id", self.source)
        self.assertIn("bindNodeClicks(container)", self.source)


class TestReportLazyGraphRendering(unittest.TestCase):
    """
    Rendering every event's Mermaid graph up front blocks the page for as
    long as there are events, so graphs are drawn lazily instead.
    """

    def setUp(self):
        import inspect
        import asimov.cli.report as report

        self.source = inspect.getsource(report)

    def test_graphs_are_drawn_when_events_come_into_view(self):
        self.assertIn("new IntersectionObserver", self.source)
        self.assertIn("initGraphRendering();", self.source)

    def test_filter_changes_do_not_redraw_every_graph(self):
        start = self.source.index("function rerenderAllGraphs()")
        body = self.source[start:self.source.index("}\n", start)]
        self.assertNotIn("mermaid.render", body)
        self.assertIn("asimovRenderGeneration++", body)

    def test_queued_graphs_that_left_the_viewport_are_skipped(self):
        start = self.source.index("async function drainRenderQueue()")
        body = self.source[start:self.source.index("function scheduleGraphRender", start)]
        self.assertIn("asimovNearViewport.has(eventName)", body)
        self.assertLess(
            body.index("asimovNearViewport.has(eventName)"),
            body.index("await renderEventGraph"),
        )

    def test_graphs_are_rendered_one_at_a_time_yielding_between(self):
        self.assertIn("asimovRenderRunning", self.source)
        self.assertIn("setTimeout(resolve, 0)", self.source)


class TestPipelineResultPages(unittest.TestCase):
    """Pipelines can supply the result links shown in the analysis modal."""

    def _event_html(self, status, pages):
        import networkx as nx
        from asimov.event import Event

        node = Mock()
        node.name = "generate-psd"
        node.status = status
        node.comment = None
        node.rundir = "/proj/working/GW1/generate-psd"
        node.meta = {}
        node.dependencies = []
        node.review = []
        node.category = "analyses"
        node.pipeline = Mock()
        node.pipeline.name = "BayesWave"
        node.pipeline.result_pages = Mock(return_value=pages)
        node.event = Mock(webdir=None)

        graph = nx.DiGraph()
        graph.add_node(node)

        event = Mock(spec=Event)
        event.name = "GW1"
        event.productions = []
        event.meta = {"gps": 1.0}
        event.graph = graph
        return Event.html(event)

    def test_pipeline_result_pages_appear_in_modal_data(self):
        html = self._event_html(
            "uploaded", [("Full Megaplot output", "GW1/generate-psd/index.html")]
        )
        self.assertIn(
            'data-result-pages="GW1/generate-psd/index.html|Full Megaplot output"',
            html,
        )

    def test_unfinished_analysis_has_no_result_pages(self):
        html = self._event_html(
            "running", [("Full Megaplot output", "GW1/generate-psd/index.html")]
        )
        self.assertIn('data-result-pages=""', html)
