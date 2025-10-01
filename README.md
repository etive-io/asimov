# Asimov

Asimov is a workflow management and automation platform for scientific analyses.

[Documentation](https://asimov.docs.ligo.org/asimov) · [Releases](https://git.ligo.org/asimov/asimov/-/releases) · [Issue Tracker](https://git.ligo.org/asimov/asimov/-/issues)


[![coverage report](https://git.ligo.org/asimov/asimov/badges/master/coverage.svg)](https://git.ligo.org/asimov/asimov/-/commits/master)
[![conda-forge version](https://anaconda.org/conda-forge/asimov/badges/version.svg)](https://anaconda.org/conda-forge/asimov/)
![pypi](https://img.shields.io/pypi/v/asimov.svg)
![tests](https://git.ligo.org/asimov/asimov/badges/master/pipeline.svg)

Asimov was developed to manage and automate the parameter estimation analyses used by the LIGO, Virgo, and KAGRA collaborations to analyse gravitational wave signals, but it aims to provide tools which can be used for other workflows.

Asimov has been used to organise and run the major catalogue analyses from the third observing run, O3, but it's designed to be flexible enough to allow new pipelines and analyses to be added to the framework.

## Features

### Job monitoring and management

Asimov is able to interact with high throughput job management tools, and can submit jobs to clusters, monitor them for problems, and initiate post-processing tasks.

### Uniform pipeline interface

Asimov provides an API layer which allows a single configuration to be deployed to numerous different analysis pipelines.
Current gravitational wave pipelines which are supported are ``lalinference``, ``bayeswave``, ``RIFT``, and ``bilby``.

### Centralised configuration

Asimov records all ongoing, completed, and scheduled analyses, allowing jobs, configurations, and results to be found easily.

### Reporting overview

Asimov can provide both machine-readible and human-friendly reports of all jobs it is monitoring, while collating relevant log files and outputs.

### Results management

Your results are important, and Asimov provides special tools to help manage the outputs of analyses as well as ensuring their veracity.

## Do I need Asimov?

Asimov makes setting-up and running parameter estimation jobs easier.
It can generate configuration files for several parameter estimation pipelines, and handle submitting these to a cluster.
Whether you're setting-up a preliminary analysis for a single gravitational wave event, or analysing hundreds of events for a catalog, Asimov can help.

## Installing Asimov

Asimov is written in Python, and is available on ``pypi``. 
It can be installed by running
```
$ pip install asimov
```
It is also available on conda, and can be installed by running
```
$ conda install -c conda-forge asimov
```

Asimov also requires that you have `git` installed on your machine, and that you've set it up by running:
```
$ git config --global user.email "you@example.com"
$ git config --global user.name "Your Name"
```


## Get started

Asimov supports a variety of different ways of running, but the simplest way, running a workflow on a local machine, can be set up with a single command.

We start by setting up a project, which is a directory which keeps all of the analyses and the required metadata together.
A project can include just a single event or a whole selection of events, for example if you're producing a catalogue.
First create a directory to store your project:
```
$ mkdir my-new-project
$ cd my-new-project
```
and then get asimov to set things up
```
$ asimov init "Test project"
```
where you can replace `"Test project"` with the name you want to give your project.
A project will be set-up in your current working directory.

In order to start setting up analyses we next need to download some default settings.

An analysis is a pipeline run, and asimov supports `bayeswave`, `bilby` in the default installation.

We'll download the default configurations for jobs which are going to be run on the LIGO data grid.
We do this using the `asimov apply` command, which pulls-in data from a file either locally or online.

```
$ asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe.yaml
```

and the load default priors the same way:
```
$ asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe-priors.yaml
```

Now you can add an existing event, by downloading the event data settings using the `asimov apply` function, for example, to add GW150914 to the project you can run

```
$ asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/events/gwtc-2-1/GW150914_095045.yaml
```

This downloads the settings which were used for analysing GW150914 for the GWTC-2.1 catalogue paper, and stores them in the ledger file in the project (`.asimov/ledger.yml`).

Many analyses can be run on a single event (these are called "productions" in asimov parlence).
We can add some pre-configured analyses by downloading some analysis configuration settings.

```
$ asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/analyses/production-default.yaml -e GW150914_095045
```
Note that if you omit the `-e` argument asimov will ask which event the analyses should be applied to.


You can now build and submit your jobs to the cluster.
First use `asimov manage build` to create the configuration files for each analysis:
```
$ asimov manage build
```
These will be added to the git repositories in the `checkouts` directory inside the project directory.
You then submit the jobs to the cluster by running
```
$ asimov manage submit
```

It will normally take a long time for a parameter estimation job to finish, but you can get asimov to check up on it by running
```
$ asimov monitor
```
If the job is finished `asimov` will start post-processing using `PESummary`, and if it's fallen over it will attempt to fix the problem and resubmit it to the cluster.
If the post-processing has finished it will move the results to a read-only directory.

You can also set the asimov monitor to automatically check the status of the job every 15 minutes by running 
```
$ asimov start
```
which will automatically start any post-processing, and start any jobs once their dependencies are met.
You can stop this automatic monitoring process any time by running
```
$ asimov stop
```

For a full description of the workflow management process see the documentation.


## I want to help develop new features, or add a new pipeline

Great! We're always looking for help with developing asimov!
Please take a look at our [contributors' guide](CONTRIBUTING.rst) to get started!


## Roadmap

### Gravitic pipelines

While Asimov already supports a large number of pre-existing pipelines, and provides a straightforward interface for adding new pipelines, we also intend to support pipelines constructed using [gravitic](https://github.com/transientlunatic/gravitic), allowing experimental tools to be used without constructing an entire new pipeline, while also allowing asimov to manage the training of machine learning algorithms.


### Workflow replication, extension and duplication

Asimov will allow an existing workflow to be duplicated, in a similar way to a ``git clone``, and then extended, with new jobs gaining access to the completed jobs in the workflow.
It will also allow entire workflows to be re-run, providing a straightforward way to replicate results, or make minor modifications.


## Authors

Asimov is made by the LIGO, Virgo, and KAGRA collaborations.
The primary maintainer of the project is Daniel Williams.
Its development is supported by the Science and Technology Facilities Council.
