import os
import re

from lxml import etree

from aura import utils
from aura.compat import SafeConfigParser, StringIO, basestring, unicode


CONFIG_CACHE = {}
DOCBOOK_XSL_URI = "http://docbook.sourceforge.net/release/xsl/current"
XML_FEED_FORMAT = "drupal-book"
LXML_XML_NS = "{http://www.w3.org/XML/1998/namespace}"
LXML_DOCBOOK_NS = "{http://docbook.org/ns/docbook}"
LXML_DOCBOOK_L10N_NS = "{http://docbook.sourceforge.net/xmlns/l10n/1.0}"
LXML_XINCLUDE_NS = "{http://www.w3.org/2001/XInclude}"
CHUNKING_ELES = {
    'book': {'format': 'bk{0:02d}', 'any_level': True},
    'article': {'format': 'ar{0:02d}', 'any_level': True},
    'chapter': {'format': 'ch{0:02d}', 'any_level': True},
    'appendix': {'format': 'ap{0}', 'any_level': True, 'use_alpha': True},
    'part': {'format': 'pt{0:02d}', 'any_level': True},
    'preface': {'format': 'pr{0:02d}', 'any_level': True},
    'index': {'format': 'ix{0:02d}', 'any_level': True},
    'reference': {'format': 'rn{0:02d}', 'any_level': True},
    'refentry': {'format': 're{0:02d}', 'any_level': True},
    'colophon': {'format': 'co{0:02d}', 'any_level': True},
    'bibliography': {'format': 'bi{0:02d}', 'any_level': True},
    'glossary': {'format': 'go{0:02d}', 'any_level': True},
    'topic': {'format': 'to{0:02d}', 'any_level': True},
    'section': {'format': 's{0:02d}', 'use_parent': True},
    'sect1': {'format': 's{0:02d}', 'use_parent': True},
    'sect2': {'format': 's{0:02d}', 'use_parent': True},
    'sect3': {'format': 's{0:02d}', 'use_parent': True},
    'sect4': {'format': 's{0:02d}', 'use_parent': True},
    'sect5': {'format': 's{0:02d}', 'use_parent': True},
    'legalnotice': {'format': 'ln{0:02d}', 'any_level': True}
}
SECTION_ELES = [
    'section',
    'sect1',
    'sect2',
    'sect3',
    'sect4',
    'sect5',
    'topic',
    'simplesect'
]
DEFAULT_TOC_ELES = CHUNKING_ELES.keys()
TOC_STANDALONE_ELES = [
    'bibliography',
    'glossary',
    'index',
    'legalnotice',
    'refentry',
    'reference'
]


def get_config_val(config, option, section='publican', default=None):
    """
    Gets a publican configuration option and strips any quotation marks that shouldn't be returned.

    :param config: The publican.cfg configuration to get configuration values from.
    :param option: The option name to lookup.
    :param section: The section of the option.
    :param default: The default value to return, if the option doesn't exist.
    :return: The value stripped of any quotation marks.
    """

    if config.has_option(section, option):
        return config.get(section, option).lstrip('"').rstrip('"')
    else:
        return default


def load_publican_config(config_file, cfg_dir=None):
    """
    Loads a publican configuration from either a local file or a cached copy.

    :param config_file:
    :param cfg_dir:
    :return:
    """
    # Resolve the config file path
    cfg_dir = cfg_dir or os.getcwd()
    config_file = config_file if config_file is not None else os.path.join(cfg_dir, "publican.cfg")

    # Load the config file if it hasn't been cached
    if config_file not in CONFIG_CACHE:
        # Parse the configuration file first to get any overrides
        with (open(config_file, "r")) as fp:
            publican_config = SafeConfigParser(defaults={
                'xml_lang': 'en-US',
                'type': 'Book',
                'dtdver': '4.5',
                'tmp_dir': 'tmp',
                'chunk_section_depth': '4',
                'toc_section_depth': '2',
                'brand': 'common'
            })
            publican_config.readfp(StringIO("[publican]\n" + fp.read()))

        # Add the config file to the cache
        CONFIG_CACHE[config_file] = publican_config

    return CONFIG_CACHE[config_file]


