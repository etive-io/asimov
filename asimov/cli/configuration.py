import click
import os
from asimov import config


@click.group()
def configuration():
    """Group for all of the configuration-related command line stuff."""
    pass


@configuration.command()
@click.option("--key", "-k", "key", default=None, help="Show a specific key")
def show(key):
    """Show all configuration values"""
    if key:
        section, key = key.split("/")
        section = section.replace("-", "")
        click.echo(config.get(section, key))
    else:
        for section, values in config._sections.items():
            click.echo(click.style(section, fg="black", bg="white"))
            for key, value in values.items():
                click.secho(f"\t{key:30}\t{value}", bold=False)


@configuration.command(
    context_settings=dict(
        ignore_unknown_options=True,
    )
)
@click.argument("kwargs", nargs=-1, type=click.UNPROCESSED)
def update(kwargs):
    """Update a configuration setting."""
    key, value = kwargs
    section, key = key.split("/")
    section = section.replace("-", "")
    if not config.has_section(section):
        config.add_section(section)
    config.set(section, key, value)
    with open(os.path.join(".asimov", "asimov.conf"), "w") as config_file:
        config.write(config_file)
