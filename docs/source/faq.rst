.. _faq:

===========================
Frequently Asked Questions
===========================

This page answers common questions about asimov. If you don't find your answer here, check the :ref:`troubleshooting` guide or search the documentation.

General Questions
=================

What is asimov?
---------------

Asimov is a workflow management and automation platform for scientific analyses, primarily developed for gravitational wave parameter estimation. It helps you:

- Set up and configure analyses
- Submit jobs to computing clusters
- Monitor job progress
- Collect and archive results
- Manage multi-event studies

Who should use asimov?
----------------------

Asimov is designed for professional researchers who need to run parameter estimation analyses on gravitational wave data. It's particularly useful if you:

- Analyze multiple events as part of a catalog
- Run multiple analyses on the same event
- Need to track and reproduce analysis configurations
- Work collaboratively on analyses
- Want automated job monitoring and error recovery

What does the name "asimov" mean?
----------------------------------

Asimov is named after Isaac Asimov, the science fiction author famous for his "Robot" series and the Three Laws of Robotics. The name reflects the software's role in automating scientific analyses. The alternative command name "olivaw" refers to R. Daneel Olivaw, a robot character from Asimov's novels.

Terminology Questions
=====================

What's the difference between "Production" and "Analysis"?
----------------------------------------------------------

They're the same thing! In asimov v0.4.0, "Production" was renamed to "SimpleAnalysis" to better reflect the three-tier analysis hierarchy (SimpleAnalysis, SubjectAnalysis, ProjectAnalysis).

**Current usage:**
- Prefer "analysis" in documentation and discussions
- The ledger still uses ``productions:`` key for backward compatibility
- Internally, code may still use "production" for historical reasons

When you see "production," think "single-event analysis."

See :ref:`glossary` for more details.

What's the difference between Event, Subject, and Project?
-----------------------------------------------------------

- **Event**: A physical occurrence being analyzed (e.g., a gravitational wave detection like GW150914)
- **Subject**: Another name for an event, used particularly in the context of SubjectAnalysis
- **Project**: A collection of events and their analyses, with shared configuration

Think of it as: A **project** contains multiple **events**, and each event is the **subject** of various analyses.

What's the difference between Repository and Store?
----------------------------------------------------

- **Repository**: A git repository containing event-specific data files (PSDs, calibration files, configurations). It's mutable - files can be edited during analysis.
- **Store**: A read-only archive of completed analysis results. Once results are stored, they can't be modified.

**Use case:**
- Repository: "Where I build my analysis"
- Store: "Where I archive my results"

See :ref:`glossary` for detailed explanations.

What is a Blueprint?
--------------------

A Blueprint is a YAML document that defines events, analyses, or defaults to be added to your project. Blueprints support:

- Template variables (using Liquid syntax)
- Conditional logic
- Remote loading from URLs
- Reusable configurations

**Example use:**

.. code-block:: bash

   asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/events/gwtc-2-1/GW150914_095045.yaml

See :ref:`blueprints` for more information.

Setup and Configuration
=======================

How do I install asimov?
------------------------

.. code-block:: bash

   pip install asimov

For development installation:

.. code-block:: bash

   git clone https://github.com/etive-io/asimov
   cd asimov
   pip install -e .[docs]

See :ref:`installation` for detailed instructions.

Do I need HTCondor installed locally?
--------------------------------------

Yes, asimov requires the HTCondor Python bindings (``htcondor`` package) to submit and monitor jobs. However, you don't need to run a full HTCondor cluster locally - you just need to be able to submit to a remote scheduler.

Which Python version does asimov support?
------------------------------------------

Asimov requires Python 3.9 or later. We recommend using the latest stable Python version.

Can I use asimov without LIGO credentials?
-------------------------------------------

For public data (e.g., from GWOSC - the Gravitational Wave Open Science Center), yes! You can analyze public gravitational wave data without LIGO credentials. However, accessing LIGO proprietary data requires:

- LIGO.ORG credentials
- Kerberos authentication (``kinit``)
- Access to LIGO computing clusters

