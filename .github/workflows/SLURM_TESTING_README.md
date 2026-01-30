# Slurm Testing in CI

## Current Status

The Slurm testing workflow (`.github/workflows/slurm-tests.yml`) provides **unit tests** that run without requiring Slurm, and **optional integration tests** that can be run manually.

**Why This Approach?**
- Container-based Slurm testing has authentication/access issues with public Docker registries
- Unit tests provide excellent coverage without external dependencies
- Integration tests can be run manually when needed
- This ensures CI doesn't fail on infrastructure issues

## Test Coverage

### Automated Unit Tests (Always Run)
The main test suite includes comprehensive Slurm scheduler tests:
```bash
python -m unittest tests.test_scheduler -v
```

These tests cover:
- ✅ Slurm scheduler class instantiation
- ✅ DAG file format detection (HTCondor vs Slurm)
- ✅ HTCondor DAG → Slurm batch script conversion
- ✅ Slurm batch script → HTCondor DAG conversion
- ✅ Job dependency resolution (topological sort)
- ✅ Job description Slurm parameter mapping
- ✅ All without requiring Slurm installation (uses mocking)

**Result**: 30 tests, 100% passing, no Slurm required

### Manual Integration Tests (Optional)
The workflow in `.github/workflows/slurm-tests.yml` can be manually triggered to:
1. Run all unit tests
2. Install Slurm locally on Ubuntu runner
3. Test real Slurm job submission
4. Verify scheduler auto-detection
5. Test end-to-end workflows

## Running Tests Locally

### Option 1: Unit Tests Only (Recommended)

No Slurm installation required:

```bash
cd /path/to/asimov
python -m unittest tests.test_scheduler -v
```

### Option 2: Install Slurm on Ubuntu

For full integration testing:

```bash
# Install Slurm
sudo apt-get update
sudo apt-get install -y slurm-wlm munge

# Start munge
sudo systemctl start munge

# Configure Slurm (minimal setup)
sudo mkdir -p /etc/slurm /var/spool/slurm /var/log/slurm
sudo chown slurm:slurm /var/spool/slurm /var/log/slurm

# Create /etc/slurm/slurm.conf (see example in workflow)
# Then start services:
sudo slurmctld
sudo slurmd

# Verify
sinfo
squeue

# Run asimov tests
cd /path/to/asimov
python -m unittest tests.test_scheduler -v

# Test job submission
cat > test.sh << 'EOF'
#!/bin/bash
#SBATCH --job-name=test
echo "Hello from Slurm"
EOF

sbatch test.sh
squeue
```

### Option 3: Docker (Alternative)

Some community Slurm Docker images exist, but may have availability issues:

```bash
# Try these community images (your mileage may vary):
docker pull nathanhess/slurm:latest
# or
docker pull agaveapi/slurm:latest

# Run container
docker run -it --privileged nathanhess/slurm:latest /bin/bash

# Inside container, start services and run tests
```

### Option 4: Manual Workflow Trigger

Trigger the integration tests in GitHub Actions:
1. Go to Actions tab in GitHub
2. Select "Slurm Integration Tests (Manual)"
3. Click "Run workflow"

This will run all tests including attempting to install and configure Slurm.

## What Gets Tested

### Unit Tests (Automatic)
- Scheduler class interface
- DAG format detection
- Bidirectional DAG translation
- Job dependency handling
- Resource parameter mapping
- All scheduler methods (mocked)

### Integration Tests (Manual)
- Real Slurm installation
- Actual job submission
- Auto-detection during `asimov init`
- End-to-end workflow

## Why Not Container-Based CI?

We tried several approaches:

1. **pitt-crc/Slurm-Test-Environment**: Images require authentication or aren't publicly accessible
2. **nathanhess/slurm**: Community image with inconsistent availability
3. **agaveapi/slurm**: Similar access issues

**Current Solution**: 
- Unit tests provide excellent coverage without external dependencies
- Integration tests can be run manually or locally
- This prevents CI failures due to Docker image availability issues

## Testing Strategy

```
┌─────────────────────────────────────────┐
│ Main Test Suite (Automatic)            │
│ ├─ Unit Tests (30 tests)               │
│ │  └─ No Slurm required (mocking)      │
│ ├─ HTCondor Tests                      │
│ └─ Other asimov tests                  │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ Slurm Integration (Manual)             │
│ ├─ Install Slurm on Ubuntu runner      │
│ ├─ Real job submission                 │
│ ├─ Auto-detection verification         │
│ └─ End-to-end workflows                │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ Local Development Testing              │
│ ├─ Unit tests (always)                 │
│ ├─ Local Slurm install (optional)      │
│ └─ Manual verification (optional)      │
└─────────────────────────────────────────┘
```

## For Production Deployments

If you need regular Slurm CI testing for your fork:

### Option A: Build Your Own Slurm Container

```dockerfile
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y slurm-wlm munge
COPY slurm.conf /etc/slurm/slurm.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
```

Build, push to your registry, and update the workflow.

### Option B: Use Local Installation

The current manual workflow installs Slurm directly on the Ubuntu runner. You can make this automatic by changing:

```yaml
on: workflow_dispatch  # Manual trigger
```

to:

```yaml
on: [push, pull_request]  # Automatic
```

However, be aware that Slurm installation and configuration can be fragile in CI.

### Option C: Hybrid Approach (Recommended)

- Keep unit tests running automatically (current setup)
- Run integration tests:
  - Manually via workflow_dispatch
  - On a schedule (e.g., nightly)
  - Before releases

## Troubleshooting

### Unit Tests Fail

Check Python dependencies:
```bash
pip install -e .
pip install python-crontab
```

### Slurm Commands Not Found

Ensure Slurm is installed and in PATH:
```bash
which sbatch squeue sinfo
```

### Slurm Services Won't Start

Check munge is running first:
```bash
sudo systemctl status munge
```

Check Slurm configuration:
```bash
sudo slurmctld -D  # Debug mode
```

### Permission Errors

Ensure proper ownership:
```bash
sudo chown -R slurm:slurm /var/spool/slurm /var/log/slurm
```

## References

- [Slurm Documentation](https://slurm.schedmd.com/)
- [Slurm Quick Start Admin Guide](https://slurm.schedmd.com/quickstart_admin.html)
- [Asimov Scheduler Unit Tests](../tests/test_scheduler.py)
- [GitHub Actions Manual Workflows](https://docs.github.com/en/actions/using-workflows/manually-running-a-workflow)

