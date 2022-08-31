# Asimov

Asimov is a workflow management and automation platform for scientific analyses.

[Documentation](https://asimov.docs.ligo.org/asimov) · [Releases](https://git.ligo.org/asimov/asimov/-/releases) · [Issue Tracker](https://git.ligo.org/asimov/asimov/-/issues)

Asimov was developed to manage and automate the parameter estimation analyses used by the LIGO, Virgo, and KAGRA collaborations to analyse gravitational wave signals, but it aims to provide tools which can be used for other workflows.

Asimov has been used to organise and run the major catalogue analyses from the third observing run, O3, but it's designed to be flexible enough to allow new pipelines and analyses to be added to the framework.

## Branch notes

These notes relate to in-development features on this branch, and what's described here is only expected to be relevant during development.
More generally useful documentation will move to the main documentation before moving to production.

### Starting the logging server

Run in ``asimov`` directory:

```
export FLASK_APP=server
flask run
```

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
$ conda install -c conda-forge ligo-asimov
```


## Get started

Asimov supports a variety of different ways of running, but the simplest way, running a workflow on a local machine, can be set up with a single command:

```
$ asimov init "Test project"
```
where you can replace `"Test project"` with the name you want to give your project.
A project will be set-up in your current working directory.

You can add an existing event with preconfigured settings using the `asimov apply` function, for example, to add GW150914 to the project you can run

```
$ asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/events/gw150914.yaml
```

Alternatively, a new event with no configured settings can be added to your project by running

```
$ asimov event create GW150914
```

Many analyses can be run on a single event (these are called "productions" in asimov parlence).
We can add some pre-configured analyses (the same set of analyses which were used for the GWTC-3 catalogue) by running

```
$ asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/analyses/gwtc3-default.yaml -e GW150914
```
Note that if you omit the `-e` argument asimov will ask which event the analyses should be applied to.

Alternatively, you can add analyses at the command line, for example you can add a new lalinference production to an event using
```
$ asimov production create GW150914 lalinference --approximant IMRPhenomPv2
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
