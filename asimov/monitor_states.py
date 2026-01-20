"""
State machine implementation for asimov monitor loop.

This module provides a clean state pattern implementation to replace the
hard-coded if-elif chains in the monitor loop.
"""

from abc import ABC, abstractmethod
import configparser
import sys
import click
from asimov import logger, LOGGER_LEVEL, config, condor

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points

logger = logger.getChild("monitor_states")
logger.setLevel(LOGGER_LEVEL)


class MonitorState(ABC):
    """
    Abstract base class for monitor states.
    
    Each concrete state handles the monitoring logic for analyses in that state.
    """
    
    @abstractmethod
    def handle(self, context):
        """
        Handle the monitoring logic for an analysis in this state.
        
        Parameters
        ----------
        context : MonitorContext
            The monitoring context containing the analysis, job, and other info.
            
        Returns
        -------
        bool
            True if the state was handled successfully, False otherwise.
        """
        pass
    
    @property
    @abstractmethod
    def state_name(self):
        """Return the name of this state."""
        pass


class ReadyState(MonitorState):
    """Handle analyses in 'ready' state (not yet started)."""
    
    @property
    def state_name(self):
        return "ready"
    
    def handle(self, context):
        """Ready analyses are not yet started, just report status."""
        click.secho(f"  \t  ● {context.analysis.status.lower()}", fg="green")
        logger.debug(f"Ready analysis: {context.analysis_path}")
        return True


class StopState(MonitorState):
    """Handle analyses that need to be stopped."""
    
    @property
    def state_name(self):
        return "stop"
    
    def handle(self, context):
        """Stop the analysis job on the scheduler."""
        pipe = context.analysis.pipeline
        logger.debug(f"Stop analysis: {context.analysis_path}")
        
        if not context.dry_run:
            pipe.eject_job()
            context.analysis.status = "stopped"
            context.update_ledger()
            click.secho("  \t  Stopped", fg="red")
        else:
            click.echo(f"\t\t{context.analysis.name} --> stopped")
        
        return True


class RunningState(MonitorState):
    """Handle analyses in 'running' state."""
    
    @property
    def state_name(self):
        return "running"
    
    def handle(self, context):
        """Check if job is still running or has completed."""


        
        # Check if job has a condor ID
        if context.has_condor_job():
            return self._handle_condor_job(context)
        else:
            return self._handle_no_condor_job(context)
    
    def _handle_condor_job(self, context):
        """Handle analysis with a condor job."""
        job = context.job
        analysis = context.analysis
        
        if job is None:
            # Job not found, may have completed or been evicted
            return self._handle_no_condor_job(context)
        
        if job.status.lower() == "idle":
            click.echo(
                "  \t  "
                + click.style("●", "green")
                + f" {analysis.name} is in the queue (condor id: {context.job_id})"
            )
            return True
            
        elif job.status.lower() == "running":
            click.echo(
                "  \t  "
                + click.style("●", "green")
                + f" {analysis.name} is running (condor id: {context.job_id})"
            )
            if "profiling" not in analysis.meta:
                analysis.meta["profiling"] = {}
            if hasattr(analysis.pipeline, "while_running"):
                analysis.pipeline.while_running()
            analysis.status = "running"
            context.update_ledger()
            return True
            
        elif job.status.lower() == "completed":
            pipe = analysis.pipeline
            pipe.after_completion()
            click.echo(
                "  \t  "
                + click.style("●", "green")
                + f" {analysis.name} has finished and post-processing has been started"
            )
            context.refresh_job_list()
            return True
            
        elif job.status.lower() == "held":
            click.echo(
                "  \t  "
                + click.style("●", "yellow")
                + f" {analysis.name} is held on the scheduler"
                + f" (condor id: {context.job_id})"
            )
            analysis.status = "stuck"
            context.update_ledger()
            return True
            
        return False
    
    def _handle_no_condor_job(self, context):
        """Handle analysis without a condor job (may have completed)."""
        analysis = context.analysis
        pipe = analysis.pipeline
        
        if not pipe:
            return False
        
        # Check if job has completed
        if pipe.detect_completion():
            if "profiling" not in analysis.meta:
                analysis.meta["profiling"] = {}
            
            # Only collect profiling if we have a valid job ID
            job_id = context.job_id
            if job_id:
                try:
                    config.get("condor", "scheduler")
                    analysis.meta["profiling"] = condor.collect_history(job_id)
                    context.clear_job_id()
                    context.update_ledger()
                except (configparser.NoOptionError, configparser.NoSectionError):
                    logger.warning(
                        "Could not collect condor profiling data as no "
                        + "scheduler was specified in the config file."
                    )
                except ValueError as e:
                    logger.error("Could not collect condor profiling data.")
                    logger.exception(e)
            
            analysis.status = "finished"
            context.update_ledger()
            pipe.after_completion()
            click.secho(
                f"  \t  ● {analysis.name} - Completion detected",
                fg="green",
            )
            context.refresh_job_list()
            return True
        else:
            # Job may have been evicted
            click.echo(
                "  \t  "
                + click.style("●", "yellow")
                + f" {analysis.name} is stuck; attempting a rescue"
            )
            try:
                pipe.resurrect()
                return True
            except Exception:
                analysis.status = "stuck"
                click.echo(
                    "  \t  "
                    + click.style("●", "red")
                    + f" {analysis.name} is stuck; automatic rescue was not possible"
                )
                context.update_ledger()
                return False