Can I run asimov on my laptop?
-------------------------------

You can *manage* analyses from your laptop, but the actual computational jobs should run on a computing cluster. Asimov acts as a controller that:

- Runs locally on your laptop/workstation
- Submits jobs to a remote HTCondor cluster
- Monitors those jobs
- Collects results when complete

Workflow Questions
==================

What's the basic workflow for analyzing an event?
--------------------------------------------------

1. **Initialize project:**

   .. code-block:: bash
   
      asimov init "My Project"

2. **Add defaults:**

   .. code-block:: bash
   
      asimov apply -f <defaults-url>

3. **Add event:**

   .. code-block:: bash
   
      asimov apply -f <event-blueprint>

4. **Add analyses:**

   .. code-block:: bash
   
      asimov apply -f <analysis-blueprint> -e EVENT_NAME

5. **Build and submit:**

   .. code-block:: bash
   
      asimov manage build
      asimov manage submit

6. **Monitor:**

   .. code-block:: bash
   
      asimov monitor --once
      # or
      asimov start  # automatic monitoring

See :ref:`getting-started` for a complete tutorial.

How do I analyze multiple events?
----------------------------------

Add each event to the same project:

.. code-block:: bash

   asimov apply -f event1.yaml
   asimov apply -f event2.yaml
   asimov apply -f event3.yaml
   
   # Build all
   asimov manage build
   asimov manage submit

Asimov will manage all events in parallel.

How do I run multiple analyses on one event?
---------------------------------------------

Add multiple productions/analyses to the event:

.. code-block:: yaml

   events:
     - name: GW150914_095045
       productions:
         - Prod0:
             pipeline: bayeswave
             comment: "PSD estimation"
         - Prod1:
             pipeline: bilby
             approximant: IMRPhenomXPHM
             needs: [Prod0]  # Wait for PSD

Then build and submit as usual.

How do I rerun an analysis?
----------------------------

1. **Update status to ready:**

   .. code-block:: bash
   
      asimov production update EVENT PROD --status ready

2. **Force rebuild:**

   .. code-block:: bash
   
      asimov manage build --production PROD --force

3. **Resubmit:**

   .. code-block:: bash
   
      asimov manage submit --production PROD

Can I pause and resume monitoring?
-----------------------------------

Yes:

.. code-block:: bash

   # Start automatic monitoring
   asimov start
   
   # Stop it
   asimov stop
   
   # Restart
   asimov start

The monitoring daemon runs in the background and automatically handles jobs.

Pipeline Questions
==================

Which pipelines does asimov support?
-------------------------------------

Built-in pipelines:

- **bilby**: Bayesian inference library (parameter estimation)
- **bayeswave**: Glitch characterization and PSD estimation
- **RIFT**: Rapid parameter estimation
- **lalinference**: Legacy LIGO PE (deprecated in v0.7)

External pipelines (separate packages):

- **pycbc**: CBC parameter estimation (via asimov-pycbc)
- **cogwheel**: Reduced-order parameter estimation (via asimov-cogwheel)

See :ref:`pipelines` for pipeline-specific documentation.

How do I choose which pipeline to use?
---------------------------------------

**For parameter estimation:**

- **bilby**: General purpose, well-tested, good for most analyses
- **RIFT**: Faster for certain systems, good for rapid follow-up
- **pycbc**: Optimized for CBC, especially for large-scale surveys
- **cogwheel**: Very fast for specific waveform models

**For glitch characterization:**

- **bayeswave**: Standard tool for glitch analysis and PSD estimation

**Recommendation:** Start with bilby unless you have specific needs.

How do I add support for a new pipeline?
-----------------------------------------

See :ref:`pipelines-dev` for a complete guide. The basic steps are:

1. Create a Pipeline subclass
2. Implement required methods (``build_dag``, ``detect_completion``, etc.)
3. Register via entry point in ``pyproject.toml``
4. Install and use

Can I use custom configuration templates?
------------------------------------------

Yes! Asimov uses Liquid templates for configuration files. You can:

