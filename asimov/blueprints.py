"""
Code to handle blueprints and their associated specification.
"""

from typing import Dict, List, Optional, Tuple, Type

import pydantic
from pydantic import BaseModel, ConfigDict, model_validator
import yaml

def select_blueprint_kind(file_path: str) -> Tuple[Type, dict]:

    with open(file_path, "r") as f:
        blueprint_data = yaml.safe_load(f)

    kind = blueprint_data.pop("kind", None)
    if kind is None:
        raise ValueError("Blueprint 'kind' is missing from the blueprint data.")
    if kind.lower() == "analysis":
        return Analysis, blueprint_data
    elif kind.lower() in {"event", "subject"}:
        return Subject, blueprint_data
    else:
        raise ValueError(f"Unknown blueprint kind: {kind}")

class Blueprint(BaseModel):
    pass


class Waveform(Blueprint):
    """
    A blueprint defining the configuration for a waveform model.
    """
    enforce_signal_duration: Optional[bool] = pydantic.Field(
        alias="enforce signal duration",
        description="Whether to enforce the signal duration in the waveform model.",
        default=None,
    )
    generator: Optional[str] = pydantic.Field(
        alias="generator",
        description="The waveform generator to use.",
        default=None,
    )
    reference_frequency: Optional[float] = pydantic.Field(
        alias="reference frequency",
        description="The reference frequency for the waveform model.",
        default=None,
    )
    start_frequency: Optional[float] = pydantic.Field(
        alias="start frequency",
        description="The start frequency for the waveform model.",
        default=None,
    )
    conversion_function: Optional[str] = pydantic.Field(
        alias="conversion function",
        description="The conversion function to use in the waveform model.",
        default=None,
    )
    approximant: Optional[str] = pydantic.Field(
        alias="approximant",
        description="The approximant to use in the waveform model.",
        default=None,
    )
    pn_spin_order: Optional[int] = pydantic.Field(
        alias="pn spin order",
        description="The post-Newtonian spin order to use in the waveform model.",
        default=None,
    )
    pn_phase_order: Optional[int] = pydantic.Field(
        alias="pn phase order",
        description="The post-Newtonian phase order to use in the waveform model.",
        default=None,
    )
    pn_amplitude_order: Optional[int] = pydantic.Field(
        alias="pn amplitude order",
        description="The post-Newtonian amplitude order to use in the waveform model.",
        default=None,
    )
    file: Optional[str] = pydantic.Field(
        alias="file",
        description="The file containing an NR waveform.",
        default=None,
    )
    arguments: Optional[dict] = pydantic.Field(
        alias="arguments",
        description="Additional arguments for the waveform model.",
        default=None,
    )
    mode_array: Optional[List[str]] = pydantic.Field(
        alias="mode array",
        description="The mode array to use in the waveform model.",
        default=None,
    )


    model_config = ConfigDict(extra='forbid')

class Calibration(Blueprint):
    """
    A blueprint defining the configuration for calibration.
    """
    sample: Optional[bool] = pydantic.Field(
        default=None,
        description="Whether to sample calibration parameters. If set to True the likelihood will sample over the calibration uncertainty."
    )

    model_config = ConfigDict(extra='forbid')

class Marginalisation(Blueprint):
    """
    A blueprint defining the configuration for marginalisation.
    """
    time: Optional[bool] = pydantic.Field(
        default=None,
        description="Whether to marginalise over time."
    )
    phase: Optional[bool] = pydantic.Field(
        default=None,
        description="Whether to marginalise over phase."
    )
    distance: Optional[bool] = pydantic.Field(
        default=None,
        description="Whether to marginalise over distance."
    )
    calibration: Optional[bool] = pydantic.Field(
        default=None,
        alias="Calibration",
        description="Whether to marginalise over calibration."
    )

    model_config = ConfigDict(extra='forbid')

class ROQ(Blueprint):
    """
    A blueprint defining the configuration for Reduced Order Quadrature (ROQ).
    """
    folder: Optional[str] = pydantic.Field(
        default=None,
        description="The folder containing the ROQ basis."
    )
    weights: Optional[str] = pydantic.Field(
        default=None,
        description="The file containing the ROQ weights."
    )
    scale: Optional[float] = pydantic.Field(
        default=None,
        description="The scale factor for the ROQ."
    )
    linear_matrix: Optional[str] = pydantic.Field(
        default=None,
        alias="linear matrix",
        description="The file containing the linear matrix for the ROQ."
    )
    quadratic_matrix: Optional[str] = pydantic.Field(
        default=None,
        alias="quadratic matrix",
        description="The file containing the quadratic matrix for the ROQ."
    )

    model_config = ConfigDict(extra='forbid')