class FinishedState(MonitorState):
    """Handle analyses in 'finished' state."""
    
    @property
    def state_name(self):
        return "finished"
    
    def handle(self, context):
        """Trigger post-processing for finished analyses."""
        pipe = context.analysis.pipeline
        
        if pipe:
            pipe.after_completion()
            click.echo(
                "  \t  "
                + click.style("●", "green")
                + f" {context.analysis.name} has finished and post-processing has been started"
            )
            context.refresh_job_list()
        
        return True


class ProcessingState(MonitorState):
    """Handle analyses in 'processing' state."""
    
    @property
    def state_name(self):
        return "processing"
    
    def handle(self, context):
        """Check if post-processing has completed."""
        pipe = context.analysis.pipeline
        
        if not pipe:
            return False
        
        # Check if processing has completed
        if pipe.detect_completion_processing():
            try:
                pipe.after_processing()
                click.echo(
                    "  \t  "
                    + click.style("●", "green")
                    + f" {context.analysis.name} has been finalised and stored"
                )
                return True
            except ValueError as e:
                click.echo(e)
                return False
        else:
            # Also check if the job has just completed
            if pipe.detect_completion():
                click.echo(
                    "  \t  "
                    + click.style("●", "green")
                    + f" {context.analysis.name} has finished and post-processing is running"
                )
                return True
            else:
                click.echo(
                    "  \t  "
                    + click.style("●", "green")
                    + f" {context.analysis.name} has finished and post-processing"
                    + f" is stuck ({context.job_id})"
                )
                return False


class StuckState(MonitorState):
    """Handle analyses in 'stuck' state."""
    
    @property
    def state_name(self):
        return "stuck"
    
    def handle(self, context):
        """Report that the analysis is stuck."""
        click.echo(
            "  \t  "
            + click.style("●", "yellow")
            + f" {context.analysis.name} is stuck"
        )
        return True


class StoppedState(MonitorState):
    """Handle analyses in 'stopped' state."""
    
    @property
    def state_name(self):
        return "stopped"
    
    def handle(self, context):
        """Stopped analyses are not active, just report status."""
        click.echo(
            "  \t  "
            + click.style("●", "red")
            + f" {context.analysis.name} is stopped"
        )
        return True


# State registry for mapping status strings to state handlers
STATE_REGISTRY = {
    "ready": ReadyState(),
    "stop": StopState(),
    "running": RunningState(),
    "finished": FinishedState(),
    "processing": ProcessingState(),
    "stuck": StuckState(),
    "stopped": StoppedState(),
}


