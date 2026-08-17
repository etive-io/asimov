0.7.0
=====

This is a major feature release representing a significant evolution of asimov's
architecture and capabilities. It introduces a state-machine monitor loop, a flexible
dependency specification system, a Python API, pydantic-validated priors, first-class
Slurm scheduler support, and a hardened HTML report system. It also completes the
plugin-extraction work begun in 0.6: GraceDB and pipelines no longer ship with core asimov, they now live in their own
optional plugin packages.

This version is intended as a stepping-stone towards the required feature set for the IR1 run of the gravitational-wave detectors, but also as a first step towards making asimov into a more useful general-purpose tool.

New Features
------------

**State Machine Architecture**
  The monitor loop has been completely refactored into a state machine pattern, providing better control flow, plugin support, and pipeline-specific handlers. This enables more sophisticated workflow management and better extensibility.

**Advanced Dependency System**
  Implements a flexible dependency specification system with property-based filtering, AND/OR/negation logic, staleness tracking, and workflow graph integration. This allows complex relationships between analyses to be expressed naturally.

**Strategy Expansion**
  New strategy expansion feature enables creating multiple analyses from parameter matrices, making it easy to run parameter studies and systematic variations.

**Python API**
  Comprehensive Python API for project creation and management, including context manager support for programmatic control of asimov workflows.

**Enhanced HTML Reports**
  HTML reports now include graph-based workflow visualization with interactive modal popups, advanced filtering, and improved styling for better workflow monitoring.

**Blueprint Validator**
  Introduces validation for blueprint files to catch configuration errors early and ensure consistent project setup.

**Modern Prior Handling**
  Refactored prior handling with pydantic validation and pipeline-specific interfaces, providing better type safety and clearer error messages.

**First-class Slurm Scheduler Support**
  Asimov now ships with a full Slurm scheduler backend.  The implementation
  includes bidirectional DAG translation (HTCondor ↔ Slurm), so workflow
  graphs defined for one scheduler can be executed on the other without
  changes to the blueprint.  End-to-end CI coverage for Slurm has been added
  alongside the existing HTCondor suite.

Improvements
------------

**Hardened HTML Report Pages**
  The HTML report system has been substantially improved and hardened.  Subject
  analysis reports now render correctly, graph data generation has been
  refactored for correctness, and the overall report layout has been polished.

**CBCFlow Integration Tests**
  Integration tests for CBCFlow have been added, and ``apply_via_plugin`` has
  been updated to use the current ledger state rather than a stale snapshot.

**Enhanced Scheduler Testing Pipelines**
  Scheduler support and its associated testing pipelines have been further
  extended and hardened following the initial Slurm integration.

**GraceDB Decoupled from Core**
  ``ligo-gracedb``, ``gwpy``, ``lscsoft-glue``, and ``igwn-auth-utils`` are no longer
  dependencies of the core ``asimov`` package; GraceDB support now lives in the optional
  ``asimov-gracedb`` plugin (``pip install asimov-gracedb``). A new ``asimov.hooks.filesource``
  plugin entry-point group allows plugins to provide "fetch a file for an existing subject"
  behaviour. ``Event.get_gracedb()`` remains in core as a deprecated shim which discovers the
  plugin at call time and raises a clear error if it isn't installed; it will be removed from
  core in 0.9. ``asimov event create``'s GraceDB-backed ``--gid``/``--superevent``/``--search``
  flags are replaced by ``asimov apply -p gracedb -e <id>``, using the same
  ``asimov.hooks.applicator`` mechanism the ``cbcflow`` plugin already uses.

**Thread-Safe Logging**
  File logging setup has been refactored to ensure thread safety with shared locks, and logging is now lazy-loaded to prevent log file creation for read-only commands.

**PESummary Modernization**
  PESummary has been converted to a SubjectAnalysis with optional dependency support, enabling more flexible post-processing workflows.

**Improved Testing Infrastructure**
  Added minimal testing pipelines for SimpleAnalysis, SubjectAnalysis, and ProjectAnalysis. Comprehensive GitHub Actions workflows for HTCondor and LALInference end-to-end testing with concurrent execution.

**Build System Migration**
  Migrated from setup.py to pyproject.toml for modern Python packaging standards.

**Plugin Flexibility**
  Enhanced plugin system with additional flexibility for extending asimov's capabilities.

**Scheduler Improvements**
  Scheduler refresh implementation for better job management, which should allow asimov to integrate more easily with a larger family of job schedulling systems in the future. At present htcondor and slurm are fully supported.

