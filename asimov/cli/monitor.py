import shutil
import configparser
import sys
import traceback
import os
import click
from copy import deepcopy

from asimov import condor, config, logger, LOGGER_LEVEL
from asimov import current_ledger as ledger
from asimov.cli import ACTIVE_STATES, manage, report
from asimov.scheduler_utils import get_configured_scheduler, create_job_from_dict, get_job_list

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
    """Set up a cron job on condor to monitor the project."""

    try:
        minute_expression = config.get("condor", "cron_minute")
    except (configparser.NoOptionError, configparser.NoSectionError):
        minute_expression = "*/15"

    submit_description = {
        "executable": shutil.which("asimov"),
        "arguments": "monitor --chain",
        "accounting_group": config.get("asimov start", "accounting"),
        "output": os.path.join(".asimov", "asimov_cron.out"),
        "on_exit_remove": "false",
        "universe": "local",
        "error": os.path.join(".asimov", "asimov_cron.err"),
        "log": os.path.join(".asimov", "asimov_cron.log"),
        "request_cpus": "1",
        "cron_minute": minute_expression,
        "getenv": "true",
        "batch_name": f"asimov/monitor/{ledger.data['project']['name']}",
        "request_memory": "8192MB",
        "request_disk": "8192MB",
        "+flock_local": "False",
        "+DESIRED_Sites": "nogrid",
    }

    try:
        submit_description["accounting_group_user"] = config.get("condor", "user")
        if "asimov start" in config:
            submit_description["accounting_group"] = config["asimov start"].get(
                "accounting"
            )
        else:
            submit_description["accounting_group"] = config["condor"].get("accounting")
    except (configparser.NoOptionError, configparser.NoSectionError):
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


@click.option("--dry-run", "-n", "dry_run", is_flag=True)
@click.option("--use-scheduler-api", is_flag=True, default=False,
              help="Use the new scheduler API directly (experimental)")
