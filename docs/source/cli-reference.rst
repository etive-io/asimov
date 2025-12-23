.. _cli-reference:

==========================
CLI Commands Reference
==========================

This guide documents all command-line interface (CLI) commands available in asimov. The main command is ``asimov`` (also available as ``olivaw`` for backwards compatibility).

Command Structure
=================

Asimov commands follow this general structure:

.. code-block:: bash

   asimov [OPTIONS] COMMAND [ARGS]...

Most commands operate on the current asimov project (identified by the ``.asimov`` directory).

Global Options
==============

``--version``
   Show asimov version and exit.

``--help``
   Show help message and exit.

Project Management Commands
============================

``asimov init``
---------------

Initialize a new asimov project in the current directory.

**Syntax:**

.. code-block:: bash

   asimov init [OPTIONS] NAME

**Arguments:**

``NAME``
   Name of the project (required).

**Options:**

``--directory PATH``
   Directory to create project in (default: current directory).

``--ledger-engine TEXT``
   Ledger storage engine (default: yamlfile).
   Options: yamlfile, gitlab, tinydb, mongodb.

**Examples:**

Create a new project called "O4 Analysis":

.. code-block:: bash

   asimov init "O4 Analysis"

Create a project in a specific directory:

.. code-block:: bash

   mkdir my-project
   cd my-project
   asimov init "My Project"

Create a project with GitLab ledger:

.. code-block:: bash

   asimov init --ledger-engine gitlab "Collaborative Project"

``asimov clone``
----------------

Clone an existing asimov project from a remote location.

**Syntax:**

.. code-block:: bash

   asimov clone [OPTIONS] URL

**Arguments:**

``URL``
   URL of the project to clone.

**Options:**

``--directory PATH``
   Local directory for cloned project.

**Example:**

.. code-block:: bash

   asimov clone https://git.ligo.org/pe/o4-catalog

Blueprint and Configuration Commands
=====================================

``asimov apply``
----------------

Apply a blueprint to the ledger, adding or updating events and analyses.

**Syntax:**

.. code-block:: bash

   asimov apply [OPTIONS]

**Options:**

``-f, --file PATH``
   Path or URL to blueprint file (required).

``-e, --event TEXT``
   Event name to apply the blueprint to (for analysis blueprints).

``--dry-run``
   Show what would be applied without making changes.

**Examples:**

Apply default production settings:

.. code-block:: bash

   asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe.yaml

Add an event:

.. code-block:: bash

   asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/events/gwtc-2-1/GW150914_095045.yaml

Add analyses to a specific event:

.. code-block:: bash

   asimov apply -f analyses.yaml -e GW150914_095045

Apply from a local file:

.. code-block:: bash

   asimov apply -f ./my-blueprint.yaml

Dry run to preview changes:

.. code-block:: bash

   asimov apply --dry-run -f blueprint.yaml

Job Management Commands
=======================

``asimov manage``
-----------------

Manage analysis jobs: build configuration files, submit jobs, stop running jobs, or cancel jobs.

**Syntax:**

.. code-block:: bash

   asimov manage [OPTIONS] COMMAND

**Subcommands:**

``build``
~~~~~~~~~

Generate configuration files for analyses.

**Syntax:**

.. code-block:: bash

   asimov manage build [OPTIONS]

**Options:**

``--event TEXT``
   Build only for specific event.

``--production TEXT``
   Build only for specific analysis/production.

``--force``
   Force rebuild even if files exist.

**Examples:**

Build all pending analyses:

.. code-block:: bash

   asimov manage build

Build for a specific event:

.. code-block:: bash

   asimov manage build --event GW150914_095045

Force rebuild:

.. code-block:: bash

   asimov manage build --force

``submit``
~~~~~~~~~~

Submit jobs to the HTCondor cluster.

**Syntax:**

.. code-block:: bash

   asimov manage submit [OPTIONS]

**Options:**

``--event TEXT``
   Submit only jobs for specific event.

``--production TEXT``
   Submit only specific analysis/production.

