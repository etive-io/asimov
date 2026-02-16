"""
Olivaw management commands
"""

import os
import pathlib

import click

from asimov import current_ledger as ledger
import asimov
from asimov import condor
from asimov import LOGGER_LEVEL
from asimov.event import DescriptionException
from asimov.pipeline import PipelineException
from asimov.git import EventRepo


@click.group(chain=True)
def manage():
    """Perform management tasks such as job building and submission."""
    pass


@click.option(
    "--event",
    "event",
    default=None,
    help="The event which the ledger should be returned for, optional.",
)
@click.option(
    "--dryrun",
    "-d",
    "dryrun",
    is_flag=True,
    default=False,
    help="Print all commands which will be executed without running them",
)
@manage.command()
def build(event, dryrun):
    """
    Create the run configuration files for a given event for jobs which are ready to run.
    If no event is specified then all of the events will be processed.
    """
    logger = asimov.logger.getChild("cli").getChild("manage.build")
    logger.setLevel(LOGGER_LEVEL)

    for analysis in ledger.project_analyses:
        if analysis.status in {"ready"}:
            # Need to ensure a directory exists for these!
            subj_string = "_".join([f"{subject}" for subject in analysis._subjects])
            project_analysis_dir = os.path.join(
                "checkouts", "project-analyses", subj_string
            )
            if not os.path.exists(project_analysis_dir):
                os.makedirs(project_analysis_dir)
            click.echo(
                click.style("●", fg="green")
                + f" Building project analysis {analysis.name}"
            )

            analysis.pipeline.before_config()

            analysis.make_config(
                filename=os.path.join(project_analysis_dir, f"{analysis.name}.ini"),
                dryrun=dryrun,
            )
            click.echo(
                click.style("●", fg="green")
                + f" Created configuration for {analysis.name}"
            )

    for event in ledger.get_event(event):

        click.echo(f"● Working on {event.name}")
        ready_productions = event.get_all_latest()
        for production in ready_productions:
            logger.info(f"{event.name}/{production.name}")
            click.echo(f"\tWorking on production {production.name}")
            if production.status in {
                "running",
                "stuck",
                "wait",
                "finished",
                "uploaded",
                "cancelled",
                "stopped",
            }:
                if dryrun:
                    click.echo(
                        click.style("●", fg="yellow")
                        + f" {production.name} is marked as {production.status.lower()} so no action will be performed"
                    )
                continue  # I think this test might be unused
            try:
                ini_loc = production.event.repository.find_prods(
                    production.name, production.category
                )[0]
                if not os.path.exists(ini_loc):
                    raise KeyError
            except KeyError:
                try:

                    # if production.rundir:
                    #     path = pathlib.Path(production.rundir)
                    # else:
                    #     path = pathlib.Path(config.get("general", "rundir_default"))

                    if dryrun:
                        print(f"Will create {production.name}.ini")
                    else:
                        # path.mkdir(parents=True, exist_ok=True)
                        config_loc = os.path.join(f"{production.name}.ini")
                        production.pipeline.before_config()
                        production.make_config(config_loc, dryrun=dryrun)
                        click.echo(f"Production config {production.name} created.")
                        try:
                            event.repository.add_file(
                                config_loc,
                                os.path.join(
                                    f"{production.category}", f"{production.name}.ini"
                                ),
                            )
                            logger.info(
                                "Configuration committed to event repository.",
                            )
                            ledger.update_event(event)

                        except Exception as e:
                            logger.error(
                                f"Configuration could not be committed to repository.\n{e}",
                            )
                            logger.exception(e)
                        os.remove(config_loc)

                except DescriptionException as e:
                    logger.error("Run configuration failed")
                    logger.exception(e)