**Removed Legacy Assumptions**
  Removed calibration categories and fixed hardcoded git branch assumptions for greater flexibility in deployment environments.

Bug Fixes
---------

**Git Repository Initialisation**
  Fixes an issue with ``git init`` during project creation that could cause
  project setup to fail in some environments.

**Event Application Reliability**
  Several bugs in the event-apply path have been fixed, covering analysis
  application ordering, ledger persistence during apply, and edge cases in
  the event update workflow.

**Ledger I/O Fix**
  A bug in ledger reading and writing that could corrupt state under certain
  conditions has been corrected.

**Production Status Persistence**
  ``asimov production set -s <status>`` reported success but never actually wrote the change
  to ``.asimov/ledger.yml``, silently losing it on the next ledger load.

**Minimum Frequency Canonical Location**
  An earlier 0.7 pre-release briefly documented, and enforced, a requirement that
  ``minimum frequency`` must live in the ``waveform`` section of a blueprint. In practice
  every pipeline that consumes it (``bilby``, ``bayeswave``, ``pesummary``) has always read
  it from ``likelihood``, and the ``waveform`` location was never actually wired up
  anywhere, so that requirement was corrected ahead of this release. ``likelihood`` is the
  documented, enforced canonical location, matching the ``Likelihood`` blueprint schema and
  every pipeline's own validation. The legacy ``quality`` location (its original home, from
  when the value came from data-quality recommendations) is kept as a deprecated fallback:
  values found under ``quality`` are automatically migrated into ``likelihood``, with a
  warning, the same way ``maximum frequency`` has always been handled.

**Documentation Build Fixed**
  ``sphinx-multiversion`` calls Sphinx's ``Config.read(confpath, overrides)``
  positionally, which Sphinx 9 broke by making ``overrides``/``tags`` keyword-only;
  the docs build crashed immediately with a ``TypeError``. ``sphinx<9`` is now pinned
  in the ``docs`` extra until ``sphinx-multiversion`` is patched or replaced.

Breaking Changes
----------------

This release introduces significant architectural changes. While efforts have been made to maintain backward compatibility where possible, some changes in behavior are expected, particularly in:

- Monitor loop behavior due to state machine refactoring
- Dependency specification syntax (old syntax may need updating)
- Prior specification format (now uses pydantic models)

**Bundled Pipelines Removed**
  Support for the ``bilby``, ``rift``, ``bayeswave``, ``lalinference``, and ``pesummary`` pipelines no longer
  ships with core ``asimov``; each now lives exclusively in its own optional plugin package
  (``bilby_pipe``, ``RIFT``, ``asimov-bayeswave``, ``asimov-lalinference``, ``asimov-pesummary``), installed via the
  same ``asimov.pipelines`` entry-point mechanism and the same pipeline names used in
  blueprints, following the pattern already established for GraceDB above. Blueprints that
  reference these pipelines will fail to apply unless the corresponding plugin is installed.

Known Issues
------------

**``bilby`` Pipeline Entry Point Naming**
  Blueprints referencing the ``bilby`` pipeline currently fail to resolve via the
  ``asimov.pipelines`` entry-point mechanism: the installed ``bilby_pipe`` registers its
  own asimov integration under the name ``bilby_native`` rather than ``bilby``. This is a
  naming mismatch in ``bilby_pipe``, not a missing asimov plugin -- unlike bayeswave,
  lalinference, and pesummary, ``bilby_pipe`` has shipped its own ``asimov.pipelines``
  entry point for some time. A ``bilby_pipe`` release dropping the ``bilby_native`` name
  in favour of ``bilby`` is expected soon, at which point this should resolve without any
  change needed in asimov core.

GitHub Pull Requests
--------------------

