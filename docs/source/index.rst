:page_template: homepage.html

Manage and automate analyses with ``asimov``
============================================

.. raw:: html

	<p class="lead mb-4 text-center">Workflow orchestration for scientific analyses on HTCondor and Slurm clusters.</p>
	<div class="d-flex flex-column flex-lg-row justify-content-center align-items-center gap-3 mb-4">
	<div class="asimov-code"><pre>$ pip install asimov</pre></div>
	<a class="btn btn-lg btn-primary fw-semibold" href="getting-started.html"><i class="bi bi-book"></i><span class="ps-2">Quickstart guide</span></a>
	</div>

Asimov sets up, submits, monitors and reports on scientific analysis jobs, and records everything
it does in a database so that results can be reproduced. It is used in production for
gravitational-wave analysis by LIGO, Virgo and KAGRA, and works with any pipeline
that can be described through its plugin interface, whether you are analysing one event or
hundreds.

.. raw:: html

	<div class="row g-3 row-cols-1 row-cols-md-2 row-cols-xl-3 my-4 home-cards">
	<div class="col"><div class="home-card">
	<h3><a class="stretched-link" href="getting-started.html">Get started</a></h3>
	<p>Install asimov and run your first analysis in a few minutes.</p>
	</div></div>
	<div class="col"><div class="home-card">
	<h3><a class="stretched-link" href="ledger.html">Understanding projects</a></h3>
	<p>How projects, events and analyses are recorded, versioned and shared.</p>
	</div></div>
	<div class="col"><div class="home-card">
	<h3><a class="stretched-link" href="pipelines.html">Pipelines</a></h3>
	<p>One configuration, many pipelines: bilby, RIFT, BayesWave, LALInference or your own.</p>
	</div></div>
	<div class="col"><div class="home-card">
	<h3><a class="stretched-link" href="user-guide/running.html">Run and monitor</a></h3>
	<p>Submit jobs to HTCondor or Slurm, watch them, and recover from failures.</p>
	</div></div>
	<div class="col"><div class="home-card">
	<h3>User Guide</h3>
	<p>Explore the full documentation: <a href="rest-api.html">REST API</a>, <a href="python-api.html">Python API</a>, <a href="configuration.html">configuration</a> and the <a href="vocabulary.html">ledger vocabulary</a>.</p>
	</div></div>
	<div class="col"><div class="home-card">
	<h3><a class="stretched-link" href="tutorials/analysing-gw150914.html">Tutorials</a></h3>
	<p>Worked examples, from analysing GW150914 to writing a new pipeline.</p>
	</div></div>
	</div>

.. figure:: screenshots/report-dashboard.png
   :alt: The asimov report's summary dashboard, showing live counts of analyses by status
   :width: 70%
   :align: center

   The project report shows live counts of analyses by status. See the :doc:`reporting guide <user-guide/reporting>`.

If you use asimov in a publication, please see the :ref:`citation-guide`.

.. toctree::
   :hidden:
   :maxdepth: 2
   :caption: 📚 Users' guide

   getting-started
   installation
   user-guide/projects
   user-guide/events
   user-guide/productions
   user-guide/running
   user-guide/monitoring
   user-guide/reporting
   storage
   user-guide/review
   citing

.. toctree::
   :hidden:
   :maxdepth: 2
   :caption: The Ledger

   ledger
   vocabulary


.. toctree::
   :hidden:
   :maxdepth: 1
   :caption: Pipeline Guides

   pipelines
   pipelines/lalinference
   pipelines/bilby
   pipelines/rift
   pipelines/bayeswave
   pipelines/pesummary
   pipelines/command

.. toctree::
   :hidden:
   :maxdepth: 2
   :caption: Advanced topics

   analyses
   analysis-types
   blueprints
   priors
   environment-reproducibility
   provenance
   principals
   audit
   mcp
   registry
   build-process
   scheduler-integration
   dag-translation-examples
   monitor-state-machine
   labeller-plugins
   monitor-api
   configuration
   test-interface
   clusters
   gracedb
   advanced/projects

.. toctree::
   :hidden:
   :maxdepth: 1
   :caption: Development Guide

   contributing.rst
   code-of-conduct.rst

   asimov-repository
   code-overview
   pipelines-dev
   hooks
   building-docs

.. toctree::
   :hidden:
   :maxdepth: 1
   :caption: Tutorials

   tutorials/when-something-goes-wrong
   tutorials/scaling-up
   tutorials/analysing-gw150914
   tutorials/python-api-tutorial
   tutorials/adding-a-pipeline
   tutorials/remixing-analyses


.. toctree::
   :hidden:
   :maxdepth: 2
   :caption: REST API

   rest-api

.. toctree::
   :hidden:
   :maxdepth: 1
   :caption: Python API

   python-api
   api/project
   api/asimov
   api/condor
   api/event
   api/git
   api/ini
   api/ledger
   api/locutus
   api/logging
   api/mattermost
   api/olivaw
   api/pipeline
   api/schedulers
   config

.. toctree::
   :hidden:
   :maxdepth: 1
   :caption: LIGO Analysis Cookbook

   ligo-cookbook/bayeswave
   ligo-cookbook/bilby
   ligo-cookbook/defaults
   ligo-cookbook/working-with-gwosc


