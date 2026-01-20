# Matrix Strategies

## Overview

Matrix strategies allow you to automatically generate multiple similar analyses with different parameter values, similar to how [GitHub Actions matrix strategies](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/run-job-variations) work. Instead of manually creating dozens or hundreds of similar productions with slightly different parameters, you can define a single production with a `strategy` section that specifies which parameters should vary.

## Use Cases

Matrix strategies are particularly useful for:

- **Waveform comparison studies**: Testing multiple waveform approximants (e.g., IMRPhenomXPHM, SEOBNRv4PHM, IMRPhenomD)
- **Sampler comparison**: Comparing different samplers or sampler settings
- **Parameter-parameter tests**: Generating ensembles for p-p plot validation
- **Systematic studies**: Varying calibration envelopes, PSD settings, or other parameters

## Basic Syntax

A production with a matrix strategy looks like this:

```yaml
productions:
  - name: MyAnalysis
    pipeline: bilby
    strategy:
      matrix:
        parameter.name:
          - value1
          - value2
          - value3
```

When asimov processes this configuration, it will automatically expand it into multiple productions:
- `MyAnalysis-0` with `parameter.name: value1`
- `MyAnalysis-1` with `parameter.name: value2`
- `MyAnalysis-2` with `parameter.name: value3`

## Single Parameter Example

To test three different waveform approximants:

```yaml
productions:
  - name: WaveformTest
    pipeline: bilby
    strategy:
      matrix:
        waveform.approximant:
          - IMRPhenomXPHM
          - SEOBNRv4PHM
          - IMRPhenomD
    # Common settings that apply to all expanded productions
    sampler:
      sampler: dynesty
      nlive: 1000
```

This creates three productions: `WaveformTest-0`, `WaveformTest-1`, and `WaveformTest-2`.

## Multiple Parameter Example

You can vary multiple parameters simultaneously. The matrix will create all combinations:

```yaml
productions:
  - name: ComparisonStudy
    pipeline: bilby
    strategy:
      matrix:
        waveform.approximant:
          - IMRPhenomXPHM
          - SEOBNRv4PHM
        sampler.sampler:
          - dynesty
          - nestle
```

This creates 2 × 2 = 4 productions with all combinations:
- `ComparisonStudy-0`: IMRPhenomXPHM + dynesty
- `ComparisonStudy-1`: IMRPhenomXPHM + nestle
- `ComparisonStudy-2`: SEOBNRv4PHM + dynesty
- `ComparisonStudy-3`: SEOBNRv4PHM + nestle

## Nested Parameters

Matrix strategies support nested parameter paths using dot notation:

```yaml
strategy:
  matrix:
    waveform.approximant:
      - IMRPhenomXPHM
      - SEOBNRv4PHM
    sampler.nlive:
      - 1000
      - 2000
    likelihood.distance_marginalization:
      - true
      - false
```

## Combining with Regular Productions

You can mix productions with and without strategies in the same event:

```yaml
productions:
  - name: ControlRun
    pipeline: bilby
    waveform:
      approximant: IMRPhenomXPHM
    
  - name: TestMatrix
    pipeline: bilby
    strategy:
      matrix:
        waveform.approximant:
          - SEOBNRv4PHM
          - IMRPhenomD
```

This creates 3 total productions: the control run plus two from the matrix.

## Parameter Inheritance

Matrix parameters override any existing values but preserve other settings:

```yaml
productions:
  - name: Test
    pipeline: bilby
    waveform:
      approximant: IMRPhenomXPHM  # Will be overridden by matrix
      mode_array: [[2,2], [3,3]]  # Will be preserved
    strategy:
      matrix:
        waveform.approximant:
          - SEOBNRv4PHM
          - IMRPhenomD
```

Both expanded productions will have:
- Different `waveform.approximant` values (from the matrix)
- The same `waveform.mode_array: [[2,2], [3,3]]` (preserved from the original)

## Naming Convention

Expanded productions are automatically named with a suffix: `{original-name}-{index}`

- `MyAnalysis-0`
- `MyAnalysis-1`
- `MyAnalysis-2`
- etc.

The index starts at 0 and increments sequentially.

## Limitations and Notes

1. **No name conflicts**: Make sure your matrix expansion doesn't create productions with names that conflict with other productions in the event
2. **Cartesian product**: With multiple parameters, be aware that the number of productions grows multiplicatively (2 × 3 × 4 = 24 productions)
3. **Dependencies**: Productions created from a matrix can still use the `needs` field to depend on other productions

## Complete Examples

See the following example files for more details:
- `tests/test_data/strategy_example_waveforms.yaml` - Single parameter waveform comparison
- `tests/test_data/strategy_example_multi_param.yaml` - Multi-parameter matrix
- `tests/test_data/strategy_example_sampler_settings.yaml` - Sampler configuration testing

## Implementation Details

The matrix strategy expansion happens during event initialization, before any productions are created. The `expand_strategy()` function in `asimov/utils.py` handles the expansion logic, creating deep copies of the base production configuration and applying each combination of matrix parameters.
