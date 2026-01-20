Monitor State Machine Architecture
===================================

Overview
--------

The asimov monitor loop has been refactored to use a state machine pattern, replacing the previous hard-coded if-elif chains. This new architecture provides better maintainability, extensibility, and clarity in how analyses transition between states.

Architecture Components
----------------------

The refactored monitor system consists of three main components:

1. **MonitorState**: Abstract state handlers for each analysis state
2. **MonitorContext**: Context object managing analysis monitoring
3. **monitor_helpers**: Reusable functions for monitoring analyses

MonitorState Classes
-------------------

Each analysis state is handled by a dedicated state class that implements the ``MonitorState`` abstract base class:

.. code-block:: python

    from asimov.monitor_states import MonitorState
    
    class CustomState(MonitorState):
        @property
        def state_name(self):
            return "custom"
        
        def handle(self, context):
            # Implement state-specific logic here
            return True

Built-in State Handlers
^^^^^^^^^^^^^^^^^^^^^^^

The following state handlers are provided:

* **ReadyState**: Handles analyses in 'ready' state (not yet started)
* **StopState**: Handles analyses that need to be stopped
* **RunningState**: Handles analyses currently running on the scheduler
* **FinishedState**: Handles analyses that have completed execution
* **ProcessingState**: Handles analyses in post-processing phase
* **StuckState**: Handles analyses that are stuck and need intervention
* **StoppedState**: Handles analyses that have been stopped

State Transitions
^^^^^^^^^^^^^^^^

The state machine enforces the following transitions:

.. code-block::

    ready → running → finished → processing → uploaded
      ↓                  ↓
    stop → stopped    stuck (error state)
               ↓
            restart

Each state handler is responsible for:

* Checking the current status of the analysis
* Performing any necessary actions (e.g., calling pipeline hooks)
* Updating the analysis status for transitions
* Updating the ledger through the context

MonitorContext
-------------

The ``MonitorContext`` class encapsulates all the state and operations needed to monitor a single analysis:

.. code-block:: python

    from asimov.monitor_context import MonitorContext
    
    context = MonitorContext(
        analysis=analysis,
        job_list=job_list,
        ledger=ledger,
        dry_run=False,
        analysis_path="GW150914/analysis_name"
    )

Key Features
^^^^^^^^^^^

* **Job Management**: Retrieves condor job information
* **Ledger Updates**: Handles both event and project analysis updates
* **Dry Run Support**: Allows testing without actual updates
* **Job List Refresh**: Coordinates with condor job list

Helper Functions
---------------

monitor_analysis
^^^^^^^^^^^^^^^

The ``monitor_analysis`` function provides a unified interface for monitoring both event and project analyses:

.. code-block:: python

    from asimov.monitor_helpers import monitor_analysis
    
    success = monitor_analysis(
        analysis=analysis,
        job_list=job_list,
        ledger=ledger,
        dry_run=False,
        analysis_path="GW150914/bilby_analysis"
    )

This function:

1. Creates a ``MonitorContext``
2. Gets the appropriate state handler for the analysis
3. Delegates to the state handler
4. Updates the ledger if successful

monitor_analyses_list
^^^^^^^^^^^^^^^^^^^^

For monitoring multiple analyses, use ``monitor_analyses_list``:

.. code-block:: python

    from asimov.monitor_helpers import monitor_analyses_list
    
    stats = monitor_analyses_list(
        analyses=event.productions,
        job_list=job_list,
        ledger=ledger,
        label="productions"
    )
    
    print(f"Total: {stats['total']}, Running: {stats['running']}")

Extending the State Machine
---------------------------

Adding Custom States
^^^^^^^^^^^^^^^^^^^

To add a new state to the system:

1. Create a new state class inheriting from ``MonitorState``
2. Implement the ``state_name`` property and ``handle`` method
3. Register the state in ``STATE_REGISTRY``

Example:

.. code-block:: python

    from asimov.monitor_states import MonitorState, STATE_REGISTRY
    
    class ValidationState(MonitorState):
        @property
        def state_name(self):
            return "validation"
        
        def handle(self, context):
            analysis = context.analysis
            # Custom validation logic
            if validation_passes:
                analysis.status = "validated"
                context.update_ledger()
                return True
            return False
    
    # Register the new state
    STATE_REGISTRY["validation"] = ValidationState()

Custom Pipeline Hooks
^^^^^^^^^^^^^^^^^^^^^

Pipeline classes can now define custom hooks that are called during monitoring:

.. code-block:: python

    from asimov.pipeline import Pipeline
    
    class CustomPipeline(Pipeline):
        def while_running(self):
            """Called each monitor cycle while analysis is running."""
            # Collect intermediate results
            self.check_convergence()
        
        def detect_completion(self):
            """Check if the analysis has completed."""
            return os.path.exists(self.results_file)
        
        def after_completion(self):
            """Called when analysis completes."""
            self.production.status = "finished"
            self.collect_results()

All pipeline hook methods now have default implementations in the base ``Pipeline`` class, so pipelines only need to override the ones they use.

Migration Guide
--------------

Updating Existing Code
^^^^^^^^^^^^^^^^^^^^^

The refactored monitor is backward compatible. Existing code will continue to work without changes. However, to take advantage of the new architecture:

**Old approach (deprecated):**

.. code-block:: python

    if analysis.status.lower() == "running":
        if job.status.lower() == "completed":
            pipe.after_completion()
            analysis.status = "finished"
            ledger.update()

**New approach:**

.. code-block:: python

    from asimov.monitor_helpers import monitor_analysis
    
    monitor_analysis(analysis, job_list, ledger)

The new approach automatically handles all state transitions.

Custom Analysis Types
^^^^^^^^^^^^^^^^^^^^

For custom analysis types, define monitoring behavior by creating custom state handlers:

.. code-block:: python

    class PopulationAnalysisState(ProcessingState):
        def handle(self, context):
            # Custom logic for population analyses
            if self.all_events_complete(context.analysis):
                return super().handle(context)
            else:
                click.echo("Waiting for all events to complete")
                return True

Testing
-------

The state machine components are fully unit tested. See ``tests/test_monitor_states.py`` and ``tests/test_monitor_helpers.py`` for examples of how to test custom states and monitor logic.

Example test:

.. code-block:: python

    import unittest
    from unittest.mock import Mock
    from asimov.monitor_states import RunningState
    from asimov.monitor_context import MonitorContext
    
    class TestCustomState(unittest.TestCase):
        def test_running_state(self):
            state = RunningState()
            analysis = Mock()
            analysis.status = "running"
            context = MonitorContext(analysis, job_list, ledger)
            
            result = state.handle(context)
            self.assertTrue(result)

Best Practices
-------------

1. **Keep state handlers focused**: Each state should handle only its specific concerns
2. **Use context methods**: Always use ``context.update_ledger()`` rather than direct ledger calls
3. **Handle errors gracefully**: State handlers should catch exceptions and report them appropriately
4. **Test state transitions**: Write unit tests for any custom state handlers
5. **Document custom states**: Add documentation for any new states you introduce

See Also
--------

* :doc:`code-overview` - General asimov architecture
* :doc:`hooks` - Post-monitor hooks
* :doc:`api/asimov` - API reference
