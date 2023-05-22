import shutil
import configparser
import sys
import click

from asimov import condor, config, logger, LOGGER_LEVEL
from asimov import current_ledger as ledger
from asimov.cli import ACTIVE_STATES, manage, report

logger = logger.getChild("cli").getChild("monitor")
logger.setLevel(LOGGER_LEVEL)

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points


@click.option("--dry-run", "-n", "dry_run", is_flag=True)
@click.command()
def start(dry_run):
    """Set up a cron job on condor to monitor the project."""

    try:
        minute_expression = config.get("asimov start", "cron_minute")
    except (configparser.NoOptionError, configparser.NoSectionError):
        minute_expression = "*/15"

    submit_description = {
        "executable": shutil.which("asimov"),
        "arguments": "monitor --chain",
        "accounting_group_user": config.get('condor', 'user'),
        "accounting_group": config.get("asimov start", "accounting"),
        "output": "asimov_cron.out",
        "on_exit_remove": "false",
        "universe": "local",
        "error": "asimov_cron.err",
        "log": "asimov_cron.log",
        "request_cpus": "1",
        "cron_minute": minute_expression,
        "getenv": "true",
        "batch_name": f"asimov/monitor/{ledger.data['project']['name']}",
        "request_memory": "8192MB",
        "request_disk": "8192MB",
    }
    cluster = condor.submit_job(submit_description)
    ledger.data["cronjob"] = cluster
    ledger.save()
    click.secho(f"  \t  ● Asimov is running ({cluster})", fg="green")
    logger.info(f"Running asimov cronjob as  {cluster}")


@click.option("--dry-run", "-n", "dry_run", is_flag=True)
@click.command()
def stop(dry_run):
    """Set up a cron job on condor to monitor the project."""
    cluster = ledger.data["cronjob"]
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
        # First pull the condor job listing
        job_list = condor.CondorJobList()
    except condor.htcondor.HTCondorLocateError:
        click.echo(click.style("Could not find the condor scheduler", bold=True))
        click.echo(
            "You need to run asimov on a machine which has access to a"
            "condor scheduler in order to work correctly, or to specify"
            "the address of a valid sceduler."
        )
        sys.exit()

    for event in ledger.get_event(event):
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
                if "job id" in production.meta:
                    if not dry_run:
                        if production.meta["job id"] in job_list.jobs:
                            job = job_list.jobs[production.meta["job id"]]
                        else:
                            job = None
                    else:
                        logger.debug(
                            f"Running analysis: {event}/{production.name}, cluster {production.meta['job id']}"
                        )
                        click.echo("\t\tRunning under condor")
                else:
                    raise ValueError  # Pass to the exception handler

                if not dry_run:

                    if (
                        job.status.lower() == "running"
                        and production.status == "processing"
                    ):
                        click.echo(
                            "  \t  "
                            + click.style("●", "green")
                            + f" Postprocessing for {production.name} is running"
                            + f" (condor id: {production.meta['job id']})"
                        )

                    elif (
                        job.status.lower() == "running"
                        and production.status == "processing"
                    ):
                        click.echo(
                            "  \t  "
                            + click.style("●", "green")
                            + f" {production.name} is postprocessing (condor id: {production.meta['job id']})"
                        )
                        production.meta["postprocessing"]["status"] = "running"

                    elif job.status.lower() == "running":
                        click.echo(
                            "  \t  "
                            + click.style("●", "green")
                            + f" {production.name} is running (condor id: {production.meta['job id']})"
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
                            + f" (condor id: {production.meta['job id']})"
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
                                + f" is stuck ({production.meta['job id']})"
                            )
                            production.meta["postprocessing"]["status"] = "stuck"
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
                            production.meta["profiling"] = condor.collect_history(
                                production.meta["job id"]
                            )
                            production.meta["job id"] = None
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
                        except Exception:  # Sorry, but there are many ways the above command can fail
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
                needs = ", ".join(production.meta["needs"])
                click.echo(f"\t{production.name} which needs {needs}")

        # Post-monitor hooks
        if "hooks" in ledger.data:
            discovered_hooks = entry_points(group="asimov.hooks.postmonitor")
            for hook in discovered_hooks:
                if hook.name in list(ledger.data["hooks"]["postmonitor"].keys()):
                    hook.load()(ledger).run()

        if chain:
            ctx.invoke(report.html)
