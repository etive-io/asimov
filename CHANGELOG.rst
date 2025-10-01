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
