import sys

import click

from aura import transformers
from aura.commands import BaseCommand, normalize_lang


@click.command("translate", short_help="Creates the gettext POT/PO files required for translation.")
@click.option("--build-config", metavar="CONFIG", help="Use this configuration instead of the default build configuration file.",
              type=click.Path(exists=True))
@click.option("--doctype", metavar="DOCTYPE", help="The document type. If no type is passed, the type is assumed to be a book.",
              type=click.Choice(['book', 'article']))
@click.option("--langs", metavar="LANGS", multiple=True, required=True, help="A comma separated list of languages to translate to.")
@click.option("--main-file", metavar="FILE", help="The main file to build from.", type=click.Path(exists=True))
@click.option("--po-only", is_flag=True, help="Create the po translation files only.")
@click.option("--pot-only", is_flag=True, help="Create the pot translation files only.")
@click.option("source_lang", "--src-lang", metavar="LANG",
              help="The documents source language. If no language is passed, \"en-US\" is used as a default.")
@click.option("source_format", "--type", help="The source format type. If no type is passed, the type is guessed.",
              type=click.Choice(transformers.FORMATS))
@click.pass_context
def cli(ctx, langs, build_config, doctype, main_file, source_format, source_lang, po_only, pot_only):
    """
    This will create the gettext POT/PO files required for translation from the source content.
    """
    cmd = TranslateCommand(ctx, langs,
                           build_config=build_config,
                           doctype=doctype,
                           main_file=main_file,
                           source_format=source_format,
                           source_lang=source_lang,
                           po_only=po_only,
                           pot_only=pot_only)
    cmd.execute()


class TranslateCommand(BaseCommand):
    def __init__(self, ctx, langs, build_config=None, doctype=None, main_file=None, source_format=None, source_lang=None, po_only=False,
                 pot_only=False):
        super(TranslateCommand, self).__init__(ctx)
        self.build_config = build_config
        self.main_file = main_file
        self.doctype = doctype
        self.source_format = source_format
        self.source_lang = source_lang
        self.po_only = po_only
        self.pot_only = pot_only

        # Langs could contain a comma separated list, so break down each lang
        if langs is not None:
            self.langs = set()
            for lang in langs:
                sub_langs = lang.split(",")
                for sub_lang in sub_langs:
                    self.langs.add(normalize_lang(ctx, None, sub_lang))

        self.transformer = transformers.init_transformer(source_format)

    def print_parsed_debug_details(self):
        """Prints information useful for debugging the command"""
        if self.source_lang:
            self.log.debug("--src-lang is %s", self.source_lang)
        if self.langs:
            self.log.debug("--langs is %s", self.langs)
        if self.build_config:
            self.log.debug("--build-config is %s", self.build_config)
        if self.main_file:
            self.log.debug("--main-file is %s", self.main_file)
        if self.source_format:
            self.log.debug("--type is %s", self.source_format)
        if self.doctype:
            self.log.debug("--doctype is %s", self.doctype)
        if self.po_only:
            self.log.debug("--po-only is %s", self.po_only)
        if self.pot_only:
            self.log.debug("--pot-only is %s", self.pot_only)

    def _execute(self):
        """Perform the actions for the translate command"""
        super(TranslateCommand, self)._execute(self)

        # Do the transformation
        if not self.transformer.build_translation_files(self.langs, self.build_config, self.main_file, self.pot_only, self.po_only,
                                                        self.source_lang, self.doctype):
            self.log.error("An error occurred when creating the translation files. Please see the previous log messages for the cause.")
            sys.exit(-1)
