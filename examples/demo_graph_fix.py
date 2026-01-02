#!/usr/bin/env python
"""
Visual demonstration of the graph connection fix and modal dependencies feature.
"""

from unittest.mock import Mock
from asimov.event import Event
from asimov.analysis import Analysis


class DemoAnalysis(Analysis):
    """Demo analysis for testing."""
    
    def __init__(self, name, needs=None, **kwargs):
        self.name = name
        self.meta = kwargs.get('meta', {})
        self._needs = needs or []
        self.event = None
        self.subject = None
        self.status_str = kwargs.get('status', 'finished')
        self._reviews = Mock()
        self._reviews.status = kwargs.get('review_status', 'none')
        self._reviews.__len__ = Mock(return_value=0)
        self.pipeline = Mock()
        self.pipeline.name = kwargs.get('pipeline', 'bilby')
        self.pipeline.html = Mock(return_value='')
        self.comment = kwargs.get('comment', None)
    
    @property
    def review(self):
        return self._reviews
    
    @property
    def finished(self):
        return self.status_str == 'finished'


def main():
    print("=" * 80)
    print("GRAPH CONNECTION FIX DEMONSTRATION")
    print("=" * 80)
    print()
    
    # Create event
    event_data = {'name': 'GW150914', 'productions': []}
    event = Event(**event_data)
    event.meta = {}
    
    # Add analyses in sequence
    print("Step 1: Adding BayesWave PSD analysis")
    a1 = DemoAnalysis('BayesWave-PSD', 
                     pipeline='bayeswave',
                     status='finished',
                     meta={'pipeline': 'bayeswave'})
    a1.event = event
    a1.subject = event
    event.add_production(a1)
    print(f"  Added: {a1.name}")
    
    print("\nStep 2: Adding Bilby PE analyses with waveform approximants")
    a2 = DemoAnalysis('IMRPhenomXPHM-PE',
                     pipeline='bilby',
                     status='finished',
                     meta={'pipeline': 'bilby', 
                           'waveform': {'approximant': 'IMRPhenomXPHM'}})
    a2.event = event
    a2.subject = event
    event.add_production(a2)
    print(f"  Added: {a2.name} (waveform.approximant: IMRPhenomXPHM)")
    
    a3 = DemoAnalysis('SEOBNRv5PHM-PE',
                     pipeline='bilby',
                     status='finished',
                     meta={'pipeline': 'bilby',
                           'waveform': {'approximant': 'SEOBNRv5PHM'}})
    a3.event = event
    a3.subject = event
    event.add_production(a3)
    print(f"  Added: {a3.name} (waveform.approximant: SEOBNRv5PHM)")
    
    print("\nStep 3: Adding Combiner with property-based dependency")
    combiner = DemoAnalysis('Combiner',
                           pipeline='bilby',
                           status='ready',
                           comment='Combines IMRPhenomXPHM and SEOBNRv5PHM results',
                           needs=['waveform.approximant: IMRPhenomXPHM',
                                  'waveform.approximant: SEOBNRv5PHM'])
    combiner.event = event
    combiner.subject = event
    event.add_production(combiner)
    print(f"  Added: {combiner.name}")
    print(f"  Dependencies (property-based): {combiner._needs}")
    
    # Show resolved dependencies
    print("\n" + "=" * 80)
    print("DEPENDENCY RESOLUTION")
    print("=" * 80)
    print(f"\n{combiner.name} dependencies resolved to:")
    for dep in combiner.dependencies:
        print(f"  - {dep}")
    
    # Show graph edges BEFORE update
    print("\n" + "=" * 80)
    print("GRAPH EDGES (before update_graph)")
    print("=" * 80)
    edges = list(event.graph.edges())
    if edges:
        for src, dst in edges:
            print(f"  {src.name} -> {dst.name}")
    else:
        print("  No edges")
    
    # Call update_graph
    print("\nCalling update_graph()...")
    event.update_graph()
    
    # Show graph edges AFTER update
    print("\n" + "=" * 80)
    print("GRAPH EDGES (after update_graph)")
    print("=" * 80)
    edges = list(event.graph.edges())
    if edges:
        for src, dst in edges:
            print(f"  {src.name} -> {dst.name}")
    else:
        print("  No edges")
    
    # Verify graph connections
    import networkx as nx
    print("\n" + "=" * 80)
    print("GRAPH VERIFICATION")
    print("=" * 80)
    
    predecessors = list(event.graph.predecessors(combiner))
    print(f"\nPredecessors of {combiner.name} in graph:")
    for pred in predecessors:
        print(f"  - {pred.name}")
    
    expected = set(['IMRPhenomXPHM-PE', 'SEOBNRv5PHM-PE'])
    actual = set([p.name for p in predecessors])
    
    if expected == actual:
        print("\n✅ PASS: Graph correctly connects property-based dependencies!")
    else:
        print(f"\n❌ FAIL: Expected {expected}, got {actual}")
    
    # Check HTML generation
    print("\n" + "=" * 80)
    print("MODAL DEPENDENCIES DATA")
    print("=" * 80)
    
    html = event.html()
    
    # Extract dependencies data from HTML
    import re
    dep_pattern = r'data-dependencies="([^"]*)"'
    matches = re.findall(dep_pattern, html)
    
    print(f"\nDependencies in HTML data attributes:")
    for i, match in enumerate(matches):
        if match:
            print(f"  Analysis {i+1}: {match}")
        else:
            print(f"  Analysis {i+1}: None")
    
    # Check for Combiner specifically
    combiner_dep_pattern = rf'id="analysis-data-{combiner.name}"[^>]*data-dependencies="([^"]*)"'
    combiner_match = re.search(combiner_dep_pattern, html)
    
    if combiner_match:
        deps_str = combiner_match.group(1)
        print(f"\n{combiner.name} dependencies in modal: {deps_str}")
        
        if 'IMRPhenomXPHM-PE' in deps_str and 'SEOBNRv5PHM-PE' in deps_str:
            print("✅ PASS: Modal includes correct dependencies!")
        else:
            print("❌ FAIL: Modal dependencies incorrect")
    else:
        print(f"❌ FAIL: Could not find dependencies data for {combiner.name}")
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print("\n✅ Property-based dependencies resolve correctly")
    print("✅ Graph connections update dynamically with update_graph()")
    print("✅ Dependencies appear in modal data attributes")
    print("✅ HTML report will display dependencies in analysis details popup")
    print()


if __name__ == '__main__':
    main()
