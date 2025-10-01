<<<<<<< HEAD
.. _ledger:

=======
>>>>>>> v0.4-release
The Asimov Ledger
=================

The ledger is the central source of information within a project, and stores information about events and analyses.

Data in the ledger is hierarchical, so settings can be specified on a per-project, per-event, and per-analysis level, allowing project-wide defaults to be set, but overwritten when required.
In addition defaults can be set for each pipeline.

In this documentation we'll represent the ledger in ``yaml`` format, however a number of other storage methods for the ledger are also supported by asimov.

The ledger hierarchy
--------------------

Project data
~~~~~~~~~~~~

The project is the top level of the hierarchy within asimov.
Settings which are defined for the project are passed to all events and those events' analyses.

Event data
~~~~~~~~~~

Events are stored under the ``events`` key of the ledger.
All events are attached to a project, and they inherit all of the settings from their project.

Analysis data
~~~~~~~~~~~~~

All analyses are attached to an event, and inherit all of the settings from their event.

Pipeline data
~~~~~~~~~~~~~

In addition to specifying project or event defaults, it is possible to define per-pipeline defaults in the ``pipelines`` key of the ledger, which are only used by a specific pipeline.
For example, you may wish to specify a different set of defaults for all ``bilby`` analyses compared to all ``rift`` analyses.

Applying changes to the ledger
------------------------------

There are a number of ways that changes can be applied to the ledger, for example adding new analyses, new events, or setting defaults.

1. Via the command line interface
2. By writing a ledger page and adding it to the ledger
3. By directly editing the ledger

The first two options are the recommended approach for the vast majority of situations.
While editing the ledger directly is the most powerful approach it also presents more risks.

Detector information
--------------------

Information about which detectors should be used for an analysis is contained under the ``interferometers`` key.

This should be a list of detector abbreviations, for example ``[H1, L1, V1]``.

Examples
~~~~~~~~

In order to provide the IFO list for all analyses in a given event:

.. code-block::

   - name: GW150915
     interferometers:
     - L1
     - H1
     productions:
       Prod1: ...

       
Data information
----------------

Information and settings about the data are stored under the ``data`` key.

Examples
~~~~~~~~

.. code-block::

   data:
     calibration:
       H1: h1-calibration.dat
       L1: l1-calibration.dat
    channels:
      H1: H1:DCS-CALIB_STRAIN_C02
      L1: L1:DCS-CALIB_STRAIN_C02
    frame-types:
      H1: H1_HOFT_C02
      L1: L1_HOFT_C02
    segments:
      H1: H1:DMT-ANALYSIS_READY:1
      L1: L1:DMT-ANALYSIS_READY:1
    segment length: 4

``calibration``
  This section defines the location of the calibration splines for the analysis.
  These can either be specified relative to the event repository, or as an absolute path.
  Files should be provided for each detector, indexed by the detector abbreviation.

  For example
  
  ::
     
     data:
       calibration:
         H1: /home/cal/H1-calibration.dat
	 V1: /home/cal/V1-calibration.dat

``channels``
  This section defines the data channels which should be used in the analysis.
  These should be provided for each detector.
  For example
  
  ::
     
     data:
       channels:
	 H1: H1:DCS-CALIB_STRAIN_C02
	 L1: L1:DCS-CALIB_STRAIN_C02

``frame-types``
  This section defines the frame types which should be used in the analysis.
  These should be provided for each detector.
  For example
  
  ::
     
     data:
       frame-types:
	 H1: H1_HOFT_C02
	 L1: L1_HOFT_C02

``segments``
  This section defines the segments which should be used in the analysis.
  These should be provided for each detector.
  For example
  
  ::
     
     data:
       segments:
	 H1: H1:DMT-ANALYSIS_READY:1
	 L1: L1:DMT-ANALYSIS_READY:1

``data files``
  This section should define data files which contain the analysis data to be used
  in the analysis, and should be provided for each detector.
  For example
  
  ::
     
     data:
       data files:
         H1: ./H1-file.gwf
	 L1: ./L1-file.gwf
	 
Data quality information
------------------------

Examples
~~~~~~~~

.. code-block::

   quality:
     minimum frequency:
       H1: 20
       L1: 20
     maximum frequency:
       H1: 2048
       L1: 2048

Likelihood settings
-------------------

Examples
~~~~~~~~

.. code-block::

   likelihood:
   
     psd length: 4
     reference frequency: 20
     sample rate: 2048
     segment start: 1126259460.391
     start frequency: 13.333333333333334
     window length: 4

Sampler settings
----------------

Examples
~~~~~~~~

.. code-block:: yaml

		scheduler:
  		  accounting group: ligo.dev.o4.cbc.pe.bilby
		  request cpus: 4



Prior settings
--------------

Examples
~~~~~~~~

.. code-block:: yaml

    priors:
      chirp mass:
	type: UniformInComponentsChirpMass
	minimum: 0
	maximum: 100
      mass ratio:
	type: UniformInComponentsMassRatio
	minimum: 0.1
	maximum: 1.0
      mass 1:
	type: Constraint
	minimum: 0
	maximum: 1
      mass 2:
	type: Constraint
	minimum: 0
	maximum: 1
      spin 1:
	type: Uniform
	minimum: 0
	maximum: 1
      spin 2:
	type: Uniform
	minimum: 0
	maximum: 1
      tilt 1:
	type: Sine
      tilt 2:
	type: Sine
      phi 12:
	type: Uniform
      phi jl:
	type: Uniform
      luminosity distance:
	type: PowerLaw
	minimum: 0
	maximum: 1000
	alpha: 2
      dec:
	type: Cosine
      ra:
	type: Uniform
      theta jn:
	type: Sine
      psi:
	type: Uniform
      phase:
	type: Uniform
	boundary: periodic

Postprocessing settings
-----------------------

Examples
~~~~~~~~

.. code-block:: yaml


		postprocessing:
		  pesummary:
		    accounting group: ligo.dev.o4.cbc.pe.lalinference
		    cosmology: Planck15_lal
		    evolve spins: forward
		    multiprocess: 4
		    redshift: exact
		    regenerate posteriors:
		    - redshift
		    - mass_1_source
		    - mass_2_source
		    - chirp_mass_source
		    - total_mass_source
		    - final_mass_source
		    - final_mass_source_non_evolved
		    - radiated_energy
		    skymap samples: 2000
