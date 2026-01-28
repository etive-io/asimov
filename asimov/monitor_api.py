"""
Programmatic API for asimov monitor functionality.

This module provides Python functions to run asimov monitoring operations
programmatically, suitable for use in scripts, Jupyter notebooks, or custom
automation workflows.
"""


from typing import Optional, List
from asimov import condor, logger, LOGGER_LEVEL
from asimov import current_ledger as ledger
from asimov.cli import ACTIVE_STATES
from asimov.monitor_helpers import monitor_analysis

logger = logger.getChild("monitor_api")
logger.setLevel(LOGGER_LEVEL)


def run_monitor(
    *,
    event_filter: Optional[str] = None,
    dry_run: bool = False,
    verbose: bool = False
) -> dict:
    """
    Run the asimov monitor programmatically.
    
    This function performs the same monitoring operations as the CLI command
    `asimov monitor`, but can be called from Python scripts or Jupyter notebooks.
    
    Parameters
    ----------
    event_filter : str, optional
        Filter to specific event name. If None, monitors all events.
    dry_run : bool, optional
        If True, performs monitoring without making any changes (default: False).
    verbose : bool, optional
        If True, prints progress information (default: False).
        
    Returns
    -------
    dict
        Summary of monitoring results with the following keys:
        - 'project_analyses': Number of project analyses monitored
        - 'event_analyses': Number of event analyses monitored  
        - 'total': Total number of analyses monitored
        - 'active': Number of active analyses
        - 'complete': Number of complete analyses
        - 'stuck': Number of stuck analyses
        
    Examples
    --------
    Run monitor on all analyses:
    
    >>> from asimov.monitor_api import run_monitor
    >>> results = run_monitor()
    >>> print(f"Monitored {results['total']} analyses")
    
    Run monitor for a specific event:
    
    >>> results = run_monitor(event_filter="GW150914", verbose=True)
    
    Dry run to see what would happen:
    
    >>> results = run_monitor(dry_run=True, verbose=True)
    
    Use in a Jupyter notebook:
    
    >>> results = run_monitor()
    >>> import pandas as pd
    >>> df = pd.DataFrame([results])
    >>> display(df)
    
    Raises
    ------
    RuntimeError
        If condor scheduler cannot be found.
    """
    if verbose:
        print("Starting asimov monitor...")
    
    logger.info("Running asimov monitor (programmatic API)")
    
    # Initialize results
    results = {
        'project_analyses': 0,
        'event_analyses': 0,
        'total': 0,
        'active': 0,
        'complete': 0,
        'stuck': 0,
    }
    
    # Get condor job listing
    try:
        job_list = condor.CondorJobList()
    except condor.htcondor.HTCondorLocateError:
        raise RuntimeError(
            "Could not find the condor scheduler. "
            "You need to run asimov on a machine which has access to a "
            "condor scheduler or specify the address of a valid scheduler."
        )
    
    # Monitor project analyses
    for analysis in ledger.project_analyses:
        if analysis.status.lower() in ACTIVE_STATES:
            results['project_analyses'] += 1
            results['total'] += 1
            
            if verbose:
                print(f"Monitoring project analysis: {analysis.name} [{analysis.status}]")
            
            monitor_analysis(
                analysis=analysis,
                job_list=job_list,
                ledger=ledger,
                dry_run=dry_run,
                analysis_path=f"project_analyses/{analysis.name}"
            )
            
            # Track status counts
            status_lower = analysis.status.lower()
            if status_lower in ACTIVE_STATES:
                results['active'] += 1
            if status_lower == 'stuck':
                results['stuck'] += 1
            if analysis.status in {"finished", "uploaded"}:
                results['complete'] += 1
    
    # Monitor event analyses
    for event in ledger.get_event(event_filter):
        on_deck = [
            production
            for production in event.productions
            if production.status.lower() in ACTIVE_STATES
        ]
        
        for production in on_deck:
            results['event_analyses'] += 1
            results['total'] += 1
            
            if verbose:
                print(f"Monitoring {event.name}/{production.name} [{production.status}]")
            
            monitor_analysis(
                analysis=production,
                job_list=job_list,
                ledger=ledger,
                dry_run=dry_run,
                analysis_path=f"{event.name}/{production.name}"
            )
            
            # Track status counts
            status_lower = production.status.lower()
            if status_lower in ACTIVE_STATES:
                results['active'] += 1
            if status_lower == 'stuck':
                results['stuck'] += 1
            if production.status in {"finished", "uploaded"}:
                results['complete'] += 1
        
        ledger.update_event(event)
    
    if verbose:
        print(f"\nMonitoring complete:")
        print(f"  Total analyses: {results['total']}")
        print(f"  Project analyses: {results['project_analyses']}")
        print(f"  Event analyses: {results['event_analyses']}")
        print(f"  Active: {results['active']}")
        print(f"  Complete: {results['complete']}")
        print(f"  Stuck: {results['stuck']}")
    
    logger.info(f"Monitored {results['total']} analyses")
    
    return results


