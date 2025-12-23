.. _architecture:

======================
Architecture Overview
======================

This document provides a high-level overview of asimov's architecture, explaining how the different components work together to manage and automate scientific analyses.

Core Architecture
=================

Asimov is built around a workflow management system that coordinates the submission, monitoring, and post-processing of scientific analysis jobs. The architecture consists of several interconnected components that work together to provide a seamless analysis experience.

Key Components
--------------

The main components of asimov are:

1. **Ledger**: The central database that stores all information about projects, events, and analyses
2. **Event**: Represents a subject of analysis (e.g., a gravitational wave detection)
3. **Analysis**: Defines a specific analysis task to be performed
4. **Pipeline**: The interface to external analysis software (e.g., bilby, bayeswave, RIFT)
5. **Condor**: Manages job submission and monitoring on HTCondor clusters
6. **Storage**: Handles result storage and verification

Workflow
--------

The typical workflow in asimov follows this path:

.. code-block:: text

   Ledger → Event → Analysis → Pipeline → Condor → Results → Storage

1. **Ledger**: Contains all configuration data and analysis specifications
2. **Event**: Created from ledger data, represents the subject being analyzed
3. **Analysis**: Defines what should be done with the event data
4. **Pipeline**: Generates configuration files and DAG specifications for the chosen analysis software
5. **Condor**: Executes the analysis jobs on a computing cluster
6. **Results**: Collected after job completion
7. **Storage**: Results are verified and stored in a read-only archive

Analysis Type Hierarchy
========================

Asimov defines three types of analyses based on their scope and data requirements:

SimpleAnalysis
--------------

.. note::
   Before version 0.4, ``SimpleAnalysis`` instances were called "Productions". You may still see this terminology in older documentation or code comments.

Simple analyses operate on a single event and use a specific set of configuration settings. They are the most common type of analysis in asimov.

**Use cases:**

- Single-event parameter estimation with bilby
- Single-event parameter estimation with RIFT
- PSD estimation with bayeswave
- Glitch characterization

**Key characteristics:**

- Operates on data from one event only
- Has direct access to event metadata (calibration files, PSDs, etc.)
- Can depend on other simple analyses for the same event
- Results are stored in the event's directory structure

**Example:**

.. code-block:: yaml

   productions:
     - Prod0:
         pipeline: bilby
         approximant: IMRPhenomXPHM
         status: ready
         needs:
           - Prod1  # Depends on PSD from Prod1

SubjectAnalysis
---------------

Subject analyses (also called "Event analyses") can access results from multiple simple analyses performed on a single event. These are useful for combining or comparing results.

**Use cases:**

- Combining posterior samples from multiple PE runs
- Comparing results from different waveform models
- Creating summary plots for a single event

**Key characteristics:**

- Operates on results from simple analyses for one event
- Has access to all simple analysis results for that event
- Can aggregate or combine analysis outputs
- Results are stored at the event level

**Example:**

.. code-block:: yaml

   event_analyses:
     - Compare_Waveforms:
         subjects:
           - Prod0
           - Prod1
         pipeline: pesummary
         status: ready

ProjectAnalysis
---------------

Project analyses are the most general type and have access to results from all events and their analyses in a project. These are ideal for cross-event studies.

**Use cases:**

- Population studies across multiple events
- Catalog analyses
- Rate calculations
- Multi-event parameter estimation

**Key characteristics:**

- Operates on results from all events in the project
- Has access to event and simple analysis results
- Suitable for large-scale studies
- Results are stored at the project level

**Example:**

.. code-block:: yaml

   project_analyses:
     - PopulationStudy:
         pipeline: bilby
         events:
           - GW150914_095045
           - GW151012_095443
           - GW151226_033853
         status: ready

Component Relationships
=======================

Event
-----

An ``Event`` represents a physical occurrence that needs to be analyzed (e.g., a gravitational wave detection). Each event has:

- **Metadata**: Detector configuration, GPS time, calibration files, PSDs
- **Repository**: A git repository containing event-specific data and configuration
- **Analyses**: One or more analyses to be performed on this event
- **Data Quality**: Information about segment quality, data channels, etc.

Analysis vs Production
-----------------------

.. important::
   **Terminology Change in v0.4.0**
   
   Prior to version 0.4, what we now call ``SimpleAnalysis`` was referred to as "Production". While the codebase has been updated, you may still encounter "production" terminology in:
   
   - Legacy configuration files
   - Older documentation
   - Variable names in the codebase (e.g., ``productions`` in the ledger)
   - Command output and log messages
   
   These terms are synonymous in the context of asimov.

An **Analysis** (or **Production** in older terminology) defines a specific computational task:

- Which pipeline to use (bilby, bayeswave, RIFT, etc.)
- What configuration parameters to apply
- Which data to analyze
- What dependencies it has on other analyses
- Current status (wait, ready, running, finished, etc.)

Pipeline
--------

A **Pipeline** is an interface class that bridges asimov with external analysis software. Each pipeline implementation knows how to:

- Generate configuration files from ledger metadata
- Build DAG files for HTCondor
- Submit jobs to the cluster
- Monitor job progress
- Detect completion
- Collect results