1. Create custom templates in your template directory
2. Configure the directory in ``asimov.conf``:

   .. code-block:: ini
   
      [templating]
      directory = my-templates

3. Templates have access to all ledger metadata

See the ``config.rst`` guide for template syntax.

Job Management
==============

How do I check if my jobs are running?
---------------------------------------

.. code-block:: bash

   # Quick text status
   asimov report status
   
   # HTML report
   asimov report html --open
   
   # Just one event
   asimov report status --event GW150914_095045

Why is my job stuck in "wait" status?
--------------------------------------

Common reasons:

1. **Dependencies not met:** Check ``needs`` field - required analyses must finish first
2. **Manual wait:** You set status to "wait" intentionally
3. **Missing metadata:** Required configuration fields are missing

**Solution:** Check dependencies:

.. code-block:: bash

   asimov report status --event EVENT

Set to "ready" when ready to run:

.. code-block:: bash

   asimov production update EVENT PROD --status ready

Why is my job stuck in "stuck" status?
---------------------------------------

This means HTCondor has held the job due to an error. Common causes:

1. Memory or disk limit exceeded
2. Missing input files
3. Executable not found
4. Expired credentials

**Diagnosis:**

.. code-block:: bash

   condor_q -hold <job_id>

See :ref:`troubleshooting` for solutions.

How do I manually stop a job?
------------------------------

.. code-block:: bash

   asimov manage stop --production PROD

To remove from queue entirely:

.. code-block:: bash

   asimov manage cancel --production PROD

How long do jobs typically take?
---------------------------------

Depends on the analysis:

- **PSD estimation (bayeswave):** Minutes to hours
- **Parameter estimation (bilby):** Hours to days
- **Population studies:** Days to weeks

Factors affecting runtime:
- Waveform model complexity
- Number of live points (nested sampling)
- Signal-to-noise ratio
- Number of detectors

Configuration and Customization
================================

How do I change the default settings for a pipeline?
-----------------------------------------------------

Add pipeline defaults in the ledger:

.. code-block:: yaml

   pipelines:
     bilby:
       sampler:
         nlive: 4000
       likelihood:
         marginalization:
           distance: true
           phase: true

Or in ``asimov.conf``:

.. code-block:: ini

   [bilby]
   environment = /path/to/conda/env

How do I set project-wide defaults?
------------------------------------

Use the ``defaults`` section in the ledger:

.. code-block:: yaml

   defaults:
     scheduler:
       accounting: ligo.prod.o4.cbc.pe.bilby
       request memory: 8GB
     priors:
       chirp_mass:
         minimum: 25
         maximum: 100

These apply to all events and analyses unless overridden.

Can I use a different ledger backend?
--------------------------------------

Yes! Asimov supports:

- **YAML files** (default, good for small projects)
- **GitLab issues** (good for collaboration)
- **TinyDB** (lightweight database)
- **MongoDB** (for large-scale projects)

Configure in ``asimov.conf``:

.. code-block:: ini

   [ledger]
   engine = gitlab
   location = group/project-name

Where are my results stored?
-----------------------------

By default, results are stored in the ``results/`` directory within your project. Configure in ``asimov.conf``:

.. code-block:: ini

   [storage]
   root = /data/pe-results
   results_store = o4-catalog/

Results will be in ``/data/pe-results/o4-catalog/EVENT/PROD/``.

Collaboration and Sharing
==========================

Can multiple people work on the same project?
----------------------------------------------

Yes! Use a GitLab ledger backend for collaborative projects:

.. code-block:: ini

   [ledger]
   engine = gitlab
   location = pe-group/o4-events

Each collaborator clones the project and can submit jobs. The ledger stays synchronized via GitLab.

How do I share my configuration with colleagues?
-------------------------------------------------

1. **Commit project configuration:**

   .. code-block:: bash
   
      git add asimov.conf
      git commit -m "Add project configuration"

2. **Create blueprints** for reusable configurations

3. **Share via GitLab/GitHub** or curated defaults repository

How do I reproduce someone else's analysis?
--------------------------------------------

If they used asimov:

