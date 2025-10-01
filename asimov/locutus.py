"""
The locutus script.
"""

import os

import click

from asimov.storage import AlreadyPresentException, NotAStoreError, Store

cwd = os.getcwd()
try:
    this_store = Store(root=cwd)
except NotAStoreError:
    this_store = None


@click.group()
def cli():
    pass


@click.option(
    "--name", "name", prompt="Name for the store: ", help="The name for the store."
)
@cli.command()
def init(name):
    """
    Initialise a new Store
    """

    # Get the working directory
    cwd = os.getcwd()
    Store.create(cwd, name)


@cli.command()
def info():
    """
    Check the information about this Store.
    """
    cwd = os.getcwd()
    store = Store(root=cwd)

    click.echo(store.manifest.data)


@click.argument("filename")  # , help="The file to add.")
@click.argument("production")  # , help="The production name.")
@click.argument("event")  # , help="The event label.")
@cli.command()
def store(event, production, filename):
    """
    Store a file in the Store.
    """
    try:
        click.echo(this_store.add_file(event, production, filename))
    except AlreadyPresentException:
        click.echo("This resource has already been stored.")


@click.option(
    "--hash", "hash", help="Optional hash to check the returned file against."
)
@click.argument("filename")
@click.argument("production")
@click.argument("event")
@cli.command()
def fetch(event, production, filename, hash=None):
    """
    Fetch a file from an event production.
    """
    try:
        click.echo(this_store.fetch_file(event, production, filename, hash))
    except FileNotFoundError:
        click.echo("File not found in the manifest.")


@click.argument("production")
@click.argument("event")
@cli.command()
def list(event, production):
    """
    Store a file in the Store.
    """
    click.echo(f"{'Resource':30} {'Hash':32} {'UUID':32}")
    click.echo("-" * 96)
    for resource, details in this_store.manifest.list_resources(
        event, production
    ).items():
        click.echo(f"{resource:30} {details['hash']:32} {details['uuid']:32}")
