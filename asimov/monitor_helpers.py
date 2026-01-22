"""
Helper functions for the asimov monitor loop.

This module provides reusable functions to monitor analyses,
replacing the duplicated code in the monitor command.
"""

import click
from asimov import logger, LOGGER_LEVEL
from asimov.cli import ACTIVE_STATES
from asimov.monitor_states import get_state_handler
from asimov.monitor_context import MonitorContext

logger = logger.getChild("monitor_helpers")
logger.setLevel(LOGGER_LEVEL)


def monitor_analysis(analysis, job_list, ledger, dry_run=False, analysis_path=None):
    """
    Monitor a single analysis and handle its state transitions.
    
    This function replaces the duplicated monitoring logic for both
    event analyses and project analyses.
    
    Parameters
    ----------
    analysis : Analysis
        The analysis to monitor (can be SimpleAnalysis, ProjectAnalysis, etc.).
    job_list : CondorJobList
        The condor job list for checking job status.
    ledger : Ledger
        The ledger for updating analysis state.
    dry_run : bool, optional
        If True, don't actually perform updates (default: False).
    analysis_path : str, optional
        Path to the analysis for logging (default: None).
        
    Returns
    -------
    bool
        True if monitoring was successful, False otherwise.
    """
    
    # Create analysis path for logging
    if analysis_path is None:
        if hasattr(analysis, 'event'):
            analysis_path = f"{analysis.event.name}/{analysis.name}"
        else:
            analysis_path = f"project_analyses/{analysis.name}"
    
    # Display analysis header
    click.echo(
        "\t- "
        + click.style(f"{analysis.name}", bold=True)
        + click.style(f"[{analysis.pipeline}]", fg="green")
    )
    
    # Skip inactive analyses
    if analysis.status.lower() not in ACTIVE_STATES:
        logger.debug(f"Skipping inactive analysis: {analysis_path}")
        return True
    
    logger.debug(f"Monitoring analysis: {analysis_path}")
    
    # Create monitoring context
    context = MonitorContext(
        analysis=analysis,
        job_list=job_list,
        ledger=ledger,
        dry_run=dry_run,
        analysis_path=analysis_path
    )
    
    # Get the appropriate state handler (pipeline-specific if available)
    pipeline = getattr(analysis, 'pipeline', None)
    state_handler = get_state_handler(analysis.status, pipeline=pipeline)
    
    if state_handler:
        # Use the state handler to process this analysis
        # Note: State handlers are responsible for calling context.update_ledger()
        # when they make changes that need to be persisted
        try:
            success = state_handler.handle(context)
            return success
        except Exception as e:
            logger.exception(f"Error handling state {analysis.status} for {analysis_path}")
            click.echo(
                "  \t  "
                + click.style("●", "red")
                + f" Error processing {analysis.name}: {e}"
            )
            return False
    else:
        logger.warning(f"No state handler for status: {analysis.status}")
        click.echo(
            "  \t  "
            + click.style("●", "yellow")
            + f" Unknown status: {analysis.status}"
        )
        return False


def monitor_analyses_list(analyses, job_list, ledger, dry_run=False, label="analyses"):
    """
    Monitor a list of analyses.
    
    Parameters
    ----------
    analyses : list
        List of analyses to monitor.
    job_list : CondorJobList
        The condor job list for checking job status.
    ledger : Ledger
        The ledger for updating analysis state.
    dry_run : bool, optional
        If True, don't actually perform updates (default: False).
    label : str, optional
        Label for the analyses being monitored (default: "analyses").
        
    Returns
    -------
    dict
        Statistics about the monitored analyses (counts by status).
    """
    
    stats = {
        "total": 0,
        "running": 0,
        "stuck": 0,
        "finished": 0,
        "ready": 0,
    }
    
    for analysis in analyses:
        if analysis.status.lower() in ACTIVE_STATES:
            logger.debug(f"Available {label}: {analysis.name}")
            monitor_analysis(analysis, job_list, ledger, dry_run)
            
            stats["total"] += 1
            status = analysis.status.lower()
            if status in stats:
                stats[status] += 1
    
    return stats