Currently supported pipelines:

- ``bilby`` - Bayesian inference library
- ``bayeswave`` - Glitch characterization and PSD estimation
- ``RIFT`` - Rapid parameter estimation
- ``lalinference`` - Legacy LIGO parameter estimation (deprecated in v0.7)

Ledger
------

The **Ledger** is asimov's central database. It stores:

- Project-wide defaults
- Event metadata
- Analysis specifications
- Job status and history
- Review information

The ledger uses a hierarchical structure where settings can be specified at three levels:

1. **Project level**: Applies to all events and analyses
2. **Event level**: Applies to all analyses for that event
3. **Analysis level**: Applies only to that specific analysis

Settings at lower levels override those at higher levels.

**Ledger formats:**

Asimov supports multiple ledger storage backends:

- YAML files (default for local projects)
- GitLab issues (for collaborative projects)
- TinyDB (lightweight database)
- MongoDB (for large-scale deployments)

Repository vs Store
-------------------

Asimov uses two different storage concepts:

**Repository** (``EventRepo``):

- A git repository containing event-specific data
- Stores configuration files, PSDs, calibration envelopes
- Version-controlled and mutable during analysis
- Located in the project's ``checkouts/`` directory

**Store**:

- A read-only archive for completed results
- Stores final analysis products (posterior samples, plots, logs)
- Includes manifest and hash verification
- Immutable once created
- Located in user-specified storage directory

Blueprint System
----------------

**Blueprints** are template documents that can be applied to the ledger to add or modify events and analyses. They support:

- Liquid templating for dynamic content
- Variable substitution
- Conditional logic
- Inheritance and merging

Blueprints have a ``kind`` field that specifies what they define:

- ``event``: Adds or updates an event
- ``analysis``: Adds an analysis to an event
- ``defaults``: Sets project or pipeline defaults

Job Management Flow
===================

The complete lifecycle of an analysis job:

1. **Initialization**
   
   - Event added to ledger via ``asimov apply``
   - Analysis specifications added to event
   - Status set to ``wait`` or ``ready``

2. **Build Phase** (``asimov manage build``)
   
   - Pipeline generates configuration files
   - Configuration stored in event repository
   - Repository committed to git
   - Status remains ``ready``

3. **Submission** (``asimov manage submit``)
   
   - Pipeline creates DAG file
   - DAG submitted to HTCondor scheduler
   - Job ID recorded in ledger
   - Status changed to ``running``

4. **Monitoring** (``asimov monitor``)
   
   - Job progress checked periodically
   - Log files inspected for errors
   - Stuck jobs detected and resubmitted
   - Status updated based on job state

5. **Completion Detection**
   
   - Pipeline checks for completion indicators
   - Results validated
   - Status changed to ``finished``

6. **Post-processing**
   
   - Post-processing hooks executed (e.g., PESummary)
   - Additional plots and summaries generated
   - Status changed to ``processing``

7. **Result Collection**
   
   - Analysis products collected
   - Files verified with hash checksums
   - Results moved to read-only store
   - Manifest created
   - Status changed to ``uploaded``

Status Lifecycle
================

Analyses progress through several status states:

**Waiting States:**

- ``wait``: Analysis is not ready to run (waiting for dependencies or user action)
- ``ready``: Analysis is ready to be built and submitted

**Active States:**

- ``running``: Job is executing on the cluster
- ``processing``: Post-processing is in progress

**Completion States:**

- ``finished``: Analysis completed successfully, results not yet uploaded
- ``uploaded``: Results have been collected and stored

**Error States:**

- ``stuck``: Job is held or encountering errors
- ``stopped``: Job was manually stopped
- ``cancelled``: Job was cancelled by user

**Manual States:**

- ``manual``: Job requires manual intervention

Data Flow
=========

Configuration and data flow through asimov in this manner:

.. code-block:: text

   Project Defaults
         ↓
   Pipeline Defaults
         ↓
   Event Metadata
         ↓
   Analysis Metadata
         ↓
   Liquid Template
         ↓
   Configuration File
         ↓
   HTCondor DAG
         ↓
   Analysis Execution
         ↓
   Results
         ↓
   Store

At each level, metadata can override or extend settings from higher levels, allowing for flexible configuration while maintaining sensible defaults.

Categories and Tags
===================

Asimov uses a ``category`` system to organize related data:

**Common categories:**

- ``C01_offline``: Calibration version 01, offline processing
- ``C02_offline``: Calibration version 02, offline processing
- ``O3a``: Observing run 3a
- ``O3b``: Observing run 3b

Categories are used to:

- Group calibration files by version
- Organize PSDs by processing epoch
- Separate different analysis campaigns
- Track data quality flags

The category is typically specified at the event level and inherited by all analyses for that event.

Next Steps
==========

Now that you understand asimov's architecture, you may want to:

- Read the :ref:`getting-started` guide for a practical tutorial
- Learn about the :ref:`ledger` format in detail
- Explore :ref:`pipelines-dev` to add support for new analysis software
- See the :ref:`analysis guide<analyses>` for more details on analysis types