def load_publican_info_xml(book_lang_dir, publican_cfg=None):
    """
    Looks up the info xml file from the config and parses it.

    :param book_lang_dir: The book language directory containing the XML files.
    :param publican_cfg: The publican.cfg file to use.
    :return: The parsed info file XML file
    :raise IOError: If the book info xml can't be found or an entity/xinclude can't be found.
    :raise XMLSyntaxError: If the books info xml cannot be parsed due to xml errors.
    :raise XIncludeError: If the books info xml contains an invalid XInclude.
    """
    # If publican_cfg is a string, then treat it as a filepath and load the config
    if publican_cfg is None or isinstance(publican_cfg, basestring):
        book_dir = os.path.dirname(book_lang_dir)
        publican_config = load_publican_config(publican_cfg, cfg_dir=book_dir)
    else:
        publican_config = publican_cfg

    # Find where the info file is based on the publican.cfg options
    book_type = get_config_val(publican_config, "type")
    if publican_config.has_option("publican", "info_file"):
        info_file = os.path.join(book_lang_dir, get_config_val(publican_config, "info_file"))
    else:
        info_file = os.path.join(book_lang_dir, book_type + "_Info.xml")

    # Parse the info xml content and resolve the xincludes
    tree = utils.parse_xml(info_file)
    tree.xinclude()

    return tree.getroot()


def get_npv_and_lang_from_dir(book_dir, publican_cfg=None, use_config_overrides=True):
    """
    Gets a books name/title, product, version and base language from the XML/publican.cfg stored in a book directory

    :param book_dir: The book directory to generate the id for.
    :param publican_cfg: The publican.cfg file to use.
    :param use_config_overrides: Whether or not the publican.cfg overrides should be used.
    :return: The title, product, version and language for the XML/Publican configuration.
    :raise IOError: If the book info xml can't be found or an entity/xinclude can't be found.
    :raise XMLSyntaxError: If the books info xml cannot be parsed due to xml errors.
    :raise XIncludeError: If the books info xml contains an invalid XInclude.
    """
    # Parse the configuration file first to get any overrides
    publican_config = load_publican_config(publican_cfg, cfg_dir=book_dir)

    # Load the info file and pull the title, product and version from the info file
    lang = get_config_val(publican_config, "xml_lang")
    book_lang_dir = os.path.join(book_dir, lang)
    info_ele = load_publican_info_xml(book_lang_dir, publican_config)
    title, product, version = get_npv_from_xml(info_ele, publican_config, use_config_overrides)

    return title, product, version, lang


def get_doc_id_from_npv(title, product, version, lang):
    """
    Builds the book id from the values provided.

    :param title:
    :param product:
    :param version:
    :param lang:
    """
    title = utils.clean_for_rpm_name(title)
    product = utils.clean_for_rpm_name(product)
    version = utils.clean_for_rpm_name(version)

    return "{0}-{1}-{2}-{3}".format(product, version, title, lang)


def get_npv_from_xml(xml_ele, publican_cfg=None, use_config_overrides=False):
    """
    Gets the a DocBook book/article title/name, product and version from a lxml tree object.

    :param xml_ele: The parsed lxml element or tree object.
    :param publican_cfg: The publican.cfg file to use.
    :param use_config_overrides: Whether or not the publican.cfg overrides should be used.
    :return: The title, product and version retrieved from the tree.
    """
    # Get the resulting parsed xml tree
    xml_ele = utils.ensure_lxml_element(xml_ele)

    # Get the title/product/version from the info xml
    title = utils.find_element_value(xml_ele, "title")
    product = utils.find_element_value(xml_ele, "productname")
    version = utils.find_element_value(xml_ele, "productnumber")

    # Determine the actual values that should be used
    if use_config_overrides:
        # If publican_cfg is a string, then treat it as a filepath and load the config
        if publican_cfg is None or isinstance(publican_cfg, basestring):
            publican_config = load_publican_config(publican_cfg)
        else:
            publican_config = publican_cfg

        # Load the overrides
        title = publican_config.has_option("publican", "docname") and get_config_val(publican_config, "docname") or title
        product = publican_config.has_option("publican", "product") and get_config_val(publican_config, "product") or product
        version = publican_config.has_option("publican", "version") and get_config_val(publican_config, "version") or version

    return title, product, version


def _parse_docbook_ver(docbook_ver):
    """
    Parses a docbook version into it's major and minor components and returns it as a tuple
    """
    versions = docbook_ver.split(".")
    major_version = int(versions[0])
    if len(versions) >= 2:
        minor_version = int(versions[1])
    else:
        minor_version = 0
    return major_version, minor_version


