import functools
import shlex
import time
import shutil
import configparser
import sys
import traceback
import os
import click
from copy import deepcopy
from pathlib import Path

from asimov import condor, config, logger, LOGGER_LEVEL
from asimov.context import current_context, resolve_path
from asimov.principal import Principal, acting_as
from asimov.context import active_ledger as ledger
from asimov.cli import ACTIVE_STATES, manage, report
from asimov.scheduler_utils import get_configured_scheduler, create_job_from_dict, get_job_list
from asimov.monitor_helpers import monitor_analysis
from asimov.throttle import ACTIVE_STATES as RUNNING_STATES, per_pass_limit
from asimov.telemetry import initialize_telemetry_sinks

# Try to import crontab for Slurm cron support
try:
    from crontab import CronTab
    CRONTAB_AVAILABLE = True
except ImportError:
    CRONTAB_AVAILABLE = False

logger = logger.getChild("cli").getChild("monitor")
logger.setLevel(LOGGER_LEVEL)

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points


@click.option("--dry-run", "-n", "dry_run", is_flag=True)
@click.option("--use-scheduler-api", is_flag=True, default=False, 
              help="Use the new scheduler API directly (experimental)")
@click.command()
def start(dry_run, use_scheduler_api):
    """Set up a cron job to monitor the project."""
    from asimov import setup_file_logging
    setup_file_logging()

    # Get the configured scheduler type
    try:
        scheduler_type = config.get("scheduler", "type")
    except (configparser.NoOptionError, configparser.NoSectionError, KeyError):
        scheduler_type = "htcondor"
    
    if scheduler_type == "slurm":
        # For Slurm, use a cron job instead of scheduler-based cron
        _start_slurm_monitor()
    else:
        # HTCondor implementation
        _start_htcondor_monitor(dry_run, use_scheduler_api)


def _start_htcondor_monitor(dry_run, use_scheduler_api):
    """Start monitoring using HTCondor cron job."""
    try:
        minute_expression = config.get("condor", "cron_minute")
    except (configparser.NoOptionError, configparser.NoSectionError):
        minute_expression = "*/15"

    try:
        getenv = config.get("condor", "monitor_getenv")
    except (configparser.NoOptionError, configparser.NoSectionError):
        # Production LIGO Data Grid pools reject a blanket "getenv = True"
        # outright once they set SUBMIT_ALLOW_GETENV = False (see
        # https://computing.docs.ligo.org/guide/compsoft/roadmap/LVK/htcondor_getenv_true/),
        # so an explicit variable list is required rather than "true".
        # This default covers what running `asimov` from a conda/venv
        # environment normally needs; sites needing more can override it
        # via the condor/monitor_getenv config option.
        getenv = (
            "PATH,PYTHONPATH,CONDA_PREFIX,CONDA_DEFAULT_ENV,VIRTUAL_ENV,"
            "LD_LIBRARY_PATH,HOME,USER,X509_USER_PROXY,BEARER_TOKEN_FILE,"
            "SCITOKENS_FILE,GWDATAFIND_SERVER"
        )

    submit_description = {
        "executable": shutil.which("asimov"),
        "arguments": "monitor --chain",
        "output": resolve_path(os.path.join(".asimov", "asimov_cron.out")),
        "on_exit_remove": "false",
        "universe": "local",
        "error": resolve_path(os.path.join(".asimov", "asimov_cron.err")),
        "log": resolve_path(os.path.join(".asimov", "asimov_cron.log")),
        "request_cpus": "1",
        "cron_minute": minute_expression,
        "getenv": getenv,
        "batch_name": f"asimov/monitor/{ledger.data['project']['name']}",
        "request_memory": "8192MB",
        "request_disk": "8192MB",
        "+flock_local": "False",
        "+DESIRED_Sites": "nogrid",
    }

    accounting_group = None
    if "asimov start" in config:
        accounting_group = config["asimov start"].get("accounting")
    if not accounting_group and "condor" in config:
        accounting_group = config["condor"].get("accounting")

    if accounting_group:
        submit_description["accounting_group"] = accounting_group
        try:
            submit_description["accounting_group_user"] = config.get("condor", "user")
        except (configparser.NoOptionError, configparser.NoSectionError):
            pass
    else:
        logger.warning(
            "This asimov project does not supply any accounting"
            " information, which may prevent it running on"
            " some clusters."
        )

    # Use the new scheduler API if requested, otherwise use the legacy interface
    if use_scheduler_api:
        logger.info("Using new scheduler API")
        try:
            scheduler = get_configured_scheduler()
            job = create_job_from_dict(submit_description)
            cluster = scheduler.submit(job)
        except Exception as e:
            logger.error(f"Failed to submit using scheduler API: {e}")
            logger.info("Falling back to legacy condor.submit_job")
            cluster = condor.submit_job(submit_description)
    else:
        # Use legacy interface (which internally uses the scheduler API)
        cluster = condor.submit_job(submit_description)
    
    ledger.data["cronjob"] = cluster
    ledger.save()
    click.secho(f"  \t  ● Asimov is running ({cluster})", fg="green")
    logger.info(f"Running asimov cronjob as  {cluster}")


