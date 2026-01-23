Labeller Plugin System
======================

Overview
--------

The labeller plugin system allows you to automatically assign labels and properties to analyses during the monitoring process. This feature restores functionality from v0.6 where analyses could be automatically marked as "interesting" based on custom logic.

Labellers are plugins that can:

* Mark analyses as "interesting" based on custom criteria
* Assign priorities or other metadata to analyses
* Filter analyses based on pipeline type, status, or custom properties
* Integrate custom decision logic into the monitoring workflow

Architecture
-----------

The labeller system consists of:

1. **Labeller**: Abstract base class that defines the labelling interface
2. **Labeller Registry**: System for registering and discovering labellers
3. **Entry Points**: Plugin discovery mechanism via Python package entry points
4. **Monitor Integration**: Automatic application of labellers during monitoring

How Labellers Work
-----------------

During the monitoring process, registered labellers are automatically applied to each analysis. Labellers inspect the analysis and can return a dictionary of labels/properties to add to the analysis metadata.

Common use cases:

* Setting ``interest status`` to ``True`` or ``False``
* Adding custom tags or categories
* Computing priority scores
* Marking analyses for special handling

Creating a Custom Labeller
--------------------------

Basic Example
^^^^^^^^^^^^

To create a custom labeller, subclass the ``Labeller`` abstract base class:

.. code-block:: python

    from asimov.labellers import Labeller
    
    class HighMassLabeller(Labeller):
        """Mark high-mass analyses as interesting."""
        
        @property
        def name(self):
            """Return unique name for this labeller."""
            return "high_mass_detector"
        
        def label(self, analysis, context=None):
            """
            Determine labels for the analysis.
            
            Parameters
            ----------
            analysis : Analysis
                The analysis to label.
            context : MonitorContext, optional
                Monitoring context with job info, ledger, etc.
                
            Returns
            -------
            dict
                Labels to add to analysis.meta
            """
            # Check if this is a high-mass analysis
            if hasattr(analysis, 'meta') and 'mass' in analysis.meta:
                if analysis.meta['mass'] > 50:
                    return {"interest status": True, "category": "high_mass"}
            
            return {"interest status": False}

Conditional Labelling
^^^^^^^^^^^^^^^^^^^^

You can control when a labeller runs using the ``should_label`` method:

.. code-block:: python

    class FinishedOnlyLabeller(Labeller):
        """Only label finished analyses."""
        
        @property
        def name(self):
            return "finished_checker"
        
        def should_label(self, analysis, context=None):
            """Only run for finished analyses."""
            return analysis.status in {"finished", "uploaded"}
        
        def label(self, analysis, context=None):
            # This only runs for finished analyses
            return {"interest status": True}

Using the Context
^^^^^^^^^^^^^^^^

The context parameter provides access to monitoring information:

.. code-block:: python

    class JobStatusLabeller(Labeller):
        """Label based on job status."""
        
        @property
        def name(self):
            return "job_status_checker"
        
        def label(self, analysis, context=None):
            if context is None:
                return {}
            
            # Access job information from context
            job = context.job
            if job and hasattr(job, 'status'):
                if job.status == 'completed':
                    return {"interest status": True, "job_completed": True}
            
            return {}

Registering Labellers
--------------------

Programmatic Registration
^^^^^^^^^^^^^^^^^^^^^^^^

Register a labeller at runtime:

.. code-block:: python

    from asimov.labellers import register_labeller
    
    labeller = HighMassLabeller()
    register_labeller(labeller)

Entry Point Registration (Recommended)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For production use, register labellers via entry points so they're automatically discovered.

In ``pyproject.toml``:

.. code-block:: toml

    [project.entry-points."asimov.labellers"]
    high_mass = "mypackage.labellers:HighMassLabeller"
    pipeline_filter = "mypackage.labellers:PipelineFilterLabeller"

Or in ``setup.py``:

.. code-block:: python

    from setuptools import setup
    
    setup(
        name="mypackage",
        # ... other setup parameters ...
        entry_points={
            'asimov.labellers': [
                'high_mass = mypackage.labellers:HighMassLabeller',
                'pipeline_filter = mypackage.labellers:PipelineFilterLabeller',
            ]
        }
    )

After installing your package, the labellers will be automatically discovered and registered when asimov runs.