def get_dtdver(publican_cfg):
    """
    Gets the `dtdver` setting from the publican configuration, defaulting to 4.5 if nothing is set.

    :param publican_cfg: The path to the publican configuration file
    :type publican_cfg: str
    :return: The DTD version of the source content
    :rtype: (int, int)
    """
    # Parse the configuration file first to get any overrides
    publican_config = load_publican_config(publican_cfg)
    dtdver = get_config_val(publican_config, 'dtdver')
    return _parse_docbook_ver(dtdver)


def get_xml_lang(publican_cfg):
    """
    Gets the `xml_lang` setting from the publican configuration, defaulting to en-US if nothing is set.

    :param publican_cfg: The path to the publican configuration file
    :type publican_cfg: str
    :return: The source xml language of the source content
    :rtype: str
    """
    # Parse the configuration file first to get any overrides
    publican_config = load_publican_config(publican_cfg)
    return get_config_val(publican_config, 'xml_lang')


def get_type(publican_cfg):
    """
    Gets the `type` setting from the publican configuration, defaulting to Book if nothing is set.

    :param publican_cfg:The path to the publican configuration file
    :type publican_cfg: str
    :return: The type of document
    :rtype: str
    """
    # Parse the configuration file first to get any overrides
    publican_config = load_publican_config(publican_cfg)
    return get_config_val(publican_config, 'type')


def get_brand(publican_cfg):
    """
    Gets the `brand` setting from the publican configuration.

    :param publican_cfg: The path to the publican configuration file
    :type publican_cfg: str
    :return: The brand to use when transforming the source content
    :rtype: str
    """
    # Parse the configuration file first to get any overrides
    publican_config = load_publican_config(publican_cfg)
    return get_config_val(publican_config, 'brand')


def get_chunk_section_depth(publican_cfg):
    """
    Gets the `chunk_section_depth` setting from the publican configuration.

    :param publican_cfg: The path to the publican configuration file
    :type publican_cfg: str
    :return: The chunk_section_depth to use when transforming the source content
    :rtype: str
    """
    # Parse the configuration file first to get any overrides
    publican_config = load_publican_config(publican_cfg)
    return get_config_val(publican_config, 'chunk_section_depth')


def get_toc_section_depth(publican_cfg):
    """
    Gets the `toc_section_depth` setting from the publican configuration.

    :param publican_cfg: The path to the publican configuration file
    :type publican_cfg: str
    :return: The toc_section_depth to use when generating the toc for the source content
    :rtype: str
    """
    # Parse the configuration file first to get any overrides
    publican_config = load_publican_config(publican_cfg)
    return get_config_val(publican_config, 'toc_section_depth')


def get_docname(publican_cfg):
    """
    Gets the `docname` setting from the publican configuration. If it's not set, then it generates the
    docname based on the *_Info.xml content.

    :param publican_cfg: The path to the publican configuration file
    :type publican_cfg: str
    :return: The docname of the document
    :rtype: str
    """
    # Parse the configuration file first to get any overrides
    publican_config = load_publican_config(publican_cfg)

    # Check the docname is specified, if not determine it from the book info
    if publican_config.has_option('publican', 'docname'):
        docname = get_config_val(publican_config, 'docname')
    else:
        book_dir = os.path.dirname(publican_cfg)
        docname, product, version, lang = get_npv_and_lang_from_dir(book_dir, publican_cfg)
    if docname:
        return re.sub(r'\s', "_", docname)
    else:
        return None


def get_mainfile(publican_cfg):
    """
    Gets the `mainfile` setting from the publican configuration. If it's not set, then it generates the
    expected mainfile based on the *_Info.xml content.

    :param publican_cfg: The path to the publican configuration file
    :type publican_cfg: str
    :return: The mainfile of the source content
    :rtype: str
    """
    # Parse the configuration file first to get any overrides
    publican_config = load_publican_config(publican_cfg)

    # Check the mainfile is specified, if not determine it from the book info
    lang = get_config_val(publican_config, 'xml_lang')
    if publican_config.has_option('publican', 'mainfile'):
        mainfile = get_config_val(publican_config, 'mainfile')
    else:
        mainfile = get_docname(publican_cfg)
    if mainfile:
        return os.path.join(lang, mainfile + ".xml")
    else:
        return None