def _start_slurm_monitor():
    """Start monitoring using system cron job for Slurm."""
    try:
        minute_expression = config.get("slurm", "cron_minute")
    except (configparser.NoOptionError, configparser.NoSectionError):
        minute_expression = "*/15"

    if not CRONTAB_AVAILABLE:
        _start_slurm_monitor_manual(minute_expression)
        return

    project_root = current_context().root
    asimov_executable = shutil.which("asimov")

    if not asimov_executable:
        click.secho("  \t  ● Error: asimov executable not found in PATH", fg="red")
        return

    try:
        cron = CronTab(user=True)
        job_comment = f"asimov-monitor-{ledger.data['project']['name']}"
        cron.remove_all(comment=job_comment)

        out = shlex.quote(os.path.join(project_root, ".asimov", "asimov_cron.out"))
        err = shlex.quote(os.path.join(project_root, ".asimov", "asimov_cron.err"))
        command = (
            f"cd {shlex.quote(project_root)} && "
            f"{shlex.quote(asimov_executable)} monitor --chain >> {out} 2>> {err}"
        )
        job = cron.new(command=command, comment=job_comment)

        if minute_expression.startswith("*/"):
            job.minute.every(int(minute_expression[2:]))
        else:
            job.setall(minute_expression)

        cron.write()
        ledger.data["cronjob"] = job_comment
        ledger.save()
        click.secho(f"  \t  ● Asimov is running via cron ({job_comment})", fg="green")
        logger.info(f"Running asimov cronjob via cron: {job_comment}")

    except Exception as e:
        logger.error(f"Failed to create cron job: {e}")
        click.secho(f"  \t  ● Error creating cron job: {e}", fg="red")
        _start_slurm_monitor_manual(minute_expression)


def _start_slurm_monitor_manual(minute_expression="*/15"):
    """Print manual cron setup instructions and write a helper shell script."""
    project_root = current_context().root
    asimov_executable = shutil.which("asimov") or "asimov"

    click.secho(
        "  \t  ● python-crontab not installed. Setting up cron manually...", fg="yellow"
    )

    script_path = resolve_path(os.path.join(".asimov", "asimov_monitor.sh"))
    with open(script_path, "w") as f:
        f.write("#!/bin/bash\n")
        f.write(f"cd {shlex.quote(project_root)}\n")
        out = os.path.join(project_root, ".asimov", "asimov_cron.out")
        err = os.path.join(project_root, ".asimov", "asimov_cron.err")
        f.write(
            f"{shlex.quote(asimov_executable)} monitor --chain"
            f" >> {shlex.quote(out)} 2>> {shlex.quote(err)}\n"
        )

    os.chmod(script_path, 0o755)
    click.echo("\nPlease add the following line to your crontab (crontab -e):")
    click.echo(f"{minute_expression} * * * * {script_path}")

    ledger.data["cronjob"] = "manual-cron"
    ledger.save()


