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

def check_priority_method(production):
    """         
    Check the priority method to be used for the production
                
    Args:           
    production: the production to be checked
                
    Returns:    
    the priority method to be used (between vanilla and is_interesting)
    """             
    if "needs settings" not in production.meta.keys():
        return "vanilla"
    else:   
        if "condition" in production.meta["needs settings"].keys():
            return production.meta["needs settings"]["condition"]
        else:   
            # if not specified, go back to the default method
            return "vanilla"

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
    asimov.setup_file_logging()
    logger = asimov.logger.getChild("cli").getChild("manage.build")
    logger.setLevel(LOGGER_LEVEL)

    for analysis in ledger.project_analyses:
        # MW disabling hanabi and golum_joint unless explicity re-enabled in submit
        if "hanabi" in analysis.name or "golum_joint" in analysis.name:
            if analysis.status in {"ready"}:
                analysis.status = "unready"
                ledger.update_analysis_in_project_analysis(analysis)
            elif analysis.status in {"analysis-ready"}:
                analysis.status = "ready"
                ledger.update_analysis_in_project_analysis(analysis)

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
    asimov.setup_file_logging()
    logger = asimov.logger.getChild("cli").getChild("manage.submit")
    logger.setLevel(LOGGER_LEVEL)

    # check the interest dictionary if needed
    # keep only the highest production number for the analyses
    interest_dict_project_analyses = {}
    for analysis in ledger.project_analyses:
        subj_string = "_".join([f"{subj}" for subj in analysis._subjects])
        if analysis.pipeline.name not in interest_dict_project_analyses.keys():
            interest_dict_project_analyses[analysis.pipeline.name] = {}
        if subj_string not in interest_dict_project_analyses[analysis.pipeline.name].keys():
            interest_dict_project_analyses[analysis.pipeline.name][subj_string] = {
                "prod number" : -1, "interest status" : False, "finished": False
            }
        if "interest status" in analysis.meta.keys():
            # check the production number for this event
            # assuming ProdX is somewhere in the analysis name
            prod_num = int(analysis.name.split("d")[1].split("_")[0])
            if prod_num > interest_dict_project_analyses[analysis.pipeline.name][subj_string]["prod number"]:
                interest_dict_project_analyses[analysis.pipeline.name][subj_string]["prod number"] = prod_num
                interest_dict_project_analyses[analysis.pipeline.name][subj_string]["interest status"] = analysis.meta["interest status"]
                if analysis.meta["status"] in {"uploaded", "finished"}:
                    interest_dict_project_analyses[analysis.pipeline.name][subj_string]["finished"] = True
    
    for analysis in ledger.project_analyses:
        # see which events are being analyzed
        subj_string = "_".join([f"{subj}" for subj in analysis._subjects])
        # need to change the logic of analysis set up as to account for
        # dependencies
        to_analyse = True
        extra_prio = False
        to_cancel = False
        if analysis.status not in {"ready", "unready"}:
            to_analyse = False
        elif analysis.meta['needs']:
            # check if the parent jobs are said to be interesting
            interested_pipelines = 0
            finished_pipelines = 0
            for old_analysis in analysis.meta['needs']:
                if old_analysis in interest_dict_project_analyses.keys():
                    if subj_string in interest_dict_project_analyses[old_analysis].keys():
                        if interest_dict_project_analyses[old_analysis][subj_string]["interest status"] is True:
                            interested_pipelines += 1
                        if interest_dict_project_analyses[old_analysis][subj_string]["finished"] is True:
                            finished_pipelines += 1
            # verify if enough parent analyses are interesting
            if "needs settings" in analysis.meta.keys():
                if interested_pipelines < int(analysis.meta["needs settings"]["minimum"]):
                    to_analyse = False
                    remaining_pipelines = int(len(analysis.meta["needs"]) - finished_pipelines)
                    remaining_interest_threshold = int(analysis.meta["needs settings"]["minimum"]) - interested_pipelines
                    if remaining_pipelines < remaining_interest_threshold:
                        to_cancel = True

            # check if we need to account for extra priority comming from any pipeline
            if "extra priority" in analysis.meta["needs settings"].keys():
                extra_prio_pipeline = analysis.meta["needs settings"]["extra priority"]
                if extra_prio_pipeline in interest_dict_project_analyses.keys():
                    if subj_string in interest_dict_project_analyses[extra_prio_pipeline].keys():
                        extra_prio = interest_dict_project_analyses[extra_prio_pipeline][subj_string]["interest status"]

        running_and_requiring_priority_check = False
        if analysis.status in {"running"} and analysis.meta['needs']:
            if "needs settings" in analysis.meta.keys():
                if "logic" in analysis.meta["needs settings"]:
                    if analysis.meta["needs settings"]["logic"] == "add_priority":
                        running_and_requiring_priority_check = True

        if to_cancel:
            analysis.status = "cancelled"
            ledger.update_analysis_in_project_analysis(analysis)
            click.echo(
                click.style("●", fg="red")
                + f" Project analysis {analysis.name} will not run, set to cancelled"
            )

        elif to_analyse:
            #MW: Set unready analyses to analysis-ready, i.e. fix for hanabi
            if analysis.status in {"unready"}:
                analysis.status = "analysis-ready"
                ledger.update_analysis_in_project_analysis(analysis)
                click.echo(
                    click.style("●", fg="yellow")
                    + f"Project analysis {analysis.name} set to analysis-ready will be subitted on next pass"
                )
                continue

            # Need to ensure a directory exists for these!
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
                cluster_id = pipe.submit_dag(dryrun=dryrun)
                if not dryrun:
                    analysis.job_id = int(cluster_id)
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
            for old_analysis in analysis.meta['needs']:
                if old_analysis in interest_dict_project_analyses.keys():
                    if subj_string in interest_dict_project_analyses[old_analysis].keys():
                        if interest_dict_project_analyses[old_analysis][subj_string]["interest status"] is True:
                            interested_pipelines += 1
            if interested_pipelines < analysis.meta["needs settings"]["minimum"]:
                theoretical_prio = 0
            else:
                theoretical_prio = int((interested_pipelines-analysis.meta["needs settings"]["minimum"])*10)
            extra_prio = False
            if "extra priority" in analysis.meta["needs settings"].keys():
                extra_prio_pipeline = analysis.meta["needs settings"]["extra priority"]
                if extra_prio_pipeline in interest_dict_project_analyses.keys():
                    if subj_string in interest_dict_project_analyses[extra_prio_pipeline].keys():
                        extra_prio = interest_dict_project_analyses[extra_prio_pipeline][subj_string]["interest status"]
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

    # deal with single event analysis to also allow for same prior set up
    interest_dict_single_analysis = {}
    for ev in ledger.get_event(event):
        if ev.name not in interest_dict_single_analysis.keys():
            interest_dict_single_analysis[ev.name] = {}
        productions = ev.get_all_latest()
        for production in productions:
            if production.name not in interest_dict_single_analysis[ev.name].keys():
                # default value is false to not start the run if the production is not completed
                interest_dict_single_analysis[ev.name][production.name] = {'interest status' : False,
                                                                           'done' : False}
                if "interest status" in production.meta.keys():
                    interest_dict_single_analysis[ev.name][production.name] = production.meta["interest status"]
                if production.status in {"finished", "uploaded"}:
                    interest_dict_single_analysis[ev.name][production.name]['done'] = True
    
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
            
            # For SubjectAnalysis, check if all source analyses are finished
            from asimov.analysis import SubjectAnalysis
            if isinstance(production, SubjectAnalysis):
                if not production.source_analyses_ready():
                    if dryrun:
                        click.echo(
                            click.style("●", fg="yellow")
                            + f" {production.name} is waiting on source analyses to finish"
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
                    cluster_id = pipe.submit_dag(dryrun=dryrun)
                    if not dryrun:
                        # cluster_id may be a scalar or a sequence; normalize it
                        if isinstance(cluster_id, (list, tuple)):
                            job_id_value = cluster_id[0]
                        else:
                            job_id_value = cluster_id
                        production.job_id = int(job_id_value)
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
