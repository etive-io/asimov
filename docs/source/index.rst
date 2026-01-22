:page_template: homepage.html

.. raw:: html

	 <div class="px-4 py-5 my-5 text-center">
	 <h1 class="display-5 fw-bold">
	 Manage and automate analyses with <code>asimov</code>.
	 </h1>
	 <p class="lead mb-4">
	 A powerful and extensible automation framework for scientific analysis workflows.
	 </p>
	 </div>


.. raw:: html

	 <div class="d-flex flex-column flex-lg-row align-items-md-stretch justify-content-md-center gap-3 mb-4">
	<div class="d-inline-block v-align-middle fs-5">
	<div class="asimov-code">
	<pre>$ pip install asimov</pre>
	</div>
	</div>
	 <a class="btn btn-lg btn-primary d-flex align-items-center justify-content-center fw-semibold"
	    href="getting-started.html"
	 >
	 <i class="bi bi-book"></i><span>  </span><span style="padding-left: 1rem;">Documentation</span>
	 </a>
	 </div>

`Asimov` is a python package to help with setting-up, automating, and monitoring scientific data analysis.
It is designed to make organising a scientific project, simplifying your workflow, and making your analysis easier to reproduce.

Asimov makes setting-up and running parameter estimation jobs easier.
It can generate configuration files for several parameter estimation pipelines, and handle submitting these to a cluster.
Whether you're setting-up a preliminary analysis for a single gravitational wave event, or analysing hundreds of events for a catalog, Asimov can help.

.. raw:: html

	 <div class="row g-4 py-5 row-cols-1 row-cols-lg-2">

.. raw:: html

	 <div class="feature col">
	 <i class="bi bi-bar-chart"></i>

Scientific analysis management
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Asimov is able to interact with high throughput job management tools, and can submit jobs to clusters, monitor them for problems, and initiate post-processing tasks.
Once your analysis is completed asimov can manage the data products and results, and prepare them for publication and distribution.

.. raw:: html

	 </div>

.. raw:: html

	 <div class="feature col">
	 <i class="bi bi-cpu-fill"></i>

Uniform pipeline interface
~~~~~~~~~~~~~~~~~~~~~~~~~~

Asimov provides an API layer which allows a single configuration to be deployed to numerous different analysis pipelines.
Current gravitational wave pipelines which are supported are ``lalinference``, ``bayeswave``, ``RIFT``, and ``bilby``.

.. raw:: html

	 </div>
	 </div>

.. raw:: html

	 <div class="row g-4 py-5 row-cols-1 row-cols-lg-2">

.. raw:: html

	 <div class="feature col">
	 <i class="bi bi-briefcase"></i>

Centralised configuration
~~~~~~~~~~~~~~~~~~~~~~~~~

Asimov records all ongoing, completed, and scheduled analyses, allowing jobs, configurations, and results to be found easily.

.. raw:: html

	 </div>


.. raw:: html

	 <div class="feature col">
	 <i class="bi bi-briefcase"></i>


Reporting overview
~~~~~~~~~~~~~~~~~~

Asimov can provide both machine-readible and human-friendly reports of all jobs it is monitoring, while collating relevant log files and outputs.

.. raw:: html

	 </div>
	 </div>

Quick installation
------------------

Asimov is available on ``pypi`` and can be installed via ``pip install asimov``.

Citing asimov
-------------

If you use asimov in a publication please consider consulting our :ref:`citation-guide`.



Users' guide
------------

.. toctree::
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
   olivaw/review
   citing
	     
.. toctree::
   :maxdepth: 2
   :caption: The Ledger

   ledger
      
   
.. toctree::
   :maxdepth: 1
   :caption: Pipeline Guides

   pipelines/lalinference
   pipelines/bilby
   pipelines/rift
   pipelines/bayeswave

Advanced topics
---------------

.. toctree::
   :maxdepth: 2
   :caption: Advanced topics

   analyses
   build-process
   scheduler-integration
   monitor-state-machine
   monitor-api
   configuration
   test-interface
   clusters

Developers' Guide
-----------------

.. toctree::
   :maxdepth: 1
   :caption: Development Guide

   contributing.rst
   code-of-conduct.rst

   
   asimov-repository
	     
   ledger   
   pipelines-dev
   hooks

   building-docs
   
   asimov-repository

   code-overview

   ledger
   pipelines-dev
   hooks

   building-docs

Tutorials
---------

.. toctree::
   :maxdepth: 1
   :Caption: Tutorials

   tutorials/analysing-gw150914
   tutorials/adding-a-pipeline
   tutorials/remixing-analyses
   

Python API
----------

.. toctree::
   :maxdepth: 1
   :caption: Python API

   python-api
   api/project
   api/asimov
   api/condor
   api/event
   api/git
   api/gitlab
   api/ini
   api/ledger
   api/locutus
   api/logging
   api/mattermost
   api/olivaw
   api/pipeline
   api/schedulers
   config

LIGO Analysis Cookbook
----------------------

.. toctree::
   :maxdepth: 1
   :Caption: LIGO Analysis Cookbook

   ligo-cookbook/bayeswave
   ligo-cookbook/bilby
   ligo-cookbook/working-with-gwosc

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
* :ref:`routingtable`
