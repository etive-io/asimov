import shutil
import configparser
import sys
import traceback
import os
import click
from copy import deepcopy
from pathlib import Path

from asimov import condor, config, logger, LOGGER_LEVEL
from asimov import current_ledger as ledger
from asimov.cli import ACTIVE_STATES, manage, report
from asimov.scheduler_utils import get_configured_scheduler, create_job_from_dict, get_job_list
from asimov.monitor_helpers import monitor_analysis

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
    from asimov import setup_file_logging
    setup_file_logging()

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
    from asimov import setup_file_logging
    setup_file_logging()
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
    from asimov import setup_file_logging
    setup_file_logging()

    def _webdir_for(subject_name, production_name):
        webroot = Path(config.get("general", "webroot"))
        if not webroot.is_absolute():
            webroot = Path(config.get("project", "root")) / webroot
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
            monitor_analysis(
                analysis=analysis,
                job_list=job_list,
                ledger=ledger,
                dry_run=dry_run,
                analysis_path=f"project_analyses/{analysis.name}"
            )

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
            monitor_analysis(
                analysis=production,
                job_list=job_list,
                ledger=ledger,
                dry_run=dry_run,
                analysis_path=f"{event.name}/{production.name}"
            )

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
                            current_names = [a.name for a in getattr(prod, "analyses", [])]
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
            if production.status in {"finished", "uploaded", "processing"}
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
