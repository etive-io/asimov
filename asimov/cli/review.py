"""
Review functions for asimov events.
"""

import os

import click

from asimov import config
from asimov.context import active_ledger as current_ledger
from asimov.pipelines import known_pipelines
from asimov.review import ReviewMessage


@click.group()
def review():
    """Add and view review information and sign-offs"""
    pass


@click.option("--other_subjects", "-o_e", "other_subjects", default=None)
@click.option("--pipeline", "-p", default=None)
@click.option("--message", "-m", "message", default=None)
@click.argument("status", required=False, default=None)
@click.argument("production", required=True)
@click.argument("event", required=True)
@review.command()
def add(event, production, status, message, other_subjects=None, pipeline=None):
    """
    Add a review signoff or rejection to an event.

    Arguments:
    ----------
    event: str
      The event for which we need to add a review for a given analysis.
      If we are considering a project analysis, this will be used as the first
      subject
    production: str
      The production for which we need to add the review status
    status: str
       The status of the review. Can be one of
        "rejected", "approved", "preferred", "deprecated"
    message: str, optional
       The message to add to the review
    other_subjects: str, optional
      The other subjects to be considered in the project analysis and
      for which we want to add a review status.
    pipeline: str, optional
      The pipeline used in the project analysis and for which we want to add
      the review status.

    """
    valid = {"REJECTED", "APPROVED", "PREFERRED", "DEPRECATED"}
    if status is not None and status.upper() not in valid:
        click.echo(
            click.style("●", fg="red")
            + f" Did not understand the review status {status.lower()}."
            + " The review status must be one of "
            + "{APPROVED, REJECTED, PREFERRED, DEPRECATED}"
        )
        return

    if other_subjects is not None:
        subjects = [event] + [
            subject.strip()
            for subject in other_subjects.replace("[", "").replace("]", "").split(",")
        ]
        matches = _find_project_analyses(production, subjects, pipeline)
        if not matches:
            click.secho(
                f"Unable to find a project analysis for pipeline {pipeline}, "
                f"production {production} and subjects {set(subjects)}",
                fg="red",
            )
            return
        _add_project_review(matches, status, message)
        return

    # A single subject: this is either an ordinary analysis of the event, or a
    # project analysis over just that subject.
    events = current_ledger.get_event(event)
    if events is None:
        click.echo(
            click.style("●", fg="red") + f" Could not find an event called {event}"
        )
        return

    found = False
    for event_obj in events:
        matching = [
            production_o
            for production_o in event_obj.productions
            if production_o.name == production
        ]
        if not matching:
            continue
        found = True
        analysis = matching[0]
        click.secho(event_obj.name, bold=True)

        analysis.review.add(
            ReviewMessage(message=message, status=status, production=analysis)
        )
        if hasattr(event_obj, "issue_object"):
            analysis.event.update_data()
        current_ledger.update_event(event_obj)
        if status is not None:
            click.echo(
                click.style("●", fg="green")
                + f" {event_obj.name}/{analysis.name} {status.lower()}"
            )

    if not found:
        matches = _find_project_analyses(production, [event], pipeline)
        if matches:
            _add_project_review(matches, status, message)
            found = True

    if not found:
        click.secho(
            f"Unable to find an analysis called {production} for {event}",
            fg="red",
        )


def _find_project_analyses(name, subject_names, pipeline=None):
    """
    Find the project analyses called ``name`` over exactly ``subject_names``.

    If ``pipeline`` is given, the analysis must also use that pipeline.
    ``ProjectAnalysis.subjects`` holds ``Event`` objects, so the comparison
    is made on their names.
    """
    matches = []
    for analysis in current_ledger.project_analyses:
        analysis_subject_names = {getattr(s, "name", s) for s in analysis.subjects}
        if analysis.name != name:
            continue
        if pipeline is not None and not _pipeline_matches(analysis, pipeline):
            continue
        if analysis_subject_names != set(subject_names):
            continue
        matches.append(analysis)
    return matches


def _pipeline_matches(analysis, pipeline):
    """
    Check whether ``analysis`` uses the pipeline called ``pipeline``.

    The name is matched case-insensitively against the pipeline's own name,
    its class name, and the name it was registered under in the blueprint.
    """
    candidates = {
        str(getattr(analysis.pipeline, "name", "")),
        type(analysis.pipeline).__name__,
        str(analysis.meta.get("pipeline", "")),
    }
    return pipeline.lower() in {c.lower() for c in candidates if c}


def _add_project_review(analyses, status, message):
    """Add a review message to each project analysis and save it to the ledger."""
    for analysis in analyses:
        subject_names = sorted(getattr(s, "name", s) for s in analysis.subjects)
        click.secho(analysis.name, bold=True)
        click.secho(f"{getattr(analysis.pipeline, 'name', analysis.pipeline)}: {' '.join(subject_names)}")
        analysis.review.add(
            ReviewMessage(message=message, status=status, production=analysis)
        )
        current_ledger.update_analysis_in_project_analysis(analysis)
        if status is not None:
            click.echo(
                click.style("●", fg="green")
                + f" {analysis.name} {status.lower()}"
            )
        else:
            click.echo(click.style("●", fg="green") + f" {analysis.name} note added")


@click.argument("production", default=None, required=False)
@click.argument("event", default=None, required=False)
@review.command()
def status(event, production):
    """
    Show the review status of an event.
    """
    for event in current_ledger.get_event(event):
        click.secho(event.name, bold=True)
        if production:
            productions = [
                prod for prod in event.productions if prod.name == production
            ]
        else:
            productions = event.productions

        for production in productions:
            click.secho(f"\t{production.name}", bold=True)
            if production.review:
                click.echo(f"\t\t {production.review.status.lower()}")
            else:
                click.secho("\t\tNo review information exists for this production.")


@click.argument("event", default=None, required=False)
@review.command()
def audit(event):
    """
    Conduct an audit of the contents of production ini files
    against the production ledger.

    Parameters
    ----------
    event : str, optional
       The event to be checked.
       Optional; if the event isn't provided all events will be audited.
    """
    if isinstance(event, str):
        event = [event]

    for production in current_ledger.get_event(event)[0].productions:
        category = config.get("general", "calibration_directory")
        config_file = os.path.join(
            production.event.repository.directory, category, f"{production.name}.ini"
        )
        pipe = known_pipelines[production.pipeline.lower()](production, category)
        click.echo(pipe.read_ini(config_file))
