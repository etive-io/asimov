"""
This module contains logic for interacting with a scheduling system.

Supported Schedulers are:

- HTCondor
- Slurm
- Local (lightweight subprocess-based scheduler for short-running jobs)

"""

import os
import re
import shlex
import subprocess
import tempfile
import threading
import datetime
import yaml
import warnings
from abc import ABC, abstractmethod
from dateutil import tz

try:
    warnings.filterwarnings("ignore", module="htcondor2")
    import htcondor2 as htcondor  # NoQA
    import classad2 as classad  # NoQA
    # htcondor2 uses different exception names, create aliases for compatibility
    if not hasattr(htcondor, 'HTCondorIOError'):
        htcondor.HTCondorIOError = htcondor.HTCondorException
    if not hasattr(htcondor, 'HTCondorLocateError'):
        htcondor.HTCondorLocateError = htcondor.HTCondorException
except ImportError:
    warnings.filterwarnings("ignore", module="htcondor")
    import htcondor  # NoQA
    import classad  # NoQA

UTC = tz.tzutc()


def _datetime_from_epoch(dt, tzinfo=UTC):
    """Return a :class:`datetime.datetime` for a given Unix epoch.

    Parameters
    ----------
    dt : float
        A Unix timestamp.
    tzinfo : datetime.tzinfo, optional
        The desired timezone for the output datetime.

    Returns
    -------
    datetime.datetime
    """
    return datetime.datetime.fromtimestamp(dt, tz=datetime.timezone.utc).astimezone(tzinfo)


class Scheduler(ABC):
    """ 
    The base class which represents all supported schedulers.
    """

    @abstractmethod
    def submit(self, job_description):
        """
        Submit a job to the scheduler.
        
        Parameters
        ----------
        job_description : JobDescription or dict
            The job description to submit.
            
        Returns
        -------
        str or int
            The job ID returned by the scheduler.
        """
        raise NotImplementedError
    
    @abstractmethod
    def delete(self, job_id):
        """
        Delete a job from the scheduler.
        
        Parameters
        ----------
        job_id : str or int
            The job ID to delete.
        """
        raise NotImplementedError
    
    @abstractmethod
    def query(self, job_id=None):
        """
        Query the scheduler for job status.
        
        Parameters
        ----------
        job_id : str or int, optional
            The job ID to query. If None, query all jobs.
            
        Returns
        -------
        dict or list
            Job status information.
        """
        raise NotImplementedError
    
    @abstractmethod
    def submit_dag(self, dag_file, batch_name=None, **kwargs):
        """
        Submit a DAG (Directed Acyclic Graph) workflow to the scheduler.
        
        Parameters
        ----------
        dag_file : str
            Path to the DAG file to submit.
        batch_name : str, optional
            A name for the batch of jobs.
        **kwargs
            Additional scheduler-specific parameters.
            
        Returns
        -------
        int
            The job ID (cluster ID) returned by the scheduler.
        """
        raise NotImplementedError
    
    @abstractmethod
    def query_all_jobs(self):
        """
        Query all jobs from the scheduler.

        This method is used to get a list of all jobs currently in the scheduler
        queue, which is useful for monitoring and status checking.

        Returns
        -------
        list of dict
            A list of dictionaries, each containing job information with keys:
            - id: Job ID
            - command: Command being executed
            - hosts: Number of hosts
            - status: Job status (integer code or string)
            - name: Job name (optional)
            - dag id: Parent DAG ID if this is a subjob (optional)
        """
        raise NotImplementedError

    def _is_slurm_batch_script(self, file_path):
        """
        Return True if *file_path* looks like a Slurm batch script.

        Detects Slurm markers (``#SBATCH``, etc.) and the absence of
        HTCondor DAG markers so each scheduler can identify files
        intended for the other system.
        """
        try:
            with open(file_path) as f:
                content = "".join(f.readline() for _ in range(10))
            slurm_markers = ["#SBATCH", "sbatch", "squeue", "scancel"]
            htcondor_markers = ["JOB ", "PARENT ", "CHILD ", "SCRIPT "]
            return (
                any(m in content for m in slurm_markers)
                and not any(m in content for m in htcondor_markers)
            )
        except Exception:
            return False

    @abstractmethod
    def collect_history(self, cluster_id):
        """
        Collect history information for a completed job.

        Parameters
        ----------
        cluster_id : int
            The cluster ID of the completed job.

        Returns
        -------
        dict
            A dictionary containing job history with keys:
            - end: completion date as a ``YYYY-MM-DD`` string
            - cpus: number of CPUs provisioned
            - gpus: number of GPUs provisioned
            - runtime: effective wall-clock time in seconds
              (``RemoteWallClockTime`` minus ``CumulativeSuspensionTime``)

        Raises
        ------
        ValueError
            If no history is found for the given cluster ID.
        """
        raise NotImplementedError


