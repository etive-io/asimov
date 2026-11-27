.. _tutorials:

Tutorials
=========

Each tutorial is a worked example which you follow from start to finish.
If you're new to asimov, begin with :ref:`Getting started<Getting Started>`, which introduces its main ideas in about 10 minutes.

Learn asimov on your own computer
---------------------------------

These use measurements of a stretched spring in place of real science, so you don't need a computing cluster.
They carry on in the project you make in :ref:`Getting started<Getting Started>`, so do that first.

.. list-table::
   :header-rows: 1
   :widths: 25 45 20 10

   * - Tutorial
     - What you'll do
     - Do first
     - Minutes
   * - :doc:`adding-a-pipeline`
     - Turn your program into an asimov pipeline, with its own settings.
     - Getting started, and know some Python
     - 20
   * - :doc:`when-something-goes-wrong`
     - Find out why analyses failed, run them again, and replace those with the wrong settings.
     - Getting started
     - 20
   * - :doc:`scaling-up`
     - Add many subjects and analyses at once, combine their results, and tidy up.
     - Adding a pipeline
     - 20
   * - :doc:`results-to-release`
     - Review results, release those which are approved, and record how they were made.
     - Getting started
     - 20

Analyse gravitational waves
---------------------------

.. list-table::
   :header-rows: 1
   :widths: 25 45 20 10

   * - Tutorial
     - What you'll do
     - You need
     - Minutes
   * - :doc:`analysing-gw150914`
     - Analyse the first gravitational wave to be detected, from an empty directory to a running workflow.
     - An HTCondor cluster
     - 30, then about a day of computing
   * - :doc:`your-own-event`
     - Write the blueprints for an event of your own, and find out which settings each analysis gets. Nothing is analysed.
     - Your own computer, with asimov installed
     - 20
   * - :doc:`remixing-analyses`
     - Repeat a published analysis with a different waveform, reusing its settings and data products.
     - The software and cluster used for GW150914
     - —
   * - :doc:`python-api-tutorial`
     - Run the GW150914 workflow from Python instead of the command line.
     - The software and cluster used for GW150914
     - —
