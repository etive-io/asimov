.. Remixing analyses_

Remixing published analyses
===========================

.. note::
   Tutorial by Daniel Williams, using ``asimov 0.5.9`` and ``asimov-gwdata 0.6.0``.

One of the core goals of asimov is to make it easier to reproduce gravitational wave analyses.
However, often it is helpful to be able to take a published analysis as the basis of a new analysis without needing to complete all of the steps required.

In this guide I will demonstrate how asimov makes it very easy to take an analysis published as part of the GWTC-2.1 catalogue, and "remix" it, using all of the same settings, but a different waveform.

Prerequisites
-------------

.. note::
   If this is your first time encountering asimov then you should read the :ref:`getting started guide <Getting Started>` first.

In order to create our new analysis we need to create a new asimov project, and add some default settings to it.
This requires a couple of commands:

.. code-block :: bash

   mkdir project
   cd project
   asimov init "GW150914 Remix"
   asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe.yaml
   asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe-priors.yaml

We should also add information about the event itself to the project, which we can find from the `curated settings repository <https://git.ligo.org/asimov/data/>`_ provided by the LVK.

.. code-block:: console

   $ asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/events/gwtc-2-1/GW150914_095045.yaml

Getting published data
----------------------

While the last command collected all of the settings required to recreate an analysis on GW150914, it doesn't collect all of the data required.
These data fall into two categories: calibration uncertainty envelopes, and power spectral density (noise) estimates.
Fortunately these were both provided in the LVK's data release which you can find on Zenodo `here <https://zenodo.org/records/6513631>`_.

.. warning::
   Asimov cannot (currently!) download the data release automatically, so you'll need to have a local copy of it on the machine which you're using.
   You don't need to download the entire data set, you can restrict the downloads to the files for the events you're actually reanalysing.

We can tell asimov to extract the data from the data release using the ``asimov-gwdata`` pipeline, which asimov will run as if it's an analysis (even though it doesn't actually analyse anything!).
We do this by writing a simple blueprint for the ``gwdata`` step, which points asimov to the data release file.
Note that here I've used the special variable syntax ``<event>`` in the filepath. The data release calls this event GW150914_095045, as does the curated event blueprint.
If you've rename the event in your project you'll not be able to use this, as ``<event>`` gets replaced by the event name when asimov runs the pipeline.

.. code-block:: yaml

    kind: analysis
    name: get-data
    pipeline: gwdata
    source:
      type: pesummary
      location: /home/daniel/tmp/asimov-tmp/data/IGWN-GWTC2p1-v2-<event>_PEDataRelease_mixed_cosmo.h5
    download:
    - frames
    - calibration
    - psds

Save this blueprint data to a new file called ``get-data.yaml``.
You can now get asimov to add this to the project by running

.. code-block:: console

    $ asimov apply -f get-data.yaml -e GW150914_095045

Designing the remixed analysis
------------------------------

For this example I'm going to make a rather trivial change to the original analysis, and just change the waveform which was used.
In the published analysis the LVK used the ``IMRPhenomXPHM`` waveform, but my remix will use ``IMRPhenomPv2``.
Chances are you'll want to do something more interesting, after all, this is in fact an older waveform than the one which got used!

To set this up we need another (quite short!) blueprint to configure the ``bilby`` analysis.

.. code-block:: yaml

    kind: analysis
    name: bilby-IMRPhenomPv2
    pipeline: bilby
    waveform:
    approximant: IMRPhenomPv2

    comment: PE job using IMRPhenomPv2 and bilby
    needs:
        - get-data

Two things are worth highlighting here: first I've changed the value of ``approximant`` compared to the `XPHM blueprint <https://git.ligo.org/asimov/data/-/blob/main/analyses/bilby-bbh/analysis_bilby_IMRPhenomXPHM.yaml?ref_type=heads>`_.
Second, I've added ``get-data`` as an explicit requirement; in the full end-to-end workflow the ``generate-psd`` step has this as a requirement, not the bilby job.
However we're skipping that by reusing the published PSDs, so we need to make ``get-data`` a direct prerequisite for the ``bilby`` analysis.

Save this blueprint as ``bilby-IMRPhenomPv2.yaml`` and apply it to your project:

.. code-block :: console

    $ asimov apply -f get-data.yaml -e GW150914_095045

Run your remixed analysis
-------------------------

We're now ready to run the remixed analysis!
Because you've specified a multi-stage analysis workflow it's easiest to use the ``asimov start`` tool to automate the workflow from here.

Run

.. code-block:: console

    $ asimov start

and asimov will launch each part of the analysis workflow in turn without you needing to further intervene.