class HTCondor(Scheduler):
    """
    Scheduler implementation for HTCondor.
    """

    _HISTORY_CLASSADS = [
        "CompletionDate",
        "CpusProvisioned",
        "GpusProvisioned",
        "CumulativeSuspensionTime",
        "EnteredCurrentStatus",
        "MaxHosts",
        "RemoteWallClockTime",
        "RequestCpus",
        "RequestGpus",
    ]

    def __init__(self, schedd_name=None):
        """
        Initialize the HTCondor scheduler.
        
        Parameters
        ----------
        schedd_name : str, optional
            The name of the schedd to use. If None, will try to find one automatically.
        """
        self.schedd_name = schedd_name
        self._schedd = None
    
    @property
    def schedd(self):
        """Get or create the schedd connection."""
        if self._schedd is None:
            if self.schedd_name:
                try:
                    schedulers = htcondor.Collector().locate(
                        htcondor.DaemonTypes.Schedd, self.schedd_name
                    )
                    self._schedd = htcondor.Schedd(schedulers)
                except (htcondor.HTCondorLocateError, htcondor.HTCondorIOError):
                    # Fall back to default schedd if we can't locate the named one
                    self._schedd = htcondor.Schedd()
            else:
                self._schedd = htcondor.Schedd()
        return self._schedd
    
    def submit(self, job_description):
        """
        Submit a job to the condor schedd.
        
        Parameters
        ----------
        job_description : JobDescription or dict
            The job description to submit.
            
        Returns
        -------
        int
            The cluster ID of the submitted job.
        """
        if isinstance(job_description, htcondor.Submit):
            submit_obj = job_description
        elif isinstance(job_description, JobDescription):
            submit_obj = htcondor.Submit(job_description.to_htcondor())
        else:
            submit_obj = htcondor.Submit(job_description)
        
        # Submit the job
        try:
            result = self.schedd.submit(submit_obj)
            cluster_id = result.cluster()
            return cluster_id
        except htcondor.HTCondorIOError as e:
            raise RuntimeError(f"Failed to submit job to HTCondor: {e}")
    
    def delete(self, job_id):
        """
        Delete a job from the HTCondor scheduler.
        
        Parameters
        ----------
        job_id : int
            The cluster ID to delete.
        """
        self.schedd.act(htcondor.JobAction.Remove, f"ClusterId == {job_id}")
    
    def query(self, job_id=None, projection=None):
        """
        Query the HTCondor scheduler for job status.
        
        Parameters
        ----------
        job_id : int, optional
            The cluster ID to query. If None, query all jobs.
        projection : list, optional
            List of attributes to retrieve.
            
        Returns
        -------
        list
            List of job ClassAds.
        """
        if job_id is not None:
            constraint = f"ClusterId == {job_id}"
        else:
            constraint = None
            
        if projection:
            return list(self.schedd.query(constraint=constraint, projection=projection))
        else:
            return list(self.schedd.query(constraint=constraint))
    
    def submit_dag(self, dag_file, batch_name=None, **kwargs):
        """
        Submit a DAG file to the HTCondor scheduler.
        
        This method can handle both HTCondor DAG files and Slurm-style batch scripts.
        If a Slurm-style script is detected, it will be converted to HTCondor DAG format.
        
        Parameters
        ----------
        dag_file : str
            Path to the DAG submit file (HTCondor or Slurm format).
        batch_name : str, optional
            A name for the batch of jobs.
        **kwargs
            Additional HTCondor-specific parameters.
            
        Returns
        -------
        int
            The cluster ID of the submitted DAG.
            
        Raises
        ------
        RuntimeError
            If the DAG submission fails.
        FileNotFoundError
            If the DAG file does not exist.
        """
        if not os.path.exists(dag_file):
            raise FileNotFoundError(f"DAG file not found: {dag_file}")
        
        # Check if this is a Slurm-style batch script
        if self._is_slurm_batch_script(dag_file):
            # Convert Slurm batch script to HTCondor DAG
            dag_file = self._convert_slurm_to_dag(dag_file, batch_name, **kwargs)
        
        try:
            # Use HTCondor's Submit.from_dag to create a submit description from the DAG file
            submit_obj = htcondor.Submit.from_dag(dag_file, options={})
            
            # Add batch name if provided
            if batch_name:
                # Set the batch name in the submit description
                submit_obj['JobBatchName'] = batch_name
            
            # Add any additional kwargs to the submit description
            for key, value in kwargs.items():
                submit_obj[key] = value
            
            # Submit the DAG
            result = self.schedd.submit(submit_obj)
            cluster_id = result.cluster()
            
            return cluster_id
            
        except htcondor.HTCondorIOError as e:
            raise RuntimeError(f"Failed to submit DAG to HTCondor: {e}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error submitting DAG: {e}")
    
    def _convert_slurm_to_dag(self, slurm_file, batch_name=None, **kwargs):
        """
        Convert a Slurm batch script to an HTCondor DAG file.
        
        This is a simplified conversion that handles basic Slurm batch scripts.
        
        Parameters
        ----------
        slurm_file : str
            Path to the Slurm batch script.
        batch_name : str, optional
            Name for the batch job.
        **kwargs
            Additional parameters.
            
        Returns
        -------
        str
            Path to the generated HTCondor DAG file.
        """
        slurm_dir = os.path.dirname(os.path.abspath(slurm_file))
        
        # Parse the Slurm script to extract job submissions
        jobs = []
        dependencies = {}
        
        with open(slurm_file, 'r') as f:
            content = f.read()
            
            # Find sbatch commands with dependency tracking
            # Pattern: job_id=$(sbatch [--dependency=afterok:$dep_id] --parsable --wrap "command")
            sbatch_pattern = r'job_ids?\[(\w+)\]=\$\(sbatch\s+(.*?)--wrap\s+"([^"]+)"\)'
            
            for match in re.finditer(sbatch_pattern, content, re.MULTILINE | re.DOTALL):
                job_name = match.group(1)
                sbatch_args = match.group(2)
                command = match.group(3)
                
                jobs.append({
                    'name': job_name,
                    'command': command,
                    'args': sbatch_args
                })
                
                # Extract dependencies
                dep_pattern = r'--dependency=afterok:\$\{job_ids\[(\w+)\]\}'
                dep_matches = re.findall(dep_pattern, sbatch_args)
                if dep_matches:
                    dependencies[job_name] = dep_matches
        
        # Create HTCondor DAG file
        dag_lines = []
        dag_lines.append(f"# Converted from Slurm batch script: {os.path.basename(slurm_file)}")
        dag_lines.append("")
        
        # Create submit files for each job
        submit_files = {}
        for job in jobs:
            job_name = job['name']
            command = job['command']
            
            # Create a submit file for this job
            submit_file = os.path.join(slurm_dir, f"{job_name}.sub")
            with open(submit_file, 'w') as f:
                f.write(f"# Submit file for {job_name}\n")
                f.write(f"executable = /bin/bash\n")
                f.write(f'arguments = -c "{command}"\n')
                f.write(f"output = {job_name}.out\n")
                f.write(f"error = {job_name}.err\n")
                f.write(f"log = {job_name}.log\n")
                f.write(f"request_cpus = 1\n")
                f.write(f"request_memory = 1GB\n")
                f.write(f"queue\n")
            
            submit_files[job_name] = submit_file
            dag_lines.append(f"JOB {job_name} {submit_file}")
        
        dag_lines.append("")
        
        # Add dependencies
        for child, parents in dependencies.items():
            for parent in parents:
                dag_lines.append(f"PARENT {parent} CHILD {child}")
        
        # Write the DAG file
        dag_file = os.path.join(slurm_dir, f"{os.path.splitext(os.path.basename(slurm_file))[0]}_converted.dag")
        with open(dag_file, 'w') as f:
            f.write('\n'.join(dag_lines) + '\n')
        
        return dag_file
    
    def query_all_jobs(self):
        """
        Query all jobs from HTCondor schedulers.
        
        This method queries all available HTCondor schedulers to get a complete
        list of jobs. It's used by the JobList class for monitoring.
        
        Returns
        -------
        list of dict
            A list of dictionaries containing job information.
        """
        data = []
        
        try:
            collectors = htcondor.Collector().locateAll(htcondor.DaemonTypes.Schedd)
        except htcondor.HTCondorLocateError as e:
            raise RuntimeError(f"Could not find a valid HTCondor scheduler: {e}")
        
        for schedd_ad in collectors:
            try:
                schedd = htcondor.Schedd(schedd_ad)
                jobs = schedd.query(
                    opts=htcondor.QueryOpts.DefaultMyJobsOnly,
                    projection=[
                        "ClusterId",
                        "Cmd",
                        "CurrentHosts",
                        "HoldReason",
                        "JobStatus",
                        "DAG_Status",
                        "JobBatchName",
                        "DAGManJobId",
                    ],
                )
                
                # Convert HTCondor ClassAds to dictionaries
                for job_ad in jobs:
                    if "ClusterId" in job_ad:
                        job_dict = {
                            "id": int(float(job_ad["ClusterId"])),
                            "command": job_ad.get("Cmd", ""),
                            "hosts": job_ad.get("CurrentHosts", 0),
                            "status": job_ad.get("JobStatus", 0),
                        }
                        
                        if "HoldReason" in job_ad:
                            job_dict["hold"] = job_ad["HoldReason"]
                        if "JobBatchName" in job_ad:
                            job_dict["name"] = job_ad["JobBatchName"]
                        if "DAG_Status" not in job_ad and "DAGManJobId" in job_ad:
                            job_dict["dag id"] = int(float(job_ad["DAGManJobId"]))
                        
                        data.append(job_dict)
                        
            except Exception:
                # Skip problematic schedulers
                pass
        
        return data

    def collect_history(self, cluster_id):
        """
        Collect history information for a completed HTCondor job.

        The method first tries the configured schedd; if no history is found
        there it searches all available schedds.

        Parameters
        ----------
        cluster_id : int
            The cluster ID of the completed job.

        Returns
        -------
        dict
            A dictionary with keys:
            - ``end``: completion date as a ``YYYY-MM-DD`` string
            - ``cpus``: number of CPUs provisioned
            - ``gpus``: number of GPUs provisioned
            - ``runtime``: effective wall-clock time in seconds

        Raises
        ------
        ValueError
            If no history record is found for *cluster_id*.
        """
        constraint = f"ClusterId == {cluster_id}"

        # First try the configured schedd
        try:
            jobs = list(self.schedd.history(constraint, projection=self._HISTORY_CLASSADS))
        except Exception:
            jobs = []

        # If nothing found, search all available schedds
        if not jobs:
            try:
                collectors = htcondor.Collector().locateAll(htcondor.DaemonTypes.Schedd)
            except htcondor.HTCondorLocateError:
                collectors = []

            for collector in collectors:
                try:
                    schedd = htcondor.Schedd(collector)
                    jobs = list(schedd.history(constraint, projection=self._HISTORY_CLASSADS))
                    if jobs:
                        break
                except htcondor.HTCondorIOError:
                    continue

        if not jobs:
            raise ValueError(
                f"No history found for cluster ID {cluster_id}"
            )

        # For a DAG cluster there may be multiple subjob records; use the first
        # one returned, which is the summary/parent record for the cluster.
        job = jobs[0]

        end = float(job.get("CompletionDate", 0)) or float(
            job.get("EnteredCurrentStatus", 0)
        )
        end_str = _datetime_from_epoch(end).strftime("%Y-%m-%d") if end else ""

        try:
            cpus = float(job["CpusProvisioned"])
        except (KeyError, ValueError):
            cpus = float(job.get("RequestCpus", 1))
        try:
            gpus = float(job["GpusProvisioned"])
        except (KeyError, ValueError):
            gpus = float(job.get("RequestGpus", 0))

        runtime = float(job.get("RemoteWallClockTime", 0)) - float(
            job.get("CumulativeSuspensionTime", 0)
        )

        return {"end": end_str, "cpus": cpus, "gpus": gpus, "runtime": runtime}


