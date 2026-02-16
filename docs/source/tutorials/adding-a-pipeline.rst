Integrating a new pipeline with Asimov
======================================

.. note::
   Tutorial by Daniel Williams, using ``asimov 0.5.8``.

This guide is intended to help you to make your code with asimov.

Asimov is able to automate the process of configuring, running, and monitoring analyses at scale, and can make managing large numbers of similar analyses easy while ensuring that everything is readily reproducible.

First steps
-----------

In this tutorial we'll assume that you're extending an analysis which has been written in Python, however asimov can automate analyses written in any language. Writing shims for non-Python pipelines will be covered in their own tutorial in the future. We'll also assume that your code either runs as a script in a terminal, or produces submission information for the ``htcondor`` job scheduler. While we hope to provide support for other schedulers in the future, asimov v0.5 can only work with ``htcondor``.

In order to provide concrete examples in this tutorial I'll discuss the process of integrating the ``pyring`` package with asimov. ``pyring`` is a gravitational wave analysis code, and as a result there may be some gravitational-wave specific references in the tutorial. However asimov can run any code (and from asimov 0.6 onwards we'll make this easier by further separating GW-specific code from the main codebase).

The main ``pyring`` repository looks something like this:

.. code-block:: bash

   $ ls
   AUTHORS.md    LICENSE      README.rst  pyRing                pyproject.toml    scripts    setup.py
   CHANGELOG.md  MANIFEST.in  docs        pypi_description.rst  requirements.txt  setup.cfg

we'll add the `asimov.py` file in the ``pyRing`` directory.

We need to tell asimov at least four things about our pipeline:

1. How to run it
2. How to submit it to ``htcondor``
3. How to check it's finished running
4. How to find its assets, e.g. results files

All of these are handled by methods on a class which we can make by subclassing the ``asimov.pipeline.Pipeline`` class.

For example, here we'll start by writing this to make the class:

.. code-block:: python

   import asimov.pipeline.Pipeline

   class pyRing(asimov.pipeline.Pipeline):
     """
     The pyRing Pipeline.
     """
     name = "pyRing"
     _pipeline_command = "pyring"

we can now add various bits of logic as methods on this class which will overload the base class's methods.

``build_dag``
-------------

