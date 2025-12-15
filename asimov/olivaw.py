import os
import sys

# Ignore warnings from the condor module
import warnings

import click

warnings.filterwarnings("ignore", module="htcondor")  # NoQA

# Replace this with a better logfile handling module please
# from glob import glob
import asimov  # NoQA
import asimov.pipelines  # NoQA

# Import CLI bits from elsewhere
from asimov.cli import (  # NoQA
    application,
    configuration,
    event,
    manage,
    monitor,
    production,
    project,
    report,
    review,
    blueprint,
)  # NoQA


@click.version_option(asimov.__version__)
@click.group()
@click.pass_context
def olivaw(ctx):
    """
    This is the main program which runs the DAGs for each event issue.
    """

    # Check that we're running in an actual asimov project
    if not os.path.exists(".asimov") and ctx.invoked_subcommand not in  {"init", "blueprint"}:
        # This isn't the root of an asimov project, let's fail.
        click.secho("This isn't an asimov project", fg="white", bg="red")
        sys.exit(1)
    pass


# Project initialisation
olivaw.add_command(project.init)
olivaw.add_command(project.clone)

olivaw.add_command(event.event)

# Building and submission
olivaw.add_command(manage.manage)
# Reporting commands
olivaw.add_command(report.report)
# Configuration commands
olivaw.add_command(configuration.configuration)
# Monitoring commands
olivaw.add_command(monitor.start)
olivaw.add_command(monitor.stop)
olivaw.add_command(monitor.monitor)
olivaw.add_command(event.event)
olivaw.add_command(production.production)
# Review commands
olivaw.add_command(review.review)
olivaw.add_command(application.apply)
# Blueprint commands
olivaw.add_command(blueprint.blueprint)
