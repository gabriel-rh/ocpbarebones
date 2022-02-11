import logging


class Transformer(object):
    valid_formats = []
    single_file_formats = []
    formats_sep = ","
    allows_multiple_formats = False

    def __init__(self):
        self.log = logging.getLogger(self.__module__ + "." + self.__class__.__name__)

    def get_doc_id(self, config=None, lang=None):
        """
        Gets the book id from the source content/configuration.

        :param config: The build configuration file to use.
        :type config: str
        :param lang: The language that is currently being built.
        :type lang: str
        :return: The documents natural id. eg Product-Version-Title-Lang
        :rtype: str
        """
        raise NotImplementedError()

    def set_doc_id(self, doc_id, lang):
        """
        Sets an override for the document id.

        :param doc_id: The documents natural id. eg Product-Version-Title-Lang
        :param lang: The language that is currently being built.
        """
        raise NotImplementedError()

    def get_npv(self, config=None):
        """
        Gets the name, product and version of the source content

        :param config: The configuration file.
        :type config: str
        :return: The directory path for the build directory.
        :rtype: tuple
        """

    def get_build_root_dir(self, config=None):
        """
        Gets the name of the root build directory using the configuration file.

        :param config: The configuration file.
        :type config: str
        :return: The directory path for the build directory.
        :rtype: str
        """
        raise NotImplementedError()

    def get_build_dir(self, lang, build_format, config=None):
        """
        Gets the name of the directory where all build files are stored using the configuration file provided.

        :param lang: The language of the build.
        :type lang: str
        :param build_format: The builds format.
        :type build_format: str
        :param config: The configuration file.
        :type config: str
        :return: The directory path for the build files directory.
        :rtype: str
        """
        raise NotImplementedError()

    def get_build_additional_files_dir(self, lang, build_format, config=None):
        """
        Gets the name of the directory where all additional files (images, videos, etc...) are stored using the configuration file provided.

        :param lang: The language of the build.
        :type lang: str
        :param build_format: The builds format.
        :type build_format: str
        :param config: The configuration file.
        :type config: str
        :return: The directory path for the build files directory.
        :rtype: str
        """
        raise NotImplementedError()

    def get_build_archives_dir(self, lang, config=None):
        """
        Gets the name of the directory where all archives are stored using the configuration file provided.

        :param lang: The language of the build.
        :type lang: str
        :param config: The configuration file.
        :type config: str
        :return: The directory path for the build archives directory.
        :rtype: str
        """
        raise NotImplementedError()

    def build_format(self, src_lang, lang, build_format, config=None, additional_args=None, main_file=None, doctype=None):
        """
        Builds source content either using an external tool, or building the feed locally.

        :param src_lang: The source language of the document.
        :type src_lang: str
        :param build_format: The format to build as.
        :type build_format: str
        :param lang: The language to build for.
        :type lang: str
        :param config: A configuration file to use when building.
        :type config: str
        :param additional_args: Any additional arguments to be passed to the tool.
        :type additional_args: str
        :param main_file: The main file to build from.
        :type main_file: str
        :param doctype: The type of document that is being built. (book|article)
        :type doctype: str
        :return: True if the build was successful, otherwise false.
        :rtype: bool
        """
        raise NotImplementedError()

    def build_formats(self, src_lang, lang, build_formats, config=None, additional_args=None, main_file=None, doctype=None):
        """
        Builds source content either using an external tool, or building the feed locally.

        :param src_lang: The source language of the document.
        :type src_lang: str
        :param build_formats: A list of formats to build as.
        :type build_formats: list [str]
        :param lang: The language to build for.
        :type lang: str
        :param config: A configuration file to use when building.
        :type config: str
        :param additional_args: Any additional arguments to be passed to the tool.
        :type additional_args: str
        :param main_file: The main file to build from.
        :type main_file: str
        :param doctype: The type of document that is being built. (book|article)
        :type doctype: str
        :return: True if the build was successful, otherwise false.
        :rtype: bool
        """
        raise NotImplementedError()

    def build_translation_files(self, langs, config=None, main_file=None, pot_only=False, po_only=False, src_lang=None, doctype=None):
        """
        Builds the translation files from the source content.

        :param src_lang: The source language of the document.
        :type src_lang: str
        :param langs: A list of languages to build translation files for.
        :type langs: list[str]
        :param config: A configuration file to use when building.
        :type config: str
        :param main_file: The main file to build translations from.
        :type main_file: str
        :param pot_only:
        :type pot_only: bool
        :param po_only:
        :type po_only: bool
        :param doctype: The type of document that is being built. (book|article)
        :type doctype: str
        :return: True if the translation files were built successfully, otherwise false.
        :rtype: bool
        """
        raise NotImplementedError()

    def get_build_main_file(self, lang, build_format, config=None):
        """
        Get the main build file for the input build format.

        :param lang: The language of the build.
        :type lang: str
        :param build_format: The builds format.
        :type build_format: str
        :param config: A configuration file used when building.
        :type config: str
        :return: The path to the main build file.
        :rtype: str
        """
        raise NotImplementedError()

    def clean_build_files(self, config=None):
        """
        Clean any temporary build files on the local machine.

        :param config: A configuration file used when cleaning.
        :type config: str
        :return: True if the build files were clean successfully, otherwise False.
        :rtype: bool
        """
        raise NotImplementedError()