def get_chunk_filename(ele):
    """
    Gets the chunked filename of a DocBook XML element. If the element isn't a chunkable element, then None is returned.

    :param ele:
    :return:
    """
    tag = ele.tag.replace(LXML_DOCBOOK_NS, "")

    # Check to make sure the element can be chunked
    if tag not in CHUNKING_ELES:
        return None

    filename_format = CHUNKING_ELES[tag].get('format')
    tag_count = ele.xpath("count(preceding-sibling::*[local-name()='" + tag + "'])") + 1
    if CHUNKING_ELES[tag].get('any_level', False):
        tag_count += ele.xpath("count(../preceding::*[local-name()='" + tag + "'])")
    tag_count = int(tag_count)

    if CHUNKING_ELES[tag].get('use_alpha', False):
        chunk_name = filename_format.format(utils.convert_num_to_alpha(tag_count))
    else:
        chunk_name = filename_format.format(tag_count)

    if CHUNKING_ELES[tag].get('use_parent', False) and ele.getparent() is not None:
        # Get the parents node name and then prefix
        parent_name = get_chunk_filename(ele.getparent())
        return parent_name + chunk_name
    else:
        return chunk_name


def find_ele(parent_ele, name):
    """
    Finds the child DocBook element for the specified name, by checking for both the DocBook 4.x and 5.x versions.
    """
    for tag_name in [name, LXML_DOCBOOK_NS + name]:
        ele = parent_ele.find(".//" + tag_name)
        if ele is not None:
            return ele

    return None


def find_info_ele(parent_ele):
    """
    Finds the child DocBook info element that relates to the passed XML element.
    """
    parent_ele = utils.ensure_lxml_element(parent_ele)
    for child in parent_ele.iterchildren():
        # DocBook 5+ uses just <info> whereas DocBook 4.x uses <bookinfo>
        if child.tag == LXML_DOCBOOK_NS + "info" or child.tag == (parent_ele.tag + "info"):
            return child
    return None


def get_ele_id(ele):
    """
    Gets the DocBook id of the element, by checking for both the DocBook 4.x and 5.x versions.
    """
    for id_attr in ['id', LXML_XML_NS + "id"]:
        if id_attr in ele.attrib:
            return ele.get(id_attr)

    return None


def is_ns_docbook_ver(docbook_ver):
    """
    Checks if the DocBook version specified uses the DocBook XML Namespace.
    """
    if isinstance(docbook_ver, tuple):
        major, minor = docbook_ver
    else:
        major, minor = _parse_docbook_ver(docbook_ver)
    return major >= 5


def get_legalnotice_html_title(legal_notice_ele):
    """
    Gets the related title element of a legal notice html element. This could be either a child element with the class "legalnotice-title"
    or it could be the default initial <h1> element

    :param legal_notice_ele: The Legal Notice element to find the title for.
    :return: The legal notice html title element, or None if one couldn't be found
    """
    title_eles = legal_notice_ele.xpath(".//*[contains(@class,'legalnotice-title')]")
    if len(title_eles) > 0:
        return title_eles[0]
    else:
        title_heading_ele = legal_notice_ele.find("{*}h1")
        if title_heading_ele is not None:
            return title_heading_ele
        else:
            return None


def get_legalnotice_html_id(legal_notice_ele):
    """
    Gets the related html id of a legal notice html element. This could be on the element itself or on a child <a> element.

    :param legal_notice_ele: The Legal Notice element to find an id for.
    :return: The legal notice html id, or None if one couldn't be found
    """
    if legal_notice_ele.get("id") is not None:
        return legal_notice_ele.get("id")
    else:
        anchor = legal_notice_ele.find("{*}a")
        if anchor is not None and anchor.get("id") is not None:
            return anchor.get("id")
        else:
            return None


def get_keywords(info_ele):
    """
    Gets the keywords from a DocBook info element and returns them as a list.

    :param info_ele: The info element to locate the keywords in.
    :type info_ele: etree._Element
    :return: A list of keywords defined in the info element
    :rtype: list[str]
    """
    # Add the keywords
    keywordset_ele = info_ele.find("keywordset")
    keywords_list = []
    if keywordset_ele is not None:
        for keyword_ele in keywordset_ele.findall("keyword"):
            keywords_list.append(utils.get_element_text(keyword_ele).strip())

    return keywords_list