@click.command()
def stop(dry_run, use_scheduler_api):
    """Set up a cron job on condor to monitor the project."""
    cluster = ledger.data["cronjob"]
    
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
@click.command()
@click.pass_context
def monitor(ctx, event, update, dry_run, chain):
    """
    Monitor condor jobs' status, and collect logging information.
    """

    logger.info("Running asimov monitor")

    if chain:
        logger.info("Running in chain mode")
        ctx.invoke(manage.build, event=event)
        ctx.invoke(manage.submit, event=event)

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
        except condor.htcondor.HTCondorLocateError:
            click.echo(click.style("Could not find the scheduler", bold=True))
            click.echo(
                "You need to run asimov on a machine which has access to a"
                "scheduler in order to work correctly, or to specify"
                "the address of a valid scheduler."
            )
            sys.exit()

    # also check the analyses in the project analyses
    for analysis in ledger.project_analyses:
        click.secho(f"Subjects: {analysis.subjects}", bold=True)

        if analysis.status.lower() in ACTIVE_STATES:
            logger.debug(f"Available analyses:  project_analyses/{analysis.name}")

            click.echo(
                "\t- "
                + click.style(f"{analysis.name}", bold=True)
                + click.style(f"[{analysis.pipeline}]", fg="green")
            )

            # ignore the analysis if it is set to ready as it has not been started yet
            if analysis.status.lower() == "ready":
                click.secho(f"  \t  ● {analysis.status.lower()}", fg="green")
                logger.debug(f"Ready production: project_analyses/{analysis.name}")
                continue

            # check if there are jobs that need to be stopped
            if analysis.status.lower() == "stop":
                pipe = analysis.pipeline
                logger.debug(f"Stop production project_analyses/{analysis.name}")
                if not dry_run:
                    pipe.eject_job()
                    analysis.status = "stopped"
                    ledger.update_analysis_in_project_analysis(analysis)
                    click.secho("   \t Stopped", fg="red")
                else:
                    click.echo("\t\t{analysis.name} --> stopped")
                continue

            # deal with the condor jobs
            analysis_scheduler = analysis.meta["scheduler"].copy()
            try:
                if "job id" in analysis_scheduler:
                    if not dry_run:
                        if analysis_scheduler["job id"] in job_list.jobs:
                            job = job_list.jobs[analysis_scheduler["job id"]]
                        else:
                            job = None
                    else:
                        logger.debug(
                            f"Running analysis: {event}/{analysis.name}, cluster {analysis.job_id}"
                        )
                        click.echo("\t\tRunning under condor")
                else:
                    raise ValueError

                if not dry_run:
                    if job.status.lower() == "idle":
                        click.echo(
                            "  \t  "
                            + click.style("●", "green")
                            + f" {analysis.name} is in the queue (condor id: {analysis_scheduler['job id']})"
                        )

                    elif job.status.lower() == "running":
                        click.echo(
                            "  \t  "
                            + click.style("●", "green")
                            + f" {analysis.name} is running (condor id: {analysis_scheduler['job id']})"
                        )
                        if "profiling" not in analysis.meta:
                            analysis.meta["profiling"] = {}
                        if hasattr(analysis.pipeline, "while_running"):
                            analysis.pipeline.while_running()
                        analysis.status = "running"
                        ledger.update_analysis_in_project_analysis(analysis)

                    elif job.status.lower() == "completed":
                        pipe.after_completion()
                        click.echo(
                            "  \t  "
                            + click.style("●", "green")
                            + f" {analysis.name} has finished and post-processing has been started"
                        )
                        job_list.refresh()

                    elif job.status.lower() == "held":
                        click.echo(
                            "  \t  "
                            + click.style("●", "yellow")
                            + f" {analysis.name} is held on the scheduler"
                            + f" (condor id: {analysis_scheduler['job id']})"
                        )
                        analysis.status = "stuck"
                        ledger.update_analysis_in_project_analysis(analysis)
                    else:
                        continue

            except (ValueError, AttributeError):
                if analysis.pipeline:
                    pipe = analysis.pipeline
                    if analysis.status.lower() == "stop":
                        pipe.eject_job()
                        analysis.status = "stopped"
                        ledger.update_analysis_in_project_analysis(analysis)
                        click.echo(
                            "  \t  "
                            + click.style("●", "red")
                            + f" {analysis.name} has been stopped"
                        )
                        job_list.refresh()

                    elif analysis.status.lower() == "finished":
                        pipe.after_completion()
                        click.echo(
                            "  \t  "
                            + click.style("●", "green")
                            + f" {analysis.name} has finished and post-processing has been started"
                        )
                        job_list.refresh()

                    elif analysis.status.lower() == "processing":
                        if pipe.detect_completion_processing():
                            try:
                                pipe.after_processing()
                                click.echo(
                                    "  \t  "
                                    + click.style("●", "green")
                                    + f" {analysis.name} has been finalised and stored"
                                )
                            except ValueError as e:
                                click.echo(e)
                        else:
                            click.echo(
                                "  \t  "
                                + click.style("●", "green")
                                + f" {analysis.name} has finished and post-processing"
                                + f" is stuck ({analysis_scheduler['job id']})"
                            )

                    elif (
                        pipe.detect_completion()
                        and analysis.status.lower() == "processing"
                    ):
                        click.echo(
                            "  \t  "
                            + click.style("●", "green")
                            + f" {analysis.name} has finished and post-processing is running"
                        )

                    elif (
                        pipe.detect_completion()
                        and analysis.status.lower() == "running"
                    ):
                        if "profiling" not in analysis.meta:
                            analysis.meta["profiling"] = {}

                        try:
                            config.get("condor", "scheduler")
                            analysis.meta["profiling"] = condor.collect_history(
                                analysis_scheduler["job id"]
                            )
                            analysis_scheduler["job id"] = None
                            ledger.update_analysis_in_project_analysis(analysis)
                        except (
                            configparser.NoOptionError,
                            configparser.NoSectionError,
                        ):
                            logger.warning(
                                "Could not collect condor profiling data as no "
                                + "scheduler was specified in the config file."
                            )
                        except ValueError as e:
                            logger.error("Could not collect condor profiling data.")
                            logger.exception(e)
                            pass

                        analysis.status = "finished"
                        ledger.update_analysis_in_project_analysis(analysis)
                        pipe.after_completion()
                        click.secho(
                            f"  \t  ● {analysis.name} - Completion detected",
                            fg="green",
                        )
                        job_list.refresh()

                    else:
                        # job may have been evicted from the clusters
                        click.echo(
                            "  \t  "
                            + click.style("●", "yellow")
                            + f" {analysis.name} is stuck; attempting a rescue"
                        )
                        try:
                            pipe.resurrect()
                        except (
                            Exception
                        ):  # Sorry, but there are many ways the above command can fail
                            analysis.status = "stuck"
                            click.echo(
                                "  \t  "
                                + click.style("●", "red")
                                + f" {analysis.name} is stuck; automatic rescue was not possible"
                            )
                            ledger.update_analysis_in_project_analysis(analysis)

                if analysis.status == "stuck":
                    click.echo(
                        "  \t  "
                        + click.style("●", "yellow")
                        + f" {analysis.name} is stuck"
                    )

            ledger.update_analysis_in_project_analysis(analysis)
            ledger.save()
        if chain:
            ctx.invoke(report.html)

    all_analyses = set(ledger.project_analyses)
    complete = {
        analysis
        for analysis in ledger.project_analyses
        if analysis.status in {"finished", "uploaded"}
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

        if chain:
            ctx.invoke(report.html)

    for event in sorted(ledger.get_event(event), key=lambda e: e.name):
        stuck = 0
        running = 0
        finish = 0
        click.secho(f"{event.name}", bold=True)
        on_deck = [
            production
            for production in event.productions
            if production.status.lower() in ACTIVE_STATES
        ]

        for production in on_deck:
            logger.debug(f"Available analyses: {event}/{production.name}")
            click.echo(
                "\t- "
                + click.style(f"{production.name}", bold=True)
                + click.style(f"[{production.pipeline}]", fg="green")
            )

            # Jobs marked as ready can just be ignored as they've not been stood-up
            if production.status.lower() == "ready":
                click.secho(f"  \t  ● {production.status.lower()}", fg="green")
                logger.debug(f"Ready production: {event}/{production.name}")
                continue

            # Deal with jobs which need to be stopped first
            if production.status.lower() == "stop":
                pipe = production.pipeline
                logger.debug(f"Stop production: {event}/{production.name}")
                if not dry_run:
                    pipe.eject_job()
                    production.status = "stopped"
                    click.secho("  \tStopped", fg="red")
                else:
                    click.echo("\t\t{production.name} --> stopped")
                continue

            # Get the condor jobs
            try:
                if "job id" in production.meta["scheduler"]:
                    if not dry_run:
                        if production.job_id in job_list.jobs:
                            job = job_list.jobs[production.job_id]
                        else:
                            job = None
                    else:
                        logger.debug(
                            f"Running analysis: {event}/{production.name}, cluster {production.job_id}"
                        )
                        click.echo("\t\tRunning under condor")
                else:
                    raise ValueError  # Pass to the exception handler

                if not dry_run:
                    if job.status.lower() == "idle":
                        click.echo(
                            "  \t  "
                            + click.style("●", "green")
                            + f" {production.name} is in the queue (condor id: {production.job_id})"
                        )

                    elif job.status.lower() == "running":
                        click.echo(
                            "  \t  "
                            + click.style("●", "green")
                            + f" {production.name} is running (condor id: {production.job_id})"
                        )
                        if "profiling" not in production.meta:
                            production.meta["profiling"] = {}
                        production.status = "running"

                    elif job.status.lower() == "completed":
                        pipe.after_completion()
                        click.echo(
                            "  \t  "
                            + click.style("●", "green")
                            + f" {production.name} has finished and post-processing has been started"
                        )
                        job_list.refresh()

                    elif job.status.lower() == "held":
                        click.echo(
                            "  \t  "
                            + click.style("●", "yellow")
                            + f" {production.name} is held on the scheduler"
                            + f" (condor id: {production.job_id})"
                        )
                        production.status = "stuck"
                        stuck += 1
                    else:
                        running += 1

            except (ValueError, AttributeError):
                if production.pipeline:

                    pipe = production.pipeline

                    if production.status.lower() == "stop":
                        pipe.eject_job()
                        production.status = "stopped"
                        click.echo(
                            "  \t  "
                            + click.style("●", "red")
                            + f" {production.name} has been stopped"
                        )
                        job_list.refresh()
                    elif production.status.lower() == "finished":
                        pipe.after_completion()
                        click.echo(
                            "  \t  "
                            + click.style("●", "green")
                            + f" {production.name} has finished and post-processing has been started"
                        )
                        job_list.refresh()
                    elif production.status.lower() == "processing":
                        # Need to check the upload has completed
                        if pipe.detect_completion_processing():
                            try:
                                pipe.after_processing()
                                click.echo(
                                    "  \t  "
                                    + click.style("●", "green")
                                    + f" {production.name} has been finalised and stored"
                                )
                            except ValueError as e:
                                click.echo(e)
                        else:
                            click.echo(
                                "  \t  "
                                + click.style("●", "green")
                                + f" {production.name} has finished and post-processing"
                                + f" is stuck ({production.job_id})"
                            )
                    elif (
                        pipe.detect_completion()
                        and production.status.lower() == "processing"
                    ):
                        click.echo(
                            "  \t  "
                            + click.style("●", "green")
                            + f" {production.name} has finished and post-processing is running"
                        )
                    elif (
                        pipe.detect_completion()
                        and production.status.lower() == "running"
                    ):
                        # The job has been completed, collect its assets
                        if "profiling" not in production.meta:
                            production.meta["profiling"] = {}
                        try:
                            config.get("condor", "scheduler")
                            production.meta["profiling"] = condor.collect_history(
                                production.job_id
                            )
                            production.job_id = None
                        except (
                            configparser.NoOptionError,
                            configparser.NoSectionError,
                        ):
                            logger.warning(
                                "Could not collect condor profiling data as"
                                " no scheduler was specified in the"
                                " config file."
                            )
                        except ValueError as e:
                            logger.error("Could not collect condor profiling data.")
                            logger.exception(e)
                            pass

                        finish += 1
                        production.status = "finished"
                        pipe.after_completion()
                        click.secho(
                            f"  \t  ● {production.name} - Completion detected",
                            fg="green",
                        )
                        job_list.refresh()
                    else:
                        # It looks like the job has been evicted from the cluster
                        click.echo(
                            "  \t  "
                            + click.style("●", "yellow")
                            + f" {production.name} is stuck; attempting a rescue"
                        )
                        try:
                            pipe.resurrect()
                        except (
                            Exception
                        ):  # Sorry, but there are many ways the above command can fail
                            production.status = "stuck"
                            click.echo(
                                "  \t  "
                                + click.style("●", "red")
                                + f" {production.name} is stuck; automatic rescue was not possible"
                            )

                if production.status == "stuck":
                    click.echo(
                        "  \t  "
                        + click.style("●", "yellow")
                        + f" {production.name} is stuck"
                    )

            ledger.update_event(event)

        all_productions = set(event.productions)
        complete = {
            production
            for production in event.productions
            if production.status in {"finished", "uploaded"}
        }
        others = all_productions - set(event.get_all_latest()) - complete
        if len(others) > 0:
            click.echo(
                "The event also has these analyses which are waiting on other analyses to complete:"
            )
            for production in others:
                needs = ", ".join(production._needs)
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
