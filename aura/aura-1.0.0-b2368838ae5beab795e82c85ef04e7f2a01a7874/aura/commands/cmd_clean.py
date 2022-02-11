import click

from aura import transformers
from aura.commands import BaseCommand


@click.command("clean", short_help="Clean any build data left on the local machine.")
@click.option("source_format", "--type", help="The source format type. If no type is passed, the type is guessed.",
              type=click.Choice(transformers.FORMATS))
@click.pass_context
def cli(ctx, source_format):
    """Clean any build data left on the local machine."""
    cmd = CleanCommand(ctx, source_format)
    cmd.execute()


class CleanCommand(BaseCommand):
    def __init__(self, ctx, source_format=None):
        super(CleanCommand, self).__init__(ctx)
        self.source_format = source_format
        # Get the correct helper to use
        self.transformer = transformers.init_transformer(source_format)

    def print_parsed_debug_details(self):
        """Prints information useful for debugging the command"""
        if self.source_format:
            self.log.debug("--type is %s", self.source_format)

    def _execute(self):
        """Perform the actions for the clean command"""
        super(CleanCommand, self)._execute()

        # Clean the temp files
        if self.transformer.clean_build_files():
            self.log.info("Successfully cleaned all temporary build data.")
        else:
            self.log.info("An error occurred while cleaning the temporary build data.")
