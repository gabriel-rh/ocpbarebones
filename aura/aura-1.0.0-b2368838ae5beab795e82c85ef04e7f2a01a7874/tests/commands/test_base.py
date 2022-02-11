import uuid

import pytest
from aura.commands.base import BaseXMLFeedCommand

import base


class TestBaseXMLFeedCommand(base.TestBase):
    @pytest.fixture(autouse=True)
    def init_command(self, setup_logging_and_ctx):
        self.lang = "en-US"
        self.doc_uuid = uuid.uuid4()
        self.command = BaseXMLFeedCommand(self.ctx, self.lang, self.doc_uuid, 'drupal-book')

    def test_print_debug(self):
        # Given that debug is on
        self.enable_debug_mode()
        self.command.dry_run = True

        # When printing the debug information
        self.command.print_parsed_debug_details()

        # Make sure we got the expected content printed
        logs = self.get_logs()
        assert "--lang is {0}".format(self.lang) in logs
        assert "--format is drupal-book" in logs
        assert "--dry-run is on" in logs
