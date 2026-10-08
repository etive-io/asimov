"""
Running build and submit in a separate process, so that the caller doesn't wait.

Submitting an analysis talks to the scheduler, which can be slow or stall, and
submissions are paced to keep the scheduler from being overwhelmed. A caller
which has to answer quickly (the MCP server, see :mod:`asimov.mcp_server`)
shouldn't wait for that. :func:`start_job` starts a worker process and returns
at once with a job. The job is a file in the project (``.asimov/jobs``) which
the worker keeps up to date, and which :func:`get_job` and :func:`list_jobs`
read without touching the scheduler.

Only one job which changes the project runs at a time: a lock file in the same
directory names it, and starting another while it runs raises :class:`JobBusy`.
A worker which dies without finishing (killed, or the machine restarted) is
noticed the next time its job is read, and the job is marked as failed.

The worker is ``python -m asimov.jobs run PROJECT JOB``. It does what the
command line does (:func:`asimov.cli.manage.build_analyses` and
:func:`asimov.cli.manage.submit_analyses`), as the same principal as the
caller, and what it prints goes to the job's log.
"""

import contextlib
import dataclasses
import datetime
import json
import os
import signal
import subprocess
import sys
import threading
import uuid
from typing import Optional

from asimov.audit import append_audit, new_record

__all__ = [
    "ACTIONS",
    "Job",
    "JobBusy",
    "JobError",
    "get_job",
    "list_jobs",
    "read_log",
    "run_job",
    "start_job",
]

#: What a job can do, by name.
ACTIONS = ("build", "submit")

#: The statuses of a job which has not finished.
ACTIVE = ("queued", "running")

#: How long a worker may run, by default, in seconds.
DEFAULT_TIMEOUT = 3600


class JobError(ValueError):
    """The job can't be started or found, and the message says why."""


class JobBusy(JobError):
    """Another job is running."""

    def __init__(self, job_id):
        super().__init__(f"Job {job_id} is still running: wait for it to finish.")
        self.job_id = job_id


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclasses.dataclass
class Job:
    """
    One run of build or submit.

    Parameters
    ----------
    id : str
    action : str
        ``"build"`` or ``"submit"``.
    status : str
        ``"queued"``, ``"running"``, ``"succeeded"`` or ``"failed"``.
    subject : str, optional
        Only this subject was built or submitted.
    options : dict
        ``dryrun`` and, for submit, ``max_submit``.
    principal : dict
        Who the job runs as (see :class:`asimov.principal.Principal`).
    pid : int, optional
        The worker's process id.
    created, started, finished : str
        Times (UTC, ISO 8601).
    timeout : int
        Seconds the worker may run for.
    result : dict, optional
        What the job did.
    error : str, optional
        Why it failed.
    """

    id: str
    action: str
    status: str = "queued"
    subject: Optional[str] = None
    options: dict = dataclasses.field(default_factory=dict)
    principal: dict = dataclasses.field(default_factory=dict)
    pid: Optional[int] = None
    created: str = ""
    started: Optional[str] = None
    finished: Optional[str] = None
    timeout: int = DEFAULT_TIMEOUT
    result: Optional[dict] = None
    error: Optional[str] = None

    @property
    def active(self):
        return self.status in ACTIVE

    def to_dict(self):
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data):
        names = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})


def jobs_dir(project, create=False):
    """The directory a project keeps its jobs in."""
    path = os.path.join(str(project), ".asimov", "jobs")
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def _path(project, job_id, suffix=".json"):
    if not job_id or any(c not in "0123456789abcdef" for c in job_id):
        raise JobError(f"{job_id!r} is not a job id.")
    return os.path.join(jobs_dir(project), job_id + suffix)


def _write(project, job):
    """Write the job's file so that a reader never sees half of it."""
    path = _path(project, job.id)
    scratch = f"{path}.{os.getpid()}.tmp"
    with open(scratch, "w") as handle:
        json.dump(job.to_dict(), handle, indent=1, sort_keys=True)
    os.replace(scratch, path)


def _read(project, job_id):
    try:
        with open(_path(project, job_id)) as handle:
            return Job.from_dict(json.load(handle))
    except FileNotFoundError:
        raise JobError(f"There is no job {job_id!r}.")
    except json.JSONDecodeError:
        raise JobError(f"The record of job {job_id!r} is unreadable.")


def _alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _lock_path(project):
    return os.path.join(jobs_dir(project), "lock")


def _locked_by(project):
    try:
        with open(_lock_path(project)) as handle:
            return handle.read().strip() or None
    except FileNotFoundError:
        return None


def _release(project, job_id):
    """Release the lock, if ``job_id`` holds it."""
    if _locked_by(project) == job_id:
        with contextlib.suppress(FileNotFoundError):
            os.remove(_lock_path(project))


