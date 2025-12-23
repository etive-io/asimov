"""
Prior specification and interface system for asimov.

This module provides a flexible prior specification system that:
1. Validates prior specifications using pydantic
2. Allows pipeline-specific conversion of priors
3. Supports both simple priors and reparameterizations
"""

from typing import Any, Dict, Optional, Union
from pydantic import BaseModel, field_validator, model_validator


class PriorSpecification(BaseModel):
    """
    Specification for a single prior distribution.
    
    This model validates a prior specification from a blueprint.
    Pipelines can then convert this to their own prior format.
    
    Attributes
    ----------
    minimum : float, optional
        The minimum value for the prior
    maximum : float, optional
        The maximum value for the prior
    type : str, optional
        The type/class of the prior distribution
    boundary : str, optional
        The boundary condition for the prior
    alpha : float, optional
        Power law index (for PowerLaw priors)
    mu : float, optional
        Mean (for Gaussian priors)
    sigma : float, optional
        Standard deviation (for Gaussian priors)
    """
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    type: Optional[str] = None
    boundary: Optional[str] = None
    # Additional parameters for different prior types
    alpha: Optional[float] = None
    mu: Optional[float] = None
    sigma: Optional[float] = None
    
    # Allow any additional fields for pipeline-specific settings
    model_config = {"extra": "allow"}
    
    @model_validator(mode='after')
    def validate_min_max(self):
        """Validate that minimum is less than maximum when both are specified."""
        if self.minimum is not None and self.maximum is not None:
            if self.minimum >= self.maximum:
                raise ValueError(f"minimum ({self.minimum}) must be less than maximum ({self.maximum})")
        return self
    
    @field_validator('boundary')
    @classmethod
    def validate_boundary(cls, v):
        """Validate boundary conditions."""
        if v is not None:
            allowed = ['periodic', 'reflective', None, 'None']
            if v not in allowed:
                raise ValueError(f"boundary must be one of {allowed}, got '{v}'")
        return v


class PriorDict(BaseModel):
    """
    A dictionary of prior specifications.
    
    This model validates a complete set of priors from a blueprint.
    It supports both standard parameter priors and special settings.
    
    Attributes
    ----------
    default : str, optional
        The default prior set to use (e.g., "BBHPriorDict")
    """
    default: Optional[str] = None
    
    # Allow arbitrary prior specifications as additional fields
    model_config = {"extra": "allow"}
    
    def get_prior(self, parameter_name: str) -> Optional[PriorSpecification]:
        """
        Get a prior specification for a parameter.
        
        Parameters
        ----------
        parameter_name : str
            The name of the parameter
            
        Returns
        -------
        PriorSpecification or dict
            The prior specification, or None if not found
        """
        # Get the field value directly from model fields
        value = getattr(self, parameter_name, None)
        if value is None:
            # Check in extra fields
            if hasattr(self, '__pydantic_extra__'):
                value = self.__pydantic_extra__.get(parameter_name)
        
        if value is None:
            return None
        elif isinstance(value, dict):
            return PriorSpecification(**value)
        elif isinstance(value, PriorSpecification):
            return value
        else:
            return value
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to a plain dictionary.
        
        Returns
        -------
        dict
            Dictionary representation of all priors
        """
        result = {}
        if self.default is not None:
            result['default'] = self.default
        
        # Add all extra fields
        if hasattr(self, '__pydantic_extra__'):
            for key, value in self.__pydantic_extra__.items():
                if isinstance(value, PriorSpecification):
                    result[key] = value.model_dump(exclude_none=True)
                else:
                    result[key] = value
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PriorDict":
        """
        Create a PriorDict from a plain dictionary.
        
        Parameters
        ----------
        data : dict
            Dictionary of prior specifications
            
        Returns
        -------
        PriorDict
            Validated prior dictionary
        """
        return cls(**data)


class Reparameterization(BaseModel):
    """
    Specification for a parameter reparameterization.
    
    This allows pipelines like pycbc to specify alternative
    parameterizations of the signal.
    
    Attributes
    ----------
    from_parameters : list of str
        The original parameters
    to_parameters : list of str
        The new parameters after transformation
    transform : str, optional
        The name of the transformation function
    """
    from_parameters: list[str]
    to_parameters: list[str]
    transform: Optional[str] = None
    
    # Allow any additional fields for pipeline-specific settings
    model_config = {"extra": "allow"}


class PriorInterface:
    """
    Base class for pipeline-specific prior interfaces.
    
    Each pipeline should subclass this and implement the
    conversion methods to transform asimov priors into
    pipeline-specific formats.
    """
    
    def __init__(self, prior_dict: Optional[Union[Dict, PriorDict]] = None):
        """
        Initialize the prior interface.
        
        Parameters
        ----------
        prior_dict : dict or PriorDict, optional
            The prior specification from the blueprint
        """
        if prior_dict is None:
            self.prior_dict = None
        elif isinstance(prior_dict, PriorDict):
            self.prior_dict = prior_dict
        elif isinstance(prior_dict, dict):
            self.prior_dict = PriorDict.from_dict(prior_dict)
        else:
            raise TypeError(f"prior_dict must be dict or PriorDict, got {type(prior_dict)}")
    
    def convert(self) -> Any:
        """
        Convert asimov priors to pipeline-specific format.
        
        This method should be overridden by pipeline-specific interfaces.
        
        Returns
        -------
        Any
            Pipeline-specific prior representation
        """
        raise NotImplementedError("Subclasses must implement convert()")
    
    def validate(self) -> bool:
        """
        Validate the prior specification for this pipeline.
        
        Returns
        -------
        bool
            True if valid, raises exception otherwise
        """
        # Base validation is handled by pydantic
        return True



