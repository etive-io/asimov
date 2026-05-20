# Slurm Testing in CI

The Slurm workflow (`.github/workflows/slurm-tests.yml`) now runs automatically on
pushes and pull requests and exercises two paths:

1. **Testing pipelines end-to-end on Slurm** using the lightweight testing
   pipelines already used elsewhere in CI.
2. **Bilby end-to-end on Slurm**, with the prerequisite gwdata and BayesWave
   stages submitted through the generic scheduler translation layer before Bilby
   runs using its native Slurm support.

## How it works

- `.github/actions/setup-slurm` installs and starts a single-node Slurm cluster
  directly on the GitHub runner.
- The testing-pipeline job forces `scheduler/type = slurm` and checks that all
  analyses reach `complete`.
- The Bilby job applies the existing quick-test blueprints, runs the gwdata and
  BayesWave prerequisites through the Slurm scheduler interface, and then waits
  for the final Bilby result file.

## Local reproduction

To reproduce the scheduler setup locally on Ubuntu, follow the same steps used
by `.github/actions/setup-slurm/action.yml`, then run the workflow commands
manually from the repository root.