``--dry-run``
   Show what would be submitted without actually submitting.

**Examples:**

Submit all ready jobs:

.. code-block:: bash

   asimov manage submit

Submit jobs for one event:

.. code-block:: bash

   asimov manage submit --event GW150914_095045

Dry run:

.. code-block:: bash

   asimov manage submit --dry-run

``stop``
~~~~~~~~

Stop running jobs.

**Syntax:**

.. code-block:: bash

   asimov manage stop [OPTIONS]

**Options:**

``--event TEXT``
   Stop jobs for specific event.

``--production TEXT``
   Stop specific analysis/production.

``--force``
   Force stop even if job is in critical state.

**Example:**

.. code-block:: bash

   asimov manage stop --production Prod0

``cancel``
~~~~~~~~~~

Cancel jobs (removes them from the queue).

**Syntax:**

.. code-block:: bash

   asimov manage cancel [OPTIONS]

**Options:**

``--event TEXT``
   Cancel jobs for specific event.

``--production TEXT``
   Cancel specific analysis/production.

**Example:**

.. code-block:: bash

   asimov manage cancel --event GW150914_095045

Monitoring Commands
===================

``asimov monitor``
------------------

Check status of running jobs and perform automatic maintenance (restart stuck jobs, collect results, etc.).

**Syntax:**

.. code-block:: bash

   asimov monitor [OPTIONS]

**Options:**

``--event TEXT``
   Monitor only specific event.

