"""
Custom monitor states for extended functionality.

This module contains custom state handlers that extend the base monitor functionality.
These states are kept separate from the core states and can be moved to their own
package in the future.

These states were inspired by functionality from the v0.6-release branch.
"""

import click
from asimov import logger, LOGGER_LEVEL
from asimov.monitor_states import MonitorState, register_state

logger = logger.getChild("custom_states")
logger.setLevel(LOGGER_LEVEL)


class ReviewState(MonitorState):
    """
    Handle analyses in 'review' state.
    
    This state represents analyses that have completed and are awaiting review
    before being marked as fully complete. This allows for a manual review step
    before finalizing results.
    """
    
    @property
    def state_name(self):
        return "review"
    
    def handle(self, context):
        """Handle analysis in review state."""
        analysis = context.analysis
        
        click.echo(
            "  \t  "
            + click.style("●", "blue")
            + f" {analysis.name} is awaiting review"
        )
        
        # Check if review has been completed
        if hasattr(analysis, 'review') and analysis.review:
            if hasattr(analysis.review, 'status'):
                if analysis.review.status == "approved":
                    analysis.status = "reviewed"
                    context.update_ledger()
                    click.echo(
                        "  \t  "
                        + click.style("✓", "green")
                        + f" {analysis.name} review approved"
                    )
                elif analysis.review.status == "rejected":
                    analysis.status = "review_failed"
                    context.update_ledger()
                    click.echo(
                        "  \t  "
                        + click.style("✗", "red")
                        + f" {analysis.name} review rejected"
                    )
        
        return True


class ReviewedState(MonitorState):
    """
    Handle analyses in 'reviewed' state.
    
    This state represents analyses that have been reviewed and approved.
    They can now proceed to final processing or upload.
    """
    
    @property
    def state_name(self):
        return "reviewed"
    
    def handle(self, context):
        """Handle reviewed analysis."""
        analysis = context.analysis
        
        click.echo(
            "  \t  "
            + click.style("●", "green")
            + f" {analysis.name} has been reviewed and approved"
        )
        
        # Optionally trigger next step
        if hasattr(analysis, 'pipeline') and analysis.pipeline:
            pipe = analysis.pipeline
            if hasattr(pipe, 'after_review'):
                try:
                    pipe.after_review()
                    click.echo(
                        "  \t  "
                        + click.style("●", "green")
                        + f" {analysis.name} post-review processing started"
                    )
                except Exception as e:
                    logger.error(f"Error in post-review processing: {e}")
        
        return True


class UploadingState(MonitorState):
    """
    Handle analyses in 'uploading' state.
    
    This state tracks analyses that are currently being uploaded to
    storage or distribution systems.
    """
    
    @property
    def state_name(self):
        return "uploading"
    
    def handle(self, context):
        """Handle uploading analysis."""
        analysis = context.analysis
        pipe = analysis.pipeline
        
        if not pipe:
            return False
        
        click.echo(
            "  \t  "
            + click.style("●", "cyan")
            + f" {analysis.name} is uploading"
        )
        
        # Check if upload has completed
        if hasattr(pipe, 'detect_upload_completion'):
            if pipe.detect_upload_completion():
                analysis.status = "uploaded"
                context.update_ledger()
                click.echo(
                    "  \t  "
                    + click.style("●", "green")
                    + f" {analysis.name} upload complete"
                )
        
        return True


class UploadedState(MonitorState):
    """
    Handle analyses in 'uploaded' state.
    
    This is a terminal state indicating the analysis has been successfully
    uploaded and is complete.
    """
    
    @property
    def state_name(self):
        return "uploaded"
    
    def handle(self, context):
        """Handle uploaded analysis."""
        analysis = context.analysis
        
        click.echo(
            "  \t  "
            + click.style("●", "green")
            + f" {analysis.name} is uploaded and complete"
        )
        
        return True


