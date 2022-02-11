from aura.commands.cmd_clean import CleanCommand

import base


class TestCleanCommand(base.TestBase):
    def test_print_debug(self):
        # Given that debug is on
        self.enable_debug_mode()
        # and we have a command instance
        source_format = "asciidoc"
        compile_command = CleanCommand(self.ctx, source_format)

        # When printing the debug information
        compile_command.print_parsed_debug_details()

        # Make sure we got the expected content printed
        logs = self.get_logs()
        assert "--type is asciidoc" in logs
