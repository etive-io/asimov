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

The monitor state machine supports a plugin architecture that allows you to add
custom states without modifying asimov's core code.

Adding Custom States via Entry Points
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The recommended way to add custom states is through Python's entry points system.
This allows your custom states to be automatically discovered and registered when
your package is installed.

**Step 1: Define your custom state**

.. code-block:: python

    # In mypackage/states.py
    from asimov.monitor_states import MonitorState
    
    class ValidationState(MonitorState):
        @property
        def state_name(self):
            return "validation"
        
        def handle(self, context):
            analysis = context.analysis
            # Custom validation logic
            if self.validate_analysis(analysis):
                analysis.status = "validated"
                context.update_ledger()
                return True
            else:
                analysis.status = "validation_failed"
                context.update_ledger()
                return False
        
        def validate_analysis(self, analysis):
            # Your validation logic here
            return True

**Step 2: Register via entry points**

In your package's ``setup.py``:

.. code-block:: python

    from setuptools import setup
    
    setup(
        name="mypackage",
        # ... other setup parameters ...
        entry_points={
            'asimov.monitor.states': [
                'validation = mypackage.states:ValidationState',
            ]
        }
    )

Or in ``pyproject.toml``:

.. code-block:: toml

    [project.entry-points."asimov.monitor.states"]
    validation = "mypackage.states:ValidationState"

**Step 3: Install your package**

Once installed, asimov will automatically discover and register your custom state:

.. code-block:: bash

    pip install mypackage

Your custom state is now available for use. When an analysis has ``status = "validation"``,
the ``ValidationState`` handler will be invoked automatically.

Programmatic Registration
^^^^^^^^^^^^^^^^^^^^^^^^^

For runtime or dynamic state registration, use the ``register_state()`` function:

.. code-block:: python

    from asimov.monitor_states import MonitorState, register_state
    
    class CustomState(MonitorState):
        @property
        def state_name(self):
            return "custom"
        
        def handle(self, context):
            # Custom logic
            return True
    
    # Register the state
    register_state(CustomState())

This approach is useful for:

* Testing custom states before creating a plugin
* Dynamic state registration based on runtime conditions
* Temporary state handlers

**Note:** States registered programmatically must be registered before the monitor
loop runs. Consider registering them in your application's initialization code.

Legacy Registration (Not Recommended)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Direct modification of ``STATE_REGISTRY`` still works but is not recommended:

.. code-block:: python

    from asimov.monitor_states import STATE_REGISTRY, CustomState
    
    # Not recommended - use register_state() instead
    STATE_REGISTRY["custom"] = CustomState()

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

Pipeline-Specific States
^^^^^^^^^^^^^^^^^^^^^^^^

Pipelines can define their own state handlers that override or extend the default state handlers. This enables pipeline-specific behavior for different analysis states:

.. code-block:: python

    from asimov.pipeline import Pipeline
    from asimov.monitor_states import MonitorState
    import click
    
    class BilbyRunningState(MonitorState):
        """Custom running state for Bilby pipeline."""
        
        @property
        def state_name(self):
            return "running"
        
        def handle(self, context):
            analysis = context.analysis
            # Bilby-specific running logic
            if self.check_bilby_progress(analysis):
                click.echo(f"  \t  ● Bilby progress: 75%")
            # Call default behavior
            from asimov.monitor_states import RunningState
            return RunningState().handle(context)
        
        def check_bilby_progress(self, analysis):
            # Check bilby-specific progress indicators
            return True
    
    class Bilby(Pipeline):
        def get_state_handlers(self):
            """Define Bilby-specific state handlers."""
            return {
                "running": BilbyRunningState(),
            }

**How it works:**

1. When monitoring an analysis, the monitor checks if the pipeline defines custom state handlers via ``get_state_handlers()``
2. If a custom handler exists for the current state, it's used
3. If no custom handler exists, the default handler is used
4. This allows pipelines to customize behavior without modifying core code

**Use cases:**

* Pipeline-specific progress monitoring
* Custom completion detection
* Special handling for pipeline-specific error states
* Integration with pipeline-specific tools or services

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

1. **Use entry points for production**: Entry points provide automatic discovery and clean separation
2. **Keep state handlers focused**: Each state should handle only its specific concerns
3. **Use context methods**: Always use ``context.update_ledger()`` rather than direct ledger calls
4. **Handle errors gracefully**: State handlers should catch exceptions and report them appropriately
5. **Test state transitions**: Write unit tests for any custom state handlers
6. **Document custom states**: Add documentation for any new states you introduce
7. **Version your plugins**: If distributing custom states as plugins, use semantic versioning

Complete Plugin Example
^^^^^^^^^^^^^^^^^^^^^^^

Here's a complete example of creating a plugin package with custom states:

**Directory structure:**

.. code-block::

    my-asimov-plugin/
    ├── pyproject.toml
    ├── README.md
    └── my_asimov_plugin/
        ├── __init__.py
        └── states.py

**pyproject.toml:**

.. code-block:: toml

    [build-system]
    requires = ["setuptools>=61.0"]
    build-backend = "setuptools.build_meta"
    
    [project]
    name = "my-asimov-plugin"
    version = "0.1.0"
    description = "Custom analysis states for asimov"
    dependencies = [
        "asimov>=0.7.0",
    ]
    
    [project.entry-points."asimov.monitor.states"]
    validation = "my_asimov_plugin.states:ValidationState"
    calibration = "my_asimov_plugin.states:CalibrationState"

**states.py:**

.. code-block:: python

    from asimov.monitor_states import MonitorState
    import click
    
    class ValidationState(MonitorState):
        """Validate analysis results before marking as complete."""
        
        @property
        def state_name(self):
            return "validation"
        
        def handle(self, context):
            analysis = context.analysis
            click.echo(f"  \t  ● Validating {analysis.name}")
            
            # Run validation checks
            if self.validate_results(analysis):
                analysis.status = "validated"
                click.echo(f"  \t  ✓ Validation passed", fg="green")
            else:
                analysis.status = "validation_failed"
                click.echo(f"  \t  ✗ Validation failed", fg="red")
            
            context.update_ledger()
            return True
        
        def validate_results(self, analysis):
            # Your validation logic here
            return True
    
    class CalibrationState(MonitorState):
        """Handle calibration-specific processing."""
        
        @property
        def state_name(self):
            return "calibration"
        
        def handle(self, context):
            analysis = context.analysis
            # Calibration logic here
            analysis.status = "calibrated"
            context.update_ledger()
            return True

**Installation and usage:**

.. code-block:: bash

    # Install the plugin
    pip install my-asimov-plugin
    
    # Now your custom states are available in asimov
    # Set analysis.status = "validation" to trigger ValidationState

See Also
--------

* :doc:`code-overview` - General asimov architecture
* :doc:`hooks` - Post-monitor hooks
* :doc:`api/asimov` - API reference
