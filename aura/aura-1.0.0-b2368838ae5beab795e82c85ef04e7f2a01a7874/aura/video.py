from __future__ import print_function
import json
import logging
import errno
import os
import subprocess
import sys

from PIL import Image
import numpy


log = logging.getLogger("aura.video")
_media_info_cache = {}


def get_media_info(filename):
    """
    Gets the media info of an audio/video file using ffprobe and returns the data as json

    :param filename: The video filename to get the media information from.
    """
    # Cache this as the data should be small and is faster than probing everytime some data needs to be read
    if filename in _media_info_cache:
        return _media_info_cache[filename]
    else:
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", filename]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        out, err = process.communicate()
        rv = process.returncode == 0 and json.loads(out) or None
        _media_info_cache[filename] = rv
        return rv


def get_video_resolution(file_or_media_info):
    """
    Gets a videos resolution.

    :param file_or_media_info:
    :return:
    """
    # Check if we got passed a filename, if so then load the media info
    if not isinstance(file_or_media_info, dict):
        media_info = get_media_info(file_or_media_info)
    else:
        media_info = file_or_media_info

    # Get the video stream
    for stream in media_info["streams"]:
        if stream["codec_type"] == "video":
            return int(stream["width"]), int(stream["height"])

    return None, None


def verify_input_video(input_file, base_dir=None):
    """
    Checks that the input video is a high definition mp4 video.

    :param input_file: The input video file to check
    """
    # Make sure the file exists
    fixed_input_file = input_file if base_dir is None else os.path.join(base_dir, input_file)
    if not os.path.isfile(fixed_input_file):
        log.error("Unable to find %s, no such file.", input_file)
        sys.exit(1)

    # Get the videos information
    media_info = get_media_info(fixed_input_file)
    if media_info is None:
        log.error("%s is not a valid MP4 or Ogg video.", input_file)
        sys.exit(-1)

    # Extract the format name and resolution
    format_name = media_info["format"]["format_name"]
    width, height = get_video_resolution(media_info)

    if not any(name in format_name for name in ("mp4", "ogg")):
        log.error("%s is not a valid MP4 or Ogg video.", input_file)
        sys.exit(-1)
    elif height <= 480:
        log.warn("%s is not a high definition video, which may result in loss of quality.", input_file)


def transcode(transcoder, input_file, answer_yes=False, output_path=None):
    """
    Transcodes the videos to the required formats

    :param transcoder:
    :param input_file: The input video file to transcode.
    :param answer_yes: Answer yes to overwriting any existing files.
    :param output_path: The path the transcoded files should be stored in.
    :return: Returns a list of file names for the transcoded videos.
    """
    # Get the media info for the input file
    media_info = get_media_info(input_file)
    format_name = media_info["format"]["format_name"]

    if "mp4" in format_name:
        return _transcode(transcoder, input_file, VideoFormat.OGV, answer_yes, output_path)
    elif "ogg" in format_name:
        return _transcode(transcoder, input_file, VideoFormat.MP4, answer_yes, output_path)


def _transcode(transcoder, input_file, video_format, answer_yes, output_path):
    """
    Transcodes an input high definition video to an output video specified by the format and a SD MP4.

    :param transcoder:
    :param input_file: The input video file to transcode.
    :param video_format: The format to transcode the input video into.
    :param answer_yes: Answer yes to overwriting any existing files.
    :param output_path: The path the transcoded files should be stored in.
    :return: Returns a list of file names for the transcoded videos.
    """
    if output_path is not None:
        basename = os.path.basename(input_file)
        output_file = os.path.join(output_path, basename)
    else:
        output_file = os.path.abspath(input_file)

    (prefix, sep, suffix) = output_file.rpartition('.')
    outfile = prefix + "." + video_format.get_file_extension()
    outfile_sd = prefix + "-SD.mp4"

    # Convert the HD video to the specified format
    if transcoder.transcode(input_file, outfile, video_format, answer_yes=answer_yes):
        log.info("Video successfully converted to %s", video_format.get_name())
    else:
        log.error("Failed to convert the video to %s", video_format.get_name())
        sys.exit(-1)

    # Convert the HD video to standard definition
    if transcoder.transcode(input_file, outfile_sd, VideoFormat.MP4, Size.LARGE, answer_yes=answer_yes):
        log.info("Video successfully converted to SD from HD")
    else:
        log.error("Failed to convert the video to standard definition")
        sys.exit(-1)

    return [outfile, outfile_sd]


