Describing your own event
=========================

Events in the LVK's catalogues already have blueprints, in the asimov data repository.
For a new candidate, a simulated signal, or your own choice of settings, you write the blueprints yourself.
In this tutorial you'll describe an invented gravitational wave event, and see exactly which settings each of its analyses would be given.

.. rst-class:: tutorial-intro

:What you'll learn: How to write an event blueprint, check it for mistakes, share settings across a project, find out which setting wins, and update an event safely.
:Time required: About 20 minutes.
:Prerequisites: asimov installed as in :ref:`Getting started<Getting Started>`, with its virtual environment active. You don't need a computing cluster or any gravitational wave software, because nothing is analysed.

.. rst-class:: procedural-step

Make a project
--------------

Start a new project, in a directory of its own:

.. code-block:: bash

   $ mkdir my-event
   $ cd my-event
   $ asimov init "My own event"

.. rst-class:: procedural-step

Describe the event
------------------

An event blueprint holds what is true of the event, whichever way you analyse it.
Save this one as ``event.yaml``:

.. code-block:: yaml
   :caption: event.yaml

   kind: event
   name: candidate-1
   event time: 1400000000.0
   interferometers: [H1, L1]
   data:
     segment length: 4
   likelihood:
     sample rate: 2048
     psd length: 4
     window length: 4
     segment start: 1399999998.0
     start frequency: 13.3
     minimum frequency:
       H1: 20
       L1: 20
   priors:
     chirp mass:
       minimum: 21
       maximum: 42

``event time``
   When the signal arrived, in GPS seconds.
``interferometers``
   The detectors whose data you want to analyse.
``data``
   Which data to use. Here it's only the length of the segment, in seconds.
``likelihood``
   How to treat the data: for example the sampling rate, and the lowest frequency to use from each detector.
   The segment here starts two seconds before the event.
``priors``
   What you believe about the source before looking at the data.
   The range of chirp masses is usually taken from the search which found the event.

These values are invented.
For your own event, work them out from what you know about the signal and the data.
:doc:`The blueprint guide <../blueprints>` describes the settings in full.

.. rst-class:: procedural-step

Check the blueprint
-------------------

Asimov has a *vocabulary*, a list of the settings it knows about.
Check your blueprint against it before you apply it:

.. code-block:: bash

   $ asimov vocabulary check event.yaml

.. code-block:: text

   event.yaml: OK

To see what the check catches, save this blueprint, which has a spelling mistake:

.. code-block:: yaml
   :caption: mistake.yaml

   kind: event
   name: candidate-1
   likelihood:
     minimum frequncy:
       H1: 20

.. tutorial-test: may-fail

.. code-block:: bash

   $ asimov vocabulary check mistake.yaml

.. code-block:: text

   'minimum frequncy' is not in the asimov ledger vocabulary. Did you mean 'likelihood.minimum frequency'?

This matters because ``asimov apply`` doesn't make this check.
It would accept the misspelt setting without complaint, and the analyses would never use it.

.. warning::
   The check covers the names of settings, and the types of their values.
   It can't tell you whether a number is sensible, and it doesn't check anything inside ``priors``, so read those carefully.

.. rst-class:: procedural-step

Set defaults for the project
----------------------------

Many settings are the same for every event you analyse.
Put those in a ``configuration`` blueprint, which applies to the whole project.
Save this as ``defaults.yaml``:

.. code-block:: yaml
   :caption: defaults.yaml

   kind: configuration
   likelihood:
     sample rate: 4096
     roll off time: 1.0
   waveform:
     reference frequency: 20
   priors:
     chirp mass:
       type: bilby.gw.prior.UniformInComponentsChirpMass
       minimum: 1
       maximum: 100
     luminosity distance:
       type: bilby.gw.prior.UniformSourceFrame
       minimum: 10
       maximum: 10000
   pipelines:
     simpletestpipeline:
       sampler:
         parallel jobs: 3

There are two kinds of default here:

* The sections at the top, such as ``likelihood`` and ``priors``, are passed on to every analysis.
  This works only for ``data``, ``likelihood``, ``priors``, ``quality``, ``scheduler`` and ``waveform``.
* Settings under ``pipelines`` are passed only to analyses which use the pipeline named. Put anything else, such as ``sampler`` settings, here.

``simpletestpipeline`` is a stand-in which comes with asimov for testing.
Using it means that you don't need any real pipelines installed; in your own work you'd name one such as ``bilby``.

.. warning::
   Don't put the same setting both at the top and under ``pipelines``.
   The one at the top currently wins, although you might expect the more specific one to.

Add the defaults and the event to the project:

.. code-block:: bash

   $ asimov apply -f defaults.yaml
   $ asimov apply -f event.yaml

.. rst-class:: procedural-step

Add some analyses
-----------------

Now describe three ways of analysing the event.
The second looks further away than usual, and the third uses only one detector.