def get_analysis_status(*, analysis_name: str = None, event_name: str = None) -> dict:
    """
    Get the current status of one or more analyses.
    
    Parameters
    ----------
    analysis_name : str, optional
        Name of a specific analysis to check.
    event_name : str, optional
        Name of event to filter analyses.
        
    Returns
    -------
    dict
        Dictionary mapping analysis names to their current status.
        
    Examples
    --------
    Get status of all analyses:
    
    >>> from asimov.monitor_api import get_analysis_status
    >>> statuses = get_analysis_status()
    >>> for name, status in statuses.items():
    ...     print(f"{name}: {status}")
    
    Get status for specific event:
    
    >>> statuses = get_analysis_status(event_name="GW150914")
    
    Get status for specific analysis:
    
    >>> status = get_analysis_status(analysis_name="bilby_analysis")
    """
    statuses = {}
    
    # Check project analyses
    for analysis in ledger.project_analyses:
        if analysis_name is None or analysis.name == analysis_name:
            statuses[f"project_analyses/{analysis.name}"] = analysis.status
    
    # Check event analyses
    for event in ledger.get_event(event_name):
        for production in event.productions:
            if analysis_name is None or production.name == analysis_name:
                statuses[f"{event.name}/{production.name}"] = production.status
    
    return statuses


def list_active_analyses() -> List[dict]:
    """
    List all active analyses in the current project.
    
    Returns
    -------
    list of dict
        List of dictionaries with analysis information. Each dict contains:
        - 'name': Analysis name
        - 'type': 'project' or 'event'
        - 'status': Current status
        - 'event': Event name (for event analyses only)
        - 'pipeline': Pipeline name
        
    Examples
    --------
    >>> from asimov.monitor_api import list_active_analyses
    >>> analyses = list_active_analyses()
    >>> for analysis in analyses:
    ...     print(f"{analysis['name']}: {analysis['status']}")
    
    Use with pandas in Jupyter:
    
    >>> import pandas as pd
    >>> analyses = list_active_analyses()
    >>> df = pd.DataFrame(analyses)
    >>> display(df)
    """
    analyses = []
    
    # Project analyses
    for analysis in ledger.project_analyses:
        if analysis.status.lower() in ACTIVE_STATES:
            analyses.append({
                'name': analysis.name,
                'type': 'project',
                'status': analysis.status,
                'pipeline': str(analysis.pipeline),
            })
    
    # Event analyses
    for event in ledger.get_event(None):
        for production in event.productions:
            if production.status.lower() in ACTIVE_STATES:
                analyses.append({
                    'name': production.name,
                    'type': 'event',
                    'status': production.status,
                    'event': event.name,
                    'pipeline': str(production.pipeline),
                })
    
    return analyses
