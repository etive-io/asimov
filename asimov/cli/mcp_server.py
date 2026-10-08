"""
The ``asimov mcp-server`` command: let an MCP client work with this project.
"""

import click

from asimov.principal import Principal


@click.command(
    "mcp-server",
    help="Serve this project to an MCP client over standard input and output. "
    "Changes the client makes are recorded as made by it, on behalf of you.",
)
@click.option(
    "--project",
    type=click.Path(exists=True, file_okay=False),
    default=None,
    help="The project's directory (default: the current one).",
)
@click.option(
    "--read-only",
    is_flag=True,
    help="Only offer tools which read the project.",
)
@click.option(
    "--acting-for",
    default=None,
    help="The person the client acts for (default: the local user).",
)
def mcp_server(project, read_only, acting_for):
    """Serve the project over MCP."""
    try:
        from asimov.mcp_server import serve
    except ImportError as error:
        raise click.ClickException(str(error))
    person = Principal.person(acting_for) if acting_for else None
    from asimov.context import NoProjectError

    try:
        serve(project or ".", acting_for=person, read_only=read_only)
    except NoProjectError as error:
        raise click.ClickException(str(error))
