.. _event-guide:

Creating and managing events
============================

Once you've created an asimov project you'll need to add some gravitational wave events to it to analyse.

You can do this completely manually, or you can retrieve a pre-existing event from LIGO's event database, GraceDB.

Creating an event from a YAML file
----------------------------------

The simplest way to add an event which has been used in a previous analysis is by using an event blueprint file.
For events included in the published gravitational wave catalogue a curated set of these is available.
Documentation for these blueprint files can be found in its repository: https://git.ligo.org/asimov/data/

Curated data files provide all of the settings required for a given gravitational event to be analysed, but do not include specifications for any specific analyses.
This includes information about the appropriate sampling rate to use to analyse the job, any settings required to mitigate data quality concerns, as well as things like the time of the event and the appropriate detector data channels to use for the analysis.

One of these YAML files can be added to a project with the ``asimov apply`` command, and files can either be added by specifying the URL to the file, in which case asimov will first download the file, or by providing a path to the file locally.

For example, to add GW150914 you should run

.. code-block:: console

		$ asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/events/gwtc-2-1/GW150914_095045.yaml

A full list of all of the events available in this manner is available in the curated settings documentation.

You can also write your own YAML file describing an event, and this can be more convenient that setting everything up using the command line interface, described later in this document, if there are lots of specific settings which are required for the analysis of the event, which need to override the defaults which have been added to the project.

An event YAML file needs to specify settings in a specific format, which is described fully in the :ref:`ledger` documentation.
The YAML file must also contain a ``kind: event`` pair so that asimov knows that the file describes an event.

A very simple file might look something like this.

.. code-block:: YAML

		kind: event
		name: MyEvent
		data:
		  channels:
		    H1: H1:DCS-CALIB_STRAIN_CLEAN_SUB60HZ_C01
		    L1: L1:DCS-CALIB_STRAIN_CLEAN_SUB60HZ_C01
		    V1: V1:Hrec_hoft_16384Hz
		  frame types:
		    H1: H1_HOFT_CLEAN_SUB60HZ_C01
		    L1: L1_HOFT_CLEAN_SUB60HZ_C01
		    V1: V1Online
		  segment length: 64
		event time: 1258804321
		interferometers:
		- L1
		- H1

but many more settings can be added to it.

Adding an event from GraceDB
----------------------------
		
One of the major sources of data about gravitational wave events is `GraceDB`, a database of gravitational wave triggers which have been identified by one of many searches.

GraceDB clusters these triggers into "superevents", and normally we will want to request data from one of these superevents in order to start an analysis with `asimov`.

If you're interacting with an asimov project using the command line interface you can directly download information about a trigger and create an event in the project.

If you want to pull information from non-public events you'll first need to ensure that you have a LIGO proxy set up.
The easiest way to do this as a normal user is just to run `ligo-proxy-init`:

.. code-block:: console
   
   $ ligo-proxy-init isaac.asimov

replacing isaac.asimov with your own username, and then provide your password to set up a proxy.
If you're working with publically available triggers then you can skip this step, and asimov will gather all of the publically available data which it can.

.. code-block:: console
   
   $ asimov event create --superevent S200316bj

.. note::
   
   `GraceDB` will only provide a small amount of the total information which is needed to set up an analysis.
   You'll need things like default data settings before you can start an analysis.


Getting a set of events from `GraceDB`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Sometimes it's helpful to be able to gather a large set of events from `GraceDB` according to some criteria.
You can do this by specifying the search criterion on the command line, and all of the retrieved events will be created in the project.
For example:

.. code-block:: console
		
   $ asimov event create --search "label: PE_READY"

will search `GraceDB` for all events marked as "PE READY" and will add them to the project.

A complete description of the query language for `GraceDB` can be found in its documentation: https://gracedb.ligo.org/documentation/queries.html.


Creating an event using the command line
-----------------------------------------

The simplest way to make a new event is manually (however you'll need to specify all of its details manually later).

For example, if we want to make an event, and call it "GW150914" we can run

.. code-block:: console

		$ asimov event create --name GW150914

.. warning::

   Because this approach doesn't add all of the required configuration settings for a gravitational wave analysis we don't recommend this approach for setting up most analyses, unless they're using default settings applied across the entire project.

Adding additional configuration information
-------------------------------------------

While it's possible to manually update the configuration for each event (e.g. data quality information, and prior information) these can also be imported from other locations.

Asimov supports importing configurations from both json and yaml files; these can either be files of default information, or information produced by the ``PEConfigurator`` program.


As an example, suppose we have some default data to add to an event, and this is in yaml format, saved in a file called ``data.yaml``.

.. code-block:: yaml

		kind: configuration
		data:
		  channels:
		    H1: H1:DCH-CALIB_STRAIN_C02
		    L1: L1:DCH-CALIB_STRAIN_C02
		    V1: Hrec_hoft_V1O2Repro2A_16384Hz
		  frame-types:
		    H1: H1_HOFT_C02
		    L1: L1_HOFT_C02
		    V1: V1O2Repro2A
		priors: 
		    distance: [None, 10000]
		    component: [1, 1000]
		    q: [0.05, 1.0]
		    
In order to add these default data to an existing event we can use the ``asimov apply`` command:

.. code-block:: console

		$ asimov apply -f data.yaml --event GW150914

These will then be added to the event record in the ledger.

If we have a JSON file from the PEConfigurator we need to use the ``asimov event configurator`` command, which maps the outputs from the configurator to asimov's data format:

.. code-block:: console

		$ asimov event configurator GW170817 --json gw170817.json

Adding calibration envelopes
----------------------------

Many analyses will require access to calibration envelopes for the detectors.


.. note::

   This should work on the CIT LIGO cluster, but you'll need to follow the instructions for adding calibration information manually if you're running the command elsewhere.


For an event called ``GW170817`` in the ledger you can find the calibration envelopes and add them to the ledger by running
   
.. code-block:: console

		$ asimov event calibration GW170817

This will search for the calibration files for all of the available detectors, and add them to the event record in the ledger.
Note that the ``asimov apply`` command will perform this action for you, so you don't need to run this command if you made your event from a YAML file.

If you need to add calibrations manually you can do that by specifying them as options:

.. code-block:: console

		$ asimov event calibration GW150914 --calibration H1:/home/albert.einstein/h1-cal.dat --calibration L1:/home/albert.einstein/l1-cal.dat

It's safest to use absolute filepaths here.