1. Clone their project
2. Check out the specific commit/tag
3. Review the ledger for that event/analysis
4. The configuration is fully specified in the ledger

Asimov makes analyses reproducible by design.

Troubleshooting
===============

My question isn't answered here
--------------------------------

Try:

1. :ref:`troubleshooting` guide for common problems
2. :ref:`glossary` for terminology
3. Pipeline-specific docs in :ref:`pipelines`
4. Search the `GitHub issues <https://github.com/etive-io/asimov/issues>`_
5. Ask in LIGO/Virgo/KAGRA Mattermost
6. Open a new issue with detailed description

How do I report a bug?
----------------------

Open an issue on GitHub with:

1. Asimov version (``asimov --version``)
2. Minimal reproducible example
3. Expected vs actual behavior
4. Relevant logs and error messages
5. Environment details (OS, Python version)

How do I request a feature?
----------------------------

Open a GitHub issue describing:

1. What you want to do
2. Why current functionality doesn't work
3. Proposed solution (if you have one)
4. Use cases

Or better yet, submit a pull request!

Where can I find more examples?
--------------------------------

- :ref:`getting-started`: Basic tutorial
- :ref:`tutorials`: Step-by-step guides  
- `asimov-data repository <https://git.ligo.org/asimov/data>`_: Curated blueprints
- Pipeline docs: Pipeline-specific examples

Advanced Topics
===============

Can I use asimov programmatically (Python API)?
------------------------------------------------

Yes! Asimov has a Python API:

.. code-block:: python

   from asimov.project import Project
   
   # Load project
   project = Project.load()
   
   # Get events
   for event in project.events:
       print(event.name)
       for production in event.productions:
           print(f"  {production.name}: {production.status}")

See :ref:`python-api` for details.

Can I extend asimov with custom hooks?
---------------------------------------

Yes! Asimov supports lifecycle hooks:

- ``before_config``: Before config generation
- ``before_submit``: Before job submission  
- ``after_completion``: After job completes
- ``after_upload``: After results archived

See :ref:`hooks` for implementation details.

How do I optimize for a large number of events?
------------------------------------------------

For large-scale projects (100+ events):

1. **Use database backend:**

   .. code-block:: ini
   
      [ledger]
      engine = mongodb

2. **Increase cache time:**

   .. code-block:: ini
   
      [condor]
      cache_time = 1800

3. **Use event-specific commands:**

   .. code-block:: bash
   
      asimov manage build --event EVENT

4. **Consider batch operations** with scripts

Can I run asimov in a container?
---------------------------------

Yes! You can:

1. Create a Docker/Singularity container with asimov
2. Mount your project directory
3. Ensure HTCondor access from container
4. Run asimov commands

Note: Job submission from containers may require special HTCondor configuration.

Performance Expectations
=========================

How many events can asimov handle?
-----------------------------------

Asimov has been used successfully with:

- **Small projects**: 1-10 events, simple monitoring
- **Medium projects**: 10-100 events, database recommended
- **Large projects**: 100+ events, optimized configuration needed

Performance depends on ledger backend and HTCondor pool size.

How often should I run monitoring?
-----------------------------------

Default is every 15 minutes. Adjust based on:

- **Frequent (5-10 min)**: Active development, rapid turnaround
- **Normal (15-30 min)**: Production analyses
- **Infrequent (1+ hour)**: Long-running jobs, reduce cluster load

Configure in ``asimov.conf``:

.. code-block:: ini

   [condor]
   cron_minute = */15

Does asimov work with non-GW data?
-----------------------------------

Asimov is designed for gravitational wave analyses but could be adapted for other domains. The core workflow management is general-purpose, but:

- Some pipelines are GW-specific
- Data access assumes GW frame files
- Metadata fields are GW-oriented

For non-GW use, you'd need to:

1. Create custom pipelines
2. Adapt data handling
3. Define appropriate metadata schema

See Also
========

- :ref:`getting-started`: Tutorial for new users
- :ref:`architecture`: Understanding asimov
- :ref:`troubleshooting`: Problem-solving guide
- :ref:`cli-reference`: Complete command reference
