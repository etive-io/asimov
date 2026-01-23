# Slurm Testing in CI

## Current Status

The Slurm testing workflow (`.github/workflows/slurm-tests.yml`) uses the **pitt-crc/Slurm-Test-Environment** Docker images for automated Slurm testing in GitHub Actions.

Repository: https://github.com/pitt-crc/Slurm-Test-Environment

## How It Works

The workflow:
1. Uses pre-built Slurm Docker images from `ghcr.io/pitt-crc/test-env`
2. Tests against multiple Slurm versions (23.02.5, 23.11.10)
3. Automatically starts Slurm services via the image's entrypoint
4. Runs comprehensive asimov tests with actual Slurm job submission

## Test Matrix

The CI tests against multiple Slurm versions to ensure compatibility:
- Slurm 23.02.5 (older stable)
- Slurm 23.11.10 (newer stable)

Additional versions can be added by updating the matrix in the workflow file.

## Running Tests Locally

### Option 1: Using the Same Docker Image

```bash
# Pull the test environment
docker pull ghcr.io/pitt-crc/test-env:23.02.5

# Run interactively
docker run -it ghcr.io/pitt-crc/test-env:23.02.5 /bin/bash

# Inside the container, the entrypoint has already started Slurm
# Run your tests
cd /path/to/asimov
python -m unittest tests.test_scheduler
```

### Option 2: Using Docker Compose

Create a `docker-compose.yml`:

```yaml
version: '3'
services:
  slurm-test:
    image: ghcr.io/pitt-crc/test-env:23.02.5
    volumes:
      - .:/workspace
    working_dir: /workspace
    command: /bin/bash -c "/usr/local/bin/entrypoint.sh && /bin/bash"
    stdin_open: true
    tty: true
```

Then run:
```bash
docker-compose run slurm-test
```

### Option 3: Install Slurm on Ubuntu

For local development without Docker:

```bash
# Install Slurm
sudo apt-get update
sudo apt-get install -y slurm-wlm slurm-client munge

# Configure Slurm (requires creating slurm.conf)
# See: https://slurm.schedmd.com/quickstart_admin.html

# Start services
sudo systemctl start munge
sudo systemctl start slurmctld
sudo systemctl start slurmd

# Verify
sinfo
```

### Option 4: Unit Tests Only (No Slurm Required)

The unit tests for Slurm scheduler use mocking and don't require a real Slurm installation:

```bash
cd /path/to/asimov
python -m unittest tests.test_scheduler.SlurmSchedulerTests -v
```

## What Gets Tested

The CI workflow tests:

1. **Slurm Detection**: Verifies `asimov init` correctly detects Slurm
2. **Scheduler Unit Tests**: All 30 unit tests for the scheduler abstraction
3. **Job Submission**: Actual Slurm job submission and monitoring
4. **DAG Translation**: HTCondor DAG to Slurm batch script conversion
5. **Integration**: End-to-end workflow with asimov commands

## Customizing the Test Environment

To test with a different Slurm version:

1. Check available versions at: https://github.com/pitt-crc/Slurm-Test-Environment/pkgs/container/test-env
2. Update the matrix in `.github/workflows/slurm-tests.yml`:

```yaml
matrix:
  slurm_version:
    - "20.11.9"
    - "22.05.11"
    - "23.02.5"
    - "23.11.10"
```

## Building Your Own Slurm Test Image

If you need custom Slurm configuration:

```dockerfile
FROM ghcr.io/pitt-crc/test-env:23.02.5

# Add your custom Slurm configuration
COPY my-slurm.conf /etc/slurm/slurm.conf

# Add custom setup
COPY setup-script.sh /usr/local/bin/custom-setup.sh
RUN chmod +x /usr/local/bin/custom-setup.sh
```

Then build and push to your registry:
```bash
docker build -t your-org/slurm-test:custom .
docker push your-org/slurm-test:custom
```

Update the workflow to use your image:
```yaml
container:
  image: your-org/slurm-test:custom
```

## Advantages of This Approach

1. **Reliable**: Uses maintained Docker images specifically designed for CI testing
2. **Versioned**: Test against multiple Slurm versions
3. **Pre-configured**: Slurm services start automatically via entrypoint
4. **No Manual Setup**: No need to manually start munge, slurmctld, slurmd
5. **Fast**: Images are optimized for quick startup in CI
6. **Maintained**: The pitt-crc project actively maintains these images

## Troubleshooting

### Container Fails to Start

Check the workflow logs for entrypoint errors. The entrypoint script should handle Slurm service startup automatically.

### Slurm Commands Not Found

Ensure the entrypoint has been called:
```bash
/usr/local/bin/entrypoint.sh
```

### Jobs Stay in Pending State

Check node status:
```bash
sinfo -N -o "%N %t %C"
```

If nodes are down, the entrypoint may not have completed successfully.

### Permission Errors

The test environment runs as root by default. If you encounter permission issues, check file ownership in the workspace.

## References

- [Slurm Test Environment Repository](https://github.com/pitt-crc/Slurm-Test-Environment)
- [Available Docker Images](https://github.com/pitt-crc/Slurm-Test-Environment/pkgs/container/test-env)
- [Slurm Documentation](https://slurm.schedmd.com/)
- [GitHub Actions Container Jobs](https://docs.github.com/en/actions/using-jobs/running-jobs-in-a-container)