@click.option(
    "--event",
    "event",
    default=None,
    help="The event which the ledger should be returned for, optional.",
)
@click.option(
    "--update",
    "update",
    default=False,
    help="Force the git repos to be pulled before submission occurs.",
)
@click.option(
    "--dryrun",
    "-d",
    "dryrun",
    is_flag=True,
    default=False,
    help="Print all commands which will be executed without running them",
)
@manage.command()
def submit(event, update, dryrun):
    """
    Submit the run configuration files for a given event for jobs which are ready to run.
    If no event is specified then all of the events will be processed.
    """
    logger = asimov.logger.getChild("cli").getChild("manage.submit")
    logger.setLevel(LOGGER_LEVEL)

    # this should add the required repository field to the project analysis
    # with the correct type
    # FIXME: for now, this only accountd for the case where we have multiple analysis
    # done but not yet several productions for the same event and pipelines. This would
    # require extra checks when adding to the dictionary
    interest_dict = {}
    for analysis in ledger.project_analyses:
        if analysis.pipeline.name not in interest_dict.keys():
            interest_dict[analysis.pipeline.name] = []
        if "interest status" in analysis.meta.keys():
            interest_dict[analysis.pipeline.name].append(
                {
                    "interest status": analysis.meta["interest status"],
                    "subjects": set(analysis._subjects),
                }
            )

    for analysis in ledger.project_analyses:
        # need to change the logic of analysis set up as to account for
        # dependencies
        to_analyse = True
        extra_prio = False
        if analysis.status not in {"ready"}:
            to_analyse = False
        elif analysis._needs:
            # check if the parent jobs are said to be interesting
            # this does not account for the old logic in the project analyses
            interested_pipelines = 0
            for old_analysis in analysis._needs:
                if old_analysis in interest_dict.keys():
                    if len(interest_dict[old_analysis]) > 0:
                        for cases in interest_dict[old_analysis]:
                            if cases["interest status"] is True and cases[
                                "subjects"
                            ] == set(analysis._subjects):
                                interested_pipelines += 1
            if interested_pipelines < int(analysis.meta["needs settings"]["minimum"]):
                to_analyse = False

            # check if we need to account for extra priority comming from atlenstics
            if "extra priority" in analysis.meta["needs settings"].keys():
                if (
                    analysis.meta["needs settings"]["extra priority"]
                    == "atlenstics_compatibility"
                ):
                    # we need to verify if extra priority is needed
                    if "atlenstics_compatibility" in interest_dict.keys():
                        # need to add a check on the length of the list to avoid some failures
                        if len(interest_dict["atlenstics_compatibility"]) > 0:
                            if (
                                interest_dict["atlenstics_compatibility"][0][
                                    "interest status"
                                ]
                                is True
                            ):
                                extra_prio = True
        running_and_requiring_priority_check = False
        if analysis.status in {"running"} and analysis._needs:
            if "needs settings" in analysis.meta.keys():
                if "logic" in analysis.meta["needs settings"]:
                    if analysis.meta["needs settings"]["logic"] == "add_priority":
                        running_and_requiring_priority_check = True

        if to_analyse:
            # Need to ensure a directory exists for these!
            subjects = analysis._subjects
            subj_string = "_".join([f"{subjects[i]}" for i in range(len(subjects))])
            project_analysis_dir = os.path.join(
                "checkouts",
                "project-analyses",
                subj_string,
            )
            if analysis.repository is None:
                analysis.repository = EventRepo.create(project_analysis_dir)
            else:
                if isinstance(analysis.repository, str):
                    if (
                        "git@" in analysis.repository
                        or "https://" in analysis.repository
                    ):
                        analysis.repository = EventRepo.from_url(
                            analysis.repository,
                            analysis.event.name,
                            directory=None,
                            update=update,
                        )
                    else:
                        analysis.repository = EventRepo.create(analysis.repository)

            click.echo(
                click.style("●", fg="green")
                + f" Submitting project analysis {analysis.name}"
            )
            pipe = analysis.pipeline
            try:
                pipe.build_dag(dryrun=dryrun)
            except PipelineException as e:
                logger.error(
                    "The pipeline failed to build a DAG file.",
                )
                logger.exception(e)
                click.echo(
                    click.style("●", fg="red") + f" Failed to submit {analysis.name}"
                )
            except ValueError:
                logger.info("Unable to submit an unbuilt project analysis")
                click.echo(
                    click.style("●", fg="red")
                    + f" Unable to submit {analysis.name} as it hasn't been built yet."
                )
                click.echo("Try running `asimov manage build` first.")
            try:
                pipe.submit_dag(dryrun=dryrun)
                if not dryrun:
                    click.echo(
                        click.style("●", fg="green") + f" Submitted {analysis.name}"
                    )
                    analysis.status = "running"
                    ledger.update_analysis_in_project_analysis(analysis)

                    # directly add the extra priority related if needed
                    if extra_prio:
                        job_id = analysis.scheduler["job id"]
                        extra_prio = 20
                        condor.change_job_priority(job_id, extra_prio, use_old=False)

            except PipelineException as e:
                analysis.status = "stuck"
                click.echo(
                    click.style("●", fg="red") + f" Unable to submit {analysis.name}"
                )
                logger.exception(e)
                ledger.update_analysis_in_project_analysis(analysis)
                ledger.save()
                logger.error(
                    f"The pipeline failed to submit the DAG file to the cluster. {e}",
                )
            if not dryrun:
                # Refresh the job list
                job_list = condor.CondorJobList()
                job_list.refresh()
                # Update the ledger
                ledger.save()

        else:
            click.echo(
                click.style("●", fg="yellow")
                + f"Project analysis {analysis.name} not ready to submit"
            )

        # addition to see if we need to adjust the priority of a running job
        if running_and_requiring_priority_check:
            # enquire about the old priority
            try:
                current_prio = int(
                    condor.get_job_priority(analysis.meta["scheduler"]["job id"])
                )
            except TypeError:
                # can happen when the job has done running
                current_prio = 0

            # calculate the priority it is expected to have
            interested_pipelines = 0
            for old_analysis in analysis._needs:
                if old_analysis in interest_dict.keys():
                    if len(interest_dict[old_analysis]) > 0:
                        if interest_dict[old_analysis][-1]["interest status"] is True:
                            interested_pipelines += 1
            if interested_pipelines < 2:
                theoretical_prio = 0
            else:
                theoretical_prio = int((interested_pipelines - 2) * 10)
            extra_prio = False
            if "extra priority" in analysis.meta["needs settings"].keys():
                if (
                    analysis.meta["needs settings"]["extra priority"]
                    == "atlenstics_compatibility"
                ):
                    # we need to verify if extra priority is needed
                    if "atlenstics_compatibility" in interest_dict.keys():
                        if len(interest_dict["atlenstics_compatibility"]) > 0:
                            if (
                                interest_dict["atlenstics_compatibility"][0][
                                    "interest status"
                                ]
                                is True
                            ):
                                extra_prio = True
            if extra_prio:
                theoretical_prio += 20

            # check if we currently have the correct priority or if an adaptation is needed

            if theoretical_prio != current_prio:
                logger.info(
                    f"Adjusting priority of {analysis.name} from {current_prio} to {theoretical_prio}"
                )
                condor.change_job_priority(
                    analysis.meta["scheduler"]["job id"],
                    theoretical_prio,
                    use_old=False,
                )

    for event in ledger.get_event(event):
        ready_productions = event.get_all_latest()
        for production in ready_productions:
            logger.info(f"{event.name}/{production.name}")
            if production.status.lower() in {
                "running",
                "stuck",
                "wait",
                "processing",
                "uploaded",
                "finished",
                "manual",
                "cancelled",
                "stopped",
            }:
                if dryrun:
                    click.echo(
                        click.style("●", fg="yellow")
                        + f" {production.name} is marked as {production.status.lower()} so no action will be performed"
                    )
                continue
            if production.status.lower() == "restart":
                pipe = production.pipeline
                try:
                    pipe.clean(dryrun=dryrun)
                except PipelineException as e:
                    logger.error("The pipeline failed to clean up after itself.")
                    logger.exception(e)
                pipe.submit_dag(dryrun=dryrun)
                click.echo(
                    click.style("●", fg="green")
                    + f" Resubmitted {production.event.name}/{production.name}"
                )
                production.status = "running"
            else:
                pipe = production.pipeline
                try:
                    pipe.build_dag(dryrun=dryrun)
                except PipelineException as e:
                    logger.error(
                        "failed to build a DAG file.",
                    )
                    logger.exception(e)
                    click.echo(
                        click.style("●", fg="red")
                        + f" Unable to submit {production.name}"
                    )
                except ValueError:
                    logger.info("Unable to submit an unbuilt production")
                    click.echo(
                        click.style("●", fg="red")
                        + f" Unable to submit {production.name} as it hasn't been built yet."
                    )
                    click.echo("Try running `asimov manage build` first.")
                try:
                    pipe.submit_dag(dryrun=dryrun)
                    if not dryrun:
                        click.echo(
                            click.style("●", fg="green")
                            + f" Submitted {production.event.name}/{production.name}"
                        )
                        production.status = "running"

                except PipelineException as e:
                    production.status = "stuck"
                    click.echo(
                        click.style("●", fg="red")
                        + f" Unable to submit {production.name}"
                    )
                    logger.exception(e)
                    ledger.update_event(event)
                    logger.error(
                        f"The pipeline failed to submit the DAG file to the cluster. {e}",
                    )
                if not dryrun:
                    # Refresh the job list
                    job_list = condor.CondorJobList()
                    job_list.refresh()
                    # Update the ledger
                    ledger.update_event(event)