@click.option("--dry-run", "-n", "dry_run", is_flag=True)
@click.option("--use-scheduler-api", is_flag=True, default=False,
              help="Use the new scheduler API directly (experimental)")
@click.command()
def stop(dry_run, use_scheduler_api):
    """Stop the cron job monitoring the project."""
    from asimov import setup_file_logging
    setup_file_logging()
    
    # Get the configured scheduler type
    try:
        scheduler_type = config.get("scheduler", "type")
    except (configparser.NoOptionError, configparser.NoSectionError, KeyError):
        scheduler_type = "htcondor"
    
    if scheduler_type == "slurm":
        # For Slurm, remove the cron job
        _stop_slurm_monitor()
    else:
        # HTCondor implementation
        _stop_htcondor_monitor(dry_run, use_scheduler_api)


def _stop_htcondor_monitor(dry_run, use_scheduler_api):
    """Stop monitoring using HTCondor."""
    cluster = ledger.data.get("cronjob")
    if cluster is None:
        click.secho("  \t  ● No running monitor found", fg="yellow")
        return
    
    # Use the new scheduler API if requested, otherwise use the legacy interface
    if use_scheduler_api:
        logger.info("Using new scheduler API")
        try:
            scheduler = get_configured_scheduler()
            scheduler.delete(cluster)
        except Exception as e:
            logger.error(f"Failed to delete using scheduler API: {e}")
            logger.info("Falling back to legacy condor.delete_job")
            condor.delete_job(cluster)
    else:
        # Use legacy interface (which internally uses the scheduler API)
        condor.delete_job(cluster)
    
    click.secho("  \t  ● Asimov has been stopped", fg="red")
    logger.info(f"Stopped asimov cronjob {cluster}")


def _stop_slurm_monitor():
    """Stop monitoring by removing cron job for Slurm."""
    if not CRONTAB_AVAILABLE:
        _stop_slurm_monitor_manual()
        return
    
    cronjob_id = ledger.data.get("cronjob", None)
    
    if not cronjob_id:
        click.secho("  \t  ● No running monitor found", fg="yellow")
        return
    
    if cronjob_id == "manual-cron":
        _stop_slurm_monitor_manual()
        return
    
    try:
        # Use the user's crontab
        cron = CronTab(user=True)
        
        # Remove the job by comment
        removed = cron.remove_all(comment=cronjob_id)
        
        if removed > 0:
            cron.write()
            click.secho("  \t  ● Asimov has been stopped", fg="red")
            logger.info(f"Stopped asimov cronjob: {cronjob_id}")
        else:
            click.secho(f"  \t  ● No cron job found with identifier: {cronjob_id}", fg="yellow")
            
    except Exception as e:
        logger.error(f"Failed to remove cron job: {e}")
        click.secho(f"  \t  ● Error removing cron job: {e}", fg="red")
        _stop_slurm_monitor_manual()


def _stop_slurm_monitor_manual():
    """Provide manual instructions for removing Slurm monitoring."""
    cronjob_id = ledger.data.get("cronjob", "asimov_monitor.sh")
    click.secho("  \t  ● Manual cron setup detected or python-crontab not installed.", fg="yellow")
    click.echo(f"Run 'crontab -e' and remove the line containing '{cronjob_id}'")


#: The most times ``monitor --chain`` runs build and submit again in one pass,
#: after analyses have finished, so what needs them can start without waiting for
#: the next pass (a dependency hop would otherwise cost a whole period).
CHAIN_MAX_RERUNS = 3


def _run_build_and_submit(ctx, event, max_submit=None):
    """
    Run ``manage build`` then ``manage submit``, as a chain pass does.

    A failure while building must not stop analyses which are already built
    from being submitted (or the rest of the monitor pass).

    Returns
    -------
    int
        The number of analyses which were submitted.
    """
    submitted = 0
    for step in (manage.build, manage.submit):
        kwargs = {"event": event}
        if step is manage.submit and max_submit is not None:
            kwargs["max_submit"] = max_submit
        try:
            result = ctx.invoke(step, **kwargs)
            if step is manage.submit and isinstance(result, int):
                submitted = result
        except Exception as e:
            logger.exception(e)
            click.echo(
                click.style("●", fg="red") + f" asimov manage {step.name} failed: {e}"
            )
    return submitted