def register_state(state_handler):
    """
    Register a custom state handler.
    
    This function allows custom state handlers to be registered at runtime,
    either programmatically or via entry points.
    
    Parameters
    ----------
    state_handler : MonitorState
        An instance of a MonitorState subclass to register.
        
    Examples
    --------
    >>> class CustomState(MonitorState):
    ...     @property
    ...     def state_name(self):
    ...         return "custom"
    ...     def handle(self, context):
    ...         return True
    >>> register_state(CustomState())
    """
    if not isinstance(state_handler, MonitorState):
        raise TypeError(
            f"State handler must be an instance of MonitorState, "
            f"got {type(state_handler).__name__}"
        )
    
    state_name = state_handler.state_name
    if state_name in STATE_REGISTRY:
        logger.warning(
            f"Overwriting existing state handler for '{state_name}'"
        )
    
    STATE_REGISTRY[state_name] = state_handler
    logger.debug(f"Registered state handler for '{state_name}'")


def discover_custom_states():
    """
    Discover and register custom state handlers via entry points.
    
    This function looks for entry points in the 'asimov.monitor.states' group
    and automatically registers any custom state handlers defined by plugins.
    
    Entry points should return an instance of a MonitorState subclass.
    
    Examples
    --------
    In your package's setup.py or pyproject.toml:
    
    .. code-block:: python
    
        # setup.py
        entry_points={
            'asimov.monitor.states': [
                'validation = mypackage.states:ValidationState',
            ]
        }
        
    Or in pyproject.toml:
    
    .. code-block:: toml
    
        [project.entry-points."asimov.monitor.states"]
        validation = "mypackage.states:ValidationState"
    """
    try:
        discovered_states = entry_points(group="asimov.monitor.states")
        
        for state_entry in discovered_states:
            try:
                # Load the state handler class or instance
                state_obj = state_entry.load()
                
                # If it's a class, instantiate it
                if isinstance(state_obj, type):
                    state_handler = state_obj()
                else:
                    state_handler = state_obj
                
                # Register the state
                register_state(state_handler)
                logger.info(
                    f"Discovered and registered custom state '{state_entry.name}' "
                    f"from {state_entry.value}"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to load custom state '{state_entry.name}': {e}"
                )
    except Exception as e:
        logger.debug(f"No custom states discovered: {e}")


def get_state_handler(status, pipeline=None):
    """
    Get the appropriate state handler for a given status.
    
    This function first checks for pipeline-specific state handlers if a
    pipeline is provided, then falls back to the global state registry.
    This allows pipelines to define custom behavior for specific states.
    
    Parameters
    ----------
    status : str
        The status string (e.g., "running", "finished").
    pipeline : Pipeline, optional
        The pipeline instance. If provided, pipeline-specific state handlers
        will be checked first before falling back to default handlers.
        
    Returns
    -------
    MonitorState
        The state handler for this status, or None if not found.
        
    Examples
    --------
    Get default state handler:
    
    >>> handler = get_state_handler("running")
    
    Get pipeline-specific handler with fallback:
    
    >>> handler = get_state_handler("running", pipeline=bilby_pipeline)
    """
    status_lower = status.lower()
    
    # First, check for pipeline-specific state handlers
    if pipeline is not None:
        try:
            pipeline_handlers = pipeline.get_state_handlers()
            if pipeline_handlers and status_lower in pipeline_handlers:
                logger.debug(
                    f"Using pipeline-specific handler for state '{status_lower}' "
                    f"from {pipeline.name}"
                )
                return pipeline_handlers[status_lower]
        except Exception as e:
            logger.warning(
                f"Error getting pipeline state handlers from {pipeline.name}: {e}"
            )
    
    # Fall back to global state registry
    return STATE_REGISTRY.get(status_lower)


# Discover and register custom states on module import
discover_custom_states()

# Import custom states to ensure they're registered
try:
    from asimov import custom_states
    logger.debug("Custom states module imported and registered")
except ImportError:
    logger.debug("Custom states module not available")
