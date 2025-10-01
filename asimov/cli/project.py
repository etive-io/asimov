"""
zProject management tools.
"""

try:
    import ConfigParser as configparser
except ImportError:
    import configparser

import os
import shutil
import getpass

import click

from asimov import config, storage, logger, LOGGER_LEVEL
from asimov.ledger import Ledger

logger = logger.getChild("cli").getChild("project")
logger.setLevel(LOGGER_LEVEL)


def make_project(
    name,
    root,
    working="working",
    checkouts="checkouts",
    results="results",
    logs="logs",
    user=None,
):
    """
    Create a new project called NAME.

    This command creates a new asimov project, creating the appropriate
    directory structure, and creating a blank ledger.
    """
    import pathlib

    pathlib.Path(root).mkdir(parents=True, exist_ok=True)
    os.chdir(root)

    config.set("project", "name", name)
    config.set("project", "root", root)

    project_name = name

    # Make the virtual environment
    # builder = venv.EnvBuilder(system_site_packages=False,
    #                           clear=False,
    #                           symlinks=False,
    #                           upgrade=False,
    #                           with_pip=True,
    #                           prompt=f"Asimov {project_name}")

    # builder.create("environment")

    config.set("general", "environment", "environment")

    # Make the working directory
    pathlib.Path(working).mkdir(parents=True, exist_ok=True)
    config.set("general", "rundir_default", working)

    # Make the git directory
    pathlib.Path(checkouts).mkdir(parents=True, exist_ok=True)
    config.set("general", "git_default", checkouts)

    # Make the log directory
    pathlib.Path(logs).mkdir(parents=True, exist_ok=True)
    config.set("logging", "directory", logs)

    # Make the results store
    storage.Store.create(root=results, name=f"{project_name} storage")
    config.set("storage", "directory", results)

    # Make the ledger and operative files
    pathlib.Path(".asimov").mkdir(parents=True, exist_ok=True)
    config.set("ledger", "engine", "yamlfile")
    config.set("ledger", "location", os.path.join(".asimov", "ledger.yml"))

    # Set the default environment
    python_loc = shutil.which("python").split("/")[:-2]
    config.set("pipelines", "environment", os.path.join("/", *python_loc))
    config.set("rift", "environment", os.path.join("/", *python_loc))

    try:
        config.set("pesummary", "executable", shutil.which("summarypages"))
    except Exception:
        pass

    # Set the default condor user
    if not user:
        config.set("condor", "user", getpass.getuser())
    else:
        config.set("condor", "user", user)

    Ledger.create(
        engine="yamlfile",
        name=project_name,
        location=os.path.join(".asimov", "ledger.yml"),
    )

    with open(os.path.join(".asimov", "asimov.conf"), "w") as config_file:
        config.write(config_file)


@click.command()
@click.argument("name")
@click.option(
    "--root",
    default=os.getcwd(),
    help="Location to create the project, default is the current directory.",
)
@click.option(
    "--working",
    default="working",
    help="""The location to store working directories,
 default is a directory called 'working' inside the current directory.""",
)
@click.option(
    "--checkouts",
    default="checkouts",
    help="The location to store cloned git repositories.",
)
@click.option(
    "--results",
    default="results",
    help="The location where the results store should be created.",
)
@click.option(
    "--user",
    default=None,
    help="The user account to be used for accounting purposes. Defaults to the current user if not set.",
)
def init(
    name, root, working="working", checkouts="checkouts", results="results", user=None
):
    """
    Roll-out a new project.
    """
    make_project(name, root, working=working, checkouts=checkouts, results=results)
    click.echo(click.style("●", fg="green") + " New project created successfully!")
    logger.info(f"A new project was created in {os.getcwd()}")


@click.command()
@click.argument("location")
def clone(location):
    import pathlib
    import shutil

    results = "results"

    remote_config = os.path.join(location, "asimov.conf")
    config = configparser.ConfigParser()
    config.read([remote_config])
    click.echo(f'Cloning {config.get("project", "name")}')
    root = os.path.join(
        os.getcwd(), config.get("project", "name").lower().replace(" ", "-")
    )
    pathlib.Path(root).mkdir(parents=True, exist_ok=True)
    # os.chdir(root)
    config.set("project", "root", root)
    # Make the virtual environment
    # builder = venv.EnvBuilder(system_site_packages=False,
    #                          clear=False,
    #                          symlinks=False,
    #                          upgrade=False,
    #                          with_pip=True,
    #                          prompt=f"Asimov {project_name}")

    # builder.create("environment")

    # config.set("general", "environment", "environment")

    # Make the working directory
    # shutil.copytree(os.path.join(config.get("general", "rundir_default"), working)
    # config.set("general", "rundir_default", working)

    # Make the git directory
    # pathlib.Path(checkouts).mkdir(parents=True, exist_ok=True)
    # config.set("general", "git_default", checkouts)

    # Copy the results store
    # shutil.copyfile(os.path.join(location, config.get("storage", "results_store")), results)
    shutil.copytree(
        os.path.join(location, config.get("storage", "results_store")), results
    )
    config.set("storage", "results_store", results)

    # Make the ledger
    if config.get("ledger", "engine") == "yamlfile":
        shutil.copyfile(
            os.path.join(location, config.get("ledger", "location")),
            os.path.join(".asimov", "ledger.yml"),
        )
    config.set("ledger", "engine", "yamlfile")
    config.set("ledger", "location", os.path.join(".asimov", "ledger.yml"))

    with open(os.path.join(".asimov", "asimov.conf"), "w") as config_file:
        config.write(config_file)
