import click
from ..blueprints import select_blueprint_kind

@click.group()
def blueprint():
    pass

@blueprint.command()
@click.argument("file_path", type=click.Path(exists=True))
def validate(file_path):
    """
    Validate a blueprint file.
    """
    
    try:
        model, data = select_blueprint_kind(file_path)
        model.model_validate(data, strict=True)
        click.secho(f"Blueprint '{file_path}' is valid.", fg="green")

    except Exception as e:
        click.secho(f"Blueprint '{file_path}' is invalid: {e}", fg="red")