def _finished_analyses(event):
    """The ``(subject, name)`` of every analysis which has finished."""
    finished = set()
    for subject in ledger.get_event(event):
        for analysis in subject.productions:
            if analysis.finished:
                finished.add((subject.name, analysis.name))
    for analysis in ledger.project_analyses:
        if analysis.finished:
            finished.add((None, analysis.name))
    return finished


def _settle_chain_pass(ctx, event, newly_finished, submitted):
    """
    Run build and submit again after analyses have finished in this pass.

    The monitor step is what notices that an analysis has finished, and what
    needs it is only submitted by a later run of submit. Running them again
    here starts it now, instead of in the next pass. This repeats while
    running them finishes something more (some analyses finish as they are
    submitted), at most ``CHAIN_MAX_RERUNS`` times, and keeps to the
    ``max_submit_per_pass`` limit across all of the runs in the pass.

    Parameters
    ----------
    event : str or None
        The subject which the pass is for.
    newly_finished : int
        How many analyses the monitor step found to have finished.
    submitted : int
        How many analyses the pass has submitted so far.

    Returns
    -------
    int
        The number of times build and submit were run again.
    """
    click.echo(
        click.style("●", fg="green")
        + f" {newly_finished} finished in this pass: running build and submit again"
        " so that what needs them can start"
    )
    limit = per_pass_limit()
    known = _finished_analyses(event)
    reruns = 0
    while reruns < CHAIN_MAX_RERUNS:
        remaining = None
        if limit is not None:
            remaining = limit - submitted
            if remaining <= 0:
                click.echo("The submission limit for this pass has been reached")
                break
        reruns += 1
        submitted += _run_build_and_submit(ctx, event, max_submit=remaining)
        now = _finished_analyses(event)
        if not now - known:
            break
        known = now
    return reruns


#: Exit codes of ``monitor --chain --until-idle``.
EXIT_IDLE_COMPLETE = 0   # nothing is running or can start, and everything finished
EXIT_IDLE_INCOMPLETE = 1  # nothing is running or can start, but not everything finished
EXIT_GAVE_UP = 2         # --max-passes or --timeout was reached while work continued
EXIT_NO_SCHEDULER = 3    # the scheduler could not be queried

_DONE_STATES = frozenset({"finished", "uploaded", "complete"})
#: Statuses which mean an analysis is deliberately not going to run.
_INACTIVE_STATES = frozenset({"cancelled", "stop"})


def _status_counts(event):
    """Count the analyses by status, for the subjects and project analyses."""
    counts = {}
    analyses = [a for subject in ledger.get_event(event) for a in subject.productions]
    if event is None:
        analyses += list(ledger.project_analyses)
    for analysis in analyses:
        counts[analysis.status] = counts.get(analysis.status, 0) + 1
    return counts


def _summarise(counts):
    return ", ".join(f"{n} {status}" for status, n in sorted(counts.items())) or "no analyses"


