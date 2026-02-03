=============================
Configuration file production
=============================

All of the pipelines which ``asimov`` is designed to work with use some manner of configuration file to define their operation.
Previously, creating these configuration files could be a tedious manual process, but ``asimov`` allows these files to be *templated*, combining various pieces of data and metadata from the production ledger with a template configuration file to produce the configuration which is then used to generate the DAG files which run the analysis.

The production ledger
---------------------

Each gravitational wave event which ``asimov`` handles has an assosciated production ledger.
These are currently stored in the text of issues on ``gitlab``, however, in future versions of ``asimov`` we will introduce alternative options to increase flexibility.

Details of the metadata stored in the production ledger can be found on the :ref:`The production ledger<documentation for the ledger format>`, but an example is included below:

.. code-block:: yaml

    calibration:
      H1: analyses/calibration/H1.dat
      L1: analyses/calibration/L1.dat
      V1: analyses/calibration/V1.dat
    data:
      channels:
	H1: H1:DCS-CALIB_STRAIN_CLEAN_SUB60HZ_C01
	L1: L1:DCS-CALIB_STRAIN_CLEAN_SUB60HZ_C01
	V1: V1:Hrec_hoft_16384Hz
      frame-types:
	H1: H1_HOFT_CLEAN_SUB60HZ_C01
	L1: L1_HOFT_CLEAN_SUB60HZ_C01
	V1: V1Online
    event time: 1266618172.401773
    gid: G365380
    gid_url: https://catalog-dev.ligo.org/events/G8090/view/
    interferometers:
    - H1
    - L1
    - V1
    name: S200224a
    priors:
      amp order: 1
      chirp-mass:
      - 22.852486906183355
      - 57.65416902042432
      component:
      - 1
      - 1000
      distance:
      - None
      - 10000
      q:
      - 0.05
      - 1.0
    productions:
    - Prod1:
        waveform:
	   approximant: IMRPhenomXPHM
	comment: Bilby job
	pipeline: bilby
	status: ready
    psds:
      1024:
	H1: /home/daniel.williams/events/O3/event_repos/S200224a/analyses/psds/1024/H1-psd.dat
	L1: /home/daniel.williams/events/O3/event_repos/S200224a/analyses/psds/1024/L1-psd.dat
	V1: /home/daniel.williams/events/O3/event_repos/S200224a/analyses/psds/1024/V1-psd.dat
    quality:
      lower-frequency:
	H1: 20
	L1: 20
	V1: 20
      start-frequency: 13.333333333333334
      psd-length: 4.0
      reference-frequency: 20
      sample-rate: 1024
      segment-length: 4.0
      supress:
	V1:
	  lower: 46.0
	  upper: 51.0
      window-length: 4.0
    repository: git@git.ligo.org:pe/O3/S200224ca
    working directory: /home/daniel.williams/events/O3/o3b/run_directories/S200224a



This production ledger specifies the data required to build ``Prod1``, which is a ``bilby`` job.
In order to run a ``bilby`` job a config file is required for ``bilby_pipe``.
``Asimov`` can produce this from a template.

Config file templates can be written using the liquid templating language, and should be kept in a directory which is specified in the `asimov` configuration file under the ``templating>directory`` configuration value e.g.

.. code-block:: ini

   [templating]
   directory = config-templates


The liquid language allows some logic to be included in the template.
This can be used to only include a given value if an interferometer is included in the analysis.
For example:

.. code-block:: ini

    spline-calibration-envelope-dict={
      {% if production.meta['interferometers'] contains "H1" %}
	H1:{{ production.event.repository.directory }}/{{ production.meta['calibration']['H1'] }},
      {% endif %}
      {% if production.meta['interferometers'] contains "L1" %}
	L1:{{ production.event.repository.directory }}/{{ production.meta['calibration']['L1'] }},
      {% endif %}
      {% if production.meta['interferometers'] contains "V1" %}
	V1:{{ production.event.repository.directory }}/{{ production.meta['calibration']['V1'] }}
      {% endif %}
    }

Adds only the calibration files for the required detectors to the configuration file.


The majority of the data passed to the template can be found in the ``production.meta`` dictionary.
These are stored in the same nested format as the production ledger; evbent-wide values are inherited by the production, so in the example ledger below the sample rate can be retrieved from ``production.meta['quality']['sample-rate']``, for example.

There are also a number of additional variables are available for convenience:

+ ``production.quality`` is an alias for ``production.meta['quality']``
+ ``production.psds`` provides the dictionary of PSDs for this event's specified sample rate.
+ ``production.event`` provides access to the data from the event (e.g. for the repository directory path, located at ``production.event.repository.directory``)

A full example ``bilby`` template is available below:

.. code-block:: ini

    ################################################################################
    ## Calibration arguments
    ################################################################################

    calibration-model=CubicSpline
    spline-calibration-envelope-dict={ {% if production.meta['interferometers'] contains "H1" %}H1:{{ production.event.repository.directory }}/{{ production.meta['calibration']['H1'] }},{% endif %}{% if production.meta['interferometers'] contains "L1" %}L1:{{ production.event.repository.directory }}/{{ production.meta['calibration']['L1'] }},{% endif %}{% if production.meta['interferometers'] contains "V1" %}V1:{{ production.event.repository.directory }}/{{ production.meta['calibration']['V1'] }}{% endif %} }
    spline-calibration-nodes=10
    spline-calibration-amplitude-uncertainty-dict=None
    spline-calibration-phase-uncertainty-dict=None

    ################################################################################
    ## Data generation arguments
    ################################################################################

    ignore-gwpy-data-quality-check=True
    gps-tuple=None
    gps-file=None
    timeslide-file=None
    timeslide-dict=None
    trigger-time={{ production.meta['event time'] }}
    gaussian-noise=False
    n-simulation=0
    data-dict=None
    data-format=None
    channel-dict={ {% if production.meta['interferometers'] contains "H1" %}{{ production.meta['data']['channels']['H1'] }},{% endif %} {% if production.meta['interferometers'] contains "L1" %}{{ production.meta['data']['channels']['L1'] }},{% endif %}{% if production.meta['interferometers'] contains "V1" %}{{ production.meta['data']['channels']['V1'] }}{% endif %} }

    ################################################################################
    ## Detector arguments
    ################################################################################

    coherence-test=False
    detectors={{ production.meta['interferometers'] }}
    duration={{ production.meta['quality']['segment-length'] }}
    generation-seed=None
    psd-dict={ {% if production.meta['interferometers'] contains "H1" %}H1:{{ production.psds['H1'] }},{% endif %} {% if production.meta['interferometers'] contains "L1" %}L1:{{ production.psds['L1'] }},{% endif %} {% if production.meta['interferometers'] contains "V1" %}V1:{{ production.psds['V1'] }}{% endif %} }
    psd-fractional-overlap=0.5
    post-trigger-duration=2.0
    sampling-frequency={{ production.meta['quality']['sample-rate'] }}
    psd-length={{ production.meta['quality']['psd-length'] }}
    psd-maximum-duration=1024
    psd-method=median
    psd-start-time=None
    maximum-frequency=1024
    minimum-frequency={{ production.meta['quality']['reference-frequency'] }}
    zero-noise=False
    tukey-roll-off=0.4
    resampling-method=lal

    ################################################################################
    ## Injection arguments
    ################################################################################

    injection=False
    injection-dict=None
    injection-file=None
    injection-numbers=None
    injection-waveform-approximant=None

    ################################################################################
    ## Job submission arguments
    ################################################################################

    accounting=ligo.dev.o3.cbc.pe.lalinference
    label={{ production.name }}
    local=False
    local-generation=False
    local-plot=False
    outdir={{ production.rundir }}
    periodic-restart-time=28800
    request-memory=4.0
    request-memory-generation=None
    request-cpus=4
    singularity-image=None
    scheduler=condor
    scheduler-args=None
    scheduler-module=None
    scheduler-env=None
    transfer-files=False
    log-directory=None
    online-pe=False
    osg=False

    ################################################################################
    ## Likelihood arguments
    ################################################################################

    distance-marginalization=True
    distance-marginalization-lookup-table=None
    phase-marginalization=True
    time-marginalization=True
    jitter-time=True
    reference-frame={% if production.meta['interferometers'] contains "H1" %}H1{% endif %}{% if production.meta['interferometers'] contains "L1" %}L1{% endif %}{% if production.meta['interferometers'] contains "V1" %}V1{% endif %}
    time-reference={% if production.meta['interferometers'] contains "H1" %}H1{% elsif production.meta['interferometers'] contains "L1" %}L1{% elsif production.meta['interferometers'] contains "V1" %}V1{% endif %}
    likelihood-type=GravitationalWaveTransient
    roq-folder=None
    roq-scale-factor=1
    extra-likelihood-kwargs=None

    ################################################################################
    ## Output arguments
    ################################################################################

    create-plots=True
    plot-calibration=False
    plot-corner=False
    plot-marginal=False
    plot-skymap=False
    plot-waveform=False
    plot-format=png
    create-summary=False
    email=None
    existing-dir=None
    webdir=/home/pe.o3/public_html/LVC/o3b-catalog/{{ production.event.name }}/{{ production.name }}
    summarypages-arguments=None

    ################################################################################
    ## Prior arguments
    ################################################################################

    default-prior=BBHPriorDict
    deltaT=0.2
    prior-file=4s
    prior-dict=None
    convert-to-flat-in-component-mass=False

    ################################################################################
    ## Post processing arguments
    ################################################################################

    postprocessing-executable=None
    postprocessing-arguments=None
    single-postprocessing-executable=None
    single-postprocessing-arguments=None

    ################################################################################
    ## Sampler arguments
    ################################################################################

    sampler=dynesty
    sampling-seed=None
    n-parallel=5
    sampler-kwargs={'queue_size': 4, 'nlive': 2000, 'sample': 'rwalk', 'walks': 100, 'n_check_point': 2000, 'nact': 10, 'npool': 4}

    ################################################################################
    ## Waveform arguments
    ################################################################################

    waveform-generator=bilby.gw.waveform_generator.WaveformGenerator
    reference-frequency={{ production.meta['quality']['reference-frequency'] }}
    waveform-approximant={{ production.meta['waveform']['approximant'] }}
    catch-waveform-errors=False
    pn-spin-order=-1
    pn-tidal-order=-1
    pn-phase-order=-1
    pn-amplitude-order=0
    mode-array=None
    frequency-domain-source-model=lal_binary_black_hole
