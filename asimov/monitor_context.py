"""
Context management for asimov monitor loop.

This module provides the MonitorContext class that coordinates state handling
and manages analysis monitoring.
"""

from asimov import logger, LOGGER_LEVEL

logger = logger.getChild("monitor_context")
logger.setLevel(LOGGER_LEVEL)


class MonitorContext:
    """
    Context object for monitoring an analysis.
    
    This class encapsulates all the state and operations needed to monitor
    a single analysis, including condor job lookups, ledger updates, and
    state transitions.
    
    Parameters
    ----------
    analysis : Analysis
        The analysis to monitor.
    job_list : CondorJobList
        The condor job list for checking job status.
    ledger : Ledger
        The ledger for updating analysis state.
    dry_run : bool, optional
        If True, don't actually perform updates (default: False).
    analysis_path : str, optional
        Path to the analysis for logging (default: "").
    """
    
    def __init__(self, analysis, job_list, ledger, dry_run=False, analysis_path=""):
        self.analysis = analysis
        self.job_list = job_list
        self.ledger = ledger
        self.dry_run = dry_run
        self.analysis_path = analysis_path
        self._job = None
        self._job_checked = False
    
    @property
    def job_id(self):
        """Get the condor job ID for this analysis."""
        try:
            scheduler = self.analysis.meta.get("scheduler", {})
            if scheduler:
                return scheduler.get("job id")
            return None
        except (AttributeError, TypeError):
            return None
    
    @property
    def job(self):
        """
        Get the condor job object for this analysis.
        
        Returns None if the analysis has no job ID or if the job is not found
        in the condor job list.
        """
        if not self._job_checked:
            job_id = self.job_id
            if job_id and not self.dry_run:
                self._job = self.job_list.jobs.get(job_id)
            self._job_checked = True
        return self._job
    
    def has_condor_job(self):
        """Check if this analysis has a condor job ID."""
        return self.job_id is not None
    
    def clear_job_id(self):
        """Clear the job ID from the analysis metadata."""
        if hasattr(self.analysis, 'meta') and self.analysis.meta:
            if "scheduler" in self.analysis.meta:
                self.analysis.meta["scheduler"]["job id"] = None
    
    def update_ledger(self):
        """Update the analysis in the ledger."""
        if self.dry_run:
            return
        
        # Determine if this is a project analysis or event analysis
        if hasattr(self.analysis, 'event'):
            # Event analysis (production)
            self.ledger.update_event(self.analysis.event)
        else:
            # Project analysis
            self.ledger.update_analysis_in_project_analysis(self.analysis)
        
        self.ledger.save()
    
    def refresh_job_list(self):
        """Refresh the condor job list."""
        if not self.dry_run:
            self.job_list.refresh()
