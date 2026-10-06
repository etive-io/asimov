"""
Commands for inspecting and exporting analysis provenance (see #154).
"""

import json
import os

import click

from asimov import config
from asimov import current_ledger as ledger
from asimov.provenance import ProvenanceError, build_provenance
from asimov.rocrate import package_analysis
from asimov.storage import Store


@click.command(help="Show the W3C PROV-O provenance graph for an analysis.")
@click.argument("subject")
@click.argument("analysis")
@click.option(
    "--output",
    "output",
    default=None,
    type=click.Path(),
    help="Write the provenance document to this file instead of stdout.",
)
def provenance(subject, analysis, output):
    """Show the provenance record for ANALYSIS on SUBJECT."""
    store = Store(root=config.get("storage", "directory"))
    try:
        document = build_provenance(ledger, subject, analysis, store=store)
    except ProvenanceError as error:
        raise click.ClickException(str(error))

    rendered = json.dumps(document, indent=2, default=str)
    if output:
        with open(output, "w") as output_file:
            output_file.write(rendered)
        click.echo(f"Provenance written to {output}")
    else:
        click.echo(rendered)


@click.command(help="Export an analysis as an RO-Crate for archival/sharing.")
@click.argument("subject")
@click.argument("analysis")
@click.option(
    "--output",
    "output",
    default=None,
    type=click.Path(),
    help="Directory to write the crate to (must not already exist). "
    "Defaults to <subject>-<analysis>.crate in the current directory.",
)
def package(subject, analysis, output):
    """Package ANALYSIS on SUBJECT as an RO-Crate."""
    store = Store(root=config.get("storage", "directory"))
    destination = output or f"{subject}-{analysis}.crate"
    if os.path.exists(destination):
        raise click.ClickException(f"{destination} already exists.")

    try:
        crate_path = package_analysis(ledger, subject, analysis, destination, store=store)
    except ProvenanceError as error:
        raise click.ClickException(str(error))

    click.echo(f"RO-Crate written to {crate_path}")
