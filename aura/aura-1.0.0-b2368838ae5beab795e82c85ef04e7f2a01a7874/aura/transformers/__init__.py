import fnmatch
import inspect
import logging
import os
import sys
from collections import OrderedDict
from pkg_resources import iter_entry_points

from aura.exceptions import UnknownSourceFormatException
from aura.utils import INIConfigParser


log = logging.getLogger("aura.transformers")
plugin_group_name = "aura.transformers"

# Setup the supported filetypes for each transformer
registered_filetypes = OrderedDict()
registered_filetypes["publican"] = ["publican.cfg"]
registered_filetypes["asciidoc"] = ["*.adoc", "*.asciidoc"]


def get_transformers():
    transformers_dir = os.path.dirname(__file__)

    transformers = set()
    for filename in os.listdir(transformers_dir):
        if filename.endswith('.py') and filename.startswith("tf_"):
            transformers.add(filename[3:-3])
    for plugin in iter_entry_points(plugin_group_name):
        transformers.add(plugin.name)
    return list(transformers)


FORMATS = get_transformers()


def init_transformer(source_markup=None):
    """
    Find and initialize a transformer for the source markup format.

    :param source_markup: The source markup to find a transformer for.
    :type source_markup: str
    :return: The initialized transformer instance
    :rtype: aura.transformers.base.Transformer
    """
    if source_markup:
        if source_markup in FORMATS:
            return import_transformer(source_markup)
        else:
            raise UnknownSourceFormatException(source_markup)
    else:
        # Attempt to find the source format
        files = os.listdir(os.getcwd())
        for transformer, filetypes in registered_filetypes.items():
            for filetype in filetypes:
                if any(fnmatch.fnmatchcase(filename, filetype) for filename in files):
                    return import_transformer(transformer)

        # Fallback to using the publican transformer
        return import_transformer("publican")


def _is_transformer(obj):
    from aura.transformers.base import Transformer
    return inspect.isclass(obj) and issubclass(obj, Transformer) and obj != Transformer


def import_transformer(name):
    tf_name = tf_class = None
    if sys.version_info[0] == 2:
        name = name.encode('ascii', 'replace')
    # Check if the transformer is a plugin
    for plugin in iter_entry_points(plugin_group_name):
        if plugin.name == name:
            tf_class = plugin.load()
            tf_name = tf_class.__name__

    # Not a plugin, so import the relevant module
    if tf_class is None:
        import importlib
        mod = importlib.import_module('aura.transformers.tf_' + name)
        # Inspect the module to find the transformer class to use
        tf_name, tf_class = inspect.getmembers(mod, _is_transformer)[0]

    # Create the class
    instance = tf_class()
    log.debug("Using the %s transformer", tf_name.replace("Transformer", ""))
    return instance


class DocsMetadata(object):
    __ERROR_TEMPLATE__ = "Missing %(title)s metadata. Please ensure the %(title)s is defined in %(filepath)s, eg. %(key)s = value"

    def __init__(self, filepath=None, fd=None):
        self.filepath = filepath
        self.source = DocsMetadataSource()
        self.bugs = DocsMetadataBugs()

        self.title = None
        self.product = None
        self.version = None
        self.edition = None
        self.subtitle = None
        self.keywords = None
        self.abstract = None

        if filepath is not None:
            self.__parse(filepath, fd)

    def __parse(self, filepath, fp=None):
        parser = INIConfigParser(allow_no_value=True)

        # Read in the config
        if fp is None:
            with open(filepath, "r") as f:
                parser.readfp(f)
        else:
            parser.readfp(fp)

        if parser.has_section("source"):
            self.source.__dict__.update(parser.items("source"))

        if parser.has_section("metadata"):
            self.__dict__.update(parser.items("metadata"))

        if parser.has_section("bugs"):
            self.bugs.__dict__.update(parser.items("bugs"))

    def verify(self):
        """
        Verifies that required metadata exists.

        :return: True if the required data exists, otherwise false.
        """
        rv = True
        if not self.title:
            log.error(self.__ERROR_TEMPLATE__, {"title": "title", "key": "title", "filepath": self.filepath})
            rv = False

        if not self.subtitle:
            log.error(self.__ERROR_TEMPLATE__, {"title": "subtitle", "key": "subtitle", "filepath": self.filepath})
            rv = False

        if not self.product:
            log.error(self.__ERROR_TEMPLATE__, {"title": "product name", "key": "product", "filepath": self.filepath})
            rv = False

        if not self.version:
            log.error(self.__ERROR_TEMPLATE__, {"title": "product version", "key": "version", "filepath": self.filepath})
            rv = False

        if not self.abstract:
            log.error(self.__ERROR_TEMPLATE__, {"title": "abstract", "key": "abstract", "filepath": self.filepath})
            rv = False

        return rv

    def __str__(self):
        if isinstance(self.keywords, list):
            keywords = ", ".join(self.keywords)
        else:
            keywords = self.keywords

        return str(self.source) + "\n" + \
            "[metadata]\n" + \
            "title = " + (self.title or "") + "\n" + \
            "product = " + (self.product or "") + "\n" + \
            "version = " + (self.version or "") + "\n" + \
            "subtitle = " + (self.subtitle or "") + "\n" + \
            "edition = " + (self.edition or "") + "\n" + \
            "keywords = " + (keywords or "") + "\n" + \
            "abstract = " + (self.abstract or "") + "\n" + \
            "\n" + \
            str(self.bugs)


class DocsMetadataSource(object):
    def __init__(self):
        self.lang = "en-US"
        self.type = "Book"
        self.mainfile = None
        self.markup = None

    def __str__(self):
        return "[source]\n" + \
               "lang = " + (self.lang or "") + "\n" + \
               "type = " + (self.type or "") + "\n" + \
               "mainfile = " + (self.mainfile or "") + "\n" + \
               "markup = " + (self.markup or "") + "\n"


class DocsMetadataBugs(object):
    def __init__(self):
        self.reporting_url = None
        self.type = None
        self.product = None
        self.version = None
        self.component = None

    def __str__(self):
        return "[bugs]\n" + \
               "reporting_url = " + (self.reporting_url or "") + "\n" + \
               "type = " + (self.type or "") + "\n" + \
               "product = " + (self.product or "") + "\n" + \
               "version = " + (self.version or "") + "\n" + \
               "component = " + (self.component or "") + "\n"