@click.option(
    "--event",
    "event",
    default=None,
    help="The event which the ledger should be returned for, optional.",
)
@click.option(
    "--update",
    "update",
    default=False,
    help="Force the git repos to be pulled before submission occurs.",
)
@manage.command()
def results(event, update):
    """
    Find all available results for a given event.
    """
    for event in ledger.get_event(event):
        click.secho(f"{event.name}")
        for production in event.productions:
            click.echo(f"\t- {production.name}")
            try:
                for result, meta in production.results().items():
                    click.echo(
                        f"- {production.event.name}/{production.name}/{result}, {production.results(result)}"
                    )
            except Exception:
                click.echo("\t  (No results available)")


@click.option(
    "--event",
    "event",
    default=None,
    help="The event which the ledger should be returned for, optional.",
)
@click.option(
    "--update",
    "update",
    default=False,
    help="Force the git repos to be pulled before submission occurs.",
)
@click.option("--root", "root")
@manage.command()
def resultslinks(event, update, root):
    """
    Find all available results for a given event.
    """
    for event in ledger.get_event(event):
        click.secho(f"{event.name}")
        for production in event.productions:
            try:
                for result, meta in production.results().items():
                    print(
                        f"{production.event.name}/{production.name}/{result}, {production.results(result)}"
                    )
                    pathlib.Path(
                        os.path.join(root, production.event.name, production.name)
                    ).mkdir(parents=True, exist_ok=True)
                    os.symlink(
                        f"{production.results(result)}",
                        f"{root}/{production.event.name}/{production.name}/{result.split('/')[-1]}",
                    )
            except AttributeError:
                pass
