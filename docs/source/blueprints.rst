=================
Asimov Blueprints
=================


This document contains an overview of asimov blueprints, which are the files used to configure analyses, analysis subjects (including events), pipeline defaults, and project defaults.

Adding a blueprint to an asimov project
=======================================

Asimov parses the contents of a blueprint file using the ``asimov apply`` command. This will cause asimov to read the contents of the blueprint, and add it to its internal database.

For example, if we have a blueprint file called ``GW150914_095045.yaml`` we can add it to the project by running::

    asimov apply -f GW150914_095045.yaml

Kinds of blueprint
==================

Asimov supports a number of different kinds of blueprint, which are designed to affect the project in different ways.
The blueprint's kind must be specified using the ``kind`` keyword.

.. list-table::
   :header-rows: 1

   * - Kind
     - Description
   * - ``event``
     - These blueprint files define an event (for example, a gravitational wave event).
   * - ``analysis``
     - These blueprint files define an analysis which should be performed on an event or a subject.
   * - ``configuration``
     - These blueprint files define settings which can be applied globally across the project, including pipeline defaults.
   * - ``subject``
     - These blueprint files define an analysis subject (for example a gravitational wave event).

For example, to make a (very minimal) event blueprint: ::

  kind: event
  name: GW150914_095045


Multiple blueprints in one file
===============================

You can include multiple blueprints in the same file so that they can be added to a project at the same time. This can be especially useful if you always want to add the same set of analyses to each subject, for example, in order to create a similar workflow quickly across many analysis subjects.

Individual blueprints should be separated by three hyphens ``---`` in a row on their own line.

For example::

    kind: analysis
    name: generate-psds
    pipeline: bayeswave
    ---
    kind: analysis
    name: parameter-estimation
    pipeline: bilby
    needs:
      - generate-psds

Settings precedence
===================

In order to make producing consistent results as straight-forward as possible, asimov allows settings to be applied hierarchically, so that they can apply across an entire project, an entire analysis subject, or only a specific analysis.

The order of precedence is as follows (with ``analysis`` settings being given highest priority and global settings the lowest):

1. Settings defined in an ``analysis``
2. Settings defined in an ``event`` or a ``subject``
3. Settings defined in the ``pipelines`` heading
4. Settings defined globally.

For example, consider a project using the following blueprints::

    kind: configuration
    likelihood:
      sample rate: 1024
      psd length: 8
      post trigger time: 2
      marginalisation:
        distance: True
    ---
    kind: configuration
    pipelines:
      bilby:
        likelihood:
          marginalisation:
            distance: False
    ---
    kind: event
    likelihood:
      psd length: 4
    ---
    kind: analysis
    likelihood:
      sample rate: 4096

The analysis which would be created by these blueprints would have the following likelihood settings::

    likelihood:
      sample rate: 4096    # From the analysis setting, overwriting the global value
      psd length: 4        # From the event setting, overwriting the global value
      marginalisation:
        distance: False    # From the pipeline configuration, overwriting the global value
      post trigger time: 2 # From the global value

Blueprint YAML Syntax
=====================

Reading the documentation
-------------------------

Asimov blueprint files utilise the hierarchical structure of YAML files to divide settings into logical groupings. In this documentation we collapse the hierarchical structure using colons in settings names. For example, ``likelihood:marginalisation:distance: True`` corresponds to the structure::

    likelihood:
      marginalisation:
        distance: True

General settings
----------------

These settings can be applied generally to any kind of blueprint.

.. list-table::
   :header-rows: 1

   * - Setting
     - Values
     - Description
   * - ``comment``
     - string
     - A comment which can be used to describe the object created by the blueprint.
   * - ``name``
     - string
     - A name for the object created by the blueprint. Typically required for event, subject, and analysis blueprints.

Required settings
-----------------

``kind``
  All blueprints need a ``kind`` setting so that asimov can determine what part of the analysis workflow the blueprint is intended to configure.

``name``
  Required for ``event``, ``subject``, and ``analysis`` blueprints. This is the name by which this part of the analysis is known in asimov, so that it can be referred to in other blueprints.

For example, you might name an event with ``name: GW150914_095045``, and an analysis with ``name: generate-psds``.

``pipeline``

Only required for ``analysis`` blueprints, this should specify the name of the pipeline which this analysis needs to run.

``event`` or ``subject``