class Slurm(Scheduler):
    """
    Scheduler implementation for Slurm (sbatch/squeue/scancel).
    """

    # Map Slurm state codes to HTCondor-compatible integer status codes so the
    # rest of asimov's monitoring machinery can interpret them uniformly.
    _STATE_MAP = {
        "PD": 1,   # Pending  → Idle
        "R":  2,   # Running  → Running
        "CA": 3,   # Cancelled → Removed
        "CD": 4,   # Completed → Completed
        "CG": 2,   # Completing → Running
        "F":  5,   # Failed   → Held
        "TO": 5,   # Timeout  → Held
        "OOM": 5,  # Out of memory → Held
        "NF": 5,   # Node Fail → Held
    }

    def __init__(self, user=None, partition=None):
        self.user = user or os.environ.get("USER", "")
        self.partition = partition

    def submit(self, script_file_or_description):
        """
        Submit a job to Slurm.

        Accepts either a path to an sbatch script (str) or a
        ``JobDescription`` / dict, in which case a temporary batch script
        is generated from ``_create_batch_script`` before submission.

        Returns the integer Slurm job ID.
        """
        if isinstance(script_file_or_description, (JobDescription, dict)):
            submit_dict = (
                script_file_or_description.to_slurm()
                if isinstance(script_file_or_description, JobDescription)
                else script_file_or_description
            )
            script_content = self._create_batch_script(submit_dict)
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".sh", delete=False
            ) as f:
                f.write(script_content)
                script_path = f.name
            try:
                return self._sbatch(script_path)
            finally:
                try:
                    os.unlink(script_path)
                except OSError:
                    pass
        else:
            return self._sbatch(script_file_or_description)

    def _sbatch(self, script_path):
        """Run sbatch on *script_path* and return the integer job ID."""
        try:
            result = subprocess.run(
                ["sbatch", script_path],
                capture_output=True, text=True, check=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"sbatch failed (exit {e.returncode}): {e.stderr.strip()}"
            ) from e
        match = re.search(r"Submitted batch job (\d+)", result.stdout)
        if not match:
            raise RuntimeError(
                f"Could not parse job ID from sbatch output: {result.stdout}"
            )
        return int(match.group(1))


    def _create_batch_script(self, submit_dict):
        """Build a Slurm batch script string from a submit dictionary."""
        lines = ["#!/bin/bash"]
        if self.partition:
            lines.append(f"#SBATCH --partition={self.partition}")
        job_name = submit_dict.get("job_name") or submit_dict.get("batch_name")
        if job_name:
            # Slurm job names must not contain whitespace or slashes
            safe_name = re.sub(r"[\s/]+", "_", str(job_name))
            lines.append(f"#SBATCH --job-name={safe_name}")
        for key in ("output", "error"):
            if key in submit_dict:
                lines.append(f"#SBATCH --{'output' if key == 'output' else 'error'}={submit_dict[key]}")
        if "cpus" in submit_dict:
            lines.append(f"#SBATCH --cpus-per-task={submit_dict['cpus']}")
        if "memory" in submit_dict:
            mem = submit_dict["memory"]
            if isinstance(mem, str):
                if mem.endswith("GB"):
                    mem = int(mem[:-2]) * 1024
                elif mem.endswith("MB"):
                    mem = int(mem[:-2])
                else:
                    raise ValueError(
                        f"Unrecognised memory unit in {mem!r}. Use 'MB' or 'GB'."
                    )
            lines.append(f"#SBATCH --mem={mem}")
        if "time" in submit_dict:
            lines.append(f"#SBATCH --time={submit_dict['time']}")
        for key, value in submit_dict.items():
            if key.startswith("slurm_"):
                slurm_key = key[len("slurm_"):].replace("_", "-")
                lines.append(f"#SBATCH --{slurm_key}={value}")
        if submit_dict.get("getenv"):
            lines.append("#SBATCH --export=ALL")
        lines.append("")
        if "executable" in submit_dict:
            cmd = submit_dict["executable"]
            if "arguments" in submit_dict:
                cmd += f" {submit_dict['arguments']}"
            lines.append(cmd)
        return "\n".join(lines) + "\n"

    def delete(self, job_id):
        """Cancel a Slurm job."""
        try:
            subprocess.run(
                ["scancel", str(job_id)],
                capture_output=True, text=True, check=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to cancel Slurm job {job_id}: {e.stderr}")

    def query(self, job_id=None, projection=None):
        """Return squeue output for one job (or all jobs) as a list of dicts.

        Note: the ``projection`` parameter is accepted for API compatibility
        with HTCondor but is not used; squeue always returns a fixed field set.
        """
        cmd = [
            "squeue", "--format=%i|%j|%t|%N", "--noheader",
            "--user", self.user or os.environ.get("USER", ""),
        ]

        if job_id is not None:
            cmd += ["--job", str(job_id)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError:
            return []
        jobs = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("|")
            if len(parts) >= 4:
                jobs.append({
                    "JobId": parts[0],
                    "JobName": parts[1],
                    "State": parts[2],
                    "NodeList": parts[3],
                })
        return jobs

    def submit_dag(self, dag_file, batch_name=None, **kwargs):
        """
        Submit a DAG to Slurm.

        Prefers an ``sbatch_submit.sh`` file alongside *dag_file* (written by
        ``build_dag()``).  Falls back to converting the HTCondor DAG file to a
        Slurm orchestrator script when no wrapper script is present.
        """
        if not os.path.exists(dag_file):
            raise FileNotFoundError(f"DAG file not found: {dag_file}")

        # If dag_file is already a Slurm batch script (e.g. produced by
        # bilby_pipe with scheduler=slurm), submit it directly.
        if self._is_slurm_batch_script(dag_file):
            return self._sbatch(dag_file)

        wrapper = os.path.join(os.path.dirname(dag_file), "sbatch_submit.sh")
        if os.path.exists(wrapper):
            return self._sbatch(wrapper)

        # Fall back: submit HTCondor DAG jobs directly from Python.
        # Submitting from inside a Slurm job (orchestrator approach) inherits
        # SLURM_ACCOUNT from the parent environment which causes InvalidAccount
        # failures on clusters that don't recognise that account.
        return self._submit_dag_jobs(dag_file)

    def _submit_dag_jobs(self, dag_file):
        """
        Submit all jobs in an HTCondor DAG file directly via sbatch.

        Jobs are submitted from the current Python process in topological order
        with ``--dependency=afterok:`` chaining.  This avoids the orchestrator
        job approach where inner ``sbatch`` calls inherit ``SLURM_ACCOUNT`` from
        the parent Slurm environment, causing ``InvalidAccount`` failures on
        clusters with minimal accounting configuration.

        Returns the job ID of the last submitted job.
        """
        dag_dir = os.path.dirname(os.path.abspath(dag_file))
        jobs = {}
        dependencies = {}
        dag_vars = {}  # job_name -> {macro: value} from VARS lines

        with open(dag_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("JOB"):
                    parts = line.split()
                    if len(parts) >= 3:
                        job_name, submit_file = parts[1], parts[2]
                        job_dir = dag_dir
                        if "DIR" in parts:
                            idx = parts.index("DIR")
                            if idx + 1 < len(parts):
                                job_dir = parts[idx + 1]
                                if not os.path.isabs(job_dir):
                                    job_dir = os.path.join(dag_dir, job_dir)
                        if not os.path.isabs(submit_file):
                            submit_file = os.path.join(job_dir, submit_file)
                        jobs[job_name] = {"submit_file": submit_file, "dir": job_dir}
                elif line.upper().startswith("VARS"):
                    # VARS jobname macroname="value" macroname2="value2" ...
                    parts = line.split(None, 2)
                    if len(parts) >= 3:
                        var_job = parts[1]
                        var_str = parts[2]
                        job_macros = {}
                        for m in re.finditer(r'(\w+)\s*=\s*"([^"]*)"', var_str):
                            job_macros[m.group(1).lower()] = m.group(2)
                        dag_vars.setdefault(var_job, {}).update(job_macros)
                elif line.startswith("PARENT"):
                    parts = line.split()
                    if "CHILD" in parts:
                        child_idx = parts.index("CHILD")
                        parents = parts[1:child_idx]
                        children = parts[child_idx + 1:]
                        for child in children:
                            for parent in parents:
                                dependencies.setdefault(child, []).append(parent)

        for job_name, info in jobs.items():
            wrapper_path = os.path.join(dag_dir, f"{job_name}_run.sh")
            if os.path.exists(info["submit_file"]):
                cmd, mem_mb = self._parse_submit_file_for_slurm(
                    info["submit_file"], info["dir"],
                    extra_macros=dag_vars.get(job_name, {}),
                )
            else:
                cmd = f"echo 'submit file not found for {job_name}'"
                mem_mb = None
            with open(wrapper_path, "w") as wf:
                wf.write("#!/bin/bash\n")
                wf.write("set -e\n")
                wf.write(f"{cmd}\n")
            os.chmod(wrapper_path, 0o755)
            info["wrapper"] = wrapper_path
            info["mem_mb"] = mem_mb

        job_ids = {}
        last_id = None
        for job_name in self._topological_sort(list(jobs.keys()), dependencies):
            info = jobs[job_name]
            out_path = os.path.join(dag_dir, f"{job_name}_%j.out")
            err_path = os.path.join(dag_dir, f"{job_name}_%j.err")
            args = ["sbatch", "--parsable", "--export=ALL",
                    f"--output={out_path}", f"--error={err_path}"]
            if self.partition:
                args += ["--partition", self.partition]
            if info.get("mem_mb"):
                args += [f"--mem={info['mem_mb']}M"]
            if job_name in dependencies:
                dep_str = ":".join(str(job_ids[d]) for d in dependencies[job_name])
                args.append(f"--dependency=afterok:{dep_str}")
            args.append(info.get("wrapper", "/dev/null"))
            result = subprocess.run(args, capture_output=True, text=True, check=True)
            last_id = int(result.stdout.strip())
            job_ids[job_name] = last_id

        return last_id or 0

    def _convert_dag_to_slurm(self, dag_file, batch_name=None, **kwargs):
        """
        Convert an HTCondor DAG file to a Slurm orchestrator batch script.

        A per-job wrapper ``.sh`` file is written for each DAG job so that
        commands are never embedded into the orchestrator via ``--wrap``.
        The orchestrator submits each wrapper with ``sbatch --parsable``
        in topological order, using bash associative arrays to track IDs.
        """
        dag_dir = os.path.dirname(os.path.abspath(dag_file))
        jobs = {}
        dependencies = {}

        with open(dag_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("JOB"):
                    parts = line.split()
                    if len(parts) >= 3:
                        job_name, submit_file = parts[1], parts[2]
                        job_dir = dag_dir
                        if "DIR" in parts:
                            idx = parts.index("DIR")
                            if idx + 1 < len(parts):
                                job_dir = parts[idx + 1]
                                if not os.path.isabs(job_dir):
                                    job_dir = os.path.join(dag_dir, job_dir)
                        if not os.path.isabs(submit_file):
                            submit_file = os.path.join(job_dir, submit_file)
                        jobs[job_name] = {"submit_file": submit_file, "dir": job_dir}
                elif line.startswith("PARENT"):
                    parts = line.split()
                    if "CHILD" in parts:
                        child_idx = parts.index("CHILD")
                        parents = parts[1:child_idx]
                        children = parts[child_idx + 1:]
                        for child in children:
                            for parent in parents:
                                dependencies.setdefault(child, []).append(parent)

        # Write a per-job wrapper script for each DAG job.
        for job_name, info in jobs.items():
            wrapper_path = os.path.join(dag_dir, f"{job_name}_run.sh")
            if os.path.exists(info["submit_file"]):
                cmd, _ = self._parse_submit_file_for_slurm(info["submit_file"], info["dir"])
            else:
                cmd = f"echo 'submit file not found for {job_name}'"
            with open(wrapper_path, "w") as wf:
                wf.write("#!/bin/bash\n")
                wf.write(f"{cmd}\n")
            os.chmod(wrapper_path, 0o755)
            info["wrapper"] = wrapper_path

        dag_base = os.path.splitext(os.path.basename(dag_file))[0]
        lines = [
            "#!/bin/bash",
            f"#SBATCH --job-name={batch_name or 'asimov-dag'}",
            f"#SBATCH --output={os.path.join(dag_dir, dag_base)}.out",
            f"#SBATCH --error={os.path.join(dag_dir, dag_base)}.err",
            "#SBATCH --cpus-per-task=1",
            "#SBATCH --mem=1GB",
            "",
            "declare -A job_ids",
            "",
        ]
        partition_flag = f"--partition={self.partition} " if self.partition else ""
        for job_name in self._topological_sort(list(jobs.keys()), dependencies):
            info = jobs[job_name]
            wrapper = shlex.quote(info.get("wrapper", "/dev/null"))
            if job_name in dependencies:
                dep_str = ":".join(
                    f"${{job_ids[{d}]}}" for d in dependencies[job_name]
                )
                lines.append(
                    f'job_ids[{job_name}]=$(sbatch {partition_flag}--dependency=afterok:{dep_str} --parsable {wrapper})'
                )
            else:
                lines.append(
                    f'job_ids[{job_name}]=$(sbatch {partition_flag}--parsable {wrapper})'
                )
            lines.append(f'echo "Submitted {job_name} as job ${{job_ids[{job_name}]}}"')
            lines.append("")
        lines.append("echo 'All jobs submitted'")
        return "\n".join(lines) + "\n"

    def _topological_sort(self, jobs, dependencies):
        """Kahn's algorithm; raises RuntimeError on cycles."""
        from collections import deque
        adj = {j: [] for j in jobs}
        in_degree = {j: 0 for j in jobs}
        for child, parents in dependencies.items():
            for parent in parents:
                if parent in adj:
                    adj[parent].append(child)
                    in_degree[child] += 1
        queue = deque(j for j in jobs if in_degree[j] == 0)
        result = []
        while queue:
            job = queue.popleft()
            result.append(job)
            for child in adj[job]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)
        if len(result) != len(jobs):
            raise RuntimeError("Circular dependency detected in DAG")
        return result

    # HTCondor directives that are NOT macro definitions
    _CONDOR_DIRECTIVES = frozenset({
        "executable", "arguments", "output", "error", "log", "universe",
        "getenv", "environment", "request_memory", "request_cpus",
        "request_disk", "queue", "accounting_group", "accounting_group_user",
        "notification", "should_transfer_files", "transfer_input_files",
        "transfer_output_files", "when_to_transfer_output",
        "on_exit_remove", "on_exit_hold", "periodic_remove", "periodic_hold",
        "checkpoint", "stream_output", "stream_error", "priority",
        "rank", "requirements", "concurrency_limits", "batch_name",
        "hold", "hold_reason",
    })

    def _parse_submit_file_for_slurm(self, submit_file, job_dir, extra_macros=None):
        """Extract command and resource requests from an HTCondor submit file.

        Returns a tuple of (cmd_string, mem_mb) where mem_mb is an int or None.

        HTCondor macros are resolved from two sources, with ``extra_macros``
        (from the DAG file's ``VARS`` lines) taking precedence over macro
        definitions embedded in the submit file itself.
        """
        executable = arguments = None
        request_memory = None
        macros = {}

        with open(submit_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key_lower = key.strip().lower()
                value = value.strip()

                if key_lower == "executable":
                    executable = value
                elif key_lower == "arguments":
                    arguments = value.strip('"\'')
                elif key_lower == "request_memory":
                    try:
                        request_memory = int(value.split()[0])
                    except (ValueError, IndexError):
                        pass
                elif key_lower not in self._CONDOR_DIRECTIVES:
                    macros[key_lower] = value

        # DAG VARS take precedence over inline submit-file macros
        if extra_macros:
            macros.update({k.lower(): v for k, v in extra_macros.items()})

        # Expand HTCondor $(macroname) references in arguments
        if arguments and macros:
            arguments = re.sub(
                r'\$\(([^)]+)\)',
                lambda m: macros.get(m.group(1).lower(), m.group(0)),
                arguments,
            )

        quoted_dir = shlex.quote(job_dir)
        if not executable:
            return (f"cd {quoted_dir} && echo 'No executable found in submit file'", None)
        if not os.path.isabs(executable):
            executable = os.path.join(job_dir, executable)
        quoted_exe = shlex.quote(executable)
        if arguments:
            try:
                arg_tokens = shlex.split(arguments)
                quoted_args = " ".join(shlex.quote(a) for a in arg_tokens)
            except ValueError:
                quoted_args = shlex.quote(arguments)
            return (f"cd {quoted_dir} && {quoted_exe} {quoted_args}", request_memory)
        return (f"cd {quoted_dir} && {quoted_exe}", request_memory)

    def query_all_jobs(self):
        """Return all running jobs for the configured user as a list of dicts."""
        args = ["squeue", "--format=%i|%j|%t|%C", "-h"]
        if self.user:
            args += ["-u", self.user]
        try:
            result = subprocess.run(args, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"squeue failed: {e.stderr.strip()}") from e
        data = []
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            parts = line.split("|")
            if len(parts) < 4:
                continue
            job_id, name, state, cpus = parts[:4]
            try:
                data.append({
                    "id": int(job_id),
                    "command": "",
                    "hosts": int(cpus) if cpus.isdigit() else 0,
                    "status": self._STATE_MAP.get(state, 0),
                    "name": name,
                })
            except ValueError:
                continue
        return data

    def collect_history(self, cluster_id):
        """Collect history for a Slurm job (not yet implemented)."""
        raise NotImplementedError("Slurm history collection is not yet implemented")


class LocalProcessScheduler(Scheduler):
    """
    A lightweight scheduler that runs jobs as local subprocesses.

    This scheduler is designed for jobs that complete quickly (seconds),
    where the overhead of submitting to a cluster scheduler (HTCondor, Slurm)
    exceeds the actual job runtime.  Jobs are launched as background
    subprocesses on the machine running asimov and are tracked by their
    operating-system process ID (PID).

    Notes
    -----
    The ``log`` field of a :class:`JobDescription` is not used by this
    scheduler; only ``output`` (stdout) and ``error`` (stderr) are redirected.

    Security note: the ``executable`` field is passed directly to the OS
    without further sanitisation.  Only trusted, application-constructed
    :class:`JobDescription` objects should be submitted.
    """

    def __init__(self):
        """Initialize the local process scheduler."""
        self._processes = {}  # pid -> {"process": Popen, "command": str, "name": str}
        self._lock = threading.Lock()

    def wait_for_job(self, job_id):
        """
        Block until the process identified by *job_id* has exited.

        Parameters
        ----------
        job_id : int
            The PID returned by :meth:`submit`.

        Returns
        -------
        int or None
            The process exit code, or ``None`` if the job is not tracked.
        """
        with self._lock:
            info = self._processes.get(job_id)
        if info is None:
            return None
        return info["process"].wait()

    # ------------------------------------------------------------------
    # Scheduler interface
    # ------------------------------------------------------------------

    def submit(self, job_description):
        """
        Run a job as a local background subprocess.

        Parameters
        ----------
        job_description : JobDescription or dict
            The job description to submit.  At minimum the description must
            supply an ``executable``.  The optional keys ``arguments``,
            ``output``, and ``error`` are also recognised.  The ``log`` key
            is accepted but ignored (not applicable to local subprocesses).
            Arguments are parsed with :func:`shlex.split` so quoted strings
            and paths that contain spaces are handled correctly.

        Returns
        -------
        int
            The process ID (PID) of the launched subprocess.

        Raises
        ------
        RuntimeError
            If the subprocess cannot be started.
        """
        if isinstance(job_description, JobDescription):
            executable = job_description.executable
            arguments = job_description.kwargs.get("arguments", "")
            output_file = job_description.output
            error_file = job_description.error
            name = job_description.kwargs.get(
                "batch_name", job_description.kwargs.get("name", "asimov job")
            )
        else:
            executable = job_description.get("executable")
            arguments = job_description.get("arguments", "")
            output_file = job_description.get("output")
            error_file = job_description.get("error")
            name = job_description.get(
                "batch_name", job_description.get("name", "asimov job")
            )

        if not executable:
            raise RuntimeError("No executable specified in job description")

        if arguments:
            if isinstance(arguments, str):
                command = [executable] + shlex.split(arguments)
            else:
                command = [executable] + list(arguments)
        else:
            command = [executable]

        # Open file handles before forking so that any IOError surfaces here
        # rather than being silently lost inside Popen.
        stdout_handle = open(output_file, "w") if output_file else subprocess.DEVNULL
        try:
            stderr_handle = (
                open(error_file, "w") if error_file else subprocess.DEVNULL
            )
        except OSError:
            # `open()` and all subclasses of OSError (including PermissionError) are caught.
            if stdout_handle is not subprocess.DEVNULL:
                stdout_handle.close()
            raise

        try:
            proc = subprocess.Popen(command, stdout=stdout_handle, stderr=stderr_handle)
        except OSError as exc:
            raise RuntimeError(
                f"Failed to start local process '{executable}': {exc}"
            ) from exc
        finally:
            # Close parent-side handles; the child process has inherited its own
            # file descriptors and will continue writing after these are closed.
            if stdout_handle is not subprocess.DEVNULL:
                stdout_handle.close()
            if stderr_handle is not subprocess.DEVNULL:
                stderr_handle.close()

        with self._lock:
            self._processes[proc.pid] = {
                "process": proc,
                "command": " ".join(command),
                "name": name,
            }
        return proc.pid

    def delete(self, job_id):
        """
        Terminate a running local process.

        Parameters
        ----------
        job_id : int
            The PID of the process to terminate.  Only PIDs that were
            returned by :meth:`submit` on *this* scheduler instance are
            acted upon; unknown PIDs are ignored with a warning to avoid
            accidentally killing unrelated OS processes.
        """
        with self._lock:
            info = self._processes.pop(job_id, None)

        if info is None:
            warnings.warn(
                f"LocalProcessScheduler.delete called with unknown job_id {job_id}; "
                "no process was terminated.",
                RuntimeWarning,
                stacklevel=2,
            )
            return

        proc = info["process"]
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
                proc.wait()
            except (ProcessLookupError, PermissionError):
                # ProcessLookupError: process exited between kill() and wait().
                # PermissionError: insufficient privileges (should not normally occur).
                pass
        except (ProcessLookupError, PermissionError):
            # Process already exited before terminate() was called.
            pass

    def query(self, job_id=None):
        """
        Query the status of one or all managed local processes.

        Parameters
        ----------
        job_id : int, optional
            The PID to query.  If *None*, all tracked processes are returned.
            If the PID is not known to this scheduler instance, an empty list
            is returned.

        Returns
        -------
        list of dict
            Each dictionary contains ``id``, ``command``, ``hosts``,
            ``status``, and ``name`` keys compatible with :class:`JobList`.
            Completed processes are removed from internal tracking after
            being reported.
        """
        with self._lock:
            pids = [job_id] if job_id is not None else list(self._processes.keys())

        results = []
        completed_pids = []

        for pid in pids:
            with self._lock:
                proc_info = self._processes.get(pid)
            if proc_info is None:
                continue
            poll = proc_info["process"].poll()
            if poll is None:
                status = "running"
            elif poll == 0:
                status = "completed"
                completed_pids.append(pid)
            else:
                status = f"error (exit {poll})"
                completed_pids.append(pid)
            results.append(
                {
                    "id": pid,
                    "command": proc_info["command"],
                    "hosts": 1,
                    "status": status,
                    "name": proc_info.get("name", "asimov job"),
                }
            )

        # Remove completed processes to prevent memory leaks and zombie accumulation.
        with self._lock:
            for pid in completed_pids:
                self._processes.pop(pid, None)

        return results

    def submit_dag(self, dag_file, batch_name=None, **kwargs):
        """Not supported for the local process scheduler."""
        raise NotImplementedError(
            "LocalProcessScheduler does not support DAG submission. "
            "Use submit() with a shell script instead."
        )

    def query_all_jobs(self):
        """
        Return status information for all tracked local processes.

        Returns
        -------
        list of dict
            A list of dictionaries with job information, compatible with
            :class:`JobList`.
        """
        return self.query()

    def collect_history(self, cluster_id):
        """Collect history for a Slurm job."""
        raise NotImplementedError("Slurm scheduler is not yet implemented")


class Job:
    """
    Scheduler-agnostic representation of a job.
    
    This class provides a common interface for job information across
    different schedulers.
    """
    
    def __init__(self, job_id, command, hosts, status, name=None, dag_id=None, **kwargs):
        """
        Create a Job object.
        
        Parameters
        ----------
        job_id : int
            The job ID or cluster ID.
        command : str
            The command being run.
        hosts : int
            The number of hosts currently processing the job.
        status : int or str
            The status of the job.
        name : str, optional
            The name or batch name of the job.
        dag_id : int, optional
            The DAG ID if this is a subjob.
        **kwargs
            Additional scheduler-specific attributes.
        """
        self.job_id = job_id
        self.command = command
        self.hosts = hosts
        self._status = status
        self.name = name or "asimov job"
        self.dag_id = dag_id
        self.subjobs = []
        
        # Store any additional attributes
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def add_subjob(self, job):
        """
        Add a subjob to this job.
        
        Parameters
        ----------
        job : Job
            The subjob to add.
        """
        self.subjobs.append(job)
    
    @property
    def status(self):
        """
        Get the status of the job as a string.
        
        Returns
        -------
        str
            A description of the status of the job.
        """
        # Handle both integer status codes and string status
        if isinstance(self._status, int):
            # HTCondor status codes
            statuses = {
                0: "Unexplained",
                1: "Idle",
                2: "Running",
                3: "Removed",
                4: "Completed",
                5: "Held",
                6: "Submission error",
            }
            return statuses.get(self._status, "Unknown")
        else:
            return str(self._status)
    
    def __repr__(self):
        return f"<Job | {self.job_id} | {self.status} | {self.hosts} | {self.name} | {len(self.subjobs)} subjobs>"
    
    def __str__(self):
        return repr(self)
    
    def to_dict(self):
        """
        Convert the job to a dictionary representation.
        
        Returns
        -------
        dict
            Dictionary representation of the job.
        """
        output = {
            "name": self.name,
            "id": self.job_id,
            "hosts": self.hosts,
            "status": self._status,
            "command": self.command,
        }
        
        if self.dag_id:
            output["dag_id"] = self.dag_id
        
        return output


class JobList:
    """
    Scheduler-agnostic list of running jobs.
    
    This class queries the scheduler and caches the results for performance.
    """
    
    def __init__(self, scheduler, cache_file=None, cache_time=900):
        """
        Initialize the job list.
        
        Parameters
        ----------
        scheduler : Scheduler
            The scheduler instance to query.
        cache_file : str, optional
            Path to the cache file. If None, uses ".asimov/_cache_jobs.yaml"
        cache_time : int, optional
            Maximum age of cache in seconds. Default is 900 (15 minutes).
        """
        self.scheduler = scheduler
        self.jobs = {}
        self.cache_file = cache_file or os.path.join(".asimov", "_cache_jobs.yaml")
        self.cache_time = cache_time
        
        # Try to load from cache
        if os.path.exists(self.cache_file):
            age = -os.stat(self.cache_file).st_mtime + datetime.datetime.now().timestamp()
            if float(age) < float(self.cache_time):
                try:
                    with open(self.cache_file, "r") as f:
                        cached_data = yaml.safe_load(f)
                except yaml.constructor.ConstructorError:
                    cached_data = None
                if cached_data is not None:
                    # Only use the cached data if it appears to be a mapping of
                    # job-like objects (i.e., dictionaries with the keys
                    # that JobList relies on). Otherwise, fall back to a refresh.
                    if isinstance(cached_data, dict) and cached_data:
                        valid_cache = True
                        for job_obj in cached_data.values():
                            # Cached jobs are stored as dictionaries produced by
                            # Job.to_dict(), so we validate based on required keys.
                            if not isinstance(job_obj, dict):
                                valid_cache = False
                                break
                            if "id" not in job_obj:
                                valid_cache = False
                                break
                        if valid_cache:
                            self.jobs = cached_data
                            return
        
        # Cache is stale, invalid, or doesn't exist, refresh from scheduler
        self.refresh()
    
    def refresh(self):
        """
        Poll the scheduler to get the list of running jobs and update the cache.
        """
        # Query all jobs from the scheduler
        try:
            raw_jobs = self.scheduler.query_all_jobs()
        except Exception as e:
            raise RuntimeError(f"Failed to query jobs from scheduler: {e}")
        
        # Process the raw jobs into Job objects
        self.jobs = {}
        all_jobs = []
        
        for job_data in raw_jobs:
            job = self._create_job_from_data(job_data)
            all_jobs.append(job)
        
        # Organize jobs by main jobs and subjobs
        for job in all_jobs:
            if not job.dag_id:
                self.jobs[job.job_id] = job
        
        # Add subjobs to their parent jobs
        for job in all_jobs:
            if job.dag_id:
                if job.dag_id in self.jobs:
                    self.jobs[job.dag_id].add_subjob(job)
                else:
                    # If DAG parent doesn't exist, store this job as a standalone job
                    self.jobs[job.job_id] = job
        
        # Save to cache as plain dicts so yaml.safe_load can read them back.
        cache_dir = os.path.dirname(self.cache_file)
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
        with open(self.cache_file, "w") as f:
            f.write(yaml.dump({k: v.to_dict() if isinstance(v, Job) else v for k, v in self.jobs.items()}))
    
    def _create_job_from_data(self, job_data):
        """
        Create a Job object from scheduler-specific data.
        
        Parameters
        ----------
        job_data : dict
            Scheduler-specific job data.
            
        Returns
        -------
        Job
            A Job object.
        """
        # This method can be overridden by scheduler-specific implementations
        # For now, we assume the data is already in a compatible format
        return Job(
            job_id=job_data.get("id", job_data.get("job_id")),
            command=job_data.get("command", ""),
            hosts=job_data.get("hosts", 0),
            status=job_data.get("status", 0),
            name=job_data.get("name"),
            dag_id=job_data.get("dag_id", job_data.get("dag id")),
            **{k: v for k, v in job_data.items() if k not in ["id", "job_id", "command", "hosts", "status", "name", "dag id", "dag_id"]}
        )


def get_scheduler(scheduler_type="htcondor", **kwargs):
    """
    Factory function to get the appropriate scheduler instance.
    
    Parameters
    ----------
    scheduler_type : str
        The type of scheduler to create. Options: "htcondor", "slurm", "local"
    **kwargs
        Additional keyword arguments to pass to the scheduler constructor.
        For HTCondor: schedd_name (str)
        For Slurm: partition (str)
        
    Returns
    -------
    Scheduler
        An instance of the requested scheduler.
        
    Raises
    ------
    ValueError
        If an unknown scheduler type is requested.
    """
    scheduler_type = scheduler_type.lower()
    
    if scheduler_type == "htcondor":
        return HTCondor(**kwargs)
    elif scheduler_type == "slurm":
        return Slurm(**kwargs)
    elif scheduler_type == "local":
        if kwargs:
            unexpected = ", ".join(sorted(kwargs.keys()))
            raise TypeError(
                f"LocalProcessScheduler does not accept configuration options: {unexpected}"
            )
        return LocalProcessScheduler()
    else:
        raise ValueError(f"Unknown scheduler type: {scheduler_type}")

class JobDescription: 
    """
    A class which represents the description of a job to be submitted to a scheduler.

    This will allow jobs to be easily described in a scheduler-agnostic way.
    """
    
    # Mapping of generic resource parameters to HTCondor-specific parameters
    HTCONDOR_RESOURCE_MAPPING = {
        "cpus": "request_cpus",
        "memory": "request_memory",
        "disk": "request_disk",
    }

    def __init__(self, 
                 executable,
                 output,
                 error,
                 log,
                 **kwargs,
                 ):
        """
        Create a job description object.

        Parameters
        ----------
        executable : str, path
          The path to the executable to be used to run this job.
        output : str, path
          The location where stdout from the program should be written.
        error : str, path 
          The location where the stderr from the program should be written.
        log : str, path
          The location where log messages from the scheduler should be written for this job.
        **kwargs
          Additional scheduler-specific parameters.

        """
        self.executable = executable
        self.output = output
        self.error = error
        self.log = log
        self.kwargs = kwargs


    def to_htcondor(self):
        """
        Create a submit description for the htcondor scheduler.
        
        Returns
        -------
        dict
            A dictionary containing the HTCondor submit description.
        """
        description = {}
        description["executable"] = self.executable
        description["output"] = self.output
        description["error"] = self.error
        description["log"] = self.log 

        # Map generic resource parameters to HTCondor-specific ones using the mapping
        for generic_key, htcondor_key in self.HTCONDOR_RESOURCE_MAPPING.items():
            if generic_key in self.kwargs:
                description[htcondor_key] = self.kwargs[generic_key]
        
        # Set defaults for resource parameters if not provided
        description.setdefault("request_cpus", 1)
        description.setdefault("request_memory", "1GB")
        description.setdefault("request_disk", "1GB")
        
        # Add any additional kwargs to the description
        # Skip the generic resource parameters as they've already been mapped
        for key, value in self.kwargs.items():
            if key not in self.HTCONDOR_RESOURCE_MAPPING:
                description[key] = value
        
        return description
    
    def to_slurm(self):
        """
        Create a submit description for the Slurm scheduler.
        
        Returns
        -------
        dict
            A dictionary containing the Slurm submit description.
        """
        description = {}
        description["executable"] = self.executable
        description["output"] = self.output
        description["error"] = self.error
        # Note: Slurm doesn't have a direct equivalent to HTCondor's log file
        # We'll store it for potential use in the batch script
        description["log"] = self.log
        
        # Map generic resource parameters to Slurm-specific ones
        if "cpus" in self.kwargs:
            description["cpus"] = self.kwargs["cpus"]
        if "memory" in self.kwargs:
            description["memory"] = self.kwargs["memory"]
        if "disk" in self.kwargs:
            # Slurm doesn't have a direct disk request parameter
            # Store it for potential use in specialized configurations
            description["disk"] = self.kwargs["disk"]
        
        # Set defaults for resource parameters if not provided
        description.setdefault("cpus", 1)
        description.setdefault("memory", "1GB")
        
        # Add batch_name if present
        if "batch_name" in self.kwargs:
            description["batch_name"] = self.kwargs["batch_name"]
        
        # Handle arguments
        if "arguments" in self.kwargs:
            description["arguments"] = self.kwargs["arguments"]
        
        # Handle environment variables
        if "getenv" in self.kwargs:
            description["getenv"] = self.kwargs["getenv"]
        
        # Add any additional kwargs with slurm_ prefix directly
        for key, value in self.kwargs.items():
            if key not in ["cpus", "memory", "disk", "batch_name", "arguments", "getenv"]:
                description[key] = value
        
        return description
    
    def to_dict(self, scheduler_type="htcondor"):
        """
        Convert the job description to a scheduler-specific dictionary.
        
        Parameters
        ----------
        scheduler_type : str
            The type of scheduler. Options: "htcondor", "slurm"
            
        Returns
        -------
        dict
            The scheduler-specific job description.
        """
        scheduler_type = scheduler_type.lower()
        
        if scheduler_type == "htcondor":
            return self.to_htcondor()
        elif scheduler_type == "slurm":
            return self.to_slurm()
        else:
            raise ValueError(f"Unknown scheduler type: {scheduler_type}")