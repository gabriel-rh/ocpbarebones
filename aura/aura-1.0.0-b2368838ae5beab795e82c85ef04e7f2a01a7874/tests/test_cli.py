import logging

import aura
import aura.cli as aura_cli
from click.testing import CliRunner

import base


class TestCLI(base.TestBase):

    def test_version(self):
        # When printing the version
        runner = CliRunner()
        result = runner.invoke(aura_cli.cli, ["--version"])

        # Make sure we got the expected content printed
        assert result.exit_code == 0
        assert ("cli, version %s" % aura.__version__) in result.output

    def test_debug(self):
        # Given that debug is on
        self.ctx.obj['DEBUG'] = True
        self.enable_debug_mode()

        # When printing the debug information
        aura_cli.print_parsed_debug_details(self.ctx)

        # Make sure we got the expected content printed
        assert "--debug is on" in self.get_logs()

    def test_verbose(self):
        # Given that verbose is on
        self.ctx.obj['VERBOSE'] = True
        # and the log level is set to debug
        self.enable_debug_mode()

        # When printing the debug information
        aura_cli.print_parsed_debug_details(self.ctx)

        # Make sure we got the expected content printed
        assert "--verbose is on" in self.get_logs()

    def test_init_logging(self):
        # Given we won't be debugging and not printing verbose info
        debug = False
        verbose = False

        # When initialising the logging
        aura_cli.init_logging(debug, verbose)

        root = logging.root
        handler = None
        try:
            # Then the root logger should have a handler
            assert len(root.handlers) >= 2, "No handler was setup for the logging"
            # and the last handler is a ColoredConsoleHandler
            handler = root.handlers[-1]
            assert isinstance(handler, aura_cli.ColoredConsoleHandler)
            # and the log level is ERROR
            assert root.level == logging.ERROR, "The log level is not ERROR"
            # and the formatter is '%(message)s'
            assert handler.formatter._fmt == '%(message)s'
        finally:
            # Cleanup
            if handler is not None:
                root.removeHandler(handler)
            root.setLevel(logging.INFO)
            logging.getLogger("aura").setLevel(logging.NOTSET)

    def test_init_logging_verbose(self):
        # Given we will be verbose info logging
        debug = False
        verbose = True

        # When initialising the logging
        aura_cli.init_logging(debug, verbose)

        root = logging.root
        handler = None
        try:
            # Then the root logger should have a handler
            assert len(root.handlers) >= 2, "No handler was setup for the logging"
            # and the last handler is a ColoredConsoleHandler
            handler = root.handlers[-1]
            assert isinstance(handler, aura_cli.ColoredConsoleHandler)
            # and the log level is VERBOSE
            assert root.level == aura_cli.VERBOSE_LOG_LEVEL, "The log level is not VERBOSE"
            # and the formatter is '%(message)s'
            assert handler.formatter._fmt == '%(message)s'
            # and the verbose logging function exists
            assert hasattr(logging.Logger, 'verbose'), "The verbose logging function wasn't set"
        finally:
            # Cleanup
            if handler is not None:
                root.removeHandler(handler)
            if hasattr(logging.Logger, 'verbose'):
                delattr(logging.Logger, 'verbose')
            root.setLevel(logging.INFO)

    def test_init_logging_debug(self):
        # Given we will be debugging
        debug = True
        verbose = False

        # When initialising the logging
        aura_cli.init_logging(debug, verbose)

        root = logging.root
        handler = None
        try:
            # Then the root logger should have a handler
            assert len(root.handlers) >= 2, "No handler was setup for the logging"
            # and the last handler is a ColoredConsoleHandler
            handler = root.handlers[-1]
            assert isinstance(handler, aura_cli.ColoredConsoleHandler)
            # and the log level is DEBUG
            assert root.level == logging.DEBUG, "The log level is not DEBUG"
            # and the formatter is '%(message)s'
            assert handler.formatter._fmt == '%(message)s'
        finally:
            # Cleanup
            if handler is not None:
                root.removeHandler(handler)
            root.setLevel(logging.INFO)
