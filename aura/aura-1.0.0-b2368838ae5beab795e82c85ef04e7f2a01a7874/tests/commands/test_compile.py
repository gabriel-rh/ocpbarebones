import os

import click.exceptions
import mock
import pytest
from aura.commands.cmd_compile import CompileCommand, cli as compile_cli
from click.testing import CliRunner

import base


class TestCompileCommand(base.TestBase):
    @mock.patch.object(CompileCommand, "execute")
    def test_lang_required(self, mock_execute):
        runner = CliRunner()
        result = runner.invoke(compile_cli, [])
        assert result.exit_code != 0
        assert "Missing option \"--lang\"" in result.output
        assert not mock_execute.called

    def test_print_debug(self):
        # Given that debug is on
        self.enable_debug_mode()
        # and we have been given some compile options
        lang = "en-US"
        build_format = "html-single"
        compile_command = CompileCommand(self.ctx, lang, build_format)

        # When printing the debug information
        compile_command.print_parsed_debug_details()

        # Make sure we got the expected content printed
        logs = self.get_logs()
        assert "--lang is {0}".format(lang) in logs
        assert "--format is {0}".format((build_format,)) in logs

    @mock.patch("click.launch")
    def test_open_file_html(self, mock_launch):
        # Given we have a compile command instance
        lang = "en-US"
        build_format = "html-single"
        compile_command = CompileCommand(self.ctx, lang, build_format)

        # When attempting to open the built file
        compile_command.open_built_file(build_format)

        # Then the file that was opened should be index.html
        build_dir = "tmp/{0}/{1}/".format(lang, build_format)
        mock_launch.assert_called_once_with(os.path.join(os.getcwd(), build_dir, "index.html"))

    @mock.patch("click.launch")
    @mock.patch("aura.utils.find_file_for_type")
    def test_open_file_pdf(self, mock_find_file, mock_launch):
        # Given the a file name will be found
        pdf_file = "product-title-version-release.pdf"
        mock_find_file.return_value = pdf_file
        # and we have a compile command instance
        lang = "en-US"
        build_format = "pdf"
        compile_command = CompileCommand(self.ctx, lang, build_format)

        # When attempting to open the built file
        compile_command.open_built_file(build_format)

        # Then the file that was opened should be our file returned by the find method
        build_dir = os.path.join(os.getcwd(), "tmp/{0}/{1}/".format(lang, build_format))
        mock_launch.assert_called_once_with(os.path.join(build_dir, pdf_file))
        # and the correct params were passed to find_file
        mock_find_file.assert_called_once_with(build_dir, "pdf")

    @mock.patch("click.launch")
    @mock.patch("aura.utils.find_file_for_type")
    def test_open_file_epub(self, mock_find_file, mock_launch):
        # Given the a file name will be found
        epub_file = "book.epub"
        mock_find_file.return_value = epub_file
        # and we have a compile command instance
        lang = "en-US"
        build_format = "epub"
        compile_command = CompileCommand(self.ctx, lang, build_format)

        # When attempting to open the built file
        compile_command.open_built_file(build_format)

        # Then the file that was opened should be our file returned by the find method
        build_dir = os.path.join(os.getcwd(), "tmp/{0}/".format(lang))
        mock_launch.assert_called_once_with(os.path.join(build_dir, epub_file))
        # and the correct params were passed to find_file
        mock_find_file.assert_called_once_with(build_dir, "epub")

    def test_fails_on_invalid_format(self):
        # Given an invalid format
        build_format = "invalid-format"
        # and we have a compile command instance
        lang = "en-US"
        compile_command = CompileCommand(self.ctx, lang, build_format)

        # When attempting to run
        try:
            compile_command.execute()
            pytest.fail("A UsageError should have been thrown because of the invalid format")
        except click.exceptions.UsageError as e:
            # Then an error should be printed to the output
            assert "Invalid value for \"--format\": invalid choice: " + build_format in e.message
