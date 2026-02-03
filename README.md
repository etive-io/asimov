<div align="center">
  <img src="logo.svg" alt="Asimov Logo" width="200"/>

# Asimov

### Workflow orchestration for complex scientific analyses

**A general-purpose framework for managing automated analysis pipelines on HPC clusters**

Battle-tested in production by LIGO, Virgo, and KAGRA collaborations

[Documentation](https://asimov.docs.ligo.org/asimov) · [Installation](#-installing-asimov) · [Quick Start](#-quick-start) · [Contributing](CONTRIBUTING.rst)

[![coverage report](https://git.ligo.org/asimov/asimov/badges/master/coverage.svg)](https://git.ligo.org/asimov/asimov/-/commits/master)
[![conda-forge version](https://anaconda.org/conda-forge/asimov/badges/version.svg)](https://anaconda.org/conda-forge/asimov/)
![pypi](https://img.shields.io/pypi/v/asimov.svg)
![tests](https://git.ligo.org/asimov/asimov/badges/master/pipeline.svg)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## Table of Contents

- [What is Asimov?](#what-is-asimov)
- [Why Asimov?](#why-asimov)
- [Key Features](#-key-features)
- [Primary Use Case: Gravitational Waves](#-primary-use-case-gravitational-waves)
- [Beyond Gravitational Waves](#-beyond-gravitational-waves)
- [Installing Asimov](#-installing-asimov)
- [Quick Start](#-quick-start)
- [Do I Need Asimov?](#-do-i-need-asimov)
- [Example Workflow](#-example-workflow)
- [Extensibility](#-extensibility)
- [Roadmap](#-roadmap)
- [Contributing](#-contributing)
- [Citation](#-citation)
- [Authors](#-authors)

---

## What is Asimov?

**Asimov** is a general-purpose workflow orchestration platform designed to automate complex scientific analyses on high-throughput computing (HTC) clusters.

At its core, Asimov provides:
- **Pipeline-agnostic architecture** - Coordinate multiple analysis tools through a unified interface
- **Intelligent job management** - Submit, monitor, and recover jobs automatically
- **Configuration management** - Version-controlled, reproducible analysis workflows
- **Results organization** - Structured handling of outputs with validation

**Designed for flexibility:** While gravitational wave analysis is the primary use case, Asimov's architecture supports any scientific workflow involving:
- Long-running computational jobs
- Multiple analysis pipelines or tools
- Systematic parameter studies
- HTC cluster environments (HTCondor, Slurm)
- Complex dependencies between analyses

---

## Why Asimov?

Many scientific analyses involve running computationally intensive pipelines on HPC clusters—processes that can take **days to weeks** and involve **hundreds of coordinated jobs**. Common challenges include:

- **Manual configuration** for each pipeline and analysis
- **Constant monitoring** of job status across clusters
- **Error-prone** restart and recovery procedures
- **Scattered results** across different filesystems
- **Difficult reproducibility** and collaboration
- **Pipeline lock-in** - custom scripts tied to specific tools

### Asimov solves this by providing:

✅ **Pipeline-agnostic interface** - One framework for multiple analysis tools
✅ **Automated job orchestration** - Submit, monitor, recover automatically
✅ **Version-controlled configuration** - Reproducible, auditable workflows
✅ **Intelligent error handling** - Detect and recover from failures
✅ **Results management** - Organized, validated outputs
✅ **Scalability** - From single analyses to large-scale campaigns

---

## 🚀 Key Features

### 🤖 Intelligent Job Management
Asimov interacts with high-throughput computing systems (HTCondor, Slurm) to submit jobs, monitor their progress, detect failures, and automatically initiate recovery or post-processing tasks.

### 🔌 Pipeline-Agnostic Architecture
Define analyses once, deploy across multiple pipelines. Asimov's extensible plugin system allows you to add support for new analysis tools without modifying the core framework. Current implementations include gravitational wave parameter estimation pipelines (LALInference, Bilby, BayesWave, RIFT), with support for custom pipelines.

### 📋 Centralized Configuration
All ongoing, completed, and scheduled analyses are recorded in version-controlled ledgers, making it easy to find jobs, configurations, and results. Every analysis is tracked and reproducible.

### 📊 Reporting & Monitoring
Generate both machine-readable and human-friendly reports of all monitored jobs, with automatic collation of log files, diagnostic outputs, and status summaries.

### 🗂️ Results Management
Special tools help manage analysis outputs, ensure data integrity, and organize results for publication and archival.

### 🔄 Workflow Automation
Set up continuous monitoring that automatically:
- Starts jobs when dependencies are met
- Initiates post-processing when jobs complete
- Handles errors and resubmissions
- Generates reports and summaries

---

## 🌊 Case Study: Gravitational Waves

**Proven at scale in production:** Asimov was developed by and is actively used by the **LIGO, Virgo, and KAGRA collaborations** for gravitational wave parameter estimation.

### Real-World Impact

- **GWTC-2, GWTC-3, and GWTC-4.0 catalogs** - Managed parameter estimation for 90+ gravitational wave events
- **O3 & O4 observing runs** - Continuous automated analysis of new detections
- **Multiple pipelines** - Unified interface for LALInference, Bilby, BayesWave, and RIFT
- **Production-ready** - Battle-tested on hundreds of analyses over multiple years

This production use demonstrates Asimov's capability to handle:
- **Complex Bayesian inference** (days to weeks per job)
- **Hundreds of jobs per event** (different parameter configurations)
- **Catalog-scale workflows** (90+ events × multiple pipelines)
- **Critical scientific output** (published in major collaboration papers)

See [USERS.md](USERS.md) for institutions and research groups using Asimov.

---

## 🔬 Beyond Gravitational Waves

While gravitational wave analysis is the primary driver, **Asimov's architecture is general-purpose**. It's suitable for any scientific domain requiring:

### Potential Applications

- **Astrophysics & Cosmology** - Parameter estimation for transient events, population studies, systematic surveys
- **Climate Science** - Model ensembles, parameter sweeps, multi-model comparisons
- **Particle Physics** - Monte Carlo campaigns, detector simulations, systematic studies
- **Computational Chemistry** - Molecular dynamics campaigns, conformational searches
- **Machine Learning** - Hyperparameter sweeps, model training pipelines, ensemble methods
- **Any domain with:**
  - Long-running computational jobs (hours to weeks)
  - Multiple analysis tools to coordinate
  - Need for systematic, reproducible workflows
  - HPC cluster infrastructure

### Adding Your Pipeline

Asimov provides a plugin architecture for adding new analysis pipelines. If your field has established analysis tools that run on HPC clusters, they can be integrated with Asimov. See [Contributing](#-contributing) for information on extending Asimov to new domains.

---

## 📦 Installing Asimov

Asimov is written in Python and available on PyPI and conda-forge.

### Via pip
```bash
pip install asimov
```

### Via conda
```bash
conda install -c conda-forge asimov
```

### Requirements

Asimov requires `git` to be installed and configured:
```bash
git config --global user.email "you@example.com"
git config --global user.name "Your Name"
```

**Supported Python versions:** 3.8+

---

## ⚡ Quick Start

Get started with Asimov in minutes. This example uses gravitational wave analysis:

### 1. Create a new project
```bash
mkdir my-analysis-project
cd my-analysis-project
asimov init "My Analysis Project"
```

### 2. Configure your workflow
```bash
# For gravitational wave analysis, you can use pre-configured templates:
asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe.yaml
asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe-priors.yaml

# For other domains, you'll create custom configuration files (see docs)
```

### 3. Add your analysis target
```bash
# Example: GW event
asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/events/gwtc-2-1/GW150914_095045.yaml
```

### 4. Define analyses
```bash
asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/analyses/production-default.yaml -e GW150914_095045
```

### 5. Build and submit jobs
```bash
asimov manage build    # Generate pipeline-specific configuration files
asimov manage submit   # Submit to cluster
```

### 6. Monitor your jobs
```bash
# Check status once
asimov monitor

# Or start continuous monitoring (checks every 15 minutes)
asimov start
```

Asimov will automatically handle post-processing, restart failed jobs, and organize results when complete!

**For non-GW applications:** See the [documentation](https://asimov.docs.ligo.org/asimov) for guides on adapting Asimov to your analysis workflows.

---

## 🤔 Do I Need Asimov?

**You should consider Asimov if you:**

- Are running **long-running analyses** on HPC clusters (hours to weeks per job)
- Need to **coordinate multiple analysis pipelines or tools**
- Want **reproducible, version-controlled** analysis configurations
- Are managing **many jobs** with complex dependencies
- Need **automated monitoring** and error recovery
- Are conducting **systematic studies** with parameter variations
- Want to **scale** from exploratory analyses to production campaigns

**Common Use Cases:**

- 🌊 **Parameter estimation** - Bayesian inference, MCMC, nested sampling
- 📊 **Systematic studies** - Parameter sweeps, sensitivity analyses
- 📚 **Large-scale campaigns** - Catalogs, surveys, ensemble runs
- 🔬 **Multi-tool comparisons** - Compare results across different analysis pipelines
- 👥 **Collaborative workflows** - Shared, reproducible configurations
- 🤖 **Automated pipelines** - Continuous analysis of new data

**Gravitational Wave Researchers:**
Asimov is production-ready with full support for LALInference, Bilby, BayesWave, and RIFT.

**Other Scientific Domains:**
Asimov's architecture is extensible to other fields. See [Beyond Gravitational Waves](#-beyond-gravitational-waves) for potential applications.

---

## 📖 Example Workflow

Here's what a typical Asimov workflow looks like:

```
1. Initialize project       → asimov init
                            ↓
2. Configure defaults       → asimov apply (settings & priors)
                            ↓
3. Add events              → asimov apply (event data)
                            ↓
4. Add analyses            → asimov apply (analysis configs)
                            ↓
5. Build configs           → asimov manage build
                            ↓
6. Submit to cluster       → asimov manage submit
                            ↓
7. Monitor progress        → asimov start (automated)
                            ↓
8. [Automatic steps]
   - Job monitoring
   - Error detection & recovery
   - Post-processing (PESummary)
   - Results organization
                            ↓
9. Access results          → Organized in results/ directory
```

All configurations and job metadata are stored in `.asimov/ledger.yml` for full reproducibility.

---

## 🔧 Extensibility

Asimov's plugin architecture allows new analysis pipelines to be integrated without modifying the core framework.

### Currently Supported Pipelines

Gravitational wave parameter estimation pipelines (production-ready):

| Pipeline | Description | Status |
|----------|-------------|--------|
| **LALInference** | Nested sampling & MCMC parameter estimation | ✅ Production |
| **Bilby** | Modern Bayesian inference framework | ✅ Production |
| **BayesWave** | Unmodeled analysis & glitch subtraction | ✅ Production |
| **RIFT** | Rapid parameter estimation | ✅ Production |

### Adding New Pipelines

To add support for a new analysis tool:

1. **Define the interface** - Create a pipeline class implementing Asimov's base interface
2. **Configuration mapping** - Define how Asimov configurations map to your tool's inputs
3. **Job management** - Specify how to build, submit, and monitor jobs
4. **Post-processing** - Define result handling and validation

See the [documentation](https://asimov.docs.ligo.org/asimov) and [Contributing Guide](CONTRIBUTING.rst) for detailed instructions on adding pipeline support.

### Future Extensions

- **Gravitic** - Framework for experimental gravitational wave pipelines
- **Machine learning workflows** - Training pipeline management
- **Custom pipelines** - Community contributions for new domains

---

## 🗺️ Roadmap

### Gravitic Pipelines
Support for pipelines constructed using [gravitic](https://github.com/transientlunatic/gravitic), allowing experimental tools to be used without constructing entire new pipelines. This will also enable Asimov to manage the training of machine learning algorithms.

### Workflow Replication & Extension
Allow existing workflows to be duplicated (similar to `git clone`), extended with new jobs that can access completed jobs from the parent workflow, and replicated with modifications for systematic studies.

### Enhanced Reporting
Web-based dashboards for real-time job monitoring and analysis status visualization.


### Multi-Messenger Astronomy
Improved support for joint electromagnetic and gravitational wave analyses, multi-wavelength campaigns.

---

## 🤝 Contributing

We welcome contributions from the community! Whether you're:

- 🐛 Reporting bugs
- 💡 Suggesting features
- 📝 Improving documentation
- 🔧 Adding pipeline support
- 🧪 Writing tests

Please see our [Contributors' Guide](CONTRIBUTING.rst) to get started!

### Ways to Contribute

- Report issues on our [Issue Tracker](https://git.ligo.org/etive-io/asimov/-/issues)
- Submit pull requests with improvements
- Improve documentation and examples
- Share your use cases and workflows
- **Add support for new analysis pipelines** - especially from other scientific domains!
- Contribute examples for non-GW applications

---

## 📚 Citation

If you use Asimov in your research, please cite it! This helps us demonstrate impact and secure continued development support.

**BibTeX:**
```bibtex
@ARTICLE{asimov-paper,
      author = {{Williams}, Daniel and {Veitch}, John and {Chiofalo}, Maria and {Schmidt}, Patricia and {Udall}, Rhiannon and {Vajpeyi}, Avi and {Hoy}, Charlie},
        title = "{Asimov: A framework for coordinating parameter estimation workflows}",
      journal = {The Journal of Open Source Software},
    keywords = {Python, astronomy, gravitational waves, General Relativity and Quantum Cosmology, Physics - Data Analysis, Statistics and Probability},
        year = 2023,
        month = apr,
      volume = {8},
      number = {84},
          eid = {4170},
        pages = {4170},
          doi = {10.21105/joss.04170},
archivePrefix = {arXiv},
      eprint = {2207.01468},
primaryClass = {gr-qc},
}
```

See [CITATION.cff](CITATION.cff) for more citation formats.

Publications using Asimov should also reference the relevant pipeline papers as appropriate for your domain.

---

## 👨‍💻 Authors

**Asimov** is developed by the **LIGO, Virgo, and KAGRA collaborations**.

**Primary Maintainer:** Daniel Williams ([@transientlunatic](https://github.com/transientlunatic))

**Development Support:** Science and Technology Facilities Council (STFC) and the [Institute for Gravitational Research](https://www.gla.ac.uk/schools/physics/research/groups/igr/) at the [University of Glasgow](https://www.glasgow.ac.uk).

### Contributors

We're grateful to all our contributors! See the full list in [CONTRIBUTORS.md](CONTRIBUTORS.md).

---

## 📄 License

Asimov is released under the [MIT License](LICENSE).

---

## 🔗 Links

- **Documentation:** https://asimov.docs.ligo.org/asimov
- **Issue Tracker:** https://git.ligo.org/asimov/asimov/-/issues
- **Releases:** https://git.ligo.org/asimov/asimov/-/releases
- **PyPI:** https://pypi.org/project/asimov/
- **Conda:** https://anaconda.org/conda-forge/asimov

---

<div align="center">

**⭐ If Asimov helps your research, please consider starring the repository! ⭐**

*Made with ❤️ by the scientific computing community*

</div>
