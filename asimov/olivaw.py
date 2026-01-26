import logging
import os
import sys
if sys.version_info < (3, 10):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points

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


class ProjectAwareGroup(click.Group):
    """
    Custom Click Group that checks for project directory.

    Allows certain commands (init and all plugin commands) to run
    outside of an asimov project directory.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._plugin_commands = set()

    def invoke(self, ctx):
        """Check project directory before invoking command."""
        # If no subcommand is specified (e.g., just `asimov`), let it through
        # to show the help message
        if ctx.invoked_subcommand is None:
            return super().invoke(ctx)

        # Commands that can run outside of a project
        commands_allowed_outside_project = {"init", "clone"}

        # Add all registered plugin commands (they handle their own project checks if needed)
        commands_allowed_outside_project.update(self._plugin_commands)

        # Check if we're in a project or running an allowed command
        if not os.path.exists(".asimov") and ctx.invoked_subcommand not in commands_allowed_outside_project:
            click.secho("This isn't an asimov project", fg="white", bg="red")
            sys.exit(1)

        return super().invoke(ctx)


@click.version_option(asimov.__version__)
@click.group(cls=ProjectAwareGroup)
@click.pass_context
def olivaw(ctx):
    """
    This is the main program which runs the DAGs for each event issue.
    """

    # Project presence is enforced in ProjectAwareGroup.invoke; no extra work needed here.
    return ctx


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

# Auto-discover plugin commands

discovered_commands = entry_points(group="asimov.commands")
for ep in discovered_commands:
    try:
        command = ep.load()
        olivaw.add_command(command)
        olivaw._plugin_commands.add(ep.name)
    except (ImportError, ModuleNotFoundError, AttributeError) as e:
        # Log but don't fail if a plugin command can't load due to import/attribute issues
        logger = logging.getLogger("asimov.olivaw")
        logger.debug(f"Failed to load plugin command {ep.name}: {e}")
    except Exception as e:
        # For unexpected errors, log with full traceback and re-raise
        logger = logging.getLogger("asimov.olivaw")
        logger.exception(f"Unexpected error while loading plugin command {ep.name}: {e}")
        raise
