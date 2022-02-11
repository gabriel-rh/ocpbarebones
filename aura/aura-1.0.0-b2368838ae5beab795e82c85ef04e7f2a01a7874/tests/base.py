import logging

import aura
import pytest
from aura.compat import ConfigParser, StringIO
from click.core import Context, Command


SFTP_VIDEO_DIR = "/videos/"


def generate_fake_sys_config(tmpdir, app_name="aura"):
    config = ConfigParser()
    config.add_section(app_name)
    config.set(app_name, "data_dir", str(tmpdir))
    config.add_section(aura.VIDEOS_NAME)
    config.set(aura.VIDEOS_NAME, "sftp_host", "sftp.example.com")
    config.set(aura.VIDEOS_NAME, "sftp_video_dir", SFTP_VIDEO_DIR)
    config.set(aura.VIDEOS_NAME, "sftp_username", "storage")
    return config


def generate_fake_config():
    config = ConfigParser()
    config.add_section(aura.VIDEOS_NAME)
    return config


class TestBase(object):
    fmt = logging.Formatter('%(message)s', None)

    @pytest.fixture(autouse=True)
    def setup_logging_and_ctx(self, request, tmpdir):
        # Create a handler to log to
        handler = CaptureStreamHandler()
        handler.setFormatter(self.fmt)

        # Add the handler to the root logger
        root = logging.root
        root.addHandler(handler)
        root.setLevel(logging.INFO)

        # Setup the fake context
        self.ctx = self.generate_fake_context(tmpdir)
        self.handler = handler

        def fin():
            # Remove the handler for this test
            root.removeHandler(handler)
        request.addfinalizer(fin)

    def get_logs(self):
        return self.handler.stream.getvalue()

    def enable_debug_mode(self):
        self.ctx.obj['DEBUG'] = True
        logging.root.setLevel(logging.DEBUG)

    def generate_fake_context(self, tmpdir):
        command = Command('cli')
        ctx = Context(command, info_name=command.name)
        ctx.obj = {'app_version': aura.__version__,
                   'CONFIG': generate_fake_sys_config(tmpdir),
                   'USER_CONFIG': generate_fake_config()}
        return ctx


class CaptureStreamHandler(logging.StreamHandler):
    """A class that captures the logs sent to the handler"""
    def __init__(self):
        logging.StreamHandler.__init__(self)
        self.stream = StringIO()

    def close(self):
        logging.StreamHandler.close(self)
        self.stream.close()


class StringContaining(str):
    def __eq__(self, other):
        return self in other

    def __repr__(self):
        return '<STRING CONTAINING>'
