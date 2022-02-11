import io
import sys

import pytest
import requests


@pytest.fixture(autouse=True)
def no_requests(monkeypatch):
    monkeypatch.delattr(requests.sessions.Session, "request")


@pytest.fixture()
def publican_info(request, tmpdir):
    publican_cfg = tmpdir.join("publican.cfg")
    lang_dir = tmpdir.mkdir("en-US")
    book_xml_file = tmpdir.join("en-US", "Book_Info.xml")
    article_xml_file = tmpdir.join("en-US", "Article_Info.xml")

    def fin():
        if book_xml_file.check(exists=True):
            book_xml_file.remove()
        if article_xml_file.check(exists=True):
            article_xml_file.remove()
        lang_dir.remove()
        if publican_cfg.check(exists=True):
            publican_cfg.remove()
    request.addfinalizer(fin)

    return dict(cfg=publican_cfg,
                book_xml=book_xml_file,
                article_xml=article_xml_file,
                lang_dir=lang_dir,
                book_dir=tmpdir)


@pytest.fixture()
def custom_capsys(request):
    """Manually capture stdout/stderr, as capsys doesn't play well with click when running under python 3"""

    # Create the capture and start it
    capture = CaptureFixture()
    capture.start()

    # Setup the shutdown
    def fin():
        # Stop capturing and restart capsys
        capture.stop()
    request.addfinalizer(fin)

    return capture


@pytest.fixture()
def create_temp_video(request, tmpdir):
    # Make a temporary video file
    request.instance.video_file = video_file = tmpdir.join("video.mp4")
    video_file.write("")

    def fin():
        video_file.remove()
    request.addfinalizer(fin)


class CaptureFixture(object):
    def start(self):
        # Get a reference to the current stdout/err streams
        self._oldout = sys.stdout
        self._olderr = sys.stderr

        # Create new streams and set stdout/err to use them
        self.out = io.BytesIO()
        self.err = io.BytesIO()
        sys.stdout = self.out
        sys.stderr = self.err

    def stop(self):
        # Reset stdout/err back to the original streams
        sys.stdout = self._oldout
        sys.stderr = self._olderr

    def readouterr(self):
        out = self.out.getvalue().decode('UTF-8')
        err = self.err.getvalue().decode('UTF-8')
        return out, err
