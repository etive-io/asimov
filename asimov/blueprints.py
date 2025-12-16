"""
Code to handle blueprints and their associated specification.
"""

import pydantic
from pydantic import BaseModel, ConfigDict, model_validator
import yaml

def select_blueprint_kind(file_path: str) -> type:

    with open(file_path, "r") as f:
        blueprint_data = yaml.safe_load(f)
    
    kind = blueprint_data.pop("kind", None)
    if kind.lower() == "analysis":
        return AnalysisBlueprint, blueprint_data
    else:
        raise ValueError(f"Unknown blueprint kind: {kind}")

class Blueprint(BaseModel):
    pass

class Likelihood(Blueprint):
    """
    Configuration parameters for the likelihood.
    """
    sample_rate: int = pydantic.Field(
        alias="sample rate", 
        description="The sample rate for the likelihood."
        )
    psd_length: int | None = pydantic.Field(
        alias="psd length", 
        description="The length of the data segment used to calculate the PSD. Normally, and by default, this should be the same as the sample rate.",
        default=None,
    )
    time_domain_source_model: str | None = pydantic.Field(
        alias="time domain source model", 
        description="The time domain source model to use in the likelihood.",
        default=None,
    )
    frequency_domain_source_model: str | None = pydantic.Field(
        alias="frequency domain source model", 
        description="The frequency domain source model to use in the likelihood.",
        default=None,
    )
    coherence_test: bool | None = pydantic.Field(
        alias="coherence test", 
        description="Whether to perform a coherence test in the likelihood.",
        default=None,
    )
    post_trigger_time: float | None = pydantic.Field(
        alias="post trigger time", 
        description="The amount of time after the trigger to include in the likelihood (in seconds).",
        default=None,
    )
    roll_off_time: float | None = pydantic.Field(
        alias="roll off",
        description="The amount of time to roll off the window (in seconds).",
        default=1.0,
    )
    time_reference: str | None = pydantic.Field(
        alias="time reference", 
        description="The time reference for the likelihood.",
        default=None,
    )
    reference_frame: str | None = pydantic.Field(
        alias="reference frame",
        description="The reference frame for the likelihood.",
        default=None,
    )
    type: str | None = pydantic.Field(
        alias="type", 
        description="The type of likelihood to use.",
        default=None,
    )
    kwargs: dict | None = pydantic.Field(
        alias="kwargs", 
        description="Additional keyword arguments for the likelihood.",
        default=None,
    )

    
    model_config = ConfigDict(extra='forbid')

    @model_validator(mode="after")
    def default_psd_length(self) -> "Likelihood":
        if self.psd_length is None:
            self.psd_length = self.sample_rate
        return self

class Waveform(Blueprint):
    """
    A blueprint defining the configuration for a waveform model.
    """
    enforce_signal_duration: bool | None = pydantic.Field(
        alias="enforce signal duration",
        description="Whether to enforce the signal duration in the waveform model.",
        default=None,
    )
    generator: str | None = pydantic.Field(
        alias="generator",
        description="The waveform generator to use.",
        default=None,
    )
    reference_frequency: float | None = pydantic.Field(
        alias="reference frequency",
        description="The reference frequency for the waveform model.",
        default=None,
    )
    start_frequency: float | None = pydantic.Field(
        alias="start frequency",
        description="The start frequency for the waveform model.",
        default=None,
    )
    conversion_function: str | None = pydantic.Field(
        alias="conversion function",
        description="The conversion function to use in the waveform model.",
        default=None,
    )
    approximant: str | None = pydantic.Field(
        alias="approximant",
        description="The approximant to use in the waveform model.",
        default=None,
    )
    pn_spin_order: int | None = pydantic.Field(
        alias="pn spin order",
        description="The post-Newtonian spin order to use in the waveform model.",
        default=None,
    )
    pn_phase_order: int | None = pydantic.Field(
        alias="pn phase order",
        description="The post-Newtonian phase order to use in the waveform model.",
        default=None,
    )   
    pn_amplitude_order: int | None = pydantic.Field(
        alias="pn amplitude order",
        description="The post-Newtonian amplitude order to use in the waveform model.",
        default=None,
    )
    file: str | None = pydantic.Field(
        alias="file",
        description="The file containing an NR waveform.",
        default=None,
    )
    arguments: dict | None = pydantic.Field(
        alias="arguments",
        description="Additional arguments for the waveform model.",
        default=None,
    )
    mode_array: list[str] | None = pydantic.Field(
        alias="mode array",
        description="The mode array to use in the waveform model.",
        default=None,
    )


    model_config = ConfigDict(extra='forbid')

class AnalysisBlueprint(Blueprint):
    """
    A blueprint defining the configuration for an analysis task.
    """
    name: str
    comment: str
    likelihood: Likelihood | None = pydantic.Field(
        default=None,
        description="Configuration parameters for the likelihood."
    )
    waveform: Waveform | None = pydantic.Field(
        default=None,
        description="Configuration parameters for the waveform model."
    )
    
    model_config = ConfigDict(extra='forbid')