``--once``
   Run once and exit (don't loop).

``--interval INTEGER``
   Monitoring interval in seconds (default: 900).

**Examples:**

Monitor all jobs once:

.. code-block:: bash

   asimov monitor --once

Continuous monitoring with 5-minute interval:

.. code-block:: bash

   asimov monitor --interval 300

Monitor specific event:

.. code-block:: bash

   asimov monitor --event GW150914_095045 --once

``asimov start``
----------------

Start the asimov monitoring daemon in the background.

**Syntax:**

.. code-block:: bash

   asimov start [OPTIONS]

**Options:**

``--interval INTEGER``
   Monitoring interval in seconds (default: 900).

**Example:**

.. code-block:: bash

   asimov start --interval 600

The daemon runs in the background and automatically:

- Checks job status
- Restarts stuck jobs
- Starts post-processing when jobs finish
- Collects results when complete

``asimov stop``
---------------

Stop the asimov monitoring daemon.

**Syntax:**

.. code-block:: bash

   asimov stop

**Example:**

.. code-block:: bash

   asimov stop

Reporting Commands
==================

``asimov report``
-----------------

Generate status reports in various formats.

**Syntax:**

.. code-block:: bash

   asimov report [OPTIONS] [COMMAND]

**Subcommands:**

``status``
~~~~~~~~~~

Show text status of all analyses.

**Syntax:**

.. code-block:: bash

   asimov report status [OPTIONS]

**Options:**

``--event TEXT``
   Show status for specific event only.

``--format TEXT``
   Output format: text, json, yaml (default: text).

**Examples:**

Show status of all analyses:

.. code-block:: bash

   asimov report status

Status for one event:

.. code-block:: bash

   asimov report status --event GW150914_095045

JSON output:

.. code-block:: bash

   asimov report status --format json > status.json

``html``
~~~~~~~~

Generate HTML report.

**Syntax:**

.. code-block:: bash

   asimov report html [OPTIONS]

**Options:**

``--output PATH``
   Output directory for HTML files (default: reports/).

``--open``
   Open report in web browser after generation.

**Examples:**

Generate HTML report:

.. code-block:: bash

   asimov report html

Generate and open in browser:

.. code-block:: bash

   asimov report html --open

Custom output directory:

.. code-block:: bash

   asimov report html --output /var/www/html/my-project/

``asimov report`` (default)
~~~~~~~~~~~~~~~~~~~~~~~~~~~

When called without a subcommand, generates an HTML report by default.

**Example:**

.. code-block:: bash

   asimov report

Event Commands
==============

``asimov event``
----------------

Manage events in the project.

**Syntax:**

.. code-block:: bash

   asimov event [OPTIONS] COMMAND

**Subcommands:**

``add``
~~~~~~~

Add a new event to the project.

**Syntax:**

.. code-block:: bash

   asimov event add [OPTIONS] NAME

**Arguments:**

``NAME``
   Name of the event (e.g., GW150914_095045).

**Options:**

``--time FLOAT``
   GPS time of the event (required).

``--interferometers TEXT``
   Comma-separated list of interferometers (e.g., H1,L1,V1).

``--repository URL``
   Git repository URL for event data.

**Example:**

.. code-block:: bash

   asimov event add GW150914_095045 \
       --time 1126259462.4 \
       --interferometers H1,L1 \
       --repository git@git.ligo.org:pe/O3/GW150914_095045

``list``
~~~~~~~~

List all events in the project.

**Syntax:**

.. code-block:: bash

   asimov event list

**Example:**

.. code-block:: bash

   asimov event list

``remove``
~~~~~~~~~~

Remove an event from the project.

**Syntax:**

.. code-block:: bash

   asimov event remove [OPTIONS] NAME

**Arguments:**

``NAME``
   Name of the event to remove.

**Options:**

``--force``
   Remove without confirmation.

**Example:**

.. code-block:: bash

   asimov event remove GW150914_095045

Production/Analysis Commands
=============================

``asimov production``
---------------------

Manage individual analyses (productions).

**Syntax:**

.. code-block:: bash

   asimov production [OPTIONS] COMMAND

**Subcommands:**

``add``
~~~~~~~

Add a new analysis to an event.

**Syntax:**

.. code-block:: bash

   asimov production add [OPTIONS] EVENT NAME

**Arguments:**

``EVENT``
   Name of the event.

``NAME``
   Name of the analysis/production (e.g., Prod0).

**Options:**

``--pipeline TEXT``
   Pipeline to use (required). Options: bilby, bayeswave, rift, lalinference.

``--status TEXT``
   Initial status (default: wait). Options: wait, ready.

``--approximant TEXT``
   Waveform approximant (for PE analyses).

**Example:**

.. code-block:: bash

   asimov production add GW150914_095045 Prod0 \
       --pipeline bilby \
       --approximant IMRPhenomXPHM \
       --status ready

``update``
~~~~~~~~~~

Update analysis metadata.

**Syntax:**

.. code-block:: bash

   asimov production update [OPTIONS] EVENT NAME

**Arguments:**

``EVENT``
   Name of the event.

``NAME``
   Name of the analysis.

**Options:**

``--set KEY=VALUE``
   Set metadata field (can be repeated).

``--status TEXT``
   Update status.

**Example:**

.. code-block:: bash

   asimov production update GW150914_095045 Prod0 --status ready

Review Commands
===============

``asimov review``
-----------------

Manage analysis reviews and quality assessments.

**Syntax:**

.. code-block:: bash

   asimov review [OPTIONS] COMMAND

**Subcommands:**

``approve``
~~~~~~~~~~~

Mark an analysis as approved.

**Syntax:**

.. code-block:: bash

   asimov review approve [OPTIONS] EVENT PRODUCTION

**Arguments:**

``EVENT``
   Event name.

``PRODUCTION``
   Analysis name.

**Options:**

``--comment TEXT``
   Review comment.

``--reviewer TEXT``
   Reviewer name.

**Example:**

.. code-block:: bash

   asimov review approve GW150914_095045 Prod0 \
       --comment "Results look good" \
       --reviewer "Jane Doe"

``reject``
~~~~~~~~~~

Mark an analysis as rejected.

**Syntax:**

.. code-block:: bash

   asimov review reject [OPTIONS] EVENT PRODUCTION

**Options:**

``--comment TEXT``
   Reason for rejection (required).

**Example:**

.. code-block:: bash

   asimov review reject GW150914_095045 Prod0 \
       --comment "Divergence detected in chains"

``prefer``
~~~~~~~~~~

Mark an analysis as preferred (when multiple analyses exist).

**Syntax:**

.. code-block:: bash

   asimov review prefer [OPTIONS] EVENT PRODUCTION

**Example:**

.. code-block:: bash

   asimov review prefer GW150914_095045 Prod1

``deprecate``
~~~~~~~~~~~~~

Mark an analysis as deprecated (superseded by newer analysis).

**Syntax:**

.. code-block:: bash

   asimov review deprecate [OPTIONS] EVENT PRODUCTION

**Example:**

.. code-block:: bash

   asimov review deprecate GW150914_095045 Prod0

Configuration Commands
======================

``asimov configuration``
------------------------

Manage project configuration.

**Syntax:**

.. code-block:: bash

   asimov configuration [OPTIONS] COMMAND

**Subcommands:**

``show``
~~~~~~~~

Display current configuration.

**Syntax:**

.. code-block:: bash

   asimov configuration show [OPTIONS]

**Options:**

``--section TEXT``
   Show only specific section.

**Examples:**

Show all configuration:

.. code-block:: bash

   asimov configuration show

Show specific section:

.. code-block:: bash

   asimov configuration show --section condor

``set``
~~~~~~~

Set a configuration value.

**Syntax:**

.. code-block:: bash

   asimov configuration set [OPTIONS] SECTION KEY VALUE

**Example:**

.. code-block:: bash

   asimov configuration set condor accounting ligo.prod.o4.cbc.pe.bilby

Workflow Examples
=================

Complete Workflow for New Event
--------------------------------

.. code-block:: bash

   # 1. Initialize project
   asimov init "My Analysis Project"
   
   # 2. Apply defaults
   asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe.yaml
   asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe-priors.yaml
   
   # 3. Add event
   asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/events/gwtc-2-1/GW150914_095045.yaml
   
   # 4. Add analyses
   asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/analyses/production-default.yaml -e GW150914_095045
   
   # 5. Build configurations
   asimov manage build
   
   # 6. Submit jobs
   asimov manage submit
   
   # 7. Monitor (one-time check)
   asimov monitor --once
   
   # 8. Or start automatic monitoring
   asimov start

Checking Job Status
-------------------

.. code-block:: bash

   # Quick text status
   asimov report status
   
   # Detailed HTML report
   asimov report html --open
   
   # JSON for scripting
   asimov report status --format json | jq '.events[0]'

Managing Running Jobs
---------------------

.. code-block:: bash

   # Stop a stuck job
   asimov manage stop --production Prod0
   
   # Rebuild and resubmit
   asimov manage build --production Prod0 --force
   asimov manage submit --production Prod0
   
   # Cancel a job completely
   asimov manage cancel --production Prod0

Advanced Usage
==============

Scripting with Asimov
---------------------

Get structured output for scripts:

.. code-block:: bash

   # Get JSON status
   STATUS=$(asimov report status --format json)
   
   # Count running jobs
   echo "$STATUS" | jq '[.events[].productions[] | select(.status=="running")] | length'
   
   # List finished jobs
   echo "$STATUS" | jq -r '.events[].productions[] | select(.status=="finished") | .name'

Environment-Specific Execution
-------------------------------

Use different configurations:

.. code-block:: bash

   # Production
   export ASIMOV_CONFIG=~/.config/asimov/production.conf
   asimov manage submit
   
   # Development
   export ASIMOV_CONFIG=~/.config/asimov/development.conf
   asimov manage submit --dry-run

Batch Operations
----------------

Process multiple events:

.. code-block:: bash

   # Build all
   asimov manage build
   
   # Submit only specific events
   for event in GW150914_095045 GW151012_095443 GW151226_033853; do
       asimov manage submit --event "$event"
   done

See Also
========

- :ref:`getting-started`: Step-by-step tutorial
- :ref:`architecture`: Understanding asimov's architecture
- :ref:`configuration`: Configuration file reference
- :ref:`glossary`: Terminology and concepts
