#!/usr/bin/env python
"""
Demonstration script showing HTML output for analyses with new dependency features.
This generates sample HTML to show how the new dependency indicators appear.
"""

from unittest.mock import Mock
from asimov.analysis import Analysis


class DemoAnalysis(Analysis):
    """Demo analysis for HTML generation."""
    
    def __init__(self, name, **kwargs):
        self.name = name
        self.meta = kwargs.get('meta', {})
        self._needs = kwargs.get('needs', [])
        self.event = kwargs.get('event', None)
        self.subject = self.event  # Add subject attribute
        self.status_str = kwargs.get('status', 'ready')
        self.comment = kwargs.get('comment', None)
        self._reviews = Mock()
        self._reviews.status = kwargs.get('review_status', 'none')
        self._reviews.__len__ = Mock(return_value=0)
        
        # Set pipeline
        self.pipeline = Mock()
        self.pipeline.name = kwargs.get('pipeline', 'bilby')
        self.pipeline.html = Mock(return_value='')
        
        self.rundir = kwargs.get('rundir', None)
    
    @property
    def review(self):
        return self._reviews


def generate_demo_html():
    """Generate sample HTML showing the new features."""
    
    # Create mock event
    event = Mock()
    event.meta = {}  # Add meta dict to event
    
    # Create sample analyses
    analyses = [
        DemoAnalysis('BayesWave-PSD', 
                    pipeline='bayeswave',
                    status='finished',
                    event=event,
                    meta={'pipeline': 'bayeswave'}),
        DemoAnalysis('IMRPhenomXPHM-PE',
                    pipeline='bilby',
                    status='finished',
                    event=event,
                    meta={'pipeline': 'bilby', 'waveform': {'approximant': 'IMRPhenomXPHM'}}),
        DemoAnalysis('SEOBNRv5PHM-PE',
                    pipeline='bilby',
                    status='finished',
                    event=event,
                    meta={'pipeline': 'bilby', 'waveform': {'approximant': 'SEOBNRv5PHM'}}),
    ]
    
    event.analyses = analyses
    
    # Create an analysis with dependencies
    combiner = DemoAnalysis('Combiner',
                           pipeline='bilby',
                           status='ready',
                           event=event,
                           comment='Combines multiple PE analyses',
                           needs=['waveform.approximant: IMRPhenomXPHM', 
                                  'waveform.approximant: SEOBNRv5PHM'],
                           rundir='/path/to/combiner')
    
    # Create a stale analysis
    stale_analysis = DemoAnalysis('Stale-Analysis',
                                 pipeline='bilby',
                                 status='finished',
                                 event=event,
                                 needs=['pipeline: bayeswave'],
                                 rundir=None,
                                 meta={'resolved_dependencies': ['BayesWave-PSD']})
    
    # Manually set resolved dependencies to make it stale
    stale_analysis.meta['resolved_dependencies'] = ['BayesWave-PSD']
    # Current dependencies would be different if we add more bayeswave analyses
    
    print("=" * 80)
    print("HTML OUTPUT DEMONSTRATION")
    print("=" * 80)
    print()
    
    print("1. Analysis with dependencies shown:")
    print("-" * 80)
    print(combiner.html())
    print()
    
    print("\n2. Stale analysis (dependencies changed):")
    print("-" * 80)
    # Manually show what stale would look like
    print("<div class='asimov-analysis asimov-analysis-finished'>")
    print('<span class="stale-indicator stale" title="Dependencies have changed since this analysis was run">Stale</span>')
    print("<h4>Stale-Analysis</h4>")
    print('<p class="asimov-status">')
    print('  <span class="badge badge-pill badge-success">finished</span>')
    print('</p>')
    print('<p class="asimov-pipeline-name"><strong>Pipeline:</strong> bilby</p>')
    print('<a class="toggle-details">▶ Show details</a>')
    print('<div class="details-content">')
    print('<p class="asimov-dependencies"><strong>Current Dependencies:</strong><br>BayesWave-PSD, NewBayesWaveAnalysis</p>')
    print('<p class="asimov-resolved-dependencies"><strong>Resolved Dependencies (when run):</strong><br>BayesWave-PSD</p>')
    print('</div>')
    print('</div>')
    print()
    
    print("\n3. Refreshable stale analysis:")
    print("-" * 80)
    print("<div class='asimov-analysis asimov-analysis-finished'>")
    print('<span class="stale-indicator stale-refreshable" title="Dependencies have changed since this analysis was run">Stale (will refresh)</span>')
    print("<h4>Auto-Refresh</h4>")
    print('<p class="asimov-status">')
    print('  <span class="badge badge-pill badge-success">finished</span>')
    print('</p>')
    print('<p class="asimov-pipeline-name"><strong>Pipeline:</strong> bilby</p>')
    print('</div>')
    print()
    
    print("\n" + "=" * 80)
    print("CSS STYLES FOR NEW FEATURES")
    print("=" * 80)
    print("""
.stale-indicator {
    display: inline-block;
    padding: 0.25rem 0.5rem;
    border-radius: 0.25rem;
    font-size: 0.75rem;
    font-weight: 600;
    margin-left: 0.5rem;
    text-transform: uppercase;
}

.stale-indicator.stale {
    background-color: #ffeaa7;
    color: #d63031;
    border: 1px solid #fdcb6e;
}

.stale-indicator.stale-refreshable {
    background-color: #74b9ff;
    color: #0984e3;
    border: 1px solid #0984e3;
}

.asimov-dependencies,
.asimov-resolved-dependencies {
    font-size: 0.9rem;
    color: #586069;
    margin: 0.5rem 0;
    padding: 0.5rem;
    background: #f6f8fa;
    border-radius: 0.25rem;
}

.asimov-resolved-dependencies {
    background: #fff3cd;
    border-left: 3px solid #ffc107;
}
    """)


if __name__ == '__main__':
    generate_demo_html()