class RelativeBinning(Blueprint):
    """
    A blueprint defining the configuration for Relative Binning.
    """
    fiducial_parameters: Optional[dict] = pydantic.Field(
        default=None,
        alias="fiducial parameters",
        description="The fiducial parameters for relative binning."
    )
    update_fiducial_parameters: Optional[bool] = pydantic.Field(
        default=None,
        alias="update fiducial parameters",
        description="Whether to update the fiducial parameters during the analysis."
    )
    epsilon: Optional[float] = pydantic.Field(
        default=None,
        description="The epsilon parameter for relative binning."
    )

    model_config = ConfigDict(extra='forbid')


class Likelihood(Blueprint):
    """
    Configuration parameters for the likelihood.
    """
    sample_rate: int = pydantic.Field(
        alias="sample rate",
        description="The sample rate for the likelihood."
        )
    psd_length: Optional[int] = pydantic.Field(
        alias="psd length",
        description="The length of the data segment used to calculate the PSD. Normally, and by default, this should be the same as the sample rate.",
        default=None,
    )
    time_domain_source_model: Optional[str] = pydantic.Field(
        alias="time domain source model",
        description="The time domain source model to use in the likelihood.",
        default=None,
    )
    frequency_domain_source_model: Optional[str] = pydantic.Field(
        alias="frequency domain source model",
        description="The frequency domain source model to use in the likelihood.",
        default=None,
    )
    coherence_test: Optional[bool] = pydantic.Field(
        alias="coherence test",
        description="Whether to perform a coherence test in the likelihood.",
        default=None,
    )
    post_trigger_time: Optional[float] = pydantic.Field(
        alias="post trigger time",
        description="The amount of time after the trigger to include in the likelihood (in seconds).",
        default=None,
    )
    roll_off_time: Optional[float] = pydantic.Field(
        alias="roll off",
        description="The amount of time to roll off the window (in seconds).",
        default=1.0,
    )
    time_reference: Optional[str] = pydantic.Field(
        alias="time reference",
        description="The time reference for the likelihood.",
        default=None,
    )
    reference_frame: Optional[str] = pydantic.Field(
        alias="reference frame",
        description="The reference frame for the likelihood.",
        default=None,
    )
    type: Optional[str] = pydantic.Field(
        alias="type",
        description="The type of likelihood to use.",
        default=None,
    )
    kwargs: Optional[dict] = pydantic.Field(
        alias="kwargs",
        description="Additional keyword arguments for the likelihood.",
        default=None,
    )
    marginalisation: Optional[Marginalisation] = pydantic.Field(
        alias="marginalisation",
        description="Configuration parameters for marginalisation in the likelihood.",
        default=None,
    )
    roq: Optional[ROQ] = pydantic.Field(
        alias="roq",
        description="Configuration parameters for Reduced Order Quadrature (ROQ) in the likelihood.",
        default=None,
    )
    relative_binning: Optional[RelativeBinning] = pydantic.Field(
        alias="relative binning",
        description="Configuration parameters for Relative Binning in the likelihood.",
        default=None,
    )
    minimum_frequency: Optional[Dict[str, float]] = pydantic.Field(
        alias="minimum frequency",
        description="The minimum frequency for the likelihood evaluation, given as a dictionary of values per interferometer.",
        default=None,
    )
    maximum_frequency: Optional[Dict[str, float]] = pydantic.Field(
        alias="maximum frequency",
        description="The maximum frequency for the likelihood evaluation, given as a dictionary of values per interferometer.",
        default=None,
    )

    model_config = ConfigDict(extra='forbid')

    @model_validator(mode="after")
    def default_psd_length(self) -> "Likelihood":
        if self.psd_length is None:
            self.psd_length = self.sample_rate
        return self


class Analysis(Blueprint):
    """
    A blueprint defining the configuration for an analysis task.
    """
    name: str
    comment: str
    likelihood: Optional[Likelihood] = pydantic.Field(
        default=None,
        description="Configuration parameters for the likelihood."
    )
    waveform: Optional[Waveform] = pydantic.Field(
        default=None,
        description="Configuration parameters for the waveform model."
    )

    model_config = ConfigDict(extra='forbid')

class Prior(Blueprint):
    """
    A blueprint defining the configuration for a prior.
    """
    name: Optional[str] = pydantic.Field(
        default=None,
        description="The name of the prior distribution."
    )
    minimum: Optional[float] = pydantic.Field(
        default=None,
        description="The minimum value for the prior."
    )
    maximum: Optional[float] = pydantic.Field(
        default=None,
        description="The maximum value for the prior."
    )

    model_config = ConfigDict(extra='forbid')

class Subject(Blueprint):
    """
    A blueprint defining the configuration for a subject.
    """
    name: str
    event_time: float = pydantic.Field(
        alias="event time",
        description="The GPS time of the event."
    )
    priors: Optional[Dict[str, Prior]] = pydantic.Field(
        default=None,
        description="A dictionary of prior configurations for the subject."
    )

    model_config = ConfigDict(extra='forbid')
