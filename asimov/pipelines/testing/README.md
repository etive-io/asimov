# Testing Pipelines for Asimov

This directory contains minimal testing pipelines for asimov's three analysis types. These pipelines are designed for testing asimov's infrastructure without requiring real gravitational wave analysis pipelines, and also serve as templates for pipeline developers.

## Overview

The testing pipelines provide minimal implementations for:

1. **SimpleAnalysis** (`simple.py`) - Single-event, single-pipeline analysis
2. **SubjectAnalysis** (`subject.py`) - Single-event, multi-pipeline analysis
3. **ProjectAnalysis** (`project.py`) - Multi-event, multi-pipeline analysis

## Purpose

These pipelines serve two important purposes:

### 1. Testing Infrastructure
- Enable end-to-end testing of asimov without real analysis pipelines
- Complete quickly (seconds instead of hours)
- Create dummy output files that mimic real pipeline outputs
- Allow testing of workflow management, job submission, and monitoring

### 2. Developer Templates
- Provide well-documented examples of pipeline implementation
- Show the minimum required methods and their signatures
- Demonstrate proper use of the Pipeline base class
- Illustrate best practices for each analysis type

## Usage

### In Tests

The testing pipelines are used in asimov's test suite and CI/CD pipelines:

```yaml
# Example test configuration
kind: analysis
name: test-simple
pipeline: simpletestpipeline
status: ready
```

See `tests/test_blueprints/` for complete examples.

### As Templates

Pipeline developers can use these as starting points:

```python
from asimov.pipeline import Pipeline

class MyPipeline(Pipeline):
    """My new pipeline implementation."""
    
    name = "MyPipeline"
    STATUS = {"wait", "stuck", "stopped", "running", "finished"}
    
    def __init__(self, production, category=None):
        super(MyPipeline, self).__init__(production, category)
        # Initialize your pipeline
        
    def submit_dag(self, dryrun=False):
        # Submit your job to the cluster
        # Return the job ID
        pass
        
    def detect_completion(self):
        # Check if the job has finished
        # Return True/False
        pass
        
    # Implement other required methods...
```

## Pipeline Descriptions

### SimpleTestPipeline

The simplest testing pipeline for basic analyses on single events.

**Features:**
- Creates a basic job script
- Generates dummy output files (results.dat, posterior_samples.dat)
- Completes immediately (no actual computation)
- Returns a fixed job ID for testing (12345)

**Use cases:**
- Testing basic job submission and monitoring
- Template for parameter estimation pipelines
- Integration testing of asimov core functionality

### SubjectTestPipeline

Testing pipeline for analyses that combine multiple simple analyses.

**Features:**
- Depends on SimpleAnalysis results
- Creates combined output files
- Logs information about dependent analyses
- Returns job ID 23456

**Use cases:**
- Testing dependency management
- Template for meta-analysis pipelines
- Testing multi-analysis workflows

### ProjectTestPipeline

Testing pipeline for population/catalog analyses across multiple events.

**Features:**
- Operates on multiple subjects (events)
- Can filter and combine analyses across events
- Creates population-level outputs
- Returns job ID 34567

**Use cases:**
- Testing project-level analyses
- Template for population studies
- Testing multi-event workflows

## Ledger dumps

Each testing pipeline writes a `ledger_dump.json` into its run directory when
its DAG is built. It records everything the ledger makes available to that
analysis at that moment, so end-to-end runs (and reviewers) can see exactly
what asimov handed the pipeline:

| Key | Contents |
| --- | --- |
| `analysis` | the analysis's name, pipeline, status, run directory and dependencies; its `ledger entry` (as stored) and its `effective settings` (including everything inherited from the subject) |
| `subjects` | each subject the analysis operates on, with its settings |
| `visible analyses` | every other analysis on those subjects: status, review status, the files in its run directory and the assets its pipeline reports. `dependency` is true for the ones this analysis `needs` |
| `encompassed analyses` | subject and project analyses only: the analyses they combine, selected by `analyses:` or `needs:` filters (for example `review: approved`) |

The dump is generated at build time because that is when asimov, rather than
the job on the cluster, has the ledger. It therefore shows what the analysis
could see at submission. `SubjectTestPipeline` and `ProjectTestPipeline` also
list the analyses they combine in the results file they write.

The helpers live in `asimov/pipelines/testing/_dump.py`. To write your own
pipeline's dump, call `write_ledger_dump(self.production)` from `build_dag()`.

## Configuration files and job output

A real pipeline is driven by the configuration file asimov renders from its
template, so each testing pipeline renders one too, from
`asimov/configs/<pipeline>.ini`, and puts it in its run directory as
`config.ini` when its DAG is built:

- `SimpleTestPipeline`'s has the settings a parameter estimation pipeline's
  template would pick out (`[data]`, `[waveform]`, `[likelihood]`,
  `[sampler]`, `[priors]`). A setting the analysis does not have is shown as
  `<not set>`.
