import mock
import pytest
from aura.commands.cmd_video import VideoTranscodeCommand
from aura import video

import base


@pytest.mark.usefixtures("create_temp_video")
class TestVideoTranscodeCommand(base.TestBase):

    def test_print_debug(self):
        # Given that debug is on
        self.enable_debug_mode()
        # and we have been given the file path
        video_file = str(self.video_file)
        video_upload_command = VideoTranscodeCommand(self.ctx, True, video_file)

        # When printing the debug information
        video_upload_command.print_parsed_debug_details()

        # Make sure we got the expected content printed
        logs = self.get_logs()
        assert "--yes is True" in logs
        assert "VFILE is {0}".format(video_file) in logs

    @mock.patch("aura.video.get_media_info")
    @mock.patch("subprocess.call")
    def test_transcode_videos_success(self, mock_subprocess_call, mock_media_info):
        # Given the call to ffmpeg works
        mock_subprocess_call.return_value = 0
        # and we have been given a valid video
        video_file = str(self.video_file)
        # and the media info is successfully returned
        mock_media_info.return_value = dict(format=dict(format_name="mp4"))
        # and a transcoder
        transcoder = video.VideoTranscoder()

        # When transcoding the video
        video_files = video.transcode(transcoder, video_file)

        # Then make sure we got the correct video files
        (prefix, sep, suffix) = video_file.rpartition('.')
        assert prefix + ".ogv" in video_files
        assert prefix + "-SD.mp4" in video_files
        # and the success messages are in the logs
        logs = self.get_logs()
        assert "Video successfully converted to Ogg" in logs
        assert "Video successfully converted to SD from HD" in logs

    @mock.patch("aura.video.get_media_info")
    @mock.patch("subprocess.call")
    def test_transcode_videos_ogg_fail(self, mock_subprocess_call, mock_media_info):
        # Given the call to ffmpeg fails for the first invocation
        mock_subprocess_call.return_value = 137
        # and we have been given a valid video
        video_file = str(self.video_file)
        # and the media info is successfully returned
        mock_media_info.return_value = dict(format=dict(format_name="mp4"))
        # and a transcoder
        transcoder = video.VideoTranscoder()

        # When transcoding the video
        try:
            video.transcode(transcoder, video_file)
        except SystemExit:
            # Make sure an error was printed
            logs = self.get_logs()
            assert "Failed to convert the video to Ogg" in logs
        else:
            pytest.fail("sys.exit() should have been called")