Only required for ``analysis`` blueprints. This should be the name of either the ``event`` or the ``subject`` which this analysis is to be run on.

However, this option can be omitted by instead applying the blueprint to the project with the additional ``--event`` argument, for example ``asimov apply --file bilby.yaml --event GW150914``.

Defining analysis requirements
------------------------------

Asimov will determine the required computation order of analyses in a project automatically, but in order to do this it needs to be given details of which analyses require the results of a previous analysis. It will then compute a directed acyclic graph (DAG) of all the analyses.

Requirements can be specified in the ``needs`` setting of an analysis. For example, in order to define a job which uses the ``bilby`` pipeline, but requires results from an analysis using the ``bayeswave`` pipeline you should specify the name of the ``bayeswave`` analysis in the ``needs`` section of the ``bilby`` analysis. For example::

    kind: analysis
    name: generate-psds
    pipeline: bayeswave
    ---
    kind: analysis
    name: parameter-estimation
    pipeline: bilby
    needs:
      - generate-psds

In asimov 0.5 you need to explicitly specify the ``name`` of analyses which provide job dependencies, but in future versions this will be made more flexible so that results can be automatically gathered based, for example, on the pipeline which generated them.

Top-level event and subject settings
=====================================

These settings can be specified at the event or subject level and will be inherited by all analyses defined for that subject.

