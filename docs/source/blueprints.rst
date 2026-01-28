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

Requirements can be specified in the ``needs`` setting of an analysis using a flexible syntax that supports complex dependency conditions.

Simple name-based dependencies
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The simplest form of dependency is to specify the name of a required analysis::

    kind: analysis
    name: generate-psds
    pipeline: bayeswave
    ---
    kind: analysis
    name: parameter-estimation
    pipeline: bilby
    needs:
      - generate-psds

Property-based dependencies
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Dependencies can also be specified using properties of analyses. Any property can be used, including nested properties accessed with dot notation::

    kind: analysis
    name: parameter-estimation
    pipeline: bilby
    needs:
      - pipeline: bayeswave
      - waveform.approximant: IMRPhenomXPHM

This will match all analyses that use the ``bayeswave`` pipeline OR have ``IMRPhenomXPHM`` as their waveform approximant.

Review status dependencies
^^^^^^^^^^^^^^^^^^^^^^^^^^

The review status is a commonly used dependency criterion::

    kind: analysis
    name: combiner
    pipeline: bilby
    needs:
      - review.status: approved

Negated dependencies
^^^^^^^^^^^^^^^^^^^^

You can specify that an analysis should depend on analyses that do NOT match a criterion by prefixing the value with ``!``::

    kind: analysis
    name: non-bayeswave-analyses
    pipeline: bilby
    needs:
      - pipeline: "!bayeswave"

This will match all analyses except those using the bayeswave pipeline.

OR logic (multiple dependencies)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

By default, multiple items in the ``needs`` list are combined with OR logic. An analysis will depend on any analysis matching ANY of the conditions::

    kind: analysis
    name: combiner
    pipeline: bilby
    needs:
      - waveform.approximant: IMRPhenomXPHM
      - waveform.approximant: SEOBNRv5PHM

This will match analyses using either ``IMRPhenomXPHM`` OR ``SEOBNRv5PHM``.

AND logic (all conditions must match)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To specify that ALL conditions must match (AND logic), use a nested list::

    kind: analysis
    name: specific-analysis
    pipeline: bilby
    needs:
      - - review.status: approved
        - waveform.approximant: IMRPhenomXPHM

This will only match analyses that are both approved AND use IMRPhenomXPHM.

Complex dependency specifications
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You can combine AND and OR logic for complex dependency specifications::

    kind: analysis
    name: complex-combiner
    pipeline: bilby
    needs:
      - - review.status: approved
        - pipeline: bayeswave
      - waveform.approximant: IMRPhenomXPHM

This will match analyses that are (approved AND use bayeswave) OR use IMRPhenomXPHM.

Dependency tracking and staleness
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When an analysis runs, asimov records which analyses were its dependencies at that time. If the set of matching analyses changes later (for example, if new analyses are added that match the dependency criteria), the original analysis is marked as **stale**.

Stale analyses are indicated in the HTML report. You can mark an analysis as **refreshable** to indicate it should be automatically re-run when it becomes stale::

    kind: analysis
    name: auto-refresh-analysis
    pipeline: bilby
    refreshable: true
    needs:
      - review.status: approved

The resolved dependencies (those that were actually used when the analysis ran) are stored in the ledger and displayed in the HTML report alongside the current matching dependencies.

Strategies
==========

Strategies allow you to create multiple similar analyses with parameter variations from a single blueprint. This is similar to GitHub Actions matrix strategies and is useful for:

- Testing multiple waveform approximants
- Comparing different samplers
- Running parameter-parameter (p-p) tests
- Performing systematic studies

Basic Strategy Syntax
---------------------

A strategy is defined using the ``strategy`` keyword in an analysis blueprint. The strategy specifies parameters and the values they should take::

    kind: analysis
    name: bilby-{waveform.approximant}
    event: GW150914
    pipeline: bilby
    strategy:
      waveform.approximant:
        - IMRPhenomXPHM
        - SEOBNRv4PHM
        - IMRPhenomD

This will create three separate analyses:
- ``bilby-IMRPhenomXPHM`` with ``waveform.approximant: IMRPhenomXPHM``
- ``bilby-SEOBNRv4PHM`` with ``waveform.approximant: SEOBNRv4PHM``
- ``bilby-IMRPhenomD`` with ``waveform.approximant: IMRPhenomD``

Name Templates
--------------

The ``name`` field can include placeholders in curly braces (``{}``) that will be replaced with strategy parameter values. The placeholder name should match the full parameter path::

    kind: analysis
    name: bilby-{waveform.approximant}-analysis
    pipeline: bilby
    strategy:
      waveform.approximant:
        - IMRPhenomXPHM
        - SEOBNRv4PHM

This creates:
- ``bilby-IMRPhenomXPHM-analysis``
- ``bilby-SEOBNRv4PHM-analysis``

If no placeholder is used, all generated analyses will have the same name, which may cause conflicts.

Matrix Strategies (Multiple Parameters)
----------------------------------------

You can specify multiple parameters in a strategy to create all combinations (cross-product)::

    kind: analysis
    name: bilby-{waveform.approximant}-{sampler.sampler}
    event: GW150914
    pipeline: bilby
    strategy:
      waveform.approximant:
        - IMRPhenomXPHM
        - SEOBNRv4PHM
      sampler.sampler:
        - dynesty
        - emcee