Built-in Example Labellers
--------------------------

Asimov includes several example labellers to demonstrate the system:

AlwaysInterestingLabeller
^^^^^^^^^^^^^^^^^^^^^^^^

Marks all analyses as interesting:

.. code-block:: python

    from asimov.example_labellers import AlwaysInterestingLabeller
    from asimov.labellers import register_labeller
    
    register_labeller(AlwaysInterestingLabeller())

PipelineInterestLabeller
^^^^^^^^^^^^^^^^^^^^^^^

Marks specific pipeline types as interesting:

.. code-block:: python

    from asimov.example_labellers import PipelineInterestLabeller
    from asimov.labellers import register_labeller
    
    # Mark bilby and RIFT as interesting
    labeller = PipelineInterestLabeller(["bilby", "RIFT"])
    register_labeller(labeller)

FinishedAnalysisLabeller
^^^^^^^^^^^^^^^^^^^^^^^

Only labels finished analyses as interesting:

.. code-block:: python

    from asimov.example_labellers import FinishedAnalysisLabeller
    from asimov.labellers import register_labeller
    
    register_labeller(FinishedAnalysisLabeller())

ConditionalLabeller
^^^^^^^^^^^^^^^^^^

Uses custom logic to determine interest:

.. code-block:: python

    from asimov.example_labellers import ConditionalLabeller
    from asimov.labellers import register_labeller
    
    def is_high_priority(analysis):
        return hasattr(analysis, 'priority') and analysis.priority > 5
    
    labeller = ConditionalLabeller(
        condition_func=is_high_priority,
        labeller_name="high_priority"
    )
    register_labeller(labeller)

Factory Functions
^^^^^^^^^^^^^^^^

Use factory functions for quick labeller creation:

.. code-block:: python

    from asimov.example_labellers import (
        create_pipeline_labeller,
        create_conditional_labeller
    )
    from asimov.labellers import register_labeller
    
    # Create pipeline labeller
    labeller1 = create_pipeline_labeller(["bilby", "lalinference"])
    register_labeller(labeller1)
    
    # Create conditional labeller
    labeller2 = create_conditional_labeller(
        lambda a: "important" in a.name,
        name="important_name"
    )
    register_labeller(labeller2)

Using Labels in Workflows
-------------------------

Once labellers have been applied, the labels are stored in the analysis metadata and can be used throughout asimov:

Dependency Logic
^^^^^^^^^^^^^^^

Use labels in dependency specifications:

.. code-block:: yaml

    - name: combined_analysis
      needs:
        - bilby_analysis
        - rift_analysis
        - label: interesting>=1

This will only run the combined analysis if at least 1 of the parent analyses has the ``interesting`` label set to a truthy value.

You can also use comparison operators:

.. code-block:: yaml

    needs:
      - label: priority>5
      - label: quality==high

Custom Workflows
^^^^^^^^^^^^^^^

Access labels in your custom code:

.. code-block:: python

    for analysis in ledger.project_analyses:
        labels = analysis.meta.get('labels', {})
        if labels.get('interesting'):
            print(f"Interesting analysis: {analysis.name}")
            print(f"  Priority: {labels.get('priority', 'N/A')}")
            # Perform special handling

Monitoring Output
^^^^^^^^^^^^^^^^

Labels are visible in monitor output and reports, allowing you to track which analyses have been flagged as interesting.

Advanced Topics
--------------

Multiple Labellers
^^^^^^^^^^^^^^^^^

Multiple labellers can be registered and will all run on each analysis. If multiple labellers set the same metadata key, the last one wins.

.. code-block:: python

    # Both labellers will run
    register_labeller(PipelineInterestLabeller(["bilby"]))
    register_labeller(FinishedAnalysisLabeller())

Error Handling
^^^^^^^^^^^^^

Labellers should handle errors gracefully. If a labeller raises an exception, it's logged but doesn't stop the monitoring process:

.. code-block:: python

    class SafeLabeller(Labeller):
        @property
        def name(self):
            return "safe_labeller"
        
        def label(self, analysis, context=None):
            try:
                # Potentially risky operation
                result = self.complex_computation(analysis)
                return {"interest status": result}
            except Exception as e:
                # Log error but return safely
                logger.error(f"Error in labeller: {e}")
                return {}