def get_video_thumbnail(video_file, size=None):
    """
    Gets a frame from a video and returns it as a PIL Image object. The frame that is used, is from within a short time after the start to
    allow for video fade ins.

    :param video_file: The video to get the thumbnail from.
    :param size: The size of the thumbnail to generate in pixels (WxH).
    :return: A PIL image object for the video thumbnail.
    """
    if not os.path.isfile(video_file):
        raise IOError(errno.ENOENT, "No such file or directory", video_file)

    # Get the video resolution
    width, height = get_video_resolution(video_file) if size is None else (int(n) for n in size.split("x"))
    buffer_size = width * height * 3 + 10

    # See http://zulko.github.io/blog/2013/09/27/read-and-write-video-frames-in-python-using-ffmpeg/
    # Use 5 secs to allow for a fade in
    command = ['ffmpeg', '-ss', '00:00:05', '-i', video_file, '-f', 'image2pipe', '-pix_fmt', 'rgb24', '-vcodec', 'rawvideo',
               '-v', 'quiet']
    if size:
        command.extend(['-s', size])
    command.append('-')
    pipe = subprocess.Popen(command, stdout=subprocess.PIPE, bufsize=buffer_size)

    # read W*H*3 bytes (= 1 frame)
    raw_image = pipe.stdout.read(width * height * 3)
    # transform the byte read into a numpy array
    image = numpy.fromstring(raw_image, dtype='uint8')
    image = image.reshape((int(height), int(width), 3))
    # throw away the data in the pipe's buffer.
    pipe.stdout.flush()
    pipe.terminate()

    # Convert the numpy array to a PIL Image
    return Image.fromarray(image, 'RGB')


class VideoFormat(object):
    def __init__(self, codec_id, name, file_ext, vcodec, acodec):
        self.id = codec_id
        self.name = name
        self.file_ext = file_ext
        self.vcodec = vcodec
        self.acodec = acodec

    def get_name(self):
        return self.name

    def get_video_codec(self):
        return self.vcodec

    def get_audio_codec(self):
        return self.acodec

    def get_file_extension(self):
        return self.file_ext


VideoFormat.OGV = VideoFormat(1, "Ogg", "ogv", "libtheora", "libvorbis")
VideoFormat.MP4 = VideoFormat(2, "MP4", "mp4", "libx264", "libmp3lame")


class Size(object):
    XLARGE = "1280x720"
    LARGE = "856x480"
    MEDIUM = "640x360"
    SMALL = "480x270"


class VideoTranscoder(object):
    def __init__(self, quiet=False, verbose=False, debug=False):
        self.quiet = quiet
        self.debug = debug
        self.verbose = verbose

    def transcode(self, input_file, output_file, video_format, size=None, answer_yes=False):
        """
        Runs ffmpeg to transcode a input video and saves it as output_file.

        :param input_file: The video to transcode
        :param output_file: The output filename to save the transcoded video to
        :param video_format: The video format to transcode the video to
        :param size: The size of the frame to use when transcoding
        :param answer_yes: Whether or not "yes" should be answered for any user input questions from ffmpeg
        :return: True if the video was successfully transcoded, otherwise false
        """
        additional_args = None

        # Get the media info for the input file
        media_info = get_media_info(input_file)
        format_name = media_info["format"]["format_name"]

        # Setup the codecs and additional arguments
        if video_format == VideoFormat.MP4:
            video_codec = video_format.get_video_codec()
            if "mp4" in format_name:
                audio_codec = "copy"
            else:
                audio_codec = video_format.get_audio_codec()
            additional_args = ["-crf", "22", "-threads", "0"]
        else:
            audio_codec = video_format.get_audio_codec()
            video_codec = video_format.get_video_codec()

        # Build the arguments
        args = ["-acodec", audio_codec, "-vcodec", video_codec]
        if size is not None:
            args.extend(["-s", size])
        if additional_args is not None:
            args.extend(additional_args)

        # Do the transcode
        return self._run_ffmpeg(input_file, output_file, args, answer_yes)

    def _run_ffmpeg(self, input_file, output_file, additional_args=None, answer_yes=False):
        """
        Runs ffmpeg to transcode a input video and saves it as output_file.

        :param input_file: The video to transcode
        :param output_file: The output filename to save the transcoded video to
        :param additional_args: Any additional arguments to pass to ffmpeg
        :param answer_yes: Whether or not "yes" should be answered for any user input questions from ffmpeg
        :return: True if ffmpeg ran successfully, otherwise false
        """
        # Build the command
        ffmpeg_cmd = ["ffmpeg"]

        # Set the log level for ffmpeg
        if self.debug:
            ffmpeg_cmd.extend(["-v", "debug"])
        elif self.verbose:
            ffmpeg_cmd.extend(["-v", "verbose"])
        elif self.quiet:
            # Only show warnings/errors
            ffmpeg_cmd.extend(["-v", "warning"])
            # Add the -stats option to show progress
            ffmpeg_cmd.append("-stats")

        # Answer yes to override questions if needed
        if answer_yes:
            ffmpeg_cmd.append("-y")

        # Set the input/output file and additional args
        ffmpeg_cmd.extend(["-i", input_file])
        if additional_args is not None and len(additional_args) > 0:
            ffmpeg_cmd.extend(additional_args)
        ffmpeg_cmd.append(output_file)

        # Execute the command
        exit_status = subprocess.call(ffmpeg_cmd)

        # If quiet we need to print a new line, as one isn't printed by ffmpeg
        if exit_status == 0 and self.quiet:
            print('')

        return exit_status == 0
