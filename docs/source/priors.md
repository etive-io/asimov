# Prior Specification and Interface System

## Overview

As of version 0.6, asimov includes a refactored prior handling system that provides:

1. **Validation**: Priors are validated using pydantic models when blueprints are applied
2. **Pipeline Interfaces**: Each pipeline can define how to convert asimov priors to pipeline-specific formats
3. **Reparameterizations**: Support for both standard priors and parameter reparameterizations (useful for pipelines like pycbc)
4. **Backward Compatibility**: Existing blueprints continue to work without modification

## For Users: Specifying Priors in Blueprints

### Basic Prior Specification

Priors are specified in blueprints using the `priors` section. The format remains the same as before:

```yaml
kind: event
name: GW150914_095045
priors:
  luminosity distance:
    minimum: 10
    maximum: 1000
  mass ratio:
    minimum: 0.1
    maximum: 1.0
```

### Advanced Prior Specification

You can now specify additional parameters that will be validated:

```yaml
priors:
  default: BBHPriorDict  # The default prior set to use
  luminosity distance:
    minimum: 10
    maximum: 1000
    type: PowerLaw
    alpha: 2
  geocentric time:
    minimum: -0.1
    maximum: 0.1
    type: Uniform
    boundary: reflective
```

### Supported Prior Parameters

The following parameters are recognized by the validation system:

- `minimum`: Minimum value for the prior
- `maximum`: Maximum value for the prior
- `type`: The prior distribution type/class name
- `boundary`: Boundary condition ('periodic', 'reflective', or None)
- `alpha`: Power law index (for PowerLaw priors)
- `mu`: Mean (for Gaussian priors)
- `sigma`: Standard deviation (for Gaussian priors)

Additional pipeline-specific parameters are also allowed and will be passed through to the pipeline interface.

## For Pipeline Developers: Creating Prior Interfaces

### Creating a New Prior Interface

To add prior handling for a new pipeline, create a class that inherits from `PriorInterface`:

```python
from asimov.priors import PriorInterface, PriorDict

class MyPipelinePriorInterface(PriorInterface):
    """Prior interface for MyPipeline."""
    
    def convert(self):
        """
        Convert asimov priors to pipeline-specific format.
        
        Returns
        -------
        dict or str or Any
            The prior specification in the format required by your pipeline
        """
        if self.prior_dict is None:
            return {}
        
        # Convert to your pipeline's format
        result = {}
        for param_name in ['mass_1', 'mass_2', 'luminosity_distance']:
            prior_spec = self.prior_dict.get_prior(param_name)
            if prior_spec:
                # Convert to your format
                result[param_name] = self.convert_single_prior(prior_spec)
        
        return result
    
    def convert_single_prior(self, prior_spec):
        """Convert a single prior specification."""
        # Implement conversion logic for your pipeline
        pass
```

### Integrating with Your Pipeline Class

Override the `get_prior_interface()` method in your Pipeline class:

```python
from asimov.pipeline import Pipeline
from .my_prior_interface import MyPipelinePriorInterface

class MyPipeline(Pipeline):
    """My pipeline implementation."""
    
    def get_prior_interface(self):
        """Get the prior interface for this pipeline."""
        if self._prior_interface is None:
            priors = self.production.priors
            self._prior_interface = MyPipelinePriorInterface(priors)
        return self._prior_interface
```

### Using the Prior Interface

In your pipeline's configuration generation or submission logic:

```python
# Get the prior interface
prior_interface = self.get_prior_interface()

# Convert to pipeline-specific format
pipeline_priors = prior_interface.convert()

# Use in your pipeline
# ...
```

## Reparameterizations

For pipelines that support parameter reparameterizations (like pycbc), you can specify them:

```python
from asimov.priors import Reparameterization

reparam = Reparameterization(
    from_parameters=['mass_1', 'mass_2'],
    to_parameters=['chirp_mass', 'mass_ratio'],
    transform='mass_to_chirp_mass_ratio'
)
```

## Validation

Priors are automatically validated when they are set on an analysis:

```python
from asimov.analysis import Production

production = Production(...)

# This will be validated
production.priors = {
    'mass ratio': {
        'minimum': 0.1,
        'maximum': 1.0
    }
}

# Invalid priors will raise a validation error
try:
    production.priors = "not a dict"  # Will raise TypeError
except TypeError as e:
    print(f"Validation failed: {e}")
```

## Example: Pipeline Prior Interfaces

### Bilby Prior Interface

The bilby pipeline includes a `BilbyPriorInterface` (in `asimov/pipelines/bilby.py`) that demonstrates the pattern:

```python
from asimov.pipelines.bilby import BilbyPriorInterface

# Create interface with priors from blueprint
interface = BilbyPriorInterface({
    'default': 'BBHPriorDict',
    'luminosity distance': {
        'minimum': 10,
        'maximum': 1000,
        'type': 'PowerLaw',
        'alpha': 2
    },
    'chirp mass': {
        'minimum': 21.4,
        'maximum': 42.0
    }
})

# Convert to bilby format (returns dict)
bilby_priors = interface.convert()

# Get default prior set
default = interface.get_default_prior()  # Returns 'BBHPriorDict'

# Generate a complete prior_dict string for bilby config
prior_string = interface.to_prior_dict_string()
# Returns a formatted string like:
# {
#    chirp_mass = bilby.gw.prior.UniformInComponentsChirpMass(name='chirp_mass', minimum=21.4, maximum=42.0, unit='$M_{\odot}$'),
#    luminosity_distance = PowerLaw(name='luminosity_distance', minimum=10, maximum=1000, alpha=2, unit='Mpc'),
#    ...
# }
```

The bilby template (`configs/bilby.ini`) uses the `to_prior_dict_string()` method to generate a complete prior dictionary string that can be directly inserted into the configuration file:

```liquid
{%- assign prior_interface = production.pipeline.get_prior_interface() -%}
default-prior = {{ prior_interface.get_default_prior() }}
prior-dict = {{ prior_interface.to_prior_dict_string() }}
```

This approach provides maximum flexibility as the prior interface can generate any valid bilby prior specification, including custom prior types and reparameterizations.

### LALInference Prior Interface

The LALInference pipeline includes a `LALInferencePriorInterface` (in `asimov/pipelines/lalinference.py`) that converts asimov priors to LALInference format:

```python
from asimov.pipelines.lalinference import LALInferencePriorInterface

# Create interface with priors from blueprint
interface = LALInferencePriorInterface({
    'mass ratio': {
        'minimum': 0.05,
        'maximum': 1.0
    },
    'luminosity distance': {
        'minimum': 10,
        'maximum': 10000
    },
    'amp order': 0
})

# Convert to LALInference format (uses [min, max] arrays)
lalinf_priors = interface.convert()
# Returns: {'mass ratio': [0.05, 1.0], 'luminosity distance': [10, 10000]}

# Get amplitude order
amp_order = interface.get_amp_order()  # Returns 0
```

The LALInference template (`configs/lalinference.ini`) accesses these priors through the pipeline's prior interface.