This creates 4 analyses (2 × 2 combinations):
- ``bilby-IMRPhenomXPHM-dynesty``
- ``bilby-IMRPhenomXPHM-emcee``
- ``bilby-SEOBNRv4PHM-dynesty``
- ``bilby-SEOBNRv4PHM-emcee``

Nested Parameters
-----------------

Strategy parameters can use dot notation to set deeply nested values::

    kind: analysis
    name: bilby-margdist-{likelihood.marginalisation.distance}
    pipeline: bilby
    strategy:
      likelihood.marginalisation.distance:
        - true
        - false

This sets ``likelihood.marginalisation.distance`` in the generated analyses.

.. note::

   Special value handling:
   
   - Boolean values (``True``/``False``) are converted to lowercase strings (``true``/``false``) when used in name templates to match YAML conventions.
   - Each strategy parameter must be a list with at least one value.
   - Strategy parameters cannot be empty lists or non-list values.

Complete Strategy Example
-------------------------

Here's a complete example combining multiple features::

    kind: analysis
    name: pe-{waveform.approximant}-{sampler.sampler}
    event: GW150914
    pipeline: bilby
    comment: Systematic waveform and sampler comparison
    needs:
      - generate-psd
    likelihood:
      sample rate: 4096
      psd length: 4
    strategy:
      waveform.approximant:
        - IMRPhenomXPHM
        - SEOBNRv4PHM
        - IMRPhenomD
      sampler.sampler:
        - dynesty
        - emcee

This creates 6 analyses (3 waveforms × 2 samplers), each inheriting the ``needs``, ``likelihood``, and ``comment`` settings while varying the waveform and sampler.

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
   * - ``waveform:enforce signal duration``
     - ``True``, ``False``
     -
   * - ``waveform:generator``
     - See individual pipeline documentation.
     -
   * - ``waveform:reference frequency``
     - 
     - The reference frequency at which spins etc are defined.
   * - ``likelihood:start frequency``
     - ``float``
     - The frequency at which the generation of the waveform should be started. NB this is not the same as ``quality:minimum frequency`` which is the lowest frequency at which the inner product is evaluated.
   * - ``waveform:conversion function``
     - See individual pipeline documentation.
     - A function which can be used to perform conversions for the waveform.
   * - ``waveform:generator``
     - See individual pipeline documentation.
     - The generator to be used for the waveform.
   * - ``waveform:approximant``
     -
     - The name of the waveform approximant to be used.
   * - ``waveform:pn spin order``
     -
     -
   * - ``waveform:pn tidal order``
     -
     -
   * - ``waveform:pn phase order``
     -
     -
   * - ``waveform:pn amplitude order``
     -
     -
   * - ``waveform:file``
     -
     -
   * - ``waveform:arguments``
     -
     -
   * - ``waveform:mode array``
     -
     -
     
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
     - True, False
     - If set to true this indicates that a coherence test should be performed where a pipeline supports it.
   * - ``likelihood:post trigger time``
     - ``float``
     - The amount of time which should be analysed after the trigger time.
   * - ``likelihood:sample rate``
     - ``float``
     - The sample rate which should be used to compute the likelihood.
   * - ``likelihood:psd length``
     - ``float``
     - The length, in seconds, of the data used to produce the power spectral density estimate.
   * - ``likelihood:roll off time``
     - ``float``
     - The roll off time for data windowing.
   * - ``likelihood:time reference``
     - 
     - The reference for timing.
   * - ``likelihood:reference frame``
     -
     - The reference frame.
   * - ``likelihood:type``
     - See individual pipeline documentation.
     - The likelihood function to use.
   * - ``likelihood:kwargs``
     - ``dict``
     -  Additional keyword arguments to be passed to the likelihood function.
   * - ``likelihood:frequency domain source model``
     - See individual pipeline documentation.
     -
   * - ``likelihood:time domain source model``
     - See individual pipeline documentation.
     -

Calibration settings
--------------------

These settings affect the handling of calibration data within the likelihood function.

.. list-table::
   :header-rows: 1

   * - Setting
     - Values
     - Description
   * - likelihood:calibration:sample
     - True, False
     - If set to True then the likelihood will sample over the calibration uncertainty.

Marginalisation settings
------------------------

These settings allow various marginalisations to be turned on or off, and configured within each pipeline.

.. list-table::
   :header-rows: 1

   * - Setting
     - Values
     - Description
   * - likelihood:marginalisation:distance
     - True, False
     -
   * - likelihood:marginalisation:phase
     - True, False
     -
   * - likelihhod:marginalisation:time
     - True, False
     -
   * - likelihood:marginalisation:calibration
     - True, False
     -

ROQ settings
------------

These settings can be used to configure reduced order quadrature (ROQ) bases for ROQ-enabled likelihood functions. For precise settings to use see individual pipeline documentation.

.. list-table::
   :header-rows: 1

   * - Setting
     - Values
     - Description
   * - likelihood:roq:folder
     -
     -
   * - likelihood:roq:weights
     -
     -
   * - likelihood:roq:scale
     -
     -
   * - likelihood:roq:linear matrix
     -
     -
   * - likelihhod:roq:quadratic matrix
     -
     -

Relative Binning
----------------

These settings should be used to configure likelihood functions which use either relative binning or heterodyning.

.. list-table::
   :header-rows: 1

   * - Setting
     - Values
     - Description
   * - likelihood:relative binning:fiducial parameters
     -
     -
   * - likelihood:relative binning:update fiducial parameters
     -
     -
   * - likelihood:relative binning:epsilon
     -
     -