def build_doctype(tree, entfile=None):
    internal_dtd_entities = []
    if tree.docinfo.internalDTD:
        for entity in tree.docinfo.internalDTD.entities():
            if entity.name == "BOOK_ENTITIES" and entfile:
                internal_dtd_entities.append("<!ENTITY % BOOK_ENTITIES SYSTEM \"" + entfile + "\">\n%BOOK_ENTITIES;")
            elif entity.name == "sgml.features":
                internal_dtd_entities.append("<!ENTITY % sgml.features \"IGNORE\">")
            elif entity.name == "xml.features":
                internal_dtd_entities.append("<!ENTITY % xml.features \"INCLUDE\">")
            elif entity.name == "DOCBOOK_ENTS":
                internal_dtd_entities.append("<!ENTITY % DOCBOOK_ENTS PUBLIC \"-//OASIS//ENTITIES DocBook Character Entities V4.5//EN\""
                                             " \"http://www.oasis-open.org/docbook/xml/4.5/dbcentx.mod\">\n"
                                             "%DOCBOOK_ENTS;")
    args = {'internalDTD': "\n".join(internal_dtd_entities),
            'name': tree.docinfo.root_name,
            'public_id': tree.docinfo.public_id,
            'system_url': tree.docinfo.system_url}

    # Build up the format string
    if args['public_id']:
        doctype_format = "<!DOCTYPE {name} PUBLIC \"{public_id}\" \"{system_url}\""
    else:
        doctype_format = "<!DOCTYPE {name}"
    if args['internalDTD']:
        doctype_format += " [\n{internalDTD}\n]"
    doctype_format += ">"
    return doctype_format.format(**args)


def scrub_html(html_ele):
    """
    Removes certain html elements so only content is left, such as table of contents, navigation, headers/footers, etc...

    :param html_ele:
    :type html_ele: lxml.html.HtmlElement
    """
    # Remove the headers
    header = html_ele.find(".//p[@id='title']")
    if header is not None:
        header.getparent().remove(header)

    # Remove any tocs from the html
    for toc in html_ele.xpath(".//*[local-name()='div'][contains(@class,'toc')]"):
        toc.getparent().remove(toc)

    # Remove the initial title element
    title_ele = html_ele.find("./*/*[@class='titlepage']//*[@class='title']")
    title_ele_parent = title_ele.getparent()
    title_ele_parent.getparent().remove(title_ele_parent)

    # Remove any <script>s
    scripts = html_ele.findall(".//script")
    for script in scripts:
        script.getparent().remove(script)


def strip_block_name_from_title(block_type, title, lang="en"):
    """
    Removes the elements heading name (ie Chapter, Part, etc...) from the title so that all that's
    left is the optional number and title.

    :param block_type: The type of block the title is for (ie chapter, part, section, etc...)
    :type block_type: str
    :param title: The rendered title string that contains the block name, number and title string (ie Chapter 1. Installation)
    :type title: str
    :param lang: The language used to generated the rendered title string.
    :type lang: str
    :return: The
    :rtype: str
    """
    # Determine the language
    lang = lang.split("-")[0]
    block_type = block_type.lower()

    # Ensure the title is unicode
    if not isinstance(title, unicode):
        title = title.decode("utf-8")

    try:
        # Parse the DocBook localization file, to find out how to strip the block name
        # Note: This uses the DocBook XSL URI which should resolve to a local file depending on the local XML catalog
        xml_root = etree.parse(DOCBOOK_XSL_URI + "/common/" + lang + ".xml")

        # Get the title context information
        title_context = xml_root.find(LXML_DOCBOOK_L10N_NS + "context[@name='title']")
        title_numbered_context = xml_root.find(LXML_DOCBOOK_L10N_NS + "context[@name='title-numbered']")
        if title_context is not None and title_numbered_context is not None:
            block_context = title_context.find(LXML_DOCBOOK_L10N_NS + "template[@name='" + block_type + "']")
            block_numbered_context = title_numbered_context.find(LXML_DOCBOOK_L10N_NS + "template[@name='" + block_type + "']")
            if block_context is not None or block_numbered_context is not None:
                # Determine the DocBook template
                if block_numbered_context is not None:
                    template = block_numbered_context.attrib.get("text")
                else:
                    template = block_context.attrib.get("text")

                # Determine the regex to extract the content, replacing spaces with "\s" to match any whitespace char
                template_re = re.escape(template).replace("\\%n", r"(?P<num>\S+?)").replace("\\%t", r"(?P<text>.+?)")
                template_re = template_re.replace(u"\\\x0a", "\\s").replace("\\ ", "\\s")
                template_re = "^" + template_re + "$"

                # Match the template and replace the title with just the number/title
                match = re.match(template_re, title, re.UNICODE)
                if match:
                    if "%n" in template:
                        return match.expand(u"\g<num>. \g<text>")
                    else:
                        return match.expand(u"\g<text>")
    except etree.LxmlError:
        # Do nothing and use the default return value
        pass

    # Don't do anything and just return the title as is
    return title