+ `github#3 <https://github.com/etive-io/asimov/pull/3>`_: Scheduler refresh
+ `github#7 <https://github.com/etive-io/asimov/pull/7>`_: Introduce a blueprint validator
+ `github#14 <https://github.com/etive-io/asimov/pull/14>`_: Update licence to MIT
+ `github#15 <https://github.com/etive-io/asimov/pull/15>`_: CI improvements
+ `github#16 <https://github.com/etive-io/asimov/pull/16>`_: Update licence
+ `github#17 <https://github.com/etive-io/asimov/pull/17>`_: Fix interest dict
+ `github#20 <https://github.com/etive-io/asimov/pull/20>`_: Remove pkg-resources
+ `github#21 <https://github.com/etive-io/asimov/pull/21>`_: Workflow to actions
+ `github#23 <https://github.com/etive-io/asimov/pull/23>`_: Update bilby final
+ `github#27 <https://github.com/etive-io/asimov/pull/27>`_: Bug hunt
+ `github#29 <https://github.com/etive-io/asimov/pull/29>`_: Update the PESummary interface
+ `github#36 <https://github.com/etive-io/asimov/pull/36>`_: Refactor prior handling with pydantic validation and pipeline interfaces
+ `github#38 <https://github.com/etive-io/asimov/pull/38>`_: Add GitHub Actions workflow for building and deploying documentation
+ `github#39 <https://github.com/etive-io/asimov/pull/39>`_: Add Python API for project creation and management
+ `github#40 <https://github.com/etive-io/asimov/pull/40>`_: Add LALInference end-to-end testing to HTCondor workflow with concurrent execution
+ `github#43 <https://github.com/etive-io/asimov/pull/43>`_: Make logging lazy and prevent log file creation for read-only commands
+ `github#48 <https://github.com/etive-io/asimov/pull/48>`_: Add minimal testing pipelines for SimpleAnalysis, SubjectAnalysis, and ProjectAnalysis
+ `github#50 <https://github.com/etive-io/asimov/pull/50>`_: Enhance HTML reports with graph-based workflow visualization, modal popups, and advanced filtering
+ `github#52 <https://github.com/etive-io/asimov/pull/52>`_: Implement flexible dependency specification with property-based filtering, AND/OR logic, staleness tracking, and workflow graph integration
+ `github#55 <https://github.com/etive-io/asimov/pull/55>`_: Add review information display to HTML reports and fix review command
+ `github#56 <https://github.com/etive-io/asimov/pull/56>`_: Fix frames in workflow
+ `github#58 <https://github.com/etive-io/asimov/pull/58>`_: Fix bilby priors
+ `github#60 <https://github.com/etive-io/asimov/pull/60>`_: Convert PESummary to SubjectAnalysis with optional dependency support
+ `github#61 <https://github.com/etive-io/asimov/pull/61>`_: Fix bilby tests
+ `github#63 <https://github.com/etive-io/asimov/pull/63>`_: Remove calibration categories and fix hardcoded git branch assumptions
+ `github#65 <https://github.com/etive-io/asimov/pull/65>`_: Fix dependency resolution, graph visualization, and ledger persistence bugs
+ `github#71 <https://github.com/etive-io/asimov/pull/71>`_: Fix SubjectAnalysis dependency resolution bugs
+ `github#72 <https://github.com/etive-io/asimov/pull/72>`_: Refactor monitor loop to state machine pattern with plugin support, programmatic API, and pipeline-specific handlers
+ `github#75 <https://github.com/etive-io/asimov/pull/75>`_: Add strategy expansion for creating multiple analyses from parameter matrices
+ `github#76 <https://github.com/etive-io/asimov/pull/76>`_: Allow additional plugin flexibility
+ `github#83 <https://github.com/etive-io/asimov/pull/83>`_: Refactor file logging setup to ensure thread safety with a shared lock
+ `github#86 <https://github.com/etive-io/asimov/pull/86>`_: Add first-class Slurm scheduler support with bidirectional DAG translation and end-to-end CI coverage
+ `github#97 <https://github.com/etive-io/asimov/pull/97>`_: Fix issue with git init in project creation
+ `github#103 <https://github.com/etive-io/asimov/pull/103>`_: Fix the application of analyses
+ `github#107 <https://github.com/etive-io/asimov/pull/107>`_: Enforce waveform minimum frequency location (later corrected in #130)
+ `github#112 <https://github.com/etive-io/asimov/pull/112>`_: Fix ledger I/O
+ `github#115 <https://github.com/etive-io/asimov/pull/115>`_: Fix event apply
+ `github#116 <https://github.com/etive-io/asimov/pull/116>`_: Add CBCFlow integration tests and update apply_via_plugin to use current ledger
+ `github#117 <https://github.com/etive-io/asimov/pull/117>`_: Refactor event rendering and improve graph data generation
+ `github#118 <https://github.com/etive-io/asimov/pull/118>`_: Fix event apply (follow-up)
+ `github#121 <https://github.com/etive-io/asimov/pull/121>`_: Enhance scheduler support and testing pipelines
+ `github#122 <https://github.com/etive-io/asimov/pull/122>`_: Fix Slurm tests
+ `github#123 <https://github.com/etive-io/asimov/pull/123>`_: Improve and harden the report page
+ `github#124 <https://github.com/etive-io/asimov/pull/124>`_: Fix subject report
+ `github#128 <https://github.com/etive-io/asimov/pull/128>`_: Decouple GraceDB and unused LVK-only deps from asimov core
+ `github#129 <https://github.com/etive-io/asimov/pull/129>`_: Fix ``asimov production set -s <status>`` not persisting to the ledger
+ `github#130 <https://github.com/etive-io/asimov/pull/130>`_: Fix minimum frequency section: canonical location is likelihood, not waveform
+ `github#131 <https://github.com/etive-io/asimov/pull/131>`_: Remove built-in bayeswave, lalinference, and pesummary pipelines
+ `github#133 <https://github.com/etive-io/asimov/pull/133>`_: Fix CI: pin sphinx<9 for docs build, update cbcflow test fixture for v3 schema

0.6.1
=====

This is a bug-fix release, which does not introduce any new backwards-incompatible features.

Breaking changes
----------------

This release is not believed to introduce any backwards-incompatible changes.

Merges
------

+ `ligo!158 <https://git.ligo.org/asimov/asimov/-/merge_requests/158>`_: Fixes a bug with project analysis working directories.

0.6.0
=====

This is a major feature release which introduces some change in functionality which may have a minor effect on backwards compatibility.

New features
------------

*New analysis types*: asimov 0.6.0 introduces two new kinds of analysis: subject analyses, which allow an analysis to access configurations and results from multiple other analyses defined on a given event or subject, and project analyses which allow access to multiple analyses to be accessed across multiple events. These will allow much more complicated workflows than before which allow combinations of large numbers of subsidiary results.


Changes
-------

*Deprecation warnings*: Deprecation warnings have been added to each of the pipelines (bilby, pesummary, lalinference, rift, and bayeswave) which are currently supported "out of the box" by asimov, as these will be removed in asimov 0.7 and replaced with plugins.

*Bilby*: The online pe argument has been removed from the bilby configuration template as this has been deprecated.

*Removal of gitlab interfaces*: More logic related to the disused and deprecated gitlab issue tracker interface has been removed.

*Removal of calibration envelope logic*: We have removed the logic required to find calibration files on the LIGO Scientific Collaboration computing resources. These have been moved to the asimov-gwdata pipeline, which will be used in O4 collaboration analyses.

Deprecation
-----------

+ All pipeline interfaces in the main package have been deprecated, and will be removed in v0.7.0

Merges and fixes
----------------

+ `ligo!120 <https://git.ligo.org/asimov/asimov/-/merge_requests/120>`_: Fixes the event deletion CLI option.
+ `ligo!66 <https://git.ligo.org/asimov/asimov/-/merge_requests/66>`_: Updates the post-processing interface.
+ `ligo!128 <https://git.ligo.org/asimov/asimov/-/merge_requests/128>`_: Updates to the README
+ `ligo!157 <https://git.ligo.org/asimov/asimov/-/merge_requests/157>`_: Fixes to the interface between asimov and lensingflow

0.5.12
======

This is a bug-fix and backport release for the v0.5 maintenance branch.

Breaking changes
----------------

This release is not believed to introduce any backwards-incompatible changes.

Merges
------

+ `ligo!179 <https://git.ligo.org/asimov/asimov/-/merge_requests/179>`_: Backport ledger updates and post-monitor hooks from the v0.7 development series.
+ Update HTCondor test configuration.
+ Update GWOSC YAML configuration for gravitational wave event analysis.

0.5.11
======

This is a bug-fix release for the v0.5 maintenance branch.

Breaking changes
----------------

This release is not believed to introduce any backwards-incompatible changes.

Merges
------

+ `ligo!172 <https://git.ligo.org/asimov/asimov/-/merge_requests/172>`_: PESummary fixes correcting configuration errors in post-processing.
+ Backport bilby configuration changes from more recent releases.
+ Fix the ``asimov review`` CLI.
+ Add security testing to the CI build.

0.5.10
======

This is a bug-fix release, which does not introduce any new backwards-incompatible features, which fixes a critical bug when updating an event using the ``asimov apply --upgrade`` interface, where analyses were lost from the updated event.

Breaking changes
----------------

This release is not believed to introduce any backwards-incompatible changes.

Merges
------

+ `ligo!166 <https://git.ligo.org/asimov/asimov/-/merge_requests/166>`_: Corrects an issue with application of event updates.

0.5.9
=====

This is primarily a bug-fix release, which does not introduce any new backwards-incompatible features, but provides a number of small quality-of-life improvements.
These include a means of better handling updates to analyses by applying updates event-wide to the asimov ledger.

Breaking changes
----------------

This release is not believed to introduce any backwards-incompatible changes.

Merges
------

+ `ligo!147 <https://git.ligo.org/asimov/asimov/-/merge_requests/147>`_: Corrects an issue with luminosity distance priors for bilby.
+ `ligo!156 <https://git.ligo.org/asimov/asimov/-/merge_requests/156>`_: Adds units to disk and memory requests for bayewave condor jobs.
+ `ligo!160 <https://git.ligo.org/asimov/asimov/-/merge_requests/160>`_: Improves memory efficiency of the ``asimov monitor`` command.
+ `ligo!162 <https://git.ligo.org/asimov/asimov/-/merge_requests/162>`_: Restores tha ability of asimov to retrieve coinc.xml files from graceDB.
+ `ligo!163 <https://git.ligo.org/asimov/asimov/-/merge_requests/163>`_: Allows blueprints to update existing events.
+ `ligo!164 <https://git.ligo.org/asimov/asimov/-/merge_requests/164>`_: Transitions from setup.py to pyproject.toml for specifying build and install processes.



0.5.8
=====

This is a bug-fix release, which does not introduce any new backwards-incompatible features, but provides a number of small quality-of-life improvements.
These include bug-fixes to various aspects of the CLI, and improvements to make using the CLI easier.
This release also allows keyword arguments to be specified more easily to PESummary, and allows the environment of bilby and bayeswave executables to be specified on a per-analysis basis.

We have ceased testing 0.5.8 against python 3.6 and python 3.7, and will drop support for these entirely after the next release.

Breaking changes
----------------

This release is not believed to introduce any backwards-incompatible changes.

Merges
------

+ `ligo!140 <https://git.ligo.org/asimov/asimov/-/merge_requests/140>`_: Change CLI outputs to list events in alphanumeric order.
+ `ligo!145 <https://git.ligo.org/asimov/asimov/-/merge_requests/145>`_: Adds an error message if an unavailable pipeline is requested by an analysis.
+ `ligo!149 <https://git.ligo.org/asimov/asimov/-/merge_requests/149>`_: Fixes errors with various parts of the analysis review CLI, and improves error and information messages.
+ `ligo!151 <https://git.ligo.org/asimov/asimov/-/merge_requests/151>`_: Adds a confirmation message when a plugin is used to apply a new event to a project.
+ `ligo!152 <https://git.ligo.org/asimov/asimov/-/merge_requests/152>`_: Allows keyword arguments to be specified for summarypages jobs via a blueprint.
+ `ligo!153 <https://git.ligo.org/asimov/asimov/-/merge_requests/153>`_: Allows the analysis executable to be explicitly set from a blueprint for bilby and bayeswave.

0.5.7
=====

This is a bug-fix release, and doesn't introduce any new features.

Breaking changes
----------------

This release is not believed to introduce any backwards-incompatible changes.

Merges
------

+ `ligo!133 <https://git.ligo.org/asimov/asimov/-/merge_requests/133>`_: Fix a bug with template discovery for pipeline plugins.
+ `ligo!144 <https://git.ligo.org/asimov/asimov/-/merge_requests/144>`_: Allow the PSD roll-off factor to be specified rather than hardcoded.


0.5.6
=====

This is a bug-fix release, and doesn't introduce any new features.

Breaking changes
----------------

This release is not believed to introduce any backwards-incompatible changes.

Merges
------

+ `ligo!124 <https://git.ligo.org/asimov/asimov/-/merge_requests/124>`_: Fixes a bug in the disk request for bayeswave_post in bayeswave_pipe.

0.5.5
=====

This is a bug-fix release, and doesn't introduce any new features.

Breaking changes
----------------

This release is not believed to introduce any backwards-incompatible changes.

Merges
------

+ `ligo!115 <https://git.ligo.org/asimov/asimov/-/merge_requests/121>`_: Fixes a bug with bilby_pipe configurations when frame files are passed
+ `ligo!116 <https://git.ligo.org/asimov/asimov/-/merge_requests/116>`_: Allows configuration of a handful of bilby parameters and updates defaults to align with current bilby_pipe releases.
+ `ligo!121 <https://git.ligo.org/asimov/asimov/-/merge_requests/121>`_: Fixes a bug with bilby_pipe when frame files as specified in a frame_dict.
+ `ligo!122 <https://git.ligo.org/asimov/asimov/-/merge_requests/122>`_: Adds a bayeswave_post disk request to the bayeswave config template.
+ `ligo!123 <https://git.ligo.org/asimov/asimov/-/merge_requests/123>`_: Fixes a bug related to filepaths and frame type specifications when bilby is using OSDF data retrieval.


0.5.4
=====

This is a bug-fix release, and doesn't introduce any new features.

Breaking changes
----------------

This release is not believed to introduce any backwards-incompatible changes.

Merges
------

+ `ligo!107 <https://git.ligo.org/asimov/asimov/-/merge_requests/107>`_: Allows additional files to be specified for condor transfers of bilby jobs.
+ `ligo!109 <https://git.ligo.org/asimov/asimov/-/merge_requests/109>`_: Allows total mass priors to be specified in bilby jobs.
+ `ligo!111 <https://git.ligo.org/asimov/asimov/-/merge_requests/111>`_: Fixes a bug with bilby frame retrieval when no frame files are specified.
+ `ligo!112 <https://git.ligo.org/asimov/asimov/-/merge_requests/112>`_: Passes required environment variables to PESummary.
+ `ligo!113 <https://git.ligo.org/asimov/asimov/-/merge_requests/113>`_: Fixes a bug with asset retrieval in analyses with multiple requirements.
+ `ligo!115 <https://git.ligo.org/asimov/asimov/-/merge_requests/115>`_: Increases the default disk request for Bayeswave jobs.


0.5.3
=====

This is a bug-fix release, and doesn't introduce any new features.

Breaking changes
----------------

This release is not believed to introduce any backwards-incompatible changes.

Merges
------

+ `ligo!105 <https://git.ligo.org/asimov/asimov/-/merge_requests/105>`_: Fixes an issue with accounting tags for the ``asimov start`` command.
+ `ligo!104 <https://git.ligo.org/asimov/asimov/-/merge_requests/104>`_: Restores ability to calculate the precessing SNR in a PESummary post-processing pipeline.

0.5.2
=====

This is a bug-fix release, and doesn't introduce any new features.

Breaking changes
----------------

This release is not believed to introduce any backwards-incompatible changes.

Merges & changes
----------------

+ `ligo!94 <https://git.ligo.org/asimov/asimov/-/merge_requests/94>`_: Enables pipeline jobs to run without calibration information
+ `ligo!102 <https://git.ligo.org/asimov/asimov/-/merge_requests/102>`_: Fixes to the distribution infrastructure for asimov for pypi and conda forge
+ *Accounting information* - Support was restored for clusters which do not require accounting information by making accounting data optional
+ *Preferred event data* - Preferred event data is now stored correctly as ``ligo>preferred event`` in the ledger when new event data is downloaded from GraceDB.
+ *Frame files* (bayeswave) - Fixes are implemented in the Bayeswave interface to pass cache files rather than frame files to the pipeline, and ensure that these are associated to the correct interferometer. The Bayeswave interface was updated to explicitly skip the datafind step if cache files are provided.
+ *Frame files* (bilby) - A fix was added to ensure that the `data-dict` dictionary has the correct key:value format in the config file.
+ *PSD compatibility testing* - A bug was fixed whereby PSDs would fail to pass compatibility criteria because of flawed tests; these tests have been respecified to avoid the bug.

0.5.1
=====

This is a bug-fix release, and doesn't introduce any new features.

Breaking changes
----------------

This release is not believed to introduce any backwards-incompatible changes.

Merges
------

+ `ligo!98 <https://git.ligo.org/asimov/asimov/-/merge_requests/98>`_: Fixes to handling of preferred event data from LIGO GraceDB
+ `ligo!93 <https://git.ligo.org/asimov/asimov/-/merge_requests/93>`_: Fixes to allow code to run in environments where accounting tags are not required
+ `ligo!94 <https://git.ligo.org/asimov/asimov/-/merge_requests/94>`_: Fixes errors when calibration files are not available
+ `ligo!92 <https://git.ligo.org/asimov/asimov/-/merge_requests/92>`_: Fixes an issue with adding PSD files to some analyses
+ `ligo!90 <https://git.ligo.org/asimov/asimov/-/merge_requests/90>`_: Fixes an issue with bayeswave when data files are provided

0.5.0
=====

This is a minor feature release designed to implement new functionality required for running LIGO's O4a parameter estimation workflows.

Breaking changes
-----------------

This release is not believed to introduce any backwards-incompatible changes.

Merges
------

+ `ligo!51 <https://git.ligo.org/asimov/asimov/-/merge_requests/51>`_: Updates to the RIFT ini file
+ `ligo!71 <https://git.ligo.org/asimov/asimov/-/merge_requests/71>`_: Introduces monitor and application hooks
+ `ligo!72 <https://git.ligo.org/asimov/asimov/-/merge_requests/72>`_: Changes to the handling of state vectors
+ `ligo!73 <https://git.ligo.org/asimov/asimov/-/merge_requests/73>`_: Changes to allow bilby to use new likelihood models
+ `ligo!74 <https://git.ligo.org/asimov/asimov/-/merge_requests/74>`_: Changes to the handling of priors in bilby, removal of prior files
+ `ligo!76 <https://git.ligo.org/asimov/asimov/-/merge_requests/76>`_: Improvements to ledger file handling
+ `ligo!77 <https://git.ligo.org/asimov/asimov/-/merge_requests/77>`_: Fixes a bug with profiling data collection
+ `ligo!78 <https://git.ligo.org/asimov/asimov/-/merge_requests/78>`_: Allow ROQ use in bilby
+ `ligo!79 <https://git.ligo.org/asimov/asimov/-/merge_requests/79>`_: Fix a bug where accounting information is omitted from asimov-generated condor jobs
+ `ligo!86 <https://git.ligo.org/asimov/asimov/-/merge_requests/86>`_: Updates various bilby defaults
  
Major New Features
------------------

Hooks
"""""

Introduced in `ligo!71 <https://git.ligo.org/asimov/asimov/-/merge_requests/71>`_, asimov now allows plugins to interact with the monitor loop, and gain access to the ledger once the monitoring process has completed.
It also allows external packages to provide new data via the `asimov apply` interface.

ROQ bases in bilby
""""""""""""""""""

This version introduces support for ROQ bases in bilby.

Review status
-------------

The newly reviewed features in asimov 0.5.0 are: 

+ Monitor and apply hooks for `CBCflow <https://pypi.org/project/cbcflow/>`_
+ Integration of `peconfigurator <https://pypi.org/project/pe-configurator/>`_ via entry points
+ Integration of `asimov-gwdata <https://pypi.org/project/asimov-gwdata/>`_ via entry points
+ Reduced order quadrature support with `bilby <https://lscsoft.docs.ligo.org/bilby/index.html>`_ with the  `dynesty sampler <https://dynesty.readthedocs.io>`_

The newly reviewed capabilities in asimov 0.5.0 are: 

+ Operability on the `Open Science Grid <https://osg-htc.org/>`_ (OSG)
+ Support for shared user accounts

Additional reviewed updates:

+ Revised ``BayesWave`` defaults associated with v1.1.0 
+ Revised ``bilby_pipe`` defaults associated with v1.0.8 and also compatible with v1.1.0.
+ Compatibility with ``pesummary`` v1.0.0


Getting ``asimov v0.5.0``
-------------------------

pypi
""""
You can install this preview directly from pypi using pip:
``pip install --upgrade asimov==v0.5.0``

git
"""
You can clone this repository and install from source by running

::

   git clone git@git.ligo.org:asimov/asimov.git
   git checkout v0.5.0
   pip install .

What's next?
------------

You can find the most up to date O4 development roadmap `on the project wiki<https://git.ligo.org/asimov/asimov/-/wikis/o4-roadmap>`.


0.4.1
=====

This is a bug-fix release.

Breaking changes
----------------

This release is not believed to introduce any backwards-incompatible changes.

Bugs Fixed
----------

+ `ligo#125 <https://git.ligo.org/asimov/asimov/-/issues/125>`_

0.4.0
=====

Breaking changes
----------------

This release of asimov is not backwards compatible with releases from the v0.3 series, and has multiple breaking changes.

Major New Features
-------------------

Projects
""""""""

This version of asimov represents a major update compared to the previously released versions of asimov.
In the past asimov has relied on gitlab issue trackers in order to organise a project.
In this version we introduce infrastructure within asimov to enable management of much smaller projects as well as those asimov was initially intended for.
Projects can now be created in a user's home directory and used to organise and automate multiple runs.

Pipeline interface improvements
"""""""""""""""""""""""""""""""

We've made a serious effort in this version to improve the interface between asimov and various gravitational wave analysis pipelines, including Bayeswave, bilby, and lalinference.
We've made it much easier to use other pipelines with asimov too, which can now be implemented as plugins without requiring upstream changes to the asimov codebase.

Reporting improvements
""""""""""""""""""""""

We've introduced a number of new features to the report pages which are created by asimov in order to give a more useful overview of all of the analyses which are being run.

Command-line interface
""""""""""""""""""""""

Asimov now has a cleaner, and more consistent command line interface, which has been renamed ``asimov``.
When we started work on the project we weren't sure how asimov would be used, but we've come to the conclusion that having everything named consistently is for the best.

Blueprint files
"""""""""""""""

Setting up events and analyses in asimov requires a large amount of information.
To assist with this, asimov is now able to read-in this information in yaml-format files which we call "blueprints".
A curated collection of these for the events included in the GWTC catalogues, and the analyses used for those catalogues are available from https://git.ligo.org/asimov/data.


Review status
-------------

This release has been reviewed for use in parameter estimation analyses of the LVK.
+ Review statements can be found in the ``REVIEW.rst`` file in this repository.
+ Full information regarding the review is available `in this wiki page<https://git.ligo.org/pe/O4/asimov-review/-/wikis/Asimov-version-O4>`_.

Getting ``asimov v0.4.0``
-------------------------

pypi
""""
You can install this preview directly from pypi using pip:
``pip install --upgrade asimov==v0.4.0``

git
"""
You can clone this repository and install from source by running

::

   git clone git@git.ligo.org:asimov/asimov.git
   git checkout v0.4.0
   pip install .

What's next?
------------

You can find the most up to date O4 development roadmap `on the project wiki<https://git.ligo.org/asimov/asimov/-/wikis/o4-roadmap>`.

0.3.4
=====

This is a maintenance release with packaging, documentation, and CI updates. It corrects the package name on PyPI and updates the documentation build configuration and CI pipelines.

Breaking changes
----------------

This release is not believed to introduce any backwards-incompatible changes.

0.3.3
=====

This is a minor update release.

Changes
-------

*LALInference templating*: Updates the handling of LALInference pipelines to allow analysis configuration to be expressed using Liquid templates, providing greater flexibility in how pipeline configurations are generated.

Bug Fixes
---------

*Review information*: Corrects a bug in the handling of review information stored in the ledger.

0.3.2
=====

This is a minor bug-fix release.

Breaking changes
----------------

This release is not believed to introduce any backwards-incompatible changes.

Bug Fixes
---------

*PESummary spin evolution*: Corrects a bug in the PESummary post-processing call which prevented spin evolution from being correctly calculated.

0.3.1
=====

This is a minor bug-fix release.

Breaking changes
----------------

This release is not believed to introduce any backwards-incompatible changes.

Bug Fixes
---------

*PESummary*: Adds redshift regeneration to the PESummary call at production completion.

*Bayeswave*: Removes writing of user information to Bayeswave productions in the ledger.

0.3.0
=====

This is the first fully reviewed version of asimov, representing the state of the codebase at the O3a_final review.

Reviewed support for bilby, RIFT, and Bayeswave job creation, as well as operability on LIGO Data Grid (LDG) computing resources. This version was prepared for the O3a and O3b parameter estimation projects.

Breaking changes
----------------

This release is not believed to introduce any backwards-incompatible changes relative to the 0.2 series.

0.2.2
=====

Review version for the O3a final analyses. This release was used as the basis for the O3a final parameter estimation analyses and underwent internal LVK review for that purpose.

Breaking changes
----------------

This release is not believed to introduce any backwards-incompatible changes.

Bug Fixes
---------

*PSD suppression*: Corrects bugs in the PSD suppression code.

*Connectivity*: Removes the requirement to connect to GitLab when no connection is necessary (e.g. for local read-only operations).

*Requirements*: Cleans up package requirements specifications.

0.2.1
=====

This is a bug-fix release.

Breaking changes
----------------

This release is not believed to introduce any backwards-incompatible changes.

Bug Fixes
---------

+ Various bug fixes and stability improvements, including a correction to DAG construction and updates to bring the codebase in line with O3b operational requirements.

0.2.0
=====

This is a major release intended as a fully functional version for O3b parameter estimation analyses.

Asimov 0.2 represents a significant step towards production-ready workflow automation for LIGO parameter estimation, building on the O3a experience to provide a more robust and capable system.

Breaking changes
----------------

This release introduces changes that may not be fully backwards compatible with the 0.1 series.

0.1
===

This is the O3a reviewed version of asimov — the initial reviewed release, prepared for use in O3a parameter estimation analyses on the LIGO Data Grid.

0.0.1
=====

Initial release of asimov.
