"""
Testing pipelines for asimov.

This module provides minimal testing pipelines for each of the three
analysis types supported by asimov:

- SimpleAnalysis: Single-event, single-pipeline analysis
- SubjectAnalysis: Single-event, multi-pipeline analysis  
- ProjectAnalysis: Multi-event, multi-pipeline analysis

These pipelines are designed for:

1. **Testing Infrastructure**: Running end-to-end tests of asimov without
   requiring real gravitational wave analysis pipelines.
   
2. **Template/Examples**: Serving as documented examples for pipeline
   developers to use as starting points for new pipeline implementations.

The testing pipelines complete quickly, create dummy output files, and
implement all required pipeline methods without performing actual analyses.

Usage
-----
These pipelines are discoverable via asimov's standard pipeline discovery
mechanism using entry points. To use them, specify the pipeline name in
your ledger configuration:

.. code-block:: yaml

    # For SimpleAnalysis
    kind: analysis
    pipeline: simpletestpipeline
    
    # For SubjectAnalysis  
    kind: subject_analysis
    pipeline: subjecttestpipeline
    
    # For ProjectAnalysis
    kind: project_analysis
    pipeline: projecttestpipeline

Installation
------------
The testing pipelines are only installed when asimov is installed with
the testing optional dependency:

.. code-block:: bash

    pip install asimov[testing]

This ensures they don't add unnecessary dependencies for production use.

See Also
--------
asimov.pipeline.Pipeline : Base pipeline class
asimov.analysis : Analysis type definitions
"""

from .simple import SimpleTestPipeline
from .subject import SubjectTestPipeline
from .project import ProjectTestPipeline

__all__ = ['SimpleTestPipeline', 'SubjectTestPipeline', 'ProjectTestPipeline']