- `SubjectTestPipeline` and `ProjectTestPipeline` list the analyses they
  combine under `[analyses]`. `ProjectTestPipeline` also lists its subjects.
- Every one ends with `[effective settings]`, which lists every setting the
  analysis had when the file was rendered, flattened (for example
  `priors.chirp mass.minimum`).

If `asimov manage build` has made the configuration (it is committed to the
subject's repository, or for a project analysis written under
`checkouts/project-analyses/`), that file is copied, because it is the one a
real pipeline would read. Otherwise, for example when a test calls
`build_dag()` directly, the configuration is rendered when the DAG is built.

The job prints `config.ini` and then `ledger_dump.json` to its standard
output before it does anything else, each between
`===== BEGIN <file> =====` and `===== END <file> =====` lines. The output
therefore shows what the job was given, not only what asimov wrote.

The templates read settings through helpers on the pipeline
(`pipeline.setting(...)`, `pipeline.settings_under(...)`,
`pipeline.all_settings()`, `pipeline.combined_analyses()`), because a
missing key is an error in a Liquid template. These live in
`asimov/pipelines/testing/_config.py`.

## End-to-end checks

`tests/verify_ledger_dumps.py` checks the dumps, configurations and job
output produced by the multi-event scenario in
`.github/workflows/testing-pipelines.yml`. The scenario covers:

- settings coming from the project's defaults for the pipeline
  (`tests/test_blueprints/testing_pipeline_defaults.yaml`), then the subject,
  then the analysis (`simple_test_pipeline_override.yaml`);
- a rerun of an analysis with the same pipeline and narrower priors
  (`simple_test_pipeline_rerun.yaml`), which must get the new priors while
  the original keeps its own;
- `asimov apply --update`, after which a later analysis sees the new settings
  and existing ones are unchanged;
- filtering by review status.

It also checks that each job got the configuration `asimov manage build`
made, and printed it and its dump. The workflow's artifact gathers every
dump, configuration and job output into `ledger-dumps/`, `configs/` and
`job-outputs/`, named after the analysis, for a person to review.

## Implementation Details

### Required Methods

All pipelines must implement:

- `__init__(production, category=None)` - Initialize the pipeline
- `submit_dag(dryrun=False)` - Submit the job, return job ID
- `detect_completion()` - Check if job finished, return bool

### Optional Methods

Pipelines may override:

- `before_submit(dryrun=False)` - Pre-submission setup
- `before_build(dryrun=False)` - Pre-build setup
- `after_completion()` - Post-processing after job finishes
- `samples(absolute=False)` - Return paths to output samples
- `collect_assets()` - Return dict of output files for version control
- `collect_logs()` - Return log information

### Output Files

Each pipeline creates specific output files:

**SimpleTestPipeline:**
- `test_job.sh` - Job script

- `results.dat` - Analysis results
- `posterior_samples.dat` - Sample outputs

**SubjectTestPipeline:**
- `test_subject_job.sh` - Job script
- `combined_results.dat` - Combined results
- `combined_samples.dat` - Combined samples

**ProjectTestPipeline:**
- `test_project_job.sh` - Job script
- `population_results.dat` - Population results
- `population_samples.dat` - Population samples

## Installation

The testing pipelines are registered via entry points and are available when asimov is installed:

```bash
pip install asimov[testing]
```

They are automatically discovered by asimov's pipeline discovery mechanism.

## Testing

Run the testing pipeline tests:

```bash
python -m unittest tests.test_pipelines.test_testing_pipelines
```

Or use the GitHub Actions workflow that tests all three pipelines with HTCondor:

```bash
# See .github/workflows/testing-pipelines.yml
```

## Examples

### Creating a Simple Analysis

```python
from asimov.analysis import SimpleAnalysis
from asimov.event import Event

event = Event("GW150914_095045", ledger=ledger)
analysis = SimpleAnalysis(
    subject=event,
    name="test-run",
    pipeline="simpletestpipeline",
    status="ready"
)

# Submit the job
job_id = analysis.pipeline.submit_dag()

# Check completion
if analysis.pipeline.detect_completion():
    analysis.pipeline.after_completion()
```

### Creating a Subject Analysis

```yaml
kind: subject_analysis
name: combine-results
pipeline: subjecttestpipeline
needs:
  - analysis1
  - analysis2
```

### Creating a Project Analysis

```yaml
kind: project_analysis
name: population-study
pipeline: projecttestpipeline
subjects:
  - GW150914_095045
  - GW151226_033853
analyses:
  - status: finished
```

## Contributing

When adding new features to asimov that affect pipelines:

1. Update the testing pipelines to support the feature
2. Add tests using the testing pipelines
3. Update this documentation

## See Also

- [asimov.pipeline.Pipeline](../../asimov/pipeline.py) - Base pipeline class
- [asimov.analysis](../../asimov/analysis.py) - Analysis type definitions
- [tests/test_pipelines/](../../tests/test_pipelines/) - Pipeline tests
- [asimov documentation](https://asimov.docs.ligo.org/asimov) - Full documentation
