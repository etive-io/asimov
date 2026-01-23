"""
This module contains logic for interacting with a scheduling system.

Supported Schedulers are:

- HTCondor
- Slurm (planned)

"""

import os
import datetime
import yaml
import warnings
from abc import ABC, abstractmethod

try:
    warnings.filterwarnings("ignore", module="htcondor2")
    import htcondor2 as htcondor  # NoQA
    import classad2 as classad  # NoQA
except ImportError:
    warnings.filterwarnings("ignore", module="htcondor")
    import htcondor  # NoQA
    import classad  # NoQA


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


class HTCondor(Scheduler):
    """
    Scheduler implementation for HTCondor.
    """
    
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
        # Convert JobDescription to dict if needed
        if isinstance(job_description, JobDescription):
            submit_dict = job_description.to_htcondor()
        else:
            submit_dict = job_description
            
        # Create HTCondor Submit object
        submit_obj = htcondor.Submit(submit_dict)
        
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
        
        Parameters
        ----------
        dag_file : str
            Path to the DAG submit file.
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


class Slurm(Scheduler):
    """
    Scheduler implementation for Slurm.
    
    This class provides an interface to the Slurm workload manager,
    allowing job submission, deletion, and status queries.
    """
    
    def __init__(self, partition=None):
        """
        Initialize the Slurm scheduler.
        
        Parameters
        ----------
        partition : str, optional
            The Slurm partition to submit jobs to. If None, uses the default partition.
        """
        self.partition = partition
    
    def submit(self, job_description):
        """
        Submit a job to the Slurm scheduler.
        
        Parameters
        ----------
        job_description : JobDescription or dict
            The job description to submit.
            
        Returns
        -------
        int
            The job ID returned by Slurm.
            
        Raises
        ------
        RuntimeError
            If the job submission fails.
        """
        import subprocess
        import tempfile
        
        # Convert JobDescription to dict if needed
        if isinstance(job_description, JobDescription):
            submit_dict = job_description.to_slurm()
        else:
            submit_dict = job_description
        
        # Create a temporary batch script
        script_content = self._create_batch_script(submit_dict)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as script_file:
            script_file.write(script_content)
            script_path = script_file.name
        
        try:
            # Submit the job using sbatch
            result = subprocess.run(
                ['sbatch', script_path],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse the job ID from the output (format: "Submitted batch job 12345")
            output = result.stdout.strip()
            job_id = int(output.split()[-1])
            
            return job_id
            
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to submit job to Slurm: {e.stderr}")
        except (ValueError, IndexError) as e:
            raise RuntimeError(f"Failed to parse Slurm job ID from output: {result.stdout}")
        finally:
            # Clean up the temporary script file
            try:
                os.unlink(script_path)
            except (OSError, FileNotFoundError) as e:
                # Log the failure for debugging but don't raise
                import logging
                logging.debug(f"Failed to remove temporary script file {script_path}: {e}")
    
    def _create_batch_script(self, submit_dict):
        """
        Create a Slurm batch script from a submit dictionary.
        
        Parameters
        ----------
        submit_dict : dict
            Dictionary containing job parameters.
            
        Returns
        -------
        str
            The batch script content.
        """
        script_lines = ["#!/bin/bash"]
        
        # Add Slurm directives
        if self.partition:
            script_lines.append(f"#SBATCH --partition={self.partition}")
        
        if 'job_name' in submit_dict:
            script_lines.append(f"#SBATCH --job-name={submit_dict['job_name']}")
        elif 'batch_name' in submit_dict:
            script_lines.append(f"#SBATCH --job-name={submit_dict['batch_name']}")
        
        if 'output' in submit_dict:
            script_lines.append(f"#SBATCH --output={submit_dict['output']}")
        
        if 'error' in submit_dict:
            script_lines.append(f"#SBATCH --error={submit_dict['error']}")
        
        if 'cpus' in submit_dict:
            script_lines.append(f"#SBATCH --cpus-per-task={submit_dict['cpus']}")
        
        if 'memory' in submit_dict:
            # Convert memory to MB if needed (Slurm expects MB by default)
            memory = submit_dict['memory']
            if isinstance(memory, str):
                if memory.endswith('GB'):
                    memory = int(memory.replace('GB', '')) * 1024
                elif memory.endswith('MB'):
                    memory = int(memory.replace('MB', ''))
            script_lines.append(f"#SBATCH --mem={memory}")
        
        if 'time' in submit_dict:
            script_lines.append(f"#SBATCH --time={submit_dict['time']}")
        
        # Add any additional Slurm parameters
        for key, value in submit_dict.items():
            if key.startswith('slurm_'):
                slurm_key = key.replace('slurm_', '').replace('_', '-')
                script_lines.append(f"#SBATCH --{slurm_key}={value}")
        
        # Add environment setup if specified
        if 'getenv' in submit_dict and submit_dict['getenv']:
            script_lines.append("#SBATCH --export=ALL")
        
        # Add a blank line before the command
        script_lines.append("")
        
        # Add the executable and arguments
        if 'executable' in submit_dict:
            command = submit_dict['executable']
            if 'arguments' in submit_dict:
                command += f" {submit_dict['arguments']}"
            script_lines.append(command)
        
        return '\n'.join(script_lines) + '\n'
    
    def delete(self, job_id):
        """
        Delete a job from the Slurm scheduler.
        
        Parameters
        ----------
        job_id : int
            The job ID to delete.
            
        Raises
        ------
        RuntimeError
            If the job deletion fails.
        """
        import subprocess
        
        try:
            subprocess.run(
                ['scancel', str(job_id)],
                capture_output=True,
                text=True,
                check=True
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to delete Slurm job {job_id}: {e.stderr}")
    
    def query(self, job_id=None, projection=None):
        """
        Query the Slurm scheduler for job status.
        
        Parameters
        ----------
        job_id : int, optional
            The job ID to query. If None, query all jobs.
        projection : list, optional
            List of attributes to retrieve (not used for Slurm).
            
        Returns
        -------
        list
            List of job dictionaries.
        """
        import subprocess
        import getpass
        
        # Get username reliably across systems
        try:
            username = getpass.getuser()
        except Exception:
            # Fall back to environment variable if getpass fails
            username = os.environ.get('USER', 'unknown')
        
        # Build the squeue command
        cmd = ['squeue', '--user', username, '--format=%i|%j|%t|%N', '--noheader']
        
        if job_id is not None:
            cmd.extend(['--job', str(job_id)])
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            jobs = []
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                    
                parts = line.split('|')
                if len(parts) >= 4:
                    job_dict = {
                        'JobId': parts[0],
                        'JobName': parts[1],
                        'State': parts[2],
                        'NodeList': parts[3]
                    }
                    jobs.append(job_dict)
            
            return jobs
            
        except subprocess.CalledProcessError:
            # If the job doesn't exist, return empty list
            return []
    
    def submit_dag(self, dag_file, batch_name=None, **kwargs):
        """
        Submit a DAG file to the Slurm scheduler.
        
        This method converts an HTCondor DAG file to a Slurm batch script
        with job dependencies and submits it.
        
        Parameters
        ----------
        dag_file : str
            Path to the HTCondor DAG file to convert and submit.
        batch_name : str, optional
            A name for the batch of jobs.
        **kwargs
            Additional Slurm-specific parameters.
            
        Returns
        -------
        int
            The job ID of the submitted DAG script.
            
        Raises
        ------
        RuntimeError
            If the DAG submission fails.
        FileNotFoundError
            If the DAG file does not exist.
        """
        if not os.path.exists(dag_file):
            raise FileNotFoundError(f"DAG file not found: {dag_file}")
        
        # Convert the DAG file to a Slurm script
        slurm_script = self._convert_dag_to_slurm(dag_file, batch_name, **kwargs)
        
        # Write the script to a temporary file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as script_file:
            script_file.write(slurm_script)
            script_path = script_file.name
        
        try:
            # Submit the script
            import subprocess
            result = subprocess.run(
                ['sbatch', script_path],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse the job ID
            output = result.stdout.strip()
            job_id = int(output.split()[-1])
            
            return job_id
            
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to submit DAG to Slurm: {e.stderr}")
        except (ValueError, IndexError) as e:
            raise RuntimeError(f"Failed to parse Slurm job ID from output: {result.stdout}")
        finally:
            # Keep the script file for debugging purposes
            # (it will be in /tmp and cleaned up by the system)
            pass
    
    def _convert_dag_to_slurm(self, dag_file, batch_name=None, **kwargs):
        """
        Convert an HTCondor DAG file to a Slurm batch script.
        
        This is a simplified conversion that handles basic DAG structures.
        For complex DAGs, consider using a dedicated DAG workflow tool.
        
        Parameters
        ----------
        dag_file : str
            Path to the HTCondor DAG file.
        batch_name : str, optional
            Name for the batch job.
        **kwargs
            Additional parameters.
            
        Returns
        -------
        str
            The Slurm batch script content.
        """
        import re
        
        dag_dir = os.path.dirname(os.path.abspath(dag_file))
        
        # Parse the DAG file
        jobs = {}
        dependencies = {}
        
        with open(dag_file, 'r') as f:
            for line in f:
                line = line.strip()
                
                # Parse JOB lines: JOB JobName SubmitFile [DIR directory]
                if line.startswith('JOB'):
                    parts = line.split()
                    if len(parts) >= 3:
                        job_name = parts[1]
                        submit_file = parts[2]
                        
                        # Handle DIR specification
                        job_dir = dag_dir
                        if 'DIR' in parts:
                            dir_index = parts.index('DIR')
                            if dir_index + 1 < len(parts):
                                job_dir = parts[dir_index + 1]
                                if not os.path.isabs(job_dir):
                                    job_dir = os.path.join(dag_dir, job_dir)
                        
                        # Make submit file path absolute
                        if not os.path.isabs(submit_file):
                            submit_file = os.path.join(job_dir, submit_file)
                        
                        jobs[job_name] = {
                            'submit_file': submit_file,
                            'dir': job_dir
                        }
                
                # Parse PARENT-CHILD lines: PARENT JobA CHILD JobB
                elif line.startswith('PARENT'):
                    parts = line.split()
                    if len(parts) >= 4 and parts[2] == 'CHILD':
                        parent = parts[1]
                        child = parts[3]
                        
                        if child not in dependencies:
                            dependencies[child] = []
                        dependencies[child].append(parent)
        
        # Create the Slurm script
        script_lines = ["#!/bin/bash"]
        
        if batch_name:
            script_lines.append(f"#SBATCH --job-name={batch_name}")
        else:
            script_lines.append(f"#SBATCH --job-name=asimov-dag")
        
        # Set output and error files
        dag_base = os.path.splitext(os.path.basename(dag_file))[0]
        script_lines.append(f"#SBATCH --output={dag_dir}/{dag_base}.out")
        script_lines.append(f"#SBATCH --error={dag_dir}/{dag_base}.err")
        
        # Minimal resources for the DAG manager script
        script_lines.append("#SBATCH --cpus-per-task=1")
        script_lines.append("#SBATCH --mem=1GB")
        
        script_lines.append("")
        script_lines.append("# Asimov DAG execution script (converted from HTCondor DAG)")
        script_lines.append("")
        
        # Add job submission logic
        script_lines.append("# Submit jobs and track their IDs")
        script_lines.append("declare -A job_ids")
        script_lines.append("")
        
        # Topological sort to determine execution order
        sorted_jobs = self._topological_sort(jobs.keys(), dependencies)
        
        for job_name in sorted_jobs:
            job_info = jobs[job_name]
            
            # Parse the submit file to get the job command
            submit_file = job_info['submit_file']
            if os.path.exists(submit_file):
                job_cmd = self._parse_submit_file_for_slurm(submit_file, job_info['dir'])
            else:
                # Fallback: create a simple job
                job_cmd = f"echo 'Job {job_name} (submit file not found: {submit_file})'"
            
            # Add dependency handling
            if job_name in dependencies:
                deps = dependencies[job_name]
                dep_ids = ' '.join([f"${{job_ids[{dep}]}}" for dep in deps])
                script_lines.append(f"# Job {job_name} depends on: {', '.join(deps)}")
                script_lines.append(f'job_id=$(sbatch --dependency=afterok:{dep_ids} --parsable --wrap "{job_cmd}")')
            else:
                script_lines.append(f"# Job {job_name} (no dependencies)")
                script_lines.append(f'job_id=$(sbatch --parsable --wrap "{job_cmd}")')
            
            script_lines.append(f'job_ids[{job_name}]="$job_id"')
            script_lines.append(f'echo "Submitted {job_name} as job $job_id"')
            script_lines.append("")
        
        script_lines.append("echo 'All jobs submitted'")
        
        return '\n'.join(script_lines) + '\n'
    
    def _topological_sort(self, jobs, dependencies):
        """
        Perform a topological sort of jobs based on dependencies.
        
        Parameters
        ----------
        jobs : iterable
            List of job names.
        dependencies : dict
            Dictionary mapping job names to lists of parent jobs.
            
        Returns
        -------
        list
            Sorted list of job names.
        """
        from collections import deque
        
        # Build adjacency list and in-degree count
        adj_list = {job: [] for job in jobs}
        in_degree = {job: 0 for job in jobs}
        
        for child, parents in dependencies.items():
            for parent in parents:
                if parent in adj_list:
                    adj_list[parent].append(child)
                    in_degree[child] += 1
        
        # Find all jobs with no dependencies
        queue = deque([job for job in jobs if in_degree[job] == 0])
        sorted_jobs = []
        
        while queue:
            job = queue.popleft()
            sorted_jobs.append(job)
            
            for child in adj_list[job]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)
        
        # If we haven't sorted all jobs, there's a cycle
        if len(sorted_jobs) != len(list(jobs)):
            raise RuntimeError("Circular dependency detected in DAG")
        
        return sorted_jobs
    
    def _parse_submit_file_for_slurm(self, submit_file, job_dir):
        """
        Parse an HTCondor submit file and extract the command for Slurm.
        
        Parameters
        ----------
        submit_file : str
            Path to the HTCondor submit file.
        job_dir : str
            Directory where the job should be executed.
            
        Returns
        -------
        str
            The command to execute.
        """
        from pathlib import Path
        
        executable = None
        arguments = ""
        
        with open(submit_file, 'r') as f:
            for line in f:
                line = line.strip()
                
                if line.startswith('executable'):
                    executable = line.split('=', 1)[1].strip()
                elif line.startswith('arguments'):
                    arguments = line.split('=', 1)[1].strip()
                    # Remove quotes if present
                    arguments = arguments.strip('"').strip("'")
        
        if executable:
            # Make executable path absolute if needed and validate
            if not os.path.isabs(executable):
                executable = os.path.join(job_dir, executable)
            
            # Resolve path to canonical form and validate it's within expected boundaries
            try:
                executable_path = Path(executable).resolve()
                job_dir_path = Path(job_dir).resolve()
                
                # Ensure the executable is within the job directory or is an absolute system path
                # This prevents directory traversal attacks
                if not (str(executable_path).startswith(str(job_dir_path)) or executable_path.is_absolute()):
                    # If executable is not in job_dir and not absolute, treat it as potentially unsafe
                    executable = str(executable_path)
            except (OSError, ValueError):
                # If path resolution fails, use the original path
                # The scheduler will fail later if the path is invalid
                pass
            
            cmd = executable
            if arguments:
                cmd += f" {arguments}"
            
            # Change to job directory before executing (using resolved path)
            job_dir_resolved = str(Path(job_dir).resolve())
            return f"cd {job_dir_resolved} && {cmd}"
        else:
            return f"cd {job_dir} && echo 'No executable found in submit file'"
    
    def query_all_jobs(self):
        """
        Query all jobs from the Slurm scheduler.
        
        This method queries all jobs for the current user.
        
        Returns
        -------
        list of dict
            A list of dictionaries containing job information with keys:
            - id: Job ID
            - command: Job name (Slurm doesn't provide the command easily)
            - hosts: Number of nodes
            - status: Job status (converted to HTCondor-like integer codes)
            - name: Job name
        """
        import subprocess
        import getpass
        
        # Get username reliably across systems
        try:
            username = getpass.getuser()
        except Exception:
            # Fall back to environment variable if getpass fails
            username = os.environ.get('USER', 'unknown')
        
        try:
            result = subprocess.run(
                ['squeue', '--user', username, 
                 '--format=%i|%j|%t|%N|%D', '--noheader'],
                capture_output=True,
                text=True,
                check=True
            )
            
            jobs = []
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                
                parts = line.split('|')
                if len(parts) >= 5:
                    job_id = parts[0]
                    job_name = parts[1]
                    state = parts[2]
                    node_list = parts[3]
                    num_nodes = parts[4]
                    
                    # Convert Slurm state to HTCondor-like status code
                    status_map = {
                        'PD': 1,  # Pending -> Idle
                        'R': 2,   # Running -> Running
                        'CG': 2,  # Completing -> Running
                        'CD': 4,  # Completed -> Completed
                        'F': 5,   # Failed -> Held
                        'CA': 3,  # Cancelled -> Removed
                        'TO': 5,  # Timeout -> Held
                        'NF': 5,  # Node Fail -> Held
                    }
                    status_code = status_map.get(state, 0)
                    
                    job_dict = {
                        "id": int(job_id) if job_id.isdigit() else job_id,
                        "command": job_name,  # Slurm uses job name, not full command
                        "hosts": int(num_nodes) if num_nodes.isdigit() else 0,
                        "status": status_code,
                        "name": job_name,
                    }
                    
                    jobs.append(job_dict)
            
            return jobs
            
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to query Slurm jobs: {e.stderr}")


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
                with open(self.cache_file, "r") as f:
                    cached_data = yaml.safe_load(f)
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
                            if "job_id" not in job_obj or "dag_id" not in job_obj:
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
        
        # Save to cache
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        # Store Job objects directly so that cache loading logic, which expects
        # Job instances with methods, can validate and use the cached data.
        with open(self.cache_file, "w") as f:
            f.write(yaml.dump(self.jobs))
    
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
        The type of scheduler to create. Options: "htcondor", "slurm"
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