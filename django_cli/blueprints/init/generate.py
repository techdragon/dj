import click

@click.command()
@click.argument('--name')
@click.option('--class-name')
def generate(*args):
    return