def _acquire(project, job_id):
    """
    Take the project's lock for ``job_id``.

    A lock whose job has finished, or whose worker has died, is stale and is
    taken over.

    Raises
    ------
    JobBusy
        If a job which is still going holds it.
    """
    jobs_dir(project, create=True)
    for _ in range(3):
        try:
            descriptor = os.open(_lock_path(project), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            holder = _locked_by(project)
            if holder:
                try:
                    job = get_job(project, holder)
                except JobError:
                    job = None
                if job is not None and job.active:
                    raise JobBusy(holder)
            with contextlib.suppress(FileNotFoundError):
                os.remove(_lock_path(project))
            continue
        with os.fdopen(descriptor, "w") as handle:
            handle.write(job_id)
        return
    raise JobBusy(_locked_by(project) or "unknown")


def get_job(project, job_id):
    """
    The job with this id.

    A job which says it is running but whose worker has gone is marked as
    failed, and its lock released.

    Raises
    ------
    JobError
        If there is no such job.
    """
    job = _read(project, job_id)
    if job.active and job.pid and not _alive(job.pid):
        # Look again: the worker may have finished between the read and the check.
        job = _read(project, job_id)
        if job.active:
            job.status = "failed"
            job.error = "The worker stopped without finishing."
            job.finished = _now()
            _write(project, job)
            _release(project, job.id)
    return job


def list_jobs(project, limit=20, active=False):
    """
    Jobs, the newest first.

    Parameters
    ----------
    limit : int
        The most to return.
    active : bool
        Only jobs which haven't finished.
    """
    try:
        names = [n[:-5] for n in os.listdir(jobs_dir(project)) if n.endswith(".json")]
    except FileNotFoundError:
        return []
    found = []
    for name in names:
        try:
            found.append(get_job(project, name))
        except JobError:
            continue
    found.sort(key=lambda job: job.created, reverse=True)
    if active:
        found = [job for job in found if job.active]
    return found[:limit]


def read_log(project, job_id, max_bytes=20_000):
    """The end of what a job printed."""
    try:
        with open(_path(project, job_id, ".log"), "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            return handle.read().decode("utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def start_job(
    context,
    action,
    subject=None,
    dryrun=False,
    max_submit=None,
    timeout=DEFAULT_TIMEOUT,
    command=None,
):
    """
    Start a worker which builds or submits, and return its job at once.

    Parameters
    ----------
    context : asimov.context.ProjectContext
        The project. It must be active, so that the principal the job runs as
        and the ledger its start is recorded in are the caller's.
    action : str
        ``"build"`` or ``"submit"``.
    subject : str, optional
        Only this subject.
    dryrun : bool
        Print what would be run without running it.
    max_submit : int, optional
        Submit at most this many analyses.
    timeout : int
        Seconds the worker may run for.
    command : list of str, optional
        The worker's command. Defaults to ``python -m asimov.jobs run ...``.

    Returns
    -------
    Job

    Raises
    ------
    JobBusy
        If another job is still running.
    JobError
        If ``action`` is not one of :data:`ACTIONS`.
    """
    from asimov.principal import current_principal

    if action not in ACTIONS:
        raise JobError(f"{action!r} is not something a job can do: use one of {', '.join(ACTIONS)}.")
    project = context.root
    options = {"dryrun": bool(dryrun)}
    if action == "submit" and max_submit is not None:
        options["max_submit"] = int(max_submit)
    job = Job(
        id=uuid.uuid4().hex,
        action=action,
        subject=subject,
        options=options,
        principal=current_principal().to_dict(),
        created=_now(),
        timeout=int(timeout),
    )
    _acquire(project, job.id)
    try:
        _write(project, job)
        ledger = context.ledger
        with ledger.transaction():
            append_audit(
                ledger,
                new_record(
                    action,
                    "job",
                    subject or "@project",
                    content={"job": job.id, **options},
                    outcome="started",
                ),
            )
        command = command or [sys.executable, "-m", "asimov.jobs", "run", str(project), job.id]
        with open(_path(project, job.id, ".log"), "wb") as log:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                cwd=str(project),
                start_new_session=True,
            )
        # Collect the worker when it ends, so it isn't left looking alive.
        threading.Thread(target=process.wait, daemon=True).start()
        job.pid = process.pid
        _write(project, job)
    except BaseException as error:
        _release(project, job.id)
        job.status = "failed"
        job.error = f"Could not start the worker: {error}"
        job.finished = _now()
        with contextlib.suppress(Exception):
            _write(project, job)
        raise
    return job


class _TimedOut(Exception):
    pass


def run_job(project, job_id):
    """
    Do a job, in this process. This is what the worker runs.

    Parameters
    ----------
    project : str
        The project's directory.
    job_id : str

    Returns
    -------
    Job
        The job, finished.
    """
    from asimov.context import ProjectContext
    from asimov.principal import Principal, acting_as

    job = _read(project, job_id)
    job.status = "running"
    job.pid = os.getpid()
    job.started = _now()
    _write(project, job)

    def timed_out(signum, frame):
        raise _TimedOut()

    previous = None
    if hasattr(signal, "SIGALRM") and threading.current_thread() is threading.main_thread():
        previous = signal.signal(signal.SIGALRM, timed_out)
        signal.alarm(max(1, job.timeout))
    try:
        context = ProjectContext.from_directory(project)
        try:
            with context.activate(), acting_as(Principal.from_dict(job.principal)):
                from asimov.cli import manage

                if job.action == "build":
                    manage.build_analyses(event=job.subject, dryrun=job.options.get("dryrun", False))
                    job.result = {}
                else:
                    submitted = manage.submit_analyses(
                        event=job.subject,
                        dryrun=job.options.get("dryrun", False),
                        max_submit=job.options.get("max_submit"),
                    )
                    job.result = {"submitted": submitted}
        finally:
            context.reload_ledger()
        job.status = "succeeded"
    except _TimedOut:
        job.status = "failed"
        job.error = f"The job ran for more than {job.timeout} seconds and was stopped."
    except BaseException as error:  # a worker must always say how it ended
        job.status = "failed"
        job.error = f"{type(error).__name__}: {error}"
    finally:
        if previous is not None:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
        job.finished = _now()
        _write(project, job)
        _release(project, job.id)
    return job


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 3 or argv[0] != "run":
        sys.stderr.write("usage: python -m asimov.jobs run PROJECT JOB\n")
        return 2
    job = run_job(argv[1], argv[2])
    return 0 if job.status == "succeeded" else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
