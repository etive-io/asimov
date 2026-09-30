DAG Translation Examples
========================

This page shows concrete examples of how asimov translates workflow files between
HTCondor DAG format and Slurm batch script format.  The translation happens
automatically at submission time — you never need to call these methods directly.

.. contents:: Contents
   :local:
   :depth: 2


HTCondor DAG → Slurm batch script
----------------------------------

Many pipelines (bilby, bayeswave, lalinference, …) produce HTCondor DAG files.
When you are running on a Slurm cluster, ``Slurm.submit_dag()`` (``asimov/scheduler.py``) picks
between three strategies, in order:

1. If the DAG file given to it is itself already a Slurm batch script (e.g. produced directly by
   ``bilby_pipe`` with ``scheduler=slurm``), it's submitted with ``sbatch`` as-is.
2. If an ``sbatch_submit.sh`` wrapper script exists alongside the DAG file (written by the
   pipeline's own ``build_dag()``), that wrapper is submitted instead.
3. Otherwise, asimov falls back to submitting each job in the HTCondor DAG **individually and
   directly from the Python process**, described below.

**Starting point: the HTCondor DAG file (``workflow.dag``)**

.. code-block:: text

    # HTCondor DAG for asimov gravitational-wave analysis
    JOB align    align.sub
    JOB analyse  analyse.sub
    JOB postprocess postprocess.sub

    PARENT align CHILD analyse
    PARENT analyse CHILD postprocess

Each ``JOB`` line references an HTCondor submit (``.sub``) file.
A typical submit file looks like:

.. code-block:: text

    # align.sub
    executable = /usr/bin/python3
    arguments  = align.py --input data.h5 --output aligned.h5
    output     = logs/align.out
    error      = logs/align.err
    log        = logs/align.log
    request_cpus   = 4
    request_memory = 4096
    queue

**Result: per-job wrapper scripts, submitted individually**

For each ``JOB`` line, ``_submit_dag_jobs()`` writes a wrapper script derived from that job's
``.sub`` file:

.. code-block:: bash

    # align_run.sh
    #!/bin/bash
    set -e
    cd /project && /usr/bin/python3 align.py --input data.h5 --output aligned.h5

and then submits each wrapper with its own ``sbatch`` call, made directly from the asimov Python
process (not from inside another Slurm job), in topological order, chaining dependencies with
``--dependency=afterok:``:

.. code-block:: text

    sbatch --parsable --export=ALL --output=align_%j.out --error=align_%j.err align_run.sh
    sbatch --parsable --export=ALL --output=analyse_%j.out --error=analyse_%j.err \
        --dependency=afterok:<align job id> analyse_run.sh
    sbatch --parsable --export=ALL --output=postprocess_%j.out --error=postprocess_%j.err \
        --dependency=afterok:<analyse job id> postprocess_run.sh

Key translation decisions:

* **Job order** — a topological sort ensures each job's ``sbatch`` call happens after all of its
  dependencies have already been submitted, so their job IDs are known.
* **Dependencies** — HTCondor ``PARENT align CHILD analyse`` becomes
  ``--dependency=afterok:<align job id>`` on the ``sbatch`` call for ``analyse``.
* **Commands** — the executable and arguments from each ``.sub`` file are written into that job's
  own wrapper script, rather than being inlined into an ``sbatch --wrap`` argument.
* **No orchestrator job** — unlike an earlier version of this translation, there is no single outer
  "DAG manager" Slurm job submitting the others from inside the cluster. Jobs are submitted directly
  by the asimov process, because submitting from inside a Slurm job inherits ``SLURM_ACCOUNT`` from
  the parent environment, which caused ``InvalidAccount`` failures on clusters with minimal
  accounting configuration.


Slurm batch script → HTCondor DAG
-----------------------------------

Some pipelines can write Slurm batch scripts directly.  When those are submitted
on an HTCondor cluster asimov converts them in the other direction.

**Starting point: the Slurm batch script (``workflow.sh``)**

.. code-block:: bash

    #!/bin/bash
    #SBATCH --job-name=gw-analysis
    #SBATCH --output=logs/workflow.out
    #SBATCH --error=logs/workflow.err

    declare -A job_ids

    job_ids[align]=$(sbatch --parsable --wrap "cd /data && /usr/bin/python3 align.py --input data.h5 --output aligned.h5")
    echo "Submitted align as job ${job_ids[align]}"

    job_ids[analyse]=$(sbatch --dependency=afterok:${job_ids[align]} --parsable --wrap "cd /data && /usr/bin/python3 analyse.py --input aligned.h5 --output results.json")
    echo "Submitted analyse as job ${job_ids[analyse]}"

    job_ids[postprocess]=$(sbatch --dependency=afterok:${job_ids[analyse]} --parsable --wrap "cd /data && /usr/bin/python3 postprocess.py --results results.json --output report.pdf")
    echo "Submitted postprocess as job ${job_ids[postprocess]}"

    echo 'All jobs submitted'

**Result: the generated HTCondor DAG file (``workflow_converted.dag``)**

.. code-block:: text

    # Converted from Slurm batch script: workflow.sh

    JOB align       /project/align.sub
    JOB analyse     /project/analyse.sub
    JOB postprocess /project/postprocess.sub

    PARENT align CHILD analyse
    PARENT analyse CHILD postprocess

Each job also gets its own ``.sub`` file, for example:

.. code-block:: text

    # align.sub  (generated from the --wrap command)
    executable = /bin/bash
    arguments  = -c "cd /data && /usr/bin/python3 align.py --input data.h5 --output aligned.h5"
    output     = align.out
    error      = align.err
    log        = align.log
    request_cpus   = 1
    request_memory = 1GB
    queue

Key translation decisions:

* **Dependency parsing** — ``--dependency=afterok:${job_ids[align]}`` is parsed to
  identify that ``analyse`` depends on ``align``, which becomes
  ``PARENT align CHILD analyse`` in the DAG.
* **Commands** — the ``--wrap "..."`` argument becomes the shell command wrapped by
  ``/bin/bash -c "..."`` in the ``.sub`` file.
* **Resources** — because per-job ``#SBATCH --cpus-per-task`` and ``#SBATCH --mem``
  directives are not present on the inner ``sbatch`` calls (they would normally be
  in per-job scripts), the generated ``.sub`` files use conservative defaults
  (1 CPU, 1 GB).  If the pipeline writes per-job resource constraints into the
  inner ``sbatch`` calls they will be propagated correctly.


Format auto-detection
---------------------

Both ``HTCondor.submit_dag()`` and ``Slurm.submit_dag()`` detect the file format
automatically by inspecting the first few lines of the file:

* **HTCondor DAG** — contains lines that start with ``JOB``, ``PARENT``, or
  ``CHILD``.
* **Slurm batch script** — contains ``#SBATCH`` directives or calls to ``sbatch``.

This means you can pass either file type to either scheduler and asimov will do
the right thing:

.. code-block:: python

    from asimov.scheduler import Slurm, HTCondor

    # Slurm cluster, but pipeline wrote an HTCondor DAG → auto-converted
    slurm = Slurm()
    job_id = slurm.submit_dag("workflow.dag")

    # HTCondor cluster, but pipeline wrote a Slurm script → auto-converted
    condor = HTCondor()
    job_id = condor.submit_dag("workflow.sh")

    # Both schedulers also accept their own native format without conversion:
    slurm.submit_dag("workflow.sh")   # submitted directly
    condor.submit_dag("workflow.dag") # submitted via condor_dagman