.. list-table::
   :header-rows: 1

   * - Setting
     - Values
     - Description
   * - ``interferometers``
     - list of strings, e.g. ``[H1, L1, V1]``
     - The list of gravitational wave detector abbreviations which should be included in the analysis.
       Each entry should be a standard LIGO/Virgo/KAGRA detector identifier such as ``H1`` (LIGO Hanford),
       ``L1`` (LIGO Livingston), or ``V1`` (Virgo).
   * - ``event time``
     - ``float``
     - The GPS time of the gravitational wave event trigger.
   * - ``repository``
     - string (path or URL)
     - The location of the git repository for this event.
       Can be a local file path or a remote URL (``git@`` or ``https://``).
   * - ``working directory``
     - string (path)
     - The directory in which working files for this subject should be stored.
       Defaults to a subdirectory within the project run directory.
   * - ``webdir``
     - string (path)
     - The web directory for this event.
       Results pages will be placed here.
   * - ``cosmology``
     - string, e.g. ``Planck15``
     - The cosmological model to use when computing derived quantities.
       Defaults to ``Planck15``.
   * - ``psds``
     - dict (IFO → path)
     - A dictionary mapping detector abbreviations to the path of their pre-computed power spectral density (PSD) files.
       If not provided, PSDs will be obtained from a preceding BayesWave analysis specified in ``needs``.
   * - ``xml psds``
     - dict (IFO → path)
     - A dictionary mapping detector abbreviations to pre-computed PSD files in XML format.
       Required by some pipelines (e.g. RIFT).

Data
====

Settings in the ``data`` section describe the observational data which should be used in the analysis.

Data settings should be specified under the ``data`` heading in the blueprint, for example::

    data:
      segment length: 4
      channels:
        H1: H1:DCS-CALIB_STRAIN_C02
        L1: L1:DCS-CALIB_STRAIN_C02

.. list-table::
   :header-rows: 1

   * - Setting
     - Values
     - Description
   * - ``data:segment length``
     - ``float``
     - The length in seconds of the data segment to analyse.
   * - ``data:channels``
     - dict (IFO → channel name)
     - A dictionary mapping each detector abbreviation to the data channel which should be used.
       For example ``H1: H1:DCS-CALIB_STRAIN_C02``.
   * - ``data:frame types``
     - dict (IFO → frame type)
     - A dictionary mapping each detector abbreviation to the frame type for the data.
       For example ``H1: H1_HOFT_C02``.
   * - ``data:data files``
     - dict (IFO → path)
     - A dictionary mapping detector abbreviations to local data file paths.
       If not provided, data will be located using the datafind service.
   * - ``data:format``
     - string, e.g. ``gwf``
     - The file format of the gravitational wave data files.
       Defaults to ``gwf``.
   * - ``data:datafind url``
     - string (URL)
     - The URL of the datafind service to use when locating data.
       Defaults to ``https://datafind.igwn.org``.
   * - ``data:datafind url type``
     - string, e.g. ``osdf``
     - The URL type used by the datafind service.
       Defaults to ``osdf``.
   * - ``data:cache files``
     - dict (IFO → path)
     - A dictionary mapping detector abbreviations to pre-generated frame cache files.
       Used by some pipelines (e.g. BayesWave) instead of the datafind service.
   * - ``data:calibration``
     - dict (IFO → path)
     - A dictionary mapping detector abbreviations to the path of their calibration envelope files.
       Paths can be relative to the event repository or absolute.
   * - ``data:calibration:correction type``
     - string
     - The type of calibration correction to apply.
       Passed directly to the pipeline.

Quality
=======

Settings in the ``quality`` section describe the data quality parameters used to select data and configure the frequency range of the analysis.

Quality settings should be specified under the ``quality`` heading, for example::

    quality:
      minimum frequency:
        H1: 20
        L1: 20

.. list-table::
   :header-rows: 1

   * - Setting
     - Values
     - Description
   * - ``quality:minimum frequency``
     - dict (IFO → float)
     - A dictionary mapping each detector abbreviation to the minimum frequency (in Hz) at which the
       likelihood inner product is evaluated.
       This is sometimes called the "flow" or "f_low".
   * - ``quality:maximum frequency``
     - dict (IFO → float)
     - A dictionary mapping each detector abbreviation to the maximum frequency (in Hz) for the analysis.
       If not provided this is computed automatically as ``0.875 × sample_rate / 2``.
   * - ``quality:lowest minimum frequency``
     - ``float``
     - The lowest of the per-detector minimum frequencies.
       Used by BayesWave as the single ``flow`` parameter.
       If not provided it is computed automatically from ``quality:minimum frequency``.
   * - ``quality:state vector``
     - dict (IFO → state vector channel name)
     - A dictionary mapping detector abbreviations to the state-vector channel used for data quality checks.
       For example ``H1: H1:DCS-CALIB_STATE_VECTOR_C01``.

Waveform
========

The settings in this section of the blueprint affect the waveform model, and the generation of waveforms then used in the likelihood function.

For historical reasons some of these settings are contained under the ``likelihood`` heading, and are identified as such here. In future versions of asimov this syntax will be further rationalised.

General waveform settings
-------------------------

.. list-table::
   :header-rows: 1

   * - Setting
     - Values
     - Description
   * - ``waveform:approximant``
     - string
     - The name of the waveform approximant to be used, for example ``IMRPhenomXPHM`` or ``SEOBNRv4PHM``.
   * - ``waveform:reference frequency``
     - ``float``
     - The reference frequency (in Hz) at which spin magnitudes and orientations are defined.
   * - ``waveform:generator``
     - See individual pipeline documentation.
     - The waveform generator class to use.
       For bilby the default is ``bilby.gw.waveform_generator.LALCBCWaveformGenerator``.
   * - ``waveform:conversion function``
     - See individual pipeline documentation.
     - A function which can be used to perform parameter conversions for the waveform.
   * - ``waveform:generation function``
     - See individual pipeline documentation.
     - A function which can be used to generate the waveform.
   * - ``waveform:enforce signal duration``
     - ``True``, ``False``
     - If set to ``True``, enforces that the waveform duration matches the data segment length.
       Defaults to ``False``.
   * - ``waveform:pn spin order``
     - ``int``
     - The post-Newtonian order for spin terms in the waveform.
       Defaults to ``-1`` (maximum available order).
   * - ``waveform:pn tidal order``
     - ``int``
     - The post-Newtonian order for tidal terms in the waveform.
       Defaults to ``-1`` (maximum available order).
   * - ``waveform:pn phase order``
     - ``int``
     - The post-Newtonian order for the phase expansion.
       Defaults to ``-1`` (maximum available order).
   * - ``waveform:pn amplitude order``
     - ``int``
     - The post-Newtonian order for the amplitude expansion.
       Defaults to ``0``.
   * - ``waveform:file``
     - string (path)
     - The path to a numerical relativity waveform file.
       Defaults to ``None``.
   * - ``waveform:arguments``
     - dict
     - Additional keyword arguments to pass to the waveform generator.
       Should be provided as a dictionary.
       Defaults to ``None``.
   * - ``waveform:mode array``
     - list
     - A list of ``(l, m)`` mode pairs to include in the waveform.
       Defaults to ``None`` (all modes included by the approximant).
   * - ``waveform:maximum mode``
     - ``int``
     - The maximum mode order (ℓ_max) to include from the waveform model.
       Used by RIFT. Defaults to ``2``.
   * - ``likelihood:start frequency``
     - ``float``
     - The frequency (in Hz) at which waveform generation starts.
       Note: this is **not** the same as ``quality:minimum frequency``,
       which is the lowest frequency at which the inner product is evaluated.

Likelihood
==========

These settings affect the construction of the likelihood function in inference codes.

Likelihood settings should be included in the blueprint under the ``likelihood`` heading, for example::

    likelihood:
      sample rate: 1024

General likelihood settings
---------------------------

.. list-table::
   :header-rows: 1

   * - Setting
     - Values
     - Description
   * - ``likelihood:coherence test``
     - ``True``, ``False``
     - If set to true this indicates that a coherence test should be performed where a pipeline supports it.
   * - ``likelihood:post trigger time``
     - ``float``
     - The amount of time in seconds which should be analysed after the trigger time.
       Defaults to ``2.0``.
   * - ``likelihood:sample rate``
     - ``float``
     - The sample rate (in Hz) which should be used to compute the likelihood.
   * - ``likelihood:psd length``
     - ``float``
     - The length in seconds of the data used to produce the power spectral density estimate.
   * - ``likelihood:roll off time``
     - ``float``
     - The Tukey window roll-off time in seconds for data windowing.
       Defaults to ``0.4``.
   * - ``likelihood:time reference``
     - string
     - The reference point for timing, for example ``geocent``.
       Defaults to ``geocent``.
   * - ``likelihood:reference frame``
     - string
     - The reference frame for the sky localisation, for example ``sky``.
       Defaults to ``sky``.
   * - ``likelihood:type``
     - See individual pipeline documentation.
     - The likelihood function class to use.
       For bilby the default is ``GravitationalWaveTransient``;
       for ROQ analyses use ``ROQGravitationalWaveTransient``.
   * - ``likelihood:kwargs``
     - dict
     - Additional keyword arguments to pass to the likelihood function, as a YAML or JSON dictionary.
       Defaults to ``None``.
   * - ``likelihood:frequency domain source model``
     - See individual pipeline documentation.
     - The frequency-domain source model function to use.
       For example ``lal_binary_black_hole`` or ``lal_binary_neutron_star``.
       Defaults to ``lal_binary_black_hole``.
   * - ``likelihood:time domain source model``
     - See individual pipeline documentation.
     - The time-domain source model function to use.
   * - ``likelihood:segment start``
     - ``float``
     - The GPS start time of the data segment.
       If not provided it is computed from ``event time`` and ``data:segment length``.
   * - ``likelihood:window length``
     - ``float``
     - The length in seconds of the analysis window used by BayesWave.
       Defaults to ``data:segment length``.
   * - ``likelihood:reweighting_configuration``
     - string or dict
     - Configuration for nested-sample reweighting.
       Defaults to ``None``.
   * - ``likelihood:reweight_nested_samples``
     - ``True``, ``False``
     - If set to ``True``, reweights nested samples after sampling.
       Defaults to ``False``.

BayesWave-specific likelihood settings
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

These settings are specific to the BayesWave pipeline and are nested under the ``likelihood`` heading.

.. list-table::
   :header-rows: 1

   * - Setting
     - Values
     - Description
   * - ``likelihood:iterations``
     - ``int``
     - The number of MCMC iterations for BayesWave.
       Defaults to ``100000``.
   * - ``likelihood:chains``
     - ``int``
     - The number of parallel MCMC chains for BayesWave.
       Defaults to ``8``.
   * - ``likelihood:threads``
     - ``int``
     - The number of threads per chain for BayesWave.
       Defaults to ``4``.

RIFT-specific likelihood settings
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

These settings are specific to the RIFT pipeline and are nested under the ``likelihood`` heading.

``likelihood:assume``
"""""""""""""""""""""

Arguments in this section force the behaviour of the analysis by making assumptions about the physical system.
Each assumption should be provided as an item in the ``assume`` list, for example::

    likelihood:
      assume:
        - no spin
        - matter

.. list-table::
   :header-rows: 1

   * - Value
     - Description
   * - ``no spin``
     - Forces the analysis to ignore spin; both components are assumed non-spinning.
   * - ``precessing``
     - Forces the analysis to assume that spins may be misaligned (precessing).
   * - ``nonprecessing``
     - Forces the analysis to assume that spins are aligned (non-precessing).
   * - ``matter``
     - Forces the analysis to assume that both components may have matter effects (e.g. binary neutron star).
   * - ``matter secondary``
     - Forces the analysis to assume that only the secondary component has matter effects (e.g. NSBH).
   * - ``eccentric``
     - Forces the analysis to assume an eccentric orbit.
   * - ``lowlatency tradeoffs``
     - Enables low-latency trade-offs to speed up the analysis.
   * - ``high q``
     - Enables settings optimised for high mass-ratio systems.
   * - ``well-placed``
     - Assumes the signal is well-placed in parameter space for faster convergence.

Calibration settings
--------------------

These settings affect the handling of calibration uncertainties within the likelihood function.

.. list-table::
   :header-rows: 1

   * - Setting
     - Values
     - Description
   * - ``likelihood:calibration:sample``
     - ``True``, ``False``
     - If set to ``True`` then the likelihood will sample over the calibration uncertainty using spline envelope files.
       Defaults to ``True`` when calibration envelopes are provided.

Marginalisation settings
------------------------

These settings allow various marginalisations to be turned on or off within the likelihood function.

.. list-table::
   :header-rows: 1

   * - Setting
     - Values
     - Description
   * - ``likelihood:marginalisation:distance``
     - ``True``, ``False``
     - Enables marginalisation over luminosity distance.
       Defaults to ``True`` for bilby, ``False`` for RIFT.
   * - ``likelihood:marginalisation:phase``
     - ``True``, ``False``
     - Enables marginalisation over the orbital phase.
       Defaults to ``False``.
   * - ``likelihood:marginalisation:time``
     - ``True``, ``False``
     - Enables marginalisation over the coalescence time.
       Defaults to ``False``.
   * - ``likelihood:marginalisation:calibration``
     - ``True``, ``False``
     - Enables marginalisation over calibration uncertainty.
       Defaults to ``False``.
   * - ``likelihood:marginalisation:distance lookup``
     - string (path)
     - Path to a pre-computed lookup table for distance marginalisation.
       If not provided, the table is computed during the analysis.

ROQ settings
------------

These settings configure reduced order quadrature (ROQ) bases for ROQ-enabled likelihood functions.
For precise settings to use see individual pipeline documentation.

.. list-table::
   :header-rows: 1

   * - Setting
     - Values
     - Description
   * - ``likelihood:roq:folder``
     - string (path)
     - The directory containing the ROQ basis files.
       Defaults to ``None``.
   * - ``likelihood:roq:weights``
     - string (path)
     - The path to a pre-computed ROQ weights file.
       Defaults to ``None``.
   * - ``likelihood:roq:weight format``
     - string
     - The file format of the ROQ weights file.
       Defaults to ``None``.
   * - ``likelihood:roq:scale``
     - ``float``
     - A scale factor to apply to the ROQ weights.
       Defaults to ``1``.
   * - ``likelihood:roq:linear matrix``
     - string (path)
     - The path to the ROQ linear basis matrix file.
   * - ``likelihood:roq:quadratic matrix``
     - string (path)
     - The path to the ROQ quadratic basis matrix file.

Relative Binning
----------------

These settings configure likelihood functions which use either relative binning or heterodyning.

.. list-table::
   :header-rows: 1

   * - Setting
     - Values
     - Description
   * - ``likelihood:relative binning:fiducial parameters``
     - dict
     - A dictionary of fiducial parameter values used as the reference point for the relative binning expansion.
       Defaults to ``None``.
   * - ``likelihood:relative binning:update fiducial parameters``
     - ``True``, ``False``
     - If ``True``, the fiducial parameters are updated during sampling.
       Defaults to ``False``.
   * - ``likelihood:relative binning:epsilon``
     - ``float``
     - The fractional accuracy threshold for the relative binning approximation.
       Defaults to ``0.025``.

Sampler
=======

Settings in the ``sampler`` section configure the sampling algorithm used by the pipeline.

Sampler settings should be specified under the ``sampler`` heading, for example::

    sampler:
      sampler: dynesty
      parallel jobs: 4

General sampler settings
------------------------

These settings apply to samplers in most pipelines (particularly bilby).

.. list-table::
   :header-rows: 1

   * - Setting
     - Values
     - Description
   * - ``sampler:sampler``
     - string
     - The name of the sampler to use.
       For bilby this defaults to ``dynesty``.
       Supported values include ``dynesty``, ``emcee``, ``nessai``, and others supported by bilby.
   * - ``sampler:seed``
     - ``int``
     - The random seed for the sampler.
       Defaults to ``1``.
   * - ``sampler:parallel jobs``
     - ``int``
     - The number of parallel sampling jobs to run.
       Defaults to ``2``.
   * - ``sampler:sampler kwargs``
     - dict or JSON string
     - A dictionary of sampler-specific keyword arguments passed directly to the sampler.
       For example, for dynesty::

           sampler kwargs: "{'nlive': 1000, 'naccept': 60, 'sample': 'acceptance-walk'}"

RIFT-specific sampler settings
-------------------------------

RIFT uses two sampling stages, ILE (Importance sampling of the Likelihood with Extrinsic parameters) and CIP (Compute Intrinsic Parameters).
Their settings are specified in sub-sections of ``sampler``.

CIP settings
~~~~~~~~~~~~

.. list-table::
   :header-rows: 1

   * - Setting
     - Values
     - Description
   * - ``sampler:cip:fitting method``
     - ``rf``, ``gp``
     - The fitting method used in the CIP stage.
       Defaults to ``rf`` (random forest).
   * - ``sampler:cip:sampling method``
     - ``default``, ``GMM``, ``adaptive_cartesian_gpu``
     - The sampling method used in the CIP stage.
       Defaults to ``default``.
   * - ``sampler:cip:explode jobs``
     - ``int``
     - The number of CIP jobs to split work across.
       Higher values reduce runtime.
       Defaults to ``3``.
   * - ``sampler:cip:explode jobs auto``
     - ``True``, ``False``
     - If ``True``, the number of CIP jobs is determined automatically.
       Defaults to ``True``.

ILE settings
~~~~~~~~~~~~

.. list-table::
   :header-rows: 1

   * - Setting
     - Values
     - Description
   * - ``sampler:ile:n eff``
     - ``int``
     - The target effective sample count for each ILE iteration.
       Defaults to ``100``.
   * - ``sampler:ile:runtime max minutes``
     - ``int``
     - The maximum runtime (in minutes) for each ILE job.
       Defaults to ``700``.
   * - ``sampler:ile:jobs per worker``
     - ``int``
     - The number of likelihood evaluations per ILE worker process.
       Defaults to ``20``.
   * - ``sampler:ile sampling method``
     - string
     - The sampling method for ILE.
       Defaults to ``adaptive_cartesian_gpu``.
   * - ``sampler:force iterations``
     - ``int``
     - Forces a specific number of iterations in RIFT.
       Optional; if not set the number of iterations is determined adaptively.
   * - ``sampler:manual grid``
     - string (path)
     - Path to a pre-generated grid file used to bootstrap a RIFT analysis.
       Used in conjunction with ``bootstrap: manual``.

Scheduler
=========

Settings in the ``scheduler`` section configure the job submission to the computing cluster.

Scheduler settings should be specified under the ``scheduler`` heading, for example::

    scheduler:
      accounting group: ligo.dev.o4.cbc.pe.bilby
      request cpus: 4
      request memory: 8.0

.. list-table::
   :header-rows: 1

   * - Setting
     - Values
     - Description
   * - ``scheduler:accounting group``
     - string
     - The accounting tag for cluster resource tracking.
       For example ``ligo.dev.o4.cbc.pe.bilby``.
       Required on most LIGO clusters.
   * - ``scheduler:type``
     - string
     - The scheduler type to use.
       Defaults to ``condor`` (HTCondor).
   * - ``scheduler:request memory``
     - ``float`` (GB) or string (e.g. ``8192 MB``)
     - The amount of memory to request per job.
       For bilby this defaults to ``4.0`` GB.
       For BayesWave this defaults to ``8192 MB``.
   * - ``scheduler:request generation memory``
     - ``float`` (GB)
     - The amount of memory to request for the data generation jobs in bilby.
       Defaults to ``None`` (same as ``request memory``).
   * - ``scheduler:request post memory``
     - string (e.g. ``16384 MB``)
     - The amount of memory to request for BayesWave post-processing jobs.
       Defaults to ``16384 MB``.
   * - ``scheduler:request cpus``
     - ``int``
     - The number of CPUs to request per job.
       Defaults to ``1``.
   * - ``scheduler:request disk``
     - ``float`` (GB) or string (e.g. ``64 MB``)
     - The amount of disk space to request per job.
       For bilby this defaults to ``1`` GB.
       For BayesWave this defaults to ``64 MB``.
   * - ``scheduler:request post disk``
     - string (e.g. ``64 MB``)
     - The amount of disk space to request for BayesWave post-processing jobs.
       Defaults to ``64 MB``.
   * - ``scheduler:generation pool``
     - string
     - The HTCondor pool to use for data generation jobs in bilby.
       Defaults to ``local-pool``.
   * - ``scheduler:periodic restart time``
     - ``int``
     - The time in seconds after which a job is periodically restarted (useful for checkpointing).
       Defaults to ``28800`` (8 hours).
   * - ``scheduler:transfer files``
     - ``True``, ``False``
     - If ``True``, input files are transferred to the worker node.
       Defaults to ``True`` (or ``True`` if ``osg`` is set).
   * - ``scheduler:osg``
     - ``True``, ``False``
     - If ``True``, the job is submitted to the Open Science Grid.
       Defaults to ``False``.
   * - ``scheduler:desired sites``
     - string
     - A comma-separated list of OSG sites where the job is allowed to run.
       Defaults to ``None``.
   * - ``scheduler:container``
     - string
     - The path to a container image (e.g. Singularity/Apptainer .sif file) to use for the job.
       Defaults to ``None``.
   * - ``scheduler:conda env``
     - string
     - The name of a conda environment to activate for the job.
       Defaults to ``None``.
   * - ``scheduler:environment variables``
     - dict or string
     - Environment variables to set for the job.
       Defaults to ``{'HDF5_USE_FILE_LOCKING': False, 'OMP_NUM_THREADS': 1, 'OMP_PROC_BIND': False}``.
   * - ``scheduler:analysis executable``
     - string (path)
     - The path to the analysis executable.
       Defaults to ``None`` (bilby_pipe default).
   * - ``scheduler:scitoken issuer``
     - string (URL)
     - The SciToken issuer URL for authentication on the OSG.
       Defaults to ``None``.
   * - ``scheduler:queue``
     - string
     - The scheduler queue to submit jobs to.
       Defaults to ``None``.
   * - ``scheduler:additional files``
     - list of strings
     - A list of additional files to transfer alongside the job.
       Used when ``transfer files`` is enabled.
   * - ``scheduler:environment``
     - string (path)
     - The path to the software environment (pipeline installation) to use.
       If not specified, the global ``pipelines:environment`` configuration is used.

Priors
======

Settings in the ``priors`` section define the prior probability distributions for each physical parameter.
When using bilby, these are used to construct the prior dictionary passed to the sampler.

Prior settings should be specified under the ``priors`` heading, for example::

    priors:
      default: BBHPriorDict
      chirp mass:
        type: UniformInComponentsChirpMass
        minimum: 10
        maximum: 100

Each parameter prior is specified as a sub-section with the following optional keys:

- ``type``: the prior class name (e.g. ``Uniform``, ``Sine``, ``Cosine``, ``PowerLaw``, ``Constraint``).
- ``minimum``: the minimum value.
- ``maximum``: the maximum value.
- ``boundary``: the boundary condition, e.g. ``periodic``, ``reflective``.
- ``alpha``: the power-law exponent (for ``PowerLaw`` distributions).

.. list-table::
   :header-rows: 1

   * - Setting
     - Default type
     - Description
   * - ``priors:default``
     - string
     - The name of a bilby ``PriorDict`` class to use as the base prior.
       For example ``BBHPriorDict`` or ``BNSPriorDict``.
       Defaults to ``BBHPriorDict``.
   * - ``priors:geocentric time``
     - ``Uniform``
     - Prior on the geocentric coalescence time.
       Requires ``minimum``, ``maximum``, and optionally ``boundary``.
   * - ``priors:chirp mass``
     - ``UniformInComponentsChirpMass``
     - Prior on the chirp mass in solar masses.
       Requires ``minimum`` and ``maximum``.
   * - ``priors:mass ratio``
     - ``UniformInComponentsMassRatio``
     - Prior on the mass ratio :math:`q = m_2/m_1 \leq 1`.
       Requires ``minimum`` and ``maximum``.
   * - ``priors:total mass``
     - ``Constraint``
     - Constraint prior on the total mass.
       Requires ``minimum`` and ``maximum``.
   * - ``priors:mass 1``
     - ``Constraint``
     - Constraint prior on the primary component mass.
       Requires ``minimum`` and ``maximum``.
   * - ``priors:mass 2``
     - ``Constraint``
     - Constraint prior on the secondary component mass.
       Requires ``minimum`` and ``maximum``.
   * - ``priors:spin 1``
     - ``Uniform``
     - Prior on the dimensionless spin magnitude of the primary component.
       Defaults to ``Uniform(0, 0.99)``.
   * - ``priors:spin 2``
     - ``Uniform``
     - Prior on the dimensionless spin magnitude of the secondary component.
       Defaults to ``Uniform(0, 0.99)``.
   * - ``priors:tilt 1``
     - ``Sine``
     - Prior on the tilt angle of the primary spin.
       Defaults to ``Sine``.
   * - ``priors:tilt 2``
     - ``Sine``
     - Prior on the tilt angle of the secondary spin.
       Defaults to ``Sine``.
   * - ``priors:phi 12``
     - ``Uniform``
     - Prior on the azimuthal angle between the two spin vectors.
       Defaults to ``Uniform(0, 2*pi)`` with periodic boundary.
   * - ``priors:phi jl``
     - ``Uniform``
     - Prior on the azimuthal angle of the total angular momentum.
       Defaults to ``Uniform(0, 2*pi)`` with periodic boundary.
   * - ``priors:lambda 1``
     - ``Uniform``
     - Prior on the tidal deformability of the primary component.
       Requires ``minimum`` and ``maximum``.
       Only included when explicitly specified (relevant for BNS analyses).
   * - ``priors:lambda 2``
     - ``Uniform``
     - Prior on the tidal deformability of the secondary component.
       Requires ``minimum`` and ``maximum``.
       Only included when explicitly specified (relevant for BNS analyses).
   * - ``priors:luminosity distance``
     - ``PowerLaw``
     - Prior on the luminosity distance in Mpc.
       Defaults to a ``PowerLaw`` distribution; ``minimum``, ``maximum``, and other prior keys can be set.
   * - ``priors:volume``
     - ``comoving``
     - If set to ``comoving``, the distance prior is set in comoving volume.
       Relevant for LALInference and RIFT analyses.
   * - ``priors:calibration``
     - string
     - The boundary condition for the calibration prior.
       For example ``boundary: reflective``.

Postprocessing
==============

Settings in the ``postprocessing`` section configure post-processing pipelines which are run automatically after the main analysis completes.
Currently the primary supported post-processing pipeline is ``pesummary``.

Postprocessing settings should be specified under the ``postprocessing:pesummary`` heading, for example::

    postprocessing:
      pesummary:
        multiprocess: 4
        accounting group: ligo.dev.o4.cbc.pe.lalinference

.. list-table::
   :header-rows: 1

   * - Setting
     - Values
     - Description
   * - ``postprocessing:pesummary:accounting group``
     - string
     - The accounting tag for the PESummary job on the cluster.
   * - ``postprocessing:pesummary:multiprocess``
     - ``int``
     - The number of parallel processes to use for PESummary.
       Defaults to ``4``.
   * - ``postprocessing:pesummary:cosmology``
     - string
     - The cosmological model to use for computing derived parameters (e.g. redshift and source-frame masses).
       For example ``Planck15_lal``.
   * - ``postprocessing:pesummary:redshift``
     - string
     - The method to use for computing the redshift from the luminosity distance.
       For example ``exact``.
   * - ``postprocessing:pesummary:evolve spins``
     - string or dict
     - Controls evolution of spin angles.
       Set ``forwards`` to evolve spins forwards in time or ``backwards`` for backwards evolution.
   * - ``postprocessing:pesummary:skymap samples``
     - ``int``
     - The number of posterior samples to use when generating the sky map.
   * - ``postprocessing:pesummary:regenerate posteriors``
     - list of strings
     - A list of parameter names for which posteriors should be regenerated by PESummary.
       For example::

           regenerate posteriors:
             - redshift
             - mass_1_source
             - mass_2_source
   * - ``postprocessing:pesummary:environment variables``
     - dict
     - Additional environment variables to set when running PESummary.
   * - ``postprocessing:pesummary:keywords``
     - dict
     - Additional command-line arguments to pass to the PESummary executable,
       as a dictionary mapping argument names to values.
       Single-character keys are passed as short flags (e.g. ``-X``), longer keys as long flags (e.g. ``--key``).
