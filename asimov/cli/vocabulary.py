"""
Inspect the ledger vocabulary and check blueprints against it.
"""

import json
import sys

import click
import yaml

from asimov.vocabulary import get_vocabulary


def _load(plugins):
    return get_vocabulary(plugins=plugins)


@click.group()
def vocabulary():
    """Inspect the ledger vocabulary and check files against it."""
    pass


@vocabulary.command(name="list")
@click.option(
    "--no-plugins", is_flag=True, default=False, help="Only show the core vocabulary."
)
@click.option(
    "--deprecated/--no-deprecated",
    default=False,
    help="Include deprecated terms.",
)
def list_terms(no_plugins, deprecated):
    """List every term in the vocabulary."""
    vocab = _load(not no_plugins)
    for term in vocab.terms():
        if term.deprecated and not deprecated:
            continue
        details = [term.type + (" per ifo" if term.per_ifo else "")]
        if term.units:
            details.append(term.units)
        if term.owner:
            details.append(f"owner: {term.owner}")
        indent = "  " * (len(term.path) - 1)
        click.echo(f"{indent}{term.name}  ({', '.join(details)})")


@vocabulary.command()
@click.argument("path")
@click.option("--no-plugins", is_flag=True, default=False)
def show(path, no_plugins):
    """
    Show the definition of the term at PATH (e.g. "likelihood.sample rate").
    """
    vocab = _load(not no_plugins)
    term = vocab.lookup(path)
    if term is None:
        suggestion = vocab.suggest(path.split(".")[-1], path.split(".")[:-1])
        click.secho(f"'{path}' is not in the vocabulary.", fg="red")
        if suggestion is not None:
            click.echo(f"Did you mean '{suggestion.dotted}'?")
        sys.exit(1)
    data = term.to_dict()
    data.pop("children", None)
    click.echo(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    if term.children:
        click.echo("children: " + ", ".join(term.children))


@vocabulary.command()
@click.argument("files", nargs=-1, type=click.Path(exists=True), required=True)
@click.option(
    "--pipeline", "-p", default=None, help="The pipeline the files are written for."
)
@click.option(
    "--strict",
    is_flag=True,
    default=False,
    help="Exit non-zero on any finding, not only unknown or duplicate terms.",
)
@click.option("--json", "as_json", is_flag=True, default=False)
@click.option("--no-plugins", is_flag=True, default=False)
def check(files, pipeline, strict, as_json, no_plugins):
    """
    Check blueprint or ledger FILES against the vocabulary.

    Exits with status 1 if any key is unknown or duplicates a standard term
    (or on any finding at all with --strict).
    """
    vocab = _load(not no_plugins)
    results = {}
    failed = False
    for file_path in files:
        findings = vocab.check_file(file_path, pipeline=pipeline)
        results[file_path] = findings
        for finding in findings:
            if strict or finding.kind in {"unknown", "duplicate", "type"}:
                failed = True
    if as_json:
        click.echo(
            json.dumps(
                {path: [f.to_dict() for f in found] for path, found in results.items()},
                indent=2,
            )
        )
    else:
        colours = {"unknown": "red", "duplicate": "red", "type": "red"}
        for file_path, findings in results.items():
            if not findings:
                click.secho(f"{file_path}: OK", fg="green")
            for finding in findings:
                click.secho(
                    f"{file_path}: {finding}", fg=colours.get(finding.kind, "yellow")
                )
    sys.exit(1 if failed else 0)


@vocabulary.command()
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["yaml", "json"]),
    default="yaml",
)
@click.option("--no-plugins", is_flag=True, default=False)
def export(output_format, no_plugins):
    """
    Print the full vocabulary (including installed plugins' terms).
    """
    data = _load(not no_plugins).to_dict()
    if output_format == "json":
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


@vocabulary.command()
def lint():
    """
    Report plugin-registered terms which duplicate or clash with core terms.
    """
    vocab = _load(True)
    problems = vocab.duplicates()
    for path, plugin in vocab.conflicts:
        click.secho(f"{path}: redefined by plugin '{plugin}'", fg="red")
    for finding in problems:
        click.secho(str(finding), fg="red")
    if not problems and not vocab.conflicts:
        click.secho(
            f"No clashes ({len(vocab.plugins)} plugin vocabularies loaded).",
            fg="green",
        )
    sys.exit(1 if problems or vocab.conflicts else 0)
