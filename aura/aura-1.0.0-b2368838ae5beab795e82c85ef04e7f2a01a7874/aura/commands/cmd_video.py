import sys

import click

from aura import video, utils
from aura.video import VideoTranscoder
from aura.commands.base import BaseCommand


@click.group("video", short_help="Subcommands for interacting with videos.")
def cli():
    """Subcommands for interacting with videos."""
    pass


@cli.command("transcode", short_help="Takes a high definition mp4 video and converts it to OGG and a standard definition mp4.")
@click.option("--yes", "-y", help="Answer yes to any y/N questions.", is_flag=True, default=False)
@click.argument("video_file", "VFILE", metavar="VFILE", type=click.Path(exists=True, dir_okay=False, resolve_path=True))
@click.pass_context
def transcode_videos(ctx, yes, video_file):
    """Takes a high definition mp4 video and converts it to OGG and a standard definition mp4."""
    cmd = VideoTranscodeCommand(ctx, yes, video_file)
    cmd.execute()


class VideoTranscodeCommand(BaseCommand):
    def __init__(self, ctx, answer_yes, video_file):
        super(VideoTranscodeCommand, self).__init__(ctx)
        self.answer_yes = answer_yes
        self.video_file = video_file

    def print_parsed_debug_details(self):
        """Prints information useful for debugging the command"""
        if self.answer_yes:
            self.log.debug("--yes is True")
        if self.video_file:
            self.log.debug("VFILE is %s", self.video_file)

    def _execute(self):
        """Perform the actions for the video upload command"""
        super(VideoTranscodeCommand, self)._execute()

        # Check to make sure ffmpeg is installed
        if utils.which("ffmpeg") is None:
            self.log.error("ffmpeg is not currently installed and is needed to be able to transcode videos. " +
                           "Please ensure it is installed and try again")
            sys.exit(-1)

        # Make sure the input file is a high definition mp4
        video.verify_input_video(self.video_file)

        # Transcode the video file
        transcoder = VideoTranscoder(True, self.verbose_enabled(), self.debug_enabled())
        video.transcode(transcoder, self.video_file, self.answer_yes)

        # Print a success message
        self.log.info("Successfully transcoded the video")
