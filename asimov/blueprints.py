"""
Code to handle blueprints and their associated specification.
"""

import pydantic
from pydantic import BaseModel, ConfigDict
import yaml

def select_blueprint_kind(file_path: str) -> type:

    with open(file_path, "r") as f:
        blueprint_data = yaml.safe_load(f)
    
    kind = blueprint_data.pop("kind", None)
    if kind.lower() == "analysis":
        return AnalysisBlueprint, blueprint_data
    else:
        raise ValueError(f"Unknown blueprint kind: {kind}")

class Likelihood(BaseModel):
    """
    Configuration parameters for the likelihood.
    """
    sample_rate: int = pydantic.Field(
        alias="sample rate", 
        description="The sample rate for the likelihood."
        )
    
    model_config = ConfigDict(extra='forbid')

class AnalysisBlueprint(BaseModel):
    """
    A blueprint defining the configuration for an analysis task.
    """
    name: str
    comment: str
    likelihood: Likelihood = pydantic.Field(
        default_factory=Likelihood,
        description="Configuration parameters for the likelihood."
    )
    
    model_config = ConfigDict(extra='forbid')