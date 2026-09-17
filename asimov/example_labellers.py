"""
Example labeller implementations for asimov.

These examples demonstrate how to create labellers for automatically
marking analyses as interesting or assigning other metadata during monitoring.
"""

from asimov.labellers import Labeller
from asimov import logger, LOGGER_LEVEL

logger = logger.getChild("example_labellers")
logger.setLevel(LOGGER_LEVEL)


class AlwaysInterestingLabeller(Labeller):
    """
    Example labeller that marks all analyses as interesting.
    
    This is a simple demonstration labeller that always returns
    the "interesting" label as True for any analysis.
    
    Examples
    --------
    Register and use this labeller:
    
    >>> from asimov.labellers import register_labeller
    >>> from asimov.example_labellers import AlwaysInterestingLabeller
    >>> register_labeller(AlwaysInterestingLabeller())
    """
    
    @property
    def name(self):
        return "always_interesting"
    
    def label(self, analysis, context=None):
        """Mark all analyses as interesting."""
        return {"interesting": True}


class PipelineInterestLabeller(Labeller):
    """
    Example labeller that marks specific pipelines as interesting.
    
    This labeller allows you to specify which pipeline types should
    be marked as interesting.
    
    Parameters
    ----------
    interesting_pipelines : list of str
        List of pipeline names that should be marked as interesting.
        
    Examples
    --------
    Create a labeller for bilby and RIFT pipelines:
    
    >>> labeller = PipelineInterestLabeller(["bilby", "RIFT"])
    >>> register_labeller(labeller)
    """
    
    def __init__(self, interesting_pipelines=None):
        """
        Initialize the pipeline interest labeller.
        
        Parameters
        ----------
        interesting_pipelines : list of str, optional
            List of pipeline names to mark as interesting.
            Defaults to ["bilby", "bilby_pipe"].
        """
        if interesting_pipelines is None:
            interesting_pipelines = ["bilby", "bilby_pipe"]
        self.interesting_pipelines = [p.lower() for p in interesting_pipelines]
    
    @property
    def name(self):
        return "pipeline_interest"
    
    def label(self, analysis, context=None):
        """
        Mark analysis as interesting if it uses an interesting pipeline.
        
        Returns
        -------
        dict
            Dictionary with "interesting" label set to True/False based on pipeline.
        """
        if not hasattr(analysis, 'pipeline'):
            return {}
        
        pipeline_name = str(analysis.pipeline).lower()
        
        for interesting_pipeline in self.interesting_pipelines:
            if interesting_pipeline in pipeline_name:
                logger.debug(
                    f"Marking {analysis.name} as interesting (pipeline: {pipeline_name})"
                )
                return {"interesting": True}
        
        return {"interesting": False}


class FinishedAnalysisLabeller(Labeller):
    """
    Example labeller that only labels finished analyses as interesting.
    
    This demonstrates using the should_label method to control when
    a labeller runs.
    
    Examples
    --------
    >>> labeller = FinishedAnalysisLabeller()
    >>> register_labeller(labeller)
    """
    
    @property
    def name(self):
        return "finished_interest"
    
    def should_label(self, analysis, context=None):
        """Only label analyses that are finished."""
        return analysis.status in {"finished", "uploaded"}
    
    def label(self, analysis, context=None):
        """Mark finished analyses as interesting."""
        return {"interesting": True}


class ConditionalLabeller(Labeller):
    """
    Example labeller that uses custom logic to determine interest.
    
    This demonstrates a more complex labeller that can use custom
    criteria to determine if an analysis is interesting.
    
    Parameters
    ----------
    condition_func : callable
        A function that takes an analysis and returns True if it's interesting.
        
    Examples
    --------
    Create a labeller with custom logic:
    
    >>> def is_high_mass(analysis):
    ...     if hasattr(analysis, 'meta') and 'mass' in analysis.meta:
    ...         return analysis.meta['mass'] > 50
    ...     return False
    >>> labeller = ConditionalLabeller(is_high_mass)
    >>> register_labeller(labeller)
    """
    
    def __init__(self, condition_func=None, labeller_name="conditional"):
        """
        Initialize the conditional labeller.
        
        Parameters
        ----------
        condition_func : callable, optional
            Function that takes an analysis and returns bool.
            Defaults to always returning True.
        labeller_name : str, optional
            Name for this labeller instance.
        """
        self._name = labeller_name
        if condition_func is None:
            self.condition_func = lambda analysis: True
        else:
            self.condition_func = condition_func
    
    @property
    def name(self):
        return self._name
    
    def label(self, analysis, context=None):
        """
        Apply custom condition to determine interest.
        
        Returns
        -------
        dict
            Dictionary with "interesting" label based on condition_func result.
        """
        try:
            is_interesting = self.condition_func(analysis)
            return {"interesting": bool(is_interesting)}
        except Exception as e:
            logger.warning(
                f"Error evaluating condition for {analysis.name}: {e}"
            )
            return {}


# Example factory functions for common use cases

def create_pipeline_labeller(pipelines):
    """
    Create and register a pipeline-based interest labeller.
    
    Parameters
    ----------
    pipelines : list of str
        List of pipeline names to mark as interesting.
        
    Returns
    -------
    PipelineInterestLabeller
        The created labeller instance.
        
    Examples
    --------
    >>> from asimov.labellers import register_labeller
    >>> labeller = create_pipeline_labeller(["bilby", "RIFT"])
    >>> register_labeller(labeller)
    """
    return PipelineInterestLabeller(interesting_pipelines=pipelines)


def create_conditional_labeller(condition_func, name="conditional"):
    """
    Create a conditional labeller with custom logic.
    
    Parameters
    ----------
    condition_func : callable
        Function that takes an analysis and returns True if interesting.
    name : str, optional
        Name for the labeller.
        
    Returns
    -------
    ConditionalLabeller
        The created labeller instance.
        
    Examples
    --------
    >>> from asimov.labellers import register_labeller
    >>> def my_condition(analysis):
    ...     return "important" in analysis.name
    >>> labeller = create_conditional_labeller(my_condition, "important_name")
    >>> register_labeller(labeller)
    """
    return ConditionalLabeller(condition_func=condition_func, labeller_name=name)