class XMLFeedTransformer(Transformer):
    def __init__(self, feed_protocol=1):
        """
        :param feed_protocol: The XML Feed protocol to use when generating XML Feeds
        """
        super(XMLFeedTransformer, self).__init__()
        self.feed_protocol = feed_protocol

    def build_xml_feed(self, doc_uuid, src_lang, lang, config=None, additional_args=None, additional_formats=None, main_file=None,
                       doctype=None, archive=False):
        """
        Builds an XML Feed and archive by either using an external tool, or building the feed locally.

        :param doc_uuid: A UUID to identify the document being built.
        :type doc_uuid: uuid.UUID
        :param src_lang: The source language of the document.
        :type src_lang: str
        :param lang: The language to build the XML feed for.
        :type lang: str
        :param config: A configuration file to use when building.
        :type config: str
        :param additional_args: Any additional arguments.
        :type additional_args: str
        :param additional_formats: A list of any additional formats to build alongside the XML feed.
        :type additional_formats: list [str]
        :param main_file: The main file to build from.
        :type main_file: str
        :param doctype: The type of document that is being built. (book|article)
        :type doctype: str
        :param archive: Build an archive for the XML feed.
        :type archive: bool
        :return: True if the build was successful, otherwise false.
        :rtype: bool
        """
        raise NotImplementedError()

    def get_videos_from_feed(self, xml_feed):
        """
        Gets a list of local videos used in the book/article from the XML Feed.

        :param xml_feed: An Element tree for the XML feed.
        :type xml_feed:  etree._ElementTree
        :return: A list of video elements in the XML feed.
        :rtype:  list [etree._Element]
        """
        raise NotImplementedError()

    def get_images_from_feed(self, xml_feed):
        """
        Gets a list of local images used in the book/article from the XML Feed.

        :param xml_feed: An Element tree for the XML feed.
        :type xml_feed:  etree._ElementTree
        :return: A list of image elements in the XML feed.
        :rtype: list [etree._Element]
        """
        raise NotImplementedError()

    def get_file_links_from_feed(self, xml_feed):
        """
        Gets a list of elements that link to local additional files used in the book/article from the XML Feed.

        :param xml_feed: An Element tree for the XML feed.
        :type xml_feed:  etree._ElementTree
        :return: A list of link elements in the XML feed.
        :rtype:  list [etree._Element]
        """
        raise NotImplementedError()
