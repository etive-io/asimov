# Slurm Scheduler Support

This document describes the Slurm scheduler support added to asimov.

## Overview

Asimov now has first-class support for the Slurm scheduler, allowing you to use asimov on HPC clusters that use Slurm instead of HTCondor. This support includes:

- **Automatic scheduler detection**: Asimov automatically detects which scheduler is available during `asimov init`
- **Scheduler abstraction**: All pipelines use a unified scheduler API that works with both HTCondor and Slurm
- **DAG translation**: HTCondor DAG files are automatically converted to Slurm batch scripts
- **Monitor daemon**: Periodic monitoring via system cron instead of HTCondor cron

## Installation

To use asimov with Slurm, install the optional Slurm dependencies:

```bash
pip install asimov[slurm]
```

Or if you're installing from source:

```bash
pip install -e .[slurm]
```

This installs `python-crontab` which is used for the monitor daemon.

## Getting Started

### Creating a New Project

When you run `asimov init`, asimov will automatically detect if Slurm is available:

```bash
mkdir my-project
cd my-project
asimov init "My Project"
```

Asimov checks for `sbatch` and `squeue` commands. If found, it configures the project to use Slurm.

### Manual Configuration

You can also manually configure the scheduler in `.asimov/asimov.conf`:

```ini
[scheduler]
type = slurm

[slurm]
user = your_username
partition = compute       # Optional: specific partition
cron_minute = */15        # Optional: monitor frequency (default: every 15 minutes)
```

## Using Asimov with Slurm

Once configured, all asimov commands work the same way:

```bash
# Start the monitor daemon (creates a cron job)
asimov start

# Stop the monitor daemon (removes the cron job)
asimov stop

# Build and submit jobs
asimov manage build
asimov manage submit

# Monitor jobs
asimov monitor
```

## How It Works

### Job Submission

When you submit jobs with Slurm, asimov:

1. Creates a Slurm batch script from your job description
2. Submits the script using `sbatch`
3. Returns the Slurm job ID for tracking

### Symmetric DAG Translation

Asimov provides **bidirectional DAG translation** between HTCondor and Slurm:

**HTCondor to Slurm**

Pipelines like bilby, bayeswave, and lalinference generate HTCondor DAG files. When using Slurm, asimov automatically:

1. Parses the HTCondor DAG file
2. Identifies job dependencies (PARENT-CHILD relationships)
3. Converts to a Slurm batch script with `--dependency` flags
4. Submits the workflow using `sbatch`

**Slurm to HTCondor**

Some pipelines can generate Slurm batch scripts directly. When using HTCondor, asimov automatically:

1. Parses the Slurm batch script
2. Identifies job dependencies (`--dependency=afterok:` flags)
3. Converts to an HTCondor DAG file with PARENT-CHILD relationships
4. Submits the workflow using HTCondor's DAG manager

**Format Auto-Detection**

The scheduler automatically detects the input file format by examining its content:
- HTCondor DAG files contain `JOB`, `PARENT`, `CHILD` directives
- Slurm batch scripts contain `#SBATCH` directives or `sbatch` commands

This means you can submit either format to either scheduler - the conversion happens automatically!

### Monitor Daemon

With HTCondor, `asimov start` submits a recurring job via HTCondor's cron functionality.

With Slurm, `asimov start`:
- Creates a system cron job that runs `asimov monitor --chain` periodically
- Uses `python-crontab` to manage the cron job automatically
- Falls back to manual cron setup if `python-crontab` is not available

## Switching Between Schedulers

To switch from HTCondor to Slurm (or vice versa):

1. Update the `[scheduler]` section in `.asimov/asimov.conf`:

```ini
# Switch from HTCondor to Slurm
[scheduler]
type = slurm
```

2. Stop any running monitor daemon:

```bash
asimov stop
```

3. Start the monitor with the new scheduler:

```bash
asimov start
```

All existing job data remains compatible; only new jobs will use the new scheduler.

## Limitations

- **DAG complexity**: Very complex DAG files with advanced HTCondor features may not translate perfectly. Simple DAGs with job dependencies work well.
- **Job status mapping**: Slurm job states are mapped to HTCondor-like status codes for compatibility, but some nuances may be lost.
- **Resource specifications**: Some HTCondor-specific resource requirements may not have direct Slurm equivalents.

## Troubleshooting

### Scheduler not detected

If asimov doesn't detect Slurm automatically:

1. Verify Slurm is installed: `which sbatch squeue`
2. Manually configure in `.asimov/asimov.conf`

### Cron job not created

If `asimov start` fails to create a cron job:

1. Install python-crontab: `pip install python-crontab`
2. Or manually add to crontab: `crontab -e`

```cron
*/15 * * * * cd /path/to/project && asimov monitor --chain >> .asimov/asimov_cron.out 2>> .asimov/asimov_cron.err
```

### Job submission fails

If job submission fails:

1. Check Slurm is working: `sinfo`
2. Verify partition exists: `sinfo -o "%P"`
3. Check job logs in `.asimov/` directory

## Developer Information

### Scheduler API

The scheduler abstraction is defined in `asimov/scheduler.py`:

```python
from asimov.scheduler import get_scheduler

# Get a scheduler instance
scheduler = get_scheduler("slurm", partition="compute")

# Submit a job
from asimov.scheduler import JobDescription
job = JobDescription(
    executable="/bin/echo",
    output="out.log",
    error="err.log",
    log="job.log",
    cpus=4,
    memory="8GB"
)
cluster_id = scheduler.submit(job)

# Submit a DAG
cluster_id = scheduler.submit_dag("workflow.dag", batch_name="my-analysis")

# Query jobs
jobs = scheduler.query_all_jobs()

# Delete a job
scheduler.delete(cluster_id)
```

### Pipeline Integration

Pipelines access the scheduler via `self.scheduler`:

```python
from asimov.pipeline import Pipeline

class MyPipeline(Pipeline):
    def submit_dag(self):
        # Scheduler is automatically configured
        cluster_id = self.scheduler.submit_dag(
            dag_file=self.dag_file,
            batch_name=f"{self.production.name}"
        )
        return cluster_id
```

## Testing

Comprehensive tests are included:

```bash
# Run unit tests
python -m unittest tests.test_scheduler

# Run integration tests (requires Slurm)
# See .github/workflows/slurm-tests.yml
```

## Contributing

When adding new scheduler features:

1. Add the feature to the base `Scheduler` class
2. Implement for both `HTCondor` and `Slurm`
3. Add tests in `tests/test_scheduler.py`
4. Update documentation

## References

- [Slurm Documentation](https://slurm.schedmd.com/)
- [HTCondor Documentation](https://htcondor.readthedocs.io/)
- [Asimov Documentation](https://asimov.docs.ligo.org/)
