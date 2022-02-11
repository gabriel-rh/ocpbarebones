import os.path
import tarfile
import time

import click

from aura import transformers, utils
from aura.commands import BaseCommand, normalize_lang


@click.command("compile", short_help="Builds the book locally.")
@click.option("--archive", is_flag=True, help="Output an archive containing the built formats files.")
@click.option("--build-config", metavar="CONFIG", help="Use this configuration instead of the default build configuration file.",
              type=click.Path(exists=True))
@click.option("--build-args", metavar="ARGS", help="Additional arguments that should be passed to the external build tool.")
@click.option("--doctype", metavar="DOCTYPE", help="The document type. If no type is passed, the type is assumed to be a book.",
              type=click.Choice(['book', 'article']))
@click.option("build_formats", "--format", metavar="FORMAT", default=["html-single"], help="The format to compile to.", multiple=True)
@click.option("--lang", metavar="LANG", required=True, help="The book/article language to compile.",
              callback=normalize_lang)
@click.option("--main-file", metavar="FILE", help="The main file to build from.", type=click.Path(exists=True))
@click.option("open_book", "--open", is_flag=True, help="Open the book after it has been successfully built.")
@click.option("source_lang", "--src-lang", metavar="LANG",
              help="The documents source language. If no language is passed, \"en-US\" is used as a default.")
@click.option("source_format", "--type", help="The source format type. If no type is passed, the type is guessed.",
              type=click.Choice(transformers.FORMATS))
@click.pass_context
def cli(ctx, lang, build_formats, build_config, build_args, main_file, source_format, source_lang, doctype, open_book, archive=False):
    """This will build a book or article locally, for the given format"""
    cmd = CompileCommand(ctx, lang, build_formats,
                         build_config=build_config,
                         additional_args=build_args,
                         main_file=main_file,
                         source_format=source_format,
                         doctype=doctype,
                         open_book=open_book,
                         source_lang=source_lang,
                         archive=archive)
    cmd.execute()


class CompileCommand(BaseCommand):
    def __init__(self, ctx, lang, build_formats, build_config=None, additional_args=None, main_file=None, source_format=None,
                 doctype=None, open_book=False, source_lang=None, archive=False):
        super(CompileCommand, self).__init__(ctx)
        self.lang = lang
        self.source_lang = source_lang
        if isinstance(build_formats, str) or isinstance(build_formats, unicode):
            self.build_formats = (build_formats,)
        else:
            self.build_formats = build_formats
        self.build_config = build_config
        self.additional_args = additional_args
        self.main_file = main_file
        self.open_book = open_book
        self.source_format = source_format
        self.doctype = doctype
        self.archive = archive
        self.transformer = transformers.init_transformer(source_format)

    def print_parsed_debug_details(self):
        """Prints information useful for debugging the command"""
        if self.source_lang:
            self.log.debug("--src-lang is %s", self.source_lang)
        if self.lang:
            self.log.debug("--lang is %s", self.lang)
        if self.build_formats:
            self.log.debug("--format is %s", self.build_formats)
        if self.build_config:
            self.log.debug("--build-config is %s", self.build_config)
        if self.additional_args:
            self.log.debug("--build-args is %s", self.additional_args)
        if self.main_file:
            self.log.debug("--main-file is %s", self.main_file)
        if self.source_format:
            self.log.debug("--type is %s", self.source_format)
        if self.doctype:
            self.log.debug("--doctype is %s", self.doctype)
        if self.open_book:
            self.log.debug("--open is %s", self.open_book)
        if self.archive:
            self.log.debug("--archive is %s", self.archive)

    def _execute(self):
        """Perform the actions for the compile command"""
        super(CompileCommand, self)._execute()

        # Check the format is valid
        for build_format in self.build_formats:
            if build_format not in self.transformer.valid_formats:
                self.ctx.fail("Invalid value for \"--format\": invalid choice: {0}. (choose from {1})"
                              .format(build_format, ", ".join(self.transformer.valid_formats)))

        # Run the transformer to compile the book
        success = True
        if self.transformer.allows_multiple_formats:
            formats = self.transformer.formats_sep.join(self.build_formats)
            success = self.transformer.build_format(self.source_lang, self.lang, formats, self.build_config, self.additional_args,
                                                    self.main_file, self.doctype)
        else:
            for build_format in self.build_formats:
                if not self.transformer.build_format(self.source_lang, self.lang, build_format, self.build_config, self.additional_args,
                                                     self.main_file, self.doctype):
                    success = False

        # If the build completed successfully, then open the file(s)
        if self.open_book and success:
            for build_format in self.build_formats:
                self.open_built_file(build_format)

        if self.archive:
            self.archive_build_files()

    def open_built_file(self, build_format):
        """Open a publican build file, for the commands format and lang"""
        build_file = self.transformer.get_build_main_file(self.lang, build_format, self.build_config)
        if build_file is not None:
            click.launch(build_file)
        else:
            # Not a format we know, so just open the build directory
            build_dir = self.transformer.get_build_dir(self.lang, build_format, self.build_config)
            click.launch(build_dir, locate=True)

    def archive_build_files(self):
        """"""
        # Build up the filename/path
        doc_id = self.transformer.get_doc_id(self.build_config, self.lang)
        title, product, version = self.transformer.get_npv(self.build_config)
        archive_filename = doc_id + ".tar.gz"
        archive_dir = self.transformer.get_build_archives_dir(self.lang, self.build_config)
        archive_file = os.path.join(archive_dir, archive_filename)

        # Make sure the archive directory exists
        if not os.path.exists(archive_dir):
            os.makedirs(archive_dir)

        # Archive the files
        with tarfile.open(archive_file, 'w:gz') as archive:
            # Add the directory to store the files
            title_dir = utils.clean_for_rpm_name(title)
            t_info = tarfile.TarInfo(title_dir)
            t_info.type = tarfile.DIRTYPE
            t_info.mode = 0o775
            t_info.mtime = time.time()
            archive.addfile(t_info)

            for build_format in self.build_formats:
                if build_format in self.transformer.single_file_formats:
                    build_file = self.transformer.get_build_main_file(self.lang, build_format, self.build_config)
                    filename, file_ext = os.path.splitext(build_file)
                    archive.add(build_file, os.path.join(title_dir, doc_id + file_ext))
                else:
                    build_files_dir = self.transformer.get_build_dir(self.lang, build_format)
                    format_archive_dir = os.path.join(title_dir, build_format)
                    t_format_info = archive.gettarinfo(build_files_dir, format_archive_dir)
                    archive.addfile(t_format_info)
                    for root, dirs, files in os.walk(build_files_dir):
                        archive_root = os.path.join(format_archive_dir, root.replace(build_files_dir, ""))
                        for file_path in files:
                            archive.add(os.path.join(root, file_path), os.path.join(archive_root, file_path))

        self.log.info("Successfully archived the built files into %s", archive_file)