Performance Considerations
^^^^^^^^^^^^^^^^^^^^^^^^^

Labellers run during every monitor cycle, so keep them lightweight:

* Avoid expensive computations
* Cache results when possible
* Use ``should_label`` to skip unnecessary work
* Don't make external API calls unless necessary

Testing Labellers
^^^^^^^^^^^^^^^^

Write unit tests for your labellers:

.. code-block:: python

    import unittest
    from unittest.mock import Mock
    
    class TestHighMassLabeller(unittest.TestCase):
        def test_high_mass_is_interesting(self):
            labeller = HighMassLabeller()
            
            analysis = Mock()
            analysis.meta = {'mass': 60}
            
            labels = labeller.label(analysis)
            
            self.assertTrue(labels["interest status"])
        
        def test_low_mass_not_interesting(self):
            labeller = HighMassLabeller()
            
            analysis = Mock()
            analysis.meta = {'mass': 30}
            
            labels = labeller.label(analysis)
            
            self.assertFalse(labels["interest status"])

Complete Plugin Example
----------------------

Here's a complete example of creating a labeller plugin package:

**Directory structure:**

.. code-block::

    my-asimov-labellers/
    ├── pyproject.toml
    ├── README.md
    └── my_labellers/
        ├── __init__.py
        └── labellers.py

**pyproject.toml:**

.. code-block:: toml

    [build-system]
    requires = ["setuptools>=61.0"]
    build-backend = "setuptools.build_meta"
    
    [project]
    name = "my-asimov-labellers"
    version = "0.1.0"
    description = "Custom labellers for asimov"
    dependencies = [
        "asimov>=0.7.0",
    ]
    
    [project.entry-points."asimov.labellers"]
    quality_check = "my_labellers.labellers:QualityCheckLabeller"
    convergence = "my_labellers.labellers:ConvergenceLabeller"

**labellers.py:**

.. code-block:: python

    from asimov.labellers import Labeller
    import logging
    
    logger = logging.getLogger(__name__)
    
    class QualityCheckLabeller(Labeller):
        """Label analyses based on quality metrics."""
        
        @property
        def name(self):
            return "quality_check"
        
        def label(self, analysis, context=None):
            # Check quality metrics
            if self.passes_quality_checks(analysis):
                return {
                    "interest status": True,
                    "quality": "high"
                }
            return {
                "interest status": False,
                "quality": "low"
            }
        
        def passes_quality_checks(self, analysis):
            # Implement your quality logic
            return True
    
    class ConvergenceLabeller(Labeller):
        """Label analyses based on convergence."""
        
        @property
        def name(self):
            return "convergence_checker"
        
        def should_label(self, analysis, context=None):
            # Only check running or finished analyses
            return analysis.status in {"running", "finished"}
        
        def label(self, analysis, context=None):
            if self.check_convergence(analysis):
                return {
                    "interest status": True,
                    "converged": True
                }
            return {"converged": False}
        
        def check_convergence(self, analysis):
            # Implement convergence checking
            return False

**Installation:**

.. code-block:: bash

    pip install my-asimov-labellers
    
    # Now run asimov monitor and your labellers will be active
    asimov monitor

API Reference
------------

Labeller
^^^^^^^

.. code-block:: python

    class Labeller(ABC):
        """Abstract base class for labellers."""
        
        @property
        @abstractmethod
        def name(self):
            """Return unique name for this labeller."""
            pass
        
        @abstractmethod
        def label(self, analysis, context=None):
            """
            Return labels for the analysis.
            
            Returns:
                dict: Labels to add to analysis.meta
            """
            pass
        
        def should_label(self, analysis, context=None):
            """
            Determine if labeller should run.
            
            Returns:
                bool: True if labeller should run
            """
            return True

Functions
^^^^^^^^

.. code-block:: python

    def register_labeller(labeller):
        """Register a labeller programmatically."""
        pass
    
    def discover_labellers():
        """Discover labellers via entry points."""
        pass
    
    def apply_labellers(analysis, context=None):
        """Apply all registered labellers to an analysis."""
        pass
    
    def get_labellers():
        """Get all registered labellers."""
        pass

See Also
--------

* :doc:`monitor-state-machine` - Monitor state machine architecture
* :doc:`hooks` - Post-monitor hooks
* :doc:`api/asimov` - API reference