def _monitor_until_idle(ctx, event, update, dry_run, interval, max_passes, timeout):
    """
    Run ``monitor --chain`` repeatedly, in the foreground, until it is idle.

    The project is idle when a pass has nothing running or processing, and
    neither started nor finished anything. What is left is then either
    complete or blocked (failed, stuck, or waiting on something which will
    never finish), which the summary and the exit code say.

    Returns
    -------
    int
        The exit code: ``EXIT_IDLE_COMPLETE``, ``EXIT_IDLE_INCOMPLETE``,
        ``EXIT_GAVE_UP`` or ``EXIT_NO_SCHEDULER``.
    """
    started = time.monotonic()
    passes = 0
    while True:
        passes += 1
        click.secho(f"Pass {passes}", bold=True)
        try:
            result = ctx.invoke(
                monitor, event=event, update=update, dry_run=dry_run,
                chain=True, until_idle=False,
            )
        except SystemExit:
            click.echo(click.style("●", fg="red") + " The scheduler could not be queried")
            return EXIT_NO_SCHEDULER
        result = result or {}
        counts = _status_counts(event)
        click.echo(f"After pass {passes}: {_summarise(counts)}")

        working = any(counts.get(state) for state in RUNNING_STATES)
        progressed = result.get("submitted", 0) or result.get("newly_finished", 0)
        if not working and not progressed:
            break
        if dry_run:
            # Nothing changes in a dry run, so another pass would be identical.
            break
        if max_passes is not None and passes >= max_passes:
            click.echo(f"Stopping after {passes} passes with work still going")
            return EXIT_GAVE_UP
        if timeout is not None and time.monotonic() - started + interval > timeout:
            click.echo(f"Stopping after {timeout:g} seconds with work still going")
            return EXIT_GAVE_UP
        time.sleep(interval)

    unfinished = {
        status: n for status, n in counts.items()
        if status not in _DONE_STATES and status not in _INACTIVE_STATES
    }
    if unfinished:
        click.echo(
            click.style("●", fg="yellow")
            + f" Idle after {passes} passes, but not everything finished: {_summarise(unfinished)}"
        )
        return EXIT_IDLE_INCOMPLETE
    click.echo(click.style("●", fg="green") + f" Idle after {passes} passes: everything finished")
    return EXIT_IDLE_COMPLETE


def _as_monitor(command):
    """Run a command with changes attributed to the monitor, not a person."""

    @functools.wraps(command)
    def wrapper(*args, **kwargs):
        with acting_as(Principal.monitor()):
            return command(*args, **kwargs)

    return wrapper


