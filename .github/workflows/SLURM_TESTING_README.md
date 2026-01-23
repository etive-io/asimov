# Slurm Testing in CI

## Current Status

The Slurm testing workflow (`.github/workflows/slurm-tests.yml`) is currently set to **manual trigger** (`workflow_dispatch`) due to the complexity of setting up Slurm in GitHub Actions CI environment.

## Why Manual?

1. **Docker Image Availability**: The original workflow used a non-existent Docker image (`ghcr.io/natejenkins/slurm-docker-cluster:23.11.7`)
2. **Complexity**: Running Slurm requires:
   - Privileged container access
   - Munge authentication setup
   - Multiple Slurm daemons (controller, compute nodes)
   - Proper networking configuration
3. **Maintenance**: Community Slurm Docker images may become outdated or unavailable

## Running Slurm Tests Locally

### Option 1: Using Docker

```bash
# Pull a Slurm Docker image
docker pull nathanhess/slurm:latest

# Run the container
docker run -it --privileged --hostname slurmctld nathanhess/slurm:latest /bin/bash

# Inside the container:
# 1. Start munge
munged

# 2. Start Slurm daemons
slurmctld
slurmd

# 3. Verify Slurm is running
sinfo
squeue

# 4. Run asimov tests
cd /path/to/asimov
python -m unittest tests.test_scheduler
```

### Option 2: Install Slurm on Ubuntu

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

### Option 3: Unit Tests Only

The unit tests for Slurm scheduler can run without a real Slurm installation:

```bash
cd /path/to/asimov
python -m unittest tests.test_scheduler.SlurmSchedulerTests -v
```

These tests use mocking and don't require an actual Slurm cluster.

## Enabling Automatic CI Testing

To enable automatic Slurm testing in CI:

1. **Build Your Own Slurm Container**:
   ```dockerfile
   FROM ubuntu:22.04
   RUN apt-get update && apt-get install -y \
       slurm-wlm munge sudo python3 python3-pip git
   # Add your Slurm configuration
   COPY slurm.conf /etc/slurm/slurm.conf
   # Add startup script
   COPY start-slurm.sh /start-slurm.sh
   RUN chmod +x /start-slurm.sh
   CMD ["/start-slurm.sh"]
   ```

2. **Push to Container Registry**:
   ```bash
   docker build -t your-org/slurm-test:latest .
   docker push your-org/slurm-test:latest
   ```

3. **Update Workflow**:
   - Edit `.github/workflows/slurm-tests.yml`
   - Change `image: nathanhess/slurm:latest` to `image: your-org/slurm-test:latest`
   - Change `on: workflow_dispatch` to `on: [push, pull_request]`

## Alternative: Use Existing Public Images

Community-maintained Slurm images (use at your own risk):
- `nathanhess/slurm:latest` - Basic Slurm installation
- `agaveapi/slurm:latest` - Includes controller and compute nodes
- `xenonmiddleware/slurm:latest` - For Xenon middleware testing

Update the workflow file to use one of these images if they meet your requirements.

## Testing Strategy

The current testing strategy prioritizes:
1. **Unit tests** - Mock-based tests that don't require Slurm (always run)
2. **Integration tests** - Manual or local testing with real Slurm
3. **CI tests** - Manual trigger when Slurm container is available

This ensures the code is well-tested without blocking CI on Slurm setup complexity.
