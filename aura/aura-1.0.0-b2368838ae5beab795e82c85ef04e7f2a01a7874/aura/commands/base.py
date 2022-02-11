import logging
import sys

from lxml import etree
from lxml.etree import XMLSyntaxError, XIncludeError

from aura import utils
from aura.compat import ConfigParser
from aura.exceptions import InvalidInputException
from aura.transformers import init_transformer


class BaseCommand(object):
    def __init__(self, ctx):
        self.ctx = ctx
        self.log = logging.getLogger(self.__module__ + "." + self.__class__.__name__)
        self.app_name = ctx.find_root().info_name

    def print_parsed_debug_details(self):
        """Prints information useful for debugging the command"""
        pass

    def debug_enabled(self):
        """Checks if the --debug option was passed to the application"""
        return ("DEBUG" in self.ctx.obj and self.ctx.obj["DEBUG"]) and True or False

    def verbose_enabled(self):
        """Checks if the --verbose option was passed to the application"""
        return ("VERBOSE" in self.ctx.obj and self.ctx.obj["VERBOSE"]) and True or False

    def execute(self, *args, **kwargs):
        """Perform the actions for the command"""
        try:
            return self._execute(*args, **kwargs)
        except (IOError, InvalidInputException) as e:
            self.log.error(e)
            sys.exit(-1)

    def _execute(self, *args, **kwargs):
        """Perform the actions for the command"""
        if self.debug_enabled():
            self.print_parsed_debug_details()

    def _get_config_value(self, key, section=None):
        section = section or self.app_name
        config = self.ctx.obj['CONFIG']
        user_config = self.ctx.obj['USER_CONFIG']
        if user_config.has_option(section, key):
            return user_config.get(section, key)
        elif config.has_option(section, key):
            return config.get(section, key)
        else:
            return None

    def _get_resolved_config(self,):
        """
        Gets the resolved config based on reading from various different locations.

        :return: A ConfigParser object containing the resolved configuration.
        """
        if 'FINAL_CONFIG' in self.ctx.obj:
            return self.ctx.obj['FINAL_CONFIG']
        else:
            # Get the system configuration settings
            config = self.ctx.obj['CONFIG']
            user_config = self.ctx.obj['USER_CONFIG']

            # Build the config
            final_config = ConfigParser()

            for section in set(config.sections() + user_config.sections()):
                final_config.add_section(section)

                # Copy the global config values
                if config.has_section(section):
                    for (key, value) in config.items(section, raw=True):
                        final_config.set(section, key, str(value))

                # Copy the user config values
                if user_config.has_section(section):
                    for (key, value) in user_config.items(section, raw=True):
                        final_config.set(section, key, str(value))

            self.ctx.obj['FINAL_CONFIG'] = final_config
            return final_config


class BaseXMLFeedCommand(BaseCommand):
    def __init__(self, ctx, lang, doc_uuid, build_format, build_config=None, ignore_updated_videos=False, main_file=None,
                 source_format=None, doctype=None, dry_run=False):
        super(BaseXMLFeedCommand, self).__init__(ctx)
        self.lang = lang
        self.doc_uuid = doc_uuid
        self.build_format = build_format
        self.build_config = build_config
        self.source_format = source_format
        self.main_file = main_file
        self.dry_run = dry_run
        self.doctype = doctype
        self.ignore_updated_videos = ignore_updated_videos

        self.transformer = init_transformer(source_format)

    def print_parsed_debug_details(self):
        """Prints information useful for debugging the command"""
        super(BaseXMLFeedCommand, self).print_parsed_debug_details()
        if self.lang:
            self.log.debug("--lang is %s", self.lang)
        if self.doc_uuid:
            self.log.debug("--uuid is %s", self.doc_uuid)
        if self.build_format:
            self.log.debug("--format is %s", self.build_format)
        if self.build_config:
            self.log.debug("--build-config is %s", self.build_config)
        if self.main_file:
            self.log.debug("--main-file is %s", self.main_file)
        if self.source_format:
            self.log.debug("--type is %s", self.source_format)
        if self.doctype:
            self.log.debug("--doctype is %s", self.doctype)
        if self.dry_run:
            self.log.debug("--dry-run is on")

    def get_xml_feed(self):
        """
        Create an Element Tree from the built XML feed.

        :return:
        """
        # Get the XML file
        xml_file = self.transformer.get_build_main_file(self.lang, self.build_format, self.build_config)

        # Log a useful message
        self.log.info("Parsing %s to find additional files...", xml_file)

        try:
            # Create the parser/resolvers
            parser = etree.XMLParser(load_dtd=False, strip_cdata=False)
            parser.resolvers.add(utils.XMLEntityResolver())
            feed_tree = etree.parse(xml_file, parser)
        except (XMLSyntaxError, XIncludeError) as e:
            self.log.error(e)
            self.log.error("Unable to parse the XML feed")
            sys.exit(-1)
        except IOError as e:
            self.log.error("%s: %s", e.strerror, e.filename)
            self.log.error("Unable to parse the XML feed")
            sys.exit(-1)

        return feed_tree

    def save_xml_feed(self, xml_feed):
        """
        Saves a XML Tree, that represents the XML feed, to file.

        :param xml_feed: The XML feed to convert to a string and save.
        :type xml_feed:  etree._ElementTree
        """
        # Get the XML file name/path
        xml_file = self.transformer.get_build_main_file(self.lang, self.build_format, config=self.build_config)

        # Save the XML tree
        with open(xml_file, 'w') as f:
            xml = etree.tostring(xml_feed, encoding="UTF-8", xml_declaration=True)
            f.write(xml)