@click.argument("event", default=None, required=False)
@click.option(
    "--update",
    "update",
    default=False,
    help="Force the git repos to be pulled before submission occurs.",
)
@click.option("--dry-run", "-n", "dry_run", is_flag=True)
@click.option(
    "--chain",
    "-c",
    "chain",
    default=False,
    is_flag=True,
    help="Chain multiple asimov commands",
)
@click.option(
    "--until-idle",
    "until_idle",
    is_flag=True,
    default=False,
    help="With --chain, keep running passes in the foreground until nothing is "
    "running or can start. Exits 0 if everything finished, 1 if some did not, "
    "2 if --max-passes or --timeout was reached.",
)
@click.option(
    "--interval", default=30.0, show_default=True, type=click.FloatRange(min=0),
    help="Seconds to wait between passes with --until-idle.",
)
@click.option(
    "--max-passes", default=None, type=click.IntRange(min=1),
    help="With --until-idle, the most passes to run.",
)
@click.option(
    "--timeout", default=None, type=click.FloatRange(min=0),
    help="With --until-idle, the most seconds to keep going for.",
)
@click.command()
@click.pass_context
@_as_monitor
def monitor(ctx, event, update, dry_run, chain, until_idle, interval, max_passes, timeout):
    """
    Monitor condor jobs' status, and collect logging information.
    """
    if until_idle:
        if not chain:
            raise click.UsageError("--until-idle needs --chain")
        sys.exit(
            _monitor_until_idle(ctx, event, update, dry_run, interval, max_passes, timeout)
        )

    from asimov import setup_file_logging
    setup_file_logging()

    def _webdir_for(subject_name, production_name):
        webroot = Path(resolve_path(config.get("general", "webroot")))
        return webroot / subject_name / production_name / "pesummary"

    def _has_pesummary_outputs(webdir: Path) -> bool:
        """Detect PESummary outputs when the default sentinel is missing."""
        posterior = webdir / "samples" / "posterior_samples.h5"
        if posterior.exists():
            return True
        # Accept legacy pesummary.dat as fallback
        legacy = webdir / "samples" / f"{webdir.parent.name}_pesummary.dat"
        if legacy.exists():
            return True
        return False

    logger.info("Running asimov monitor")
    initialize_telemetry_sinks()

    # Initialize labellers from ledger configuration
    from asimov.monitor_helpers import initialize_labellers
    initialize_labellers(ledger)

    # ``event`` is reused as a loop variable below.
    event_filter = event
    submitted = 0
    newly_finished = 0

    if chain:
        logger.info("Running in chain mode")
        submitted = _run_build_and_submit(ctx, event_filter)

    try:
        # Get the job listing using the new scheduler API
        job_list = get_job_list()
    except RuntimeError as e:
        click.echo(click.style(f"Could not query the scheduler: {e}", bold=True))
        click.echo(
            "You need to run asimov on a machine which has access to a"
            "scheduler in order to work correctly, or to specify"
            "the address of a valid scheduler."
        )
        sys.exit()
    except Exception as e:
        # Fall back to legacy CondorJobList for backward compatibility
        logger.warning(f"Failed to use new JobList, falling back to legacy: {e}")
        try:
            job_list = condor.CondorJobList()
        except Exception as locate_error:
            # Handle both HTCondor 1 and 2 exceptions
            error_name = type(locate_error).__name__
            if "Locate" in error_name or "locate" in str(locate_error).lower():
                click.echo(click.style("Could not find the scheduler", bold=True))
                click.echo(
                    "You need to run asimov on a machine which has access to a"
                    "scheduler in order to work correctly, or to specify"
                    "the address of a valid scheduler."
                )
                sys.exit()
            else:
                # Re-raise if it's not a locate error
                raise

    # also check the analyses in the project analyses
    for analysis in ledger.project_analyses:
        click.secho(f"Subjects: {analysis.subjects}", bold=True)
        
        if analysis.status.lower() in ACTIVE_STATES:
            was_finished = analysis.finished
            monitor_analysis(
                analysis=analysis,
                job_list=job_list,
                ledger=ledger,
                dry_run=dry_run,
                analysis_path=f"project_analyses/{analysis.name}"
            )
            newly_finished += int(analysis.finished and not was_finished)

    all_analyses = set(ledger.project_analyses)
    complete = {
        analysis
        for analysis in ledger.project_analyses
        if analysis.status in {"finished", "uploaded", "processing"}
    }
    others = all_analyses - complete
    if len(others) > 0:
        click.echo(
            "There are also these analyses waiting for other analyses to complete:"
        )
        for analysis in others:
            needs = ", ".join(analysis._needs)
            click.echo(f"\t{analysis.name} which needs {needs}")

    # need to check for post monitor hooks for each of the analyses
    for analysis in ledger.project_analyses:
        # check for post monitoring
        if "hooks" in ledger.data:
            if "postmonitor" in ledger.data["hooks"]:
                discovered_hooks = entry_points(group="asimov.hooks.postmonitor")

                for hook in discovered_hooks:
                    # do not run cbcflow every time
                    if hook.name in list(
                        ledger.data["hooks"]["postmonitor"].keys()
                    ) and hook.name not in ["cbcflow"]:
                        try:
                            hook.load()(deepcopy(ledger)).run()
                        except Exception:
                            pass

    # Once per pass, not once per project analysis: the report covers the
    # whole project and is by far the most expensive step here.
    if chain:
        ctx.invoke(report.html)

    for event in sorted(ledger.get_event(event), key=lambda e: e.name):
        click.secho(f"{event.name}", bold=True)
        on_deck = [
            production
            for production in event.productions
            if production.status.lower() in ACTIVE_STATES
        ]

        for production in on_deck:
            was_finished = production.finished
            monitor_analysis(
                analysis=production,
                job_list=job_list,
                ledger=ledger,
                dry_run=dry_run,
                analysis_path=f"{event.name}/{production.name}"
            )
            newly_finished += int(production.finished and not was_finished)

        ledger.update_event(event)

        # Auto-refresh combined summary pages (SubjectAnalysis) when stale and refreshable
        try:
            from asimov.analysis import SubjectAnalysis
        except (ImportError, ModuleNotFoundError):
            SubjectAnalysis = None

        if SubjectAnalysis:
            for prod in event.productions:
                try:
                    if isinstance(prod, SubjectAnalysis):
                        if getattr(prod, "is_refreshable", False) and prod.source_analyses_ready():
                            current_names = [prod._qualified_name(a) for a in getattr(prod, "analyses", [])]
                            resolved = getattr(prod, "resolved_dependencies", None) or []

                            # For SubjectAnalysis with smart dependencies (_analysis_spec),
                            # the analyses list is automatically populated by dependency matching.
                            # We should NOT manually add candidates; just check if the set changed.
                            # For legacy explicit name lists, we may need to sync, but smart
                            # dependencies handle this automatically during initialization.

                            # Check if dependency set changed
                            if set(current_names) != set(resolved):
                                click.echo(
                                    "  \t  "
                                    + click.style("●", "yellow")
                                    + f" {prod.name} has new/changed analyses; refreshing combined summary pages"
                                )
                                try:
                                    cluster_id = prod.pipeline.submit_dag()
                                    prod.status = "processing"
                                    prod.job_id = cluster_id
                                    ledger.update_event(event)
                                    click.echo(
                                        "  \t  "
                                        + click.style("●", "green")
                                        + f" {prod.name} submitted (cluster {cluster_id})"
                                    )
                                except Exception as exc:
                                    logger.warning("Failed to refresh %s: %s", prod.name, exc)
                                    click.echo(
                                        "  \t  "
                                        + click.style("●", "red")
                                        + f" {prod.name} refresh failed: {exc}"
                                    )
                except Exception:
                    pass

        all_productions = set(event.productions)
        complete = {
            production
            for production in event.productions
            if production.status in {"finished", "uploaded", "processing", "complete"}
        }
        others = all_productions - set(event.get_all_latest()) - complete
        if len(others) > 0:
            click.echo(
                "The event also has these analyses which are waiting on other analyses to complete:"
            )
            for production in others:
                # Make dependency specs readable even when _needs contains nested lists/dicts
                try:
                    formatted_needs = list(production.dependencies)
                except Exception:
                    formatted_needs = []

                if not formatted_needs:
                    def _fmt_need(need):
                        if isinstance(need, list):
                            return " & ".join(_fmt_need(n) for n in need)
                        if isinstance(need, dict):
                            return ", ".join(f"{k}: {v}" for k, v in need.items())
                        return str(need)

                    formatted_needs = [_fmt_need(need) for need in getattr(production, "_needs", [])]

                needs = ", ".join(formatted_needs) if formatted_needs else "(no unmet dependencies recorded)"
                click.echo(f"\t{production.name} which needs {needs}")
        # Post-monitor hooks
        if "hooks" in ledger.data:
            if "postmonitor" in ledger.data["hooks"]:
                discovered_hooks = entry_points(group="asimov.hooks.postmonitor")
                for hook in discovered_hooks:
                    # do not run cbcflow every time
                    if hook.name in list(
                        ledger.data["hooks"]["postmonitor"].keys()
                    ) and hook.name not in ["cbcflow"]:
                        try:
                            hook.load()(deepcopy(ledger)).run()
                        except Exception as exc:
                            logger.warning("%s experienced %s", hook.name, type(exc))
                            traceback_lines = traceback.format_exc().splitlines()
                            traceback_text = "Traceback:\n" + "\n".join(traceback_lines)
                            logger.warning(traceback_text)

        if chain:
            ctx.invoke(report.html)

    # What needs an analysis which has just finished can start in this pass.
    if chain and not dry_run and newly_finished:
        if _settle_chain_pass(ctx, event_filter, newly_finished, submitted):
            ctx.invoke(report.html)

    # run the cbcflow hook once to update all the info if needed
    if "hooks" in ledger.data:
        if "postmonitor" in ledger.data["hooks"]:
            discovered_hooks = entry_points(group="asimov.hooks.postmonitor")
            for hook in discovered_hooks:
                if hook.name == "cbcflow":
                    logger.info("Found cbcflow postmonitor hook, trying to run it")
                    try:
                        hook.load()(deepcopy(ledger)).run()
                    except Exception:
                        logger.warning("Unable to run the cbcflow hook")

    return {"submitted": submitted, "newly_finished": newly_finished}