The ``build_dag`` method is used to tell asimov how to run the pipeline (and is only required if the pipeline constructs its own submission information for the ``htcondor`` scheduler. pyRing does not do this, so we can skip this method in this instance.

``submit_dag``
--------------

The ``submit_dag`` method is used to tell asimov how to submit the job to the scheduler; if we've been able to write a ``build_dag`` method we can simply tell asimov how to submit the dag file it produced, but we'll need to do a bit more work for pyRing.

First we need to look at the normal command-line for pyRing. Normally we run it like this:

``pyring --config config.ini``

where ``config.ini`` is the path to a config file (more on that later).

The executable here is ``pyring``, and the arguments are ``--config config.ini``.

Submission to ``htcondor`` can be handled directly by asimov without the need to write a submit file, but we need to construct the same information in python. We can do this by constructing a description dictionary:

.. code-block:: python

   executable = f"{os.path.join(config.get('pipelines', 'environment'), 'bin', self._pipeline_command)}"
   command = ["--config", ini]

   description = {
           "executable": executable,
           "arguments": " ".join(command),
           "output": f"{name}.out",
           "error": f"{name}.err",
           "log": f"{name}.log",
           "getenv": "True",
           "request_memory": "4096 MB",
           "batch_name": f"{self.name}/{self.production.event.name}/{name}",
           "accounting_group_user": config.get('condor', 'user'),
           "accounting_group": self.production.meta['scheduler']["accounting group"],
           "request_disk": "8192MB",
           "+flock_local": "True",
           "+DESIRED_Sites": htcondor.classad.quote("nogrid"),
   }

this has all of the information which is normally conveyed in the submit file, including the location of error files, and accounting information.

We've also included information at the end of the dictionary which prevents the code from being flocked (e.g. to the OSG or the IGWN pool for LIGO jobs). We'll need to set up file transfers for this to work, which is slightly beyond the scope of this tutorial.

This is the vast majority of the required information, and we can submit this to the cluster with ``job = htcondor.Submit(description)``. We also need to gather the cluster ID from condor to report back to asimov so it can track the job's progress. This is shown in the full code example below, as it requires a little work to identify.

In the full example below I've also written out two extra files; a bash script which contains the full command (this is really helpful for debugging things, so we can run the precise analysis on the command line), and the submit file.

Putting everything together our ``build_dag`` method looks like this:

.. code-block:: python

   def build_dag(self, dryrun=False):
      name = self.production.name
      ini = self.production.event.repository.find_prods(name, self.category)[0]
      meta = self.production.meta
      
      executable = f"{os.path.join(config.get('pipelines', 'environment'), 'bin', self._pipeline_command)}"
      command = ["--config", ini]
      
      description = {
               "executable": executable,
               "arguments": " ".join(command),
               "output": f"{name}.out",
               "error": f"{name}.err",
               "log": f"{name}.log",
               "getenv": "True",
               "request_memory": "4096 MB",
               "batch_name": f"{self.name}/{self.production.event.name}/{name}",
               "accounting_group_user": config.get('condor', 'user'),
               "accounting_group": self.production.meta['scheduler']["accounting group"],
               "request_disk": "8192MB",
               "+flock_local": "True",
               "+DESIRED_Sites": htcondor.classad.quote("nogrid"),
      }
    
       job = htcondor.Submit(description)
       os.makedirs(self.production.rundir, exist_ok=True)
       with set_directory(self.production.rundir):
           os.makedirs("results", exist_ok=True)

           with open(f"{name}.sub", "w") as subfile:
               subfile.write(job.__str__()+r"\n queue")

           with open(f"{name}.sh", "w") as bashfile:
               bashfile.write(str(full_command))

       with set_directory(self.production.rundir):
           try:
               schedulers = htcondor.Collector().locate(htcondor.DaemonTypes.Schedd, config.get("condor", "scheduler"))
           except configparser.NoOptionError:
               schedulers = htcondor.Collector().locate(htcondor.DaemonTypes.Schedd)
           schedd = htcondor.Schedd(schedulers)
           with schedd.transaction() as txn:
               cluster_id = job.queue(txn)

       self.clusterid = cluster_id

Analysis assets
---------------

When our pipeline runs it will probably produce a number of output files and data products. In the case of pyRing one of these files contains the posterior samples from the analysis. We need to tell asimov where to find these outputs; it can then ensure these are passed along to subsequent analyses, and also make them easily available to you.

The ``collect_assets`` method should return a dictionary of all the assets you want to declare to asimov. In the simple case of wishing to only declare the samples file this method can be as simple as this:

.. code-block:: python

       def collect_assets(self):
           """
           Gather all of the results assets for this job.
           """
           return {"samples": os.path.join(self.production.rundir,
                                           "Nested_sampler",
                                           "posterior.dat"),
                   }

Here asimov will return the ``Nested_sampler/posterior.dat`` file in the analysis's run directory. We could (and probably should!) add some additional logic to ensure this file actually exists, but in the interest of simplicity for this tutorial I'll just return the expected path.

Checking for completion
-----------------------

asimov needs to be told how to confirm that a job has completed successfully (simply checking the status of a job on ``htcondor`` is not a reliable way of doing this.

Typically the easiest way to do this is to check for the existence of a result file, or a set of results files. Since we already have the posterior samples file for pyRing available in the dictionary returned by ``collect_assets`` we can simply check the path exists:

.. code-block:: python

       def detect_completion(self):
           """
           Detect if the outputs have been created, and if they have,
           assert that the job is complete.
           """
           if os.path.exists(self.collect_assets().get('samples')):
               return True
           else:
               return False

There might be circumstances where simply checking for the existence of a file is insufficient to demonstrate that an analysis has finished, but you can include arbitrary code in this method to account for that.

Templating your config file
---------------------------

The majority of the work required to configure your analysis goes into creating its configuration file. Configuration files can be very large, but in this tutorial I'll start by creating a simple one which you can build on.

Let's have a look at (part of) one of pyRing's example configuration files.

.. code-block:: toml

   [input]

   run-type=full
   pesummary=0
   screen-output=1
   output=gw150914_DS_quick_example
   data-H1=data/Real_data/GW150914/H-H1_GWOSC_4KHZ_R1-1126259447-32.txt
   data-L1=data/Real_data/GW150914/L-L1_GWOSC_4KHZ_R1-1126259447-32.txt
   trigtime=1126259462.4232266
   detectors=H1,L1
   template=Damped-sinusoids
   # Number of: {"scalar", "vector", "tensor"} modes.
   n-ds-modes={"s": 0, "v": 0, "t": 1}
   sky-frame = equatorial

Right now this is set up to work on GW150914_095045 only; we can start by templating some of these values so that Asimov can substitute the correct values for the event the analysis is working on. Asimov uses the ``liquid`` language for templating, which uses double curly brackets to indicate a substitution:

.. code-block:: toml

   trigtime={{ production.meta['event time'] }}

Most of the information which we'll need are in the ``production.meta`` variable, which is a dictionary containing all of the data which Asimov knows about the analysis.

Asimov can use the ``asimov-gwdata`` pipeline to retrieve GWOSC data, and then pass the paths of the frame files to Asimov. We can add this to the template like this:

.. code-block:: toml

   {%- assign ifos = production.meta['interferometers'] -%}
   {%- if data['data files'].size > 0 %}
   # Add data which asimov has already downloaded, e.g. via asimov-gwdata
   {%- for ifo in ifos %}
   data-{{ifo}}={{data['data files'][ifo]}}
   {%- endfor %}
   {%- else %}
   # Download data for this analysis
   download-data=1
   {%- endif %}

We can keep adding additional templated variables like this, and we'll end up with something like this:

.. code-block:: toml

   {%- if production.event.repository -%}
   {%- assign repo_dir = production.event.repository.directory -%}
   {%- else -%}
   {%- assign repo_dir = "." -%}
   {%- endif -%}
   {%- assign meta = production.meta -%}
   {%- assign sampler = production.meta['sampler'] -%}
   {%- assign scheduler = production.meta['scheduler'] -%}
   {%- assign likelihood = production.meta['likelihood'] -%}
   {%- assign priors = production.meta['priors'] -%}
   {%- assign data = production.meta['data'] -%}
   {%- assign quality = production.meta['quality'] -%}
   {%- assign ifos = production.meta['interferometers'] -%}


   [input]

   run-type=full
   pesummary=0
   {%- if data['data files'].size > 0 %}
   # Add data which asimov has already downloaded, e.g. via asimov-gwdata
   {%- for ifo in ifos %}
   data-{{ifo}}={{data['data files'][ifo]}}
   {%- endfor %}
   {%- else %}
   # Download data for this analysis
   download-data=1
   {%- endif %}

   output={{ production.rundir }}

   datalen-download={{ data['segment length'] | default: 64.0 }}
   trigtime={{ production.meta['event time'] }}
   detectors={% for ifo in ifos %}{{ifo}},{% endfor %}
   template=Damped-sinusoids
   # Number of: {"scalar", "vector", "tensor"} modes.
   n-ds-modes={"s": 0, "v": 0, "t": 1}
   sky-frame = equatorial
   screen-output=1

   [Sampler settings]
   nlive=256
   maxmcmc=256
   seed=1234

   [Priors]

   mf-time-prior=67.9
   #10Mf after the peaktime
   fix-t=0.00335
   fix-ra=1.1579
   fix-dec=-1.1911
   logA_t_0-min=-21
   logA_t_0-max=-20.5
   f_t_0-min=220
   f_t_0-max=270
   tau_t_0-min=0.001
   tau_t_0-max=0.011

   [Injection]

   [Plot]

   # imr-samples=data/Real_data/GW150914/GW150914_LAL_IMRPhenomP_O1_GWOSC_Mf_af_samples.txt

We've still got more work to do, as there are a lot of hard-coded values left, but this should be able to get you started. You can have a look at more complete configuration templates like `this one <https://git.ligo.org/asimov/asimov/-/blob/review/asimov/configs/bilby.ini>`_ for bilby.

We now need to save this as ``config_template.ini`` in the same directory as the ``asimov.py`` file.

We'll need to make sure that this file gets packaged when we make the python package. We can do this by adding the file to the ``MANIFEST.in`` file (which is in the root of your project's repository):

.. code-block:: toml

   include pyRing/config_template.ini

Telling Asimov about your pipeline
----------------------------------

The final bit of engineering we'll need to do is to add some information to the installation script for the package. ``pyRing`` uses ``setup.py`` to do this, and we need to add an "entrypoint" so that Asimov can discover the pipeline. I've shortened the ``setup.py`` function here for clarity, but we just need to add some information to the ``entry_points`` variable in the ``setup()`` function:

.. code-block:: python

   setup(
       # metadata
       name="pyRingGW",
       ...
       entry_points={
           "console_scripts": [
               "pyRing = pyRing.pyRing:main",
           ],
           "asimov.pipelines": [
                  "pyRing = pyRing.asimov:pyRing"
              ]
       },
       ...
       )

The entry point needs to be ``asimov.pipelines``, and since we're only specifying a single pipeline we make a list with just one entry. The pipeline will be called ``pyRing`` by Asimov, and the class which describes it has an import path of ``pyRing.asimov`` and is called ``pyRing`` which gives is the rather complex-looking syntax above.

Writing blueprints for your pipeline
------------------------------------

We now have everything which we need to allow Asimov to set up analyses using the pyRing pipeline, but in order to create analyses using it we'll need to write a blueprint.

If you've looked at the tutorials for running parameter estimation with bilby these should be fairly familiar, and at the very simplest for pyRing one will look something like this:

.. code-block:: yaml

   kind: analysis
   pipeline: pyRing
   comment: An example pyRing analysis
   name: pyring-test

Assuming that we've set everything up in a similar way to running PE on GW150914_095045, then we can simply add this analysis to the event by running

.. code-block:: bash

   $ asimov apply -f pyring-test.yaml -e GW150914_095045

assuming that we saved the blueprint as ``pyring-test.yaml``.

And that's the very basics of adding a new pipeline to Asimov.