class RestartState(MonitorState):
    """
    Handle analyses in 'restart' state.
    
    This state allows analyses to be restarted from a previous checkpoint
    or from the beginning.
    """
    
    @property
    def state_name(self):
        return "restart"
    
    def handle(self, context):
        """Handle restart of analysis."""
        analysis = context.analysis
        pipe = analysis.pipeline
        
        if not pipe:
            return False
        
        click.echo(
            "  \t  "
            + click.style("●", "yellow")
            + f" {analysis.name} is being restarted"
        )
        
        # Clean up old job if exists
        if context.has_condor_job():
            job_id = context.job_id
            if job_id:
                try:
                    pipe.eject_job()
                    click.echo(
                        "  \t  "
                        + click.style("●", "yellow")
                        + f" {analysis.name} old job removed"
                    )
                except Exception as e:
                    logger.error(f"Error removing old job: {e}")
        
        # Reset to ready state to be picked up by submit
        analysis.status = "ready"
        context.update_ledger()
        
        click.echo(
            "  \t  "
            + click.style("●", "green")
            + f" {analysis.name} reset to ready for restart"
        )
        
        return True


class WaitState(MonitorState):
    """
    Handle analyses in 'wait' state.
    
    This state represents analyses that are waiting for dependencies
    or other conditions to be met before they can proceed.
    """
    
    @property
    def state_name(self):
        return "wait"
    
    def handle(self, context):
        """Handle waiting analysis."""
        analysis = context.analysis
        
        click.echo(
            "  \t  "
            + click.style("●", "cyan")
            + f" {analysis.name} is waiting"
        )
        
        # Check if dependencies are met
        if hasattr(analysis, '_needs') and analysis._needs:
            # Check if all dependencies are complete
            all_complete = True
            for need in analysis._needs:
                # This would need actual dependency checking logic
                # For now, just report the wait state
                pass
            
            if all_complete:
                analysis.status = "ready"
                context.update_ledger()
                click.echo(
                    "  \t  "
                    + click.style("●", "green")
                    + f" {analysis.name} dependencies met, now ready"
                )
        
        return True


class CancelledState(MonitorState):
    """
    Handle analyses in 'cancelled' state.
    
    This is a terminal state for analyses that have been cancelled
    and will not be completed.
    """
    
    @property
    def state_name(self):
        return "cancelled"
    
    def handle(self, context):
        """Handle cancelled analysis."""
        analysis = context.analysis
        
        click.echo(
            "  \t  "
            + click.style("●", "red")
            + f" {analysis.name} is cancelled"
        )
        
        # Clean up any running jobs
        if context.has_condor_job():
            pipe = analysis.pipeline
            if pipe:
                try:
                    pipe.eject_job()
                    click.echo(
                        "  \t  "
                        + click.style("●", "red")
                        + f" {analysis.name} job removed"
                    )
                except Exception as e:
                    logger.error(f"Error removing job: {e}")
        
        return True


class ManualState(MonitorState):
    """
    Handle analyses in 'manual' state.
    
    This state represents analyses that require manual intervention
    and should not be automatically managed by the monitor.
    """
    
    @property
    def state_name(self):
        return "manual"
    
    def handle(self, context):
        """Handle manual analysis."""
        analysis = context.analysis
        
        click.echo(
            "  \t  "
            + click.style("●", "yellow")
            + f" {analysis.name} requires manual intervention"
        )
        
        # Don't take any automatic action
        return True


# Register custom states
def register_custom_states():
    """
    Register all custom state handlers.
    
    This function should be called to make the custom states available
    to the monitor system.
    """
    custom_states = [
        ReviewState(),
        ReviewedState(),
        UploadingState(),
        UploadedState(),
        RestartState(),
        WaitState(),
        CancelledState(),
        ManualState(),
    ]
    
    for state in custom_states:
        register_state(state)
        logger.debug(f"Registered custom state: {state.state_name}")


# Auto-register on import
register_custom_states()