.. code-block:: yaml
   :caption: analyses.yaml

   kind: analysis
   name: standard
   pipeline: simpletestpipeline
   waveform:
     approximant: IMRPhenomXPHM
   ---
   kind: analysis
   name: distant
   pipeline: simpletestpipeline
   waveform:
     approximant: IMRPhenomXPHM
   priors:
     luminosity distance:
       maximum: 20000
   ---
   kind: analysis
   name: hanford-only
   pipeline: simpletestpipeline
   waveform:
     approximant: IMRPhenomXPHM
   interferometers: [H1]

.. code-block:: bash

   $ asimov vocabulary check analyses.yaml defaults.yaml
   $ asimov apply -f analyses.yaml -e candidate-1

.. rst-class:: procedural-step

See what each analysis gets
---------------------------

``asimov production show`` lists every setting an analysis has, wherever it came from.
(A *production* is an older name for an analysis.)

.. code-block:: bash

   $ asimov production show candidate-1 standard

Among the output you'll find:

.. code-block:: text

   maximum frequency:
   H1: 896
   roll off time: 1.0
   sample rate: 2048
   priors:
   chirp mass:
   maximum: 42
   minimum: 21
   type: bilby.gw.prior.UniformInComponentsChirpMass
   sampler:
   parallel jobs: 3
   approximant: IMRPhenomXPHM
   reference frequency: 20

Those values came from several places:

.. list-table::
   :header-rows: 1

   * - Setting
     - Value
     - Where it came from
   * - ``sample rate``
     - 2048
     - The event, which replaces the project's 4096.
   * - ``roll off time``
     - 1.0
     - The project defaults.
   * - ``maximum frequency``
     - 896
     - Asimov, which worked it out from the sampling rate.
   * - chirp mass range
     - 21 to 42
     - The event.
   * - chirp mass ``type``
     - uniform in component masses
     - The project defaults.
   * - ``parallel jobs``
     - 3
     - The defaults for the pipeline.
   * - ``approximant``
     - IMRPhenomXPHM
     - The analysis.

Now look at the second analysis:

.. code-block:: bash

   $ asimov production show candidate-1 distant

.. code-block:: text

   luminosity distance:
   maximum: 20000
   minimum: 10
   type: bilby.gw.prior.UniformSourceFrame

It changed one number, and kept the rest of the prior from the project defaults.

The rules are:

#. A setting in an **analysis** wins over the same setting in its **event**, which wins over a **project default**.
#. Sections are combined setting by setting, so you only write what differs.
#. A single value or a list is replaced as a whole. ``hanford-only`` has just ``H1`` in its ``interferometers``:

.. code-block:: bash

   $ asimov production show candidate-1 hanford-only

.. code-block:: text

   interferometers:
   - H1

.. rst-class:: procedural-step

Update the event
----------------

A new estimate suggests that the chirp mass can't be larger than 35.
An update is combined with what's already there, so the blueprint only needs what has changed.
Save this as ``new-masses.yaml``:

.. code-block:: yaml
   :caption: new-masses.yaml

   kind: event
   name: candidate-1
   priors:
     chirp mass:
       maximum: 35

None of your analyses has started, and you want all of them to use the new value, so use ``--update-unstarted``.
Preview it first:

.. code-block:: bash

   $ asimov apply -f new-masses.yaml --update-unstarted --dry-run

.. code-block:: text

   priors.chirp mass.maximum: 42 -> 35

.. code-block:: bash

   $ asimov apply -f new-masses.yaml --update-unstarted
   $ asimov production show candidate-1 distant

.. code-block:: text

   maximum: 35
   minimum: 21
   maximum: 20000

The analysis has the new chirp mass range, and still has its own distance prior.

Analyses which have started keep the settings they had.
With ``--update`` alone, the event changes but existing analyses don't: see :doc:`when-something-goes-wrong`.

.. warning::
   An analysis keeps a setting of its own only if it differed from the event's when the analysis was added.
   If the two were the same, asimov treats the analysis as following the event, and ``--update-unstarted`` changes it too.

Using this for real
-------------------

You've built up the settings, but nothing has been analysed, and a real pipeline may need more than you've given here.
To run analyses on a cluster:

* Install the pipelines, as in :doc:`analysing-gw150914`.
* Start from the published project defaults used there, in place of your ``defaults.yaml``.
* Apply your own event blueprint, in place of the one from the catalogue.
* Name real pipelines, such as ``bayeswave`` and ``bilby``, in your analyses.
* Say where the data are. The published defaults are for public data; for other data, set the channel and frame type of each detector:

  .. tutorial-test: skip

  .. code-block:: yaml

     data:
       channels:
         H1: H1:GWOSC-16KHZ_R1_STRAIN
       frame types:
         H1: H1_GWOSC_16KHZ_R1

Changing a project default later can also change analyses which have already run, which is `a known bug <https://github.com/etive-io/asimov/issues/341>`_, so settle your defaults early.

What's next?
------------

* :doc:`The blueprint guide <../blueprints>` describes every kind of blueprint and its settings.
* :doc:`The vocabulary <../vocabulary>` explains how settings are named.
* :doc:`analysing-gw150914` runs a real analysis from start to finish.
