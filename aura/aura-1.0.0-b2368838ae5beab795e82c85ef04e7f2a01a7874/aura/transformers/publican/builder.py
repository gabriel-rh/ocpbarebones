import logging
import os.path
import time
from collections import OrderedDict

from lxml import etree, html

from aura import utils
from aura.compat import urlparse
from aura.transformers.publican import utils as publican_utils
from aura.transformers.publican.utils import (XML_FEED_FORMAT, LXML_DOCBOOK_NS, CHUNKING_ELES, DEFAULT_TOC_ELES,
                                              SECTION_ELES, TOC_STANDALONE_ELES)


PROTOCOL_V1 = 1
PROTOCOL_V2 = 2


def create_element(name, value, attrs=None, indent=1):
    """
    Creates a new XML element with the specified name, value and attributes. An indent value can also be passed to specify the xml elements
    pretty print indentation.
    """
    attrs = attrs or {}
    ele = etree.Element(name, attrib=attrs)
    ele.text = value
    ele.tail = "\n" + (indent * "  ")
    return ele


def add_new_element(parent, name, value, attrs=None, indent=1, index=-1):
    """
    Creates a new element and adds it to the specified parent. If an index isn't passed, then the new element will be appended to the end.
    """
    ele = create_element(name, value, attrs, indent)
    if index >= 0:
        parent.insert(index, ele)
    else:
        parent.append(ele)
    return ele


def add_new_element_after_ele(parent, ele_name, new_name, value, attrs=None, indent=1, default_index=-1):
    """
    Creates a new element, looks up an existing element and appends it after the specified element. If the element doesn't exist, the new
    element is added to the parent using the default index instead.
    """
    existing_ele = parent.find(ele_name)
    idx = default_index if existing_ele is None else parent.index(existing_ele) + 1
    return add_new_element(parent, new_name, value, attrs=attrs, indent=indent, index=idx)


def fix_page_link(context, link):
    """
    Fixes an inter page link to use the feeds filename/page slug
    """
    # Parse the link to get just the filename
    link_filename = urlparse(link).path
    if link_filename in context.src_html_files:
        # Link to another page
        filename = link_filename.replace(".html", "")
        if context.protocol == PROTOCOL_V2:
            page_link = context.page_slug(filename)
        else:
            page_link = context.page_url_token(filename)
        return link.replace(link_filename, page_link)

    return link


class XMLFeedBuilderContext(object):
    """
    The contextual information required during a XML Feed build process.

    :param transformer: The transformer instance being used to build the XML Feed.
    :type transformer: aura.transformers.base.Transformer
    :param doc_uuid: A UUID to identify the document being built.
    :type doc_uuid: uuid.UUID
    :param src_tree: A XML tree of the parsed source XML content.
    :type src_tree: etree._ElementTree
    :param src_lang: The source language of the document.
    :type src_lang: str
    :param lang: The language to build the XML feed for.
    :type lang: str
    :param config: A configuration file to use when building the Feed.
    :type config: str
    :param trans_tree: A XML tree of the parsed translated XML content.
    :type trans_tree: etree._ElementTree
    """
    def __init__(self, transformer, doc_uuid, src_tree, src_lang, lang, config, trans_tree=None, protocol=PROTOCOL_V1):
        self.doc_id = transformer.get_doc_id(config, lang)
        self.doc_uuid = doc_uuid
        self.src_lang = src_lang
        self.src_html_dir = transformer.get_build_dir(src_lang, XML_FEED_FORMAT, config)
        self.src_tree = src_tree
        self.lang = lang
        self.trans_html_dir = transformer.get_build_dir(lang, XML_FEED_FORMAT, config)
        self.trans_tree = trans_tree or src_tree
        self.protocol = protocol

        self.toc_elements = DEFAULT_TOC_ELES

        # Init common vars from the config
        self.config = config
        self.docbook_ver = publican_utils.get_dtdver(config)
        self.doc_type = publican_utils.get_type(config).lower()
        self.toc_section_depth = int(publican_utils.get_toc_section_depth(config))

        # Cache some information we don't want to have to load each time it's needed
        self._cache = {
            "src_xml_dir": transformer.get_build_dir(src_lang, "xml", config),
            "trans_xml_dir": transformer.get_build_dir(lang, "xml", config),
            "src_info_ele": None,
            "trans_info_ele": None
        }

    @property
    def is_translation(self):
        return self.src_lang != self.lang

    @property
    def src_html_files(self):
        """
        Gets a list of source html filenames from the HTML build.
        """
        if 'src_html_files' not in self._cache:
            self._cache['src_html_files'] = os.listdir(self.src_html_dir)
        return self._cache['src_html_files']

    @property
    def trans_html_files(self):
        """
        Gets a list of translated html filenames from the HTML build.
        """
        if 'trans_html_files' not in self._cache:
            self._cache['trans_html_files'] = os.listdir(self.trans_html_dir)
        return self._cache['trans_html_files']

    @property
    def used_page_ids(self):
        """
        :return: A list of page ids that have been used/reserved during the build process
        :rtype: list[str]
        """
        if 'used_page_ids' not in self._cache:
            self._cache['used_page_ids'] = []
        return self._cache['used_page_ids']

    def page_url_token(self, filename):
        """
        Generates an XML Feeds url token using the specified filename in this context.
        """
        if filename == "index":
            url = self.doc_id
        elif filename == "ix01":
            url = self.doc_id + "-index"
        else:
            url = self.doc_id + "-" + filename
        return url

    def page_slug(self, filename):
        """
        Generates a page slug for the specified filename in this context
        """
        # Use the pages filename as the title slug, unless it's a legal notice, in which case try it a prettier url
        if filename == "ln01" and "legal-notice.html" not in self.src_html_files:
            page_url_slug = "legal-notice"
        else:
            page_url_slug = filename
        return page_url_slug

    def get_info_ele(self, use_translation=True):
        """
        Finds the documents info element from the relevant source or translation tree.

        :return: The documents info element
        :rtype: etree._Element
        """
        # Publican is stupid and instead of reading from the XML tree, it reads from the "Book_Info.xml" file, This content might not
        # even be included in the output, but nonetheless that is how publican reads the info content so we have to replicate it here.
        if self.is_translation and use_translation:
            if self._cache['trans_info_ele'] is None:
                self._cache['trans_info_ele'] = publican_utils.load_publican_info_xml(self._cache['trans_xml_dir'], self.config)
            info_ele = self._cache['trans_info_ele']
        else:
            if self._cache['src_info_ele'] is None:
                self._cache['src_info_ele'] = publican_utils.load_publican_info_xml(self._cache['src_xml_dir'], self.config)
            info_ele = self._cache['src_info_ele']

        # The root element of the publican info_file might not actually be the "info" element
        if info_ele.tag.endswith("info"):
            return info_ele
        else:
            return publican_utils.find_info_ele(info_ele)

    def get_info_ele_value(self, info_ele, name, default=None):
        """
        Finds a DocBooks "info" child elements value
        """
        value = utils.find_element_value(info_ele, name)
        # DocBook 5.0 allows the title/subtitle to be a direct descendant of the <book>/<article> element instead of being in the <info>
        if self.docbook_ver >= (5, 0) \
                and name in ["title", "subtitle"] \
                and value is None \
                and info_ele.getparent() is not None:
            value = utils.find_element_value(info_ele.getparent(), name)
        return default if value is None else value

    def html_file_path(self, filename, use_translation=True):
        """
        Resolve file path to a built html file, based on if a translation build is being performed or not.
        """
        if self.is_translation and use_translation:
            return os.path.join(self.trans_html_dir, filename)
        else:
            return os.path.join(self.src_html_dir, filename)


class XMLFeedBuilder(object):
    """
    A helper instance to build XML Feeds that can be used to pass builds to other systems.

    :param context: The feed builder build contextual data
    :type context: XMLFeedBuilderContext
    """
    XML_FEED_ELE_MAP = {
        "productnumber": "version",
        "productname": "product",
        "subtitle": "subtitle",
        "title": "title"
    }

    def __init__(self, context):
        self.log = logging.getLogger(self.__module__ + "." + self.__class__.__name__)
        self.context = context

    def build_from_source(self):
        """
        Builds an entire XML Feed from the source/translation XML passed in the constructor.
        """
        # Create the root element/tree
        doc_ele = etree.Element("document")
        doc_ele.text = "\n  "
        feed_tree = etree.ElementTree(doc_ele)

        # Add in the unique key. CCS-596/CCS-1355
        self.add_feed_id(doc_ele)

        # Add the lang/type
        self.add_lang(doc_ele)
        self.add_type(doc_ele)

        # Add a name for legacy purposes
        self.add_name(doc_ele)

        # Add in the product/version/title/etc... metadata
        self.add_info_metadata(doc_ele)

        # Add in the created date
        self.add_created_datetime(doc_ele)

        # Add in the url slugs
        if self.context.protocol == PROTOCOL_V2:
            self.add_url_slugs(doc_ele)

        # Add the page data
        self.add_pages(doc_ele)

        return feed_tree

    def add_feed_id(self, feed_ele):
        """
        Generates a readable feed ID from the source XML that is consistent across all languages and adds it,
        along with the docs UUID, to the passed feed.
        """
        # Get the document id, strip the lang and then convert to lowercase to calculate the feed id
        feed_id = self.context.doc_id.replace("-" + self.context.lang, "").lower()

        # Build the uuid/id element and add it to the start of the xml feed
        add_new_element(feed_ele, "uuid", str(self.context.doc_uuid), index=0)
        add_new_element(feed_ele, "id", feed_id, index=1)

    def add_type(self, feed_ele):
        """
        Gets the document type (book/article) from the source XML/configuration and adds it to the passed feed.
        """
        # Add the type after the id
        add_new_element_after_ele(feed_ele, "id", "type", self.context.doc_type, default_index=0)

    def add_lang(self, feed_ele):
        """
        Adds the source/translation language for the document to the passed feed.
        """
        lang_attrs = {"base": self.context.src_lang}

        # Add the lang after the id
        add_new_element_after_ele(feed_ele, "id", "lang", self.context.lang, lang_attrs, default_index=0)

    def add_name(self, feed_ele):
        """
        Adds generated name for the document to the passed feed.
        """
        # Find the book info element
        info_ele = self.context.get_info_ele()
        title, product, version = publican_utils.get_npv_from_xml(info_ele)
        # The title might not have been in the info ele for DocBook 5.0, so handle that
        if title is None:
            title = self.context.get_info_ele_value(info_ele, "title")
        name = product + " " + version + " " + title
        add_new_element(feed_ele, "name", name)

    def add_created_datetime(self, feed_ele):
        # Note from Jason:
        # I'm using a UTC timestamp for now, since a datetime would at least hint to an end user what the build is.
        # TODO: Look at replacing this with something that makes more sense to the end users? CCS-1357

        # Build the created element and add it to the feed
        created_timestamp = str(int(time.time()))
        add_new_element(feed_ele, "created", created_timestamp)

    def _add_translateable_info(self, feed_ele, info_ele):
        """
        Adds info metadata that can be translated to the feed ele.
        """
        # If the XML feed is a translation, get the source langs info
        if self.context.is_translation:
            src_info_ele = self.context.get_info_ele(False)
        else:
            src_info_ele = info_ele

        # Add the product, version and title
        for docbook_name, feed_name in self.XML_FEED_ELE_MAP.items():
            value = self.context.get_info_ele_value(info_ele, docbook_name)
            attrs = {}

            # Add the base/source value xml attribute
            if self.context.is_translation:
                src_value = utils.find_element_value(src_info_ele, docbook_name)
                attrs["base"] = src_value
            else:
                attrs["base"] = value

            add_new_element(feed_ele, feed_name, value, attrs)

    def add_info_metadata(self, feed_ele):
        """
        Adds the info metadata from the source XML (ie title, product, version, etc...) to the passed feed.
        """
        # Find the book info element
        info_ele = self.context.get_info_ele()

        # Add the product, version, title and subtitle
        self._add_translateable_info(feed_ele, info_ele)

        # Add the edition/abstract
        edition = self.context.get_info_ele_value(info_ele, "edition", "1.0")
        abstract = self.context.get_info_ele_value(info_ele, "abstract")
        add_new_element(feed_ele, "edition", edition)
        add_new_element(feed_ele, "abstract", abstract)

        # Add a release field, that doesn't change for legacy purposes
        add_new_element(feed_ele, "release", "0")

        # Add the keywords
        keywords_list = publican_utils.get_keywords(info_ele)
        if len(keywords_list) > 0:
            keywords = ",".join(keywords_list)
        else:
            keywords = None
        add_new_element(feed_ele, "keywords", keywords)

    def add_url_slugs(self, feed_ele):
        """
        Adds the title, product and version info metadata url slugs to the feed
        """
        # Find the book info element from the source tree
        src_info_tree = self.context.get_info_ele(False)
        # Get the title, product, version making sure to use the publican.cfg overrides
        title, product, version = publican_utils.get_npv_from_xml(src_info_tree, self.context.config, True)

        for name, value in [("title", title), ("product", product), ("version", version)]:
            url_slug = utils.clean_for_rpm_name(value, remove_dups=True)
            # Strip any leading full stops, so the slug doesn't appear to be a hidden filename/directory
            url_slug = url_slug.lstrip(".")
            add_new_element_after_ele(feed_ele, name, name + "_slug", url_slug)

    def add_pages(self, feed_ele):
        """
        Adds all chunked pages from the source XML to the XML feed
        """
        src_xml_root = self.context.src_tree.getroot()

        # Build up the chunking maps
        trans_chunking_map = OrderedDict()
        src_chunking_map = OrderedDict()
        self._build_chunked_map(src_xml_root, src_chunking_map)
        if self.context.is_translation:
            trans_xml_root = self.context.trans_tree.getroot()
            self._build_chunked_map(trans_xml_root, trans_chunking_map)

        # Add the pages
        self._add_pages_from_chunk_map(src_chunking_map, feed_ele, None, trans_chunking_map)

        # Add the toc
        if self.context.protocol == PROTOCOL_V2:
            if self.context.is_translation:
                self._add_toc_from_chunk_map(trans_chunking_map, feed_ele)
            else:
                self._add_toc_from_chunk_map(src_chunking_map, feed_ele)

    def _add_toc_from_chunk_map(self, chunk_map, feed_ele):
        # TODO: Look into doing this via the "toc.section.depth" XSLT params if we ever get to doing the
        # transformations ourself, instead of doing them via Publican (CCS-1898). At the moment we cannot
        # do that however, as it'll cause the ToC to be too large in static content (ie PDF and ePub) and
        # doing it via a separate transformation it would generate different dynamic node ids.

        # Add the toc element to the XML Feed
        toc_feed_ele = add_new_element(feed_ele, "toc", "\n" + (4 * " "))

        if self.context.docbook_ver >= (5, 0):
            html_transformer = DocBookHTML5Transformer()
        else:
            html_transformer = DocBookHTML4Transformer()

        # Loop over each paged/chunked html file and generate a toc representation
        complete_toc_tree = []
        for filename, chunk_data in chunk_map.items():
            # Generate the toc xml feed representation for the page
            toc_tree = self._build_toc_tree(filename, html_transformer, chunk_map=chunk_data.get('children'))

            # Fix the toc titles, to strip the "Chapter" name and fix the links to use the page slugs
            self._fix_toc_tree_title_and_links(toc_tree)

            complete_toc_tree.extend(toc_tree)

        # Transform the toc tree and copy over the items to the toc feed ele
        transformed_toc = html_transformer.transform_tree_to_xml(complete_toc_tree, max_section_depth=self.context.toc_section_depth)
        for toc_item in transformed_toc:
            toc_feed_ele.append(toc_item)

    def _fix_toc_tree_title_and_links(self, toc_tree):
        for node in toc_tree:
            # Strip the name of the block
            if node.get('type'):
                node['title'] = publican_utils.strip_block_name_from_title(node['type'], node['title'], self.context.lang)
            # Fix the link to use the page slugs
            node['href'] = fix_page_link(self.context, node['href'])
            # Process any child nodes in the tree
            if 'children' in node:
                self._fix_toc_tree_title_and_links(node['children'])

    def _build_toc_tree(self, html_filename, html_transformer, chunk_map=None):
        html_file = self.context.html_file_path(html_filename + ".html")
        if not os.path.isfile(html_file):
            return []

        # Parse the html file
        html_ele = utils.parse_xhtml(html_file)

        # Extract the html files table of contents
        chunk_map = chunk_map or {}
        toc_tree = html_transformer.extract_toc_tree_from_html(html_ele.body, toc_eles=self.context.toc_elements)

        if len(toc_tree) > 0:
            # Strip any fragments/anchors from the href for the root page entry
            first_tree_node = toc_tree[0]
            first_tree_node["href"] = html_filename + ".html"

            # Add the child pages to the toc
            for filename, chunk_data in chunk_map.items():
                child_toc_tree = self._build_toc_tree(filename, html_transformer, chunk_data.get('children'))

                # Make sure we found some toc elements and add the child elements to the last toc tree node
                if len(child_toc_tree) > 0:
                    last_tree_node = toc_tree[-1]
                    if 'children' not in last_tree_node:
                        last_tree_node['children'] = []
                    last_tree_node['children'].extend(child_toc_tree)

        return toc_tree

    def _add_pages_from_chunk_map(self, src_chunking_map, feed_ele, parent_page=None, trans_chunking_map=None):
        weight = -15
        for filename, src_chunk_data in src_chunking_map.items():
            child_parent_page = parent_page
            # Look up the matching source chunking data
            if trans_chunking_map is not None:
                trans_chunk_data = trans_chunking_map.get(filename, {})
            else:
                trans_chunk_data = {}

            # Generate the file path and if it exists add the page to the feed
            html_file = self.context.html_file_path(filename + ".html")
            if os.path.isfile(html_file):
                # Get the source chunkable elements
                src_chunkable_ele = src_chunk_data.get('element')
                trans_chunkable_ele = trans_chunk_data.get('element')

                # Add the page
                builder = XMLFeedPageBuilder(self.context, src_chunkable_ele, filename, weight, parent_page, trans_chunkable_ele)
                page_ele = child_parent_page = builder.build_page()
                feed_ele.append(page_ele)

            # Add the child pages
            self._add_pages_from_chunk_map(src_chunk_data.get('children'), feed_ele, child_parent_page, trans_chunk_data.get('children'))
            weight += 1

    def _build_chunked_map(self, src_ele, section_map):
        """
        Builds a mapping of potential chunked elements, using the filename as the key and the matching element as the value.
        """
        tag = src_ele.tag.replace(LXML_DOCBOOK_NS, "")
        child_map = section_map
        if tag in CHUNKING_ELES:
            # Determine what the filename for the chunked section would be. If it's the root element, then it'll be index.html,
            # otherwise it'll use the id and lastly it'll use a generated name
            ele_id = publican_utils.get_ele_id(src_ele)
            if tag == self.context.doc_type:
                filename = 'index'
            elif ele_id is not None:
                filename = ele_id
            else:
                filename = publican_utils.get_chunk_filename(src_ele)
            child_map = OrderedDict()
            section_map[filename] = {
                'element': src_ele,
                'children': child_map
            }

        for child_ele in src_ele.iterchildren(tag=etree.Element):
            # Add any child chunkable elements to the map. We need to treat the root element differently though, as any chunkable elements
            # in book/article "info" should be child pages, but all others should be siblings
            if tag == self.context.doc_type and "info" not in child_ele.tag:
                self._build_chunked_map(child_ele, section_map)
            else:
                self._build_chunked_map(child_ele, child_map)

        # Move any child legal notices of the first page, to the end of the document as required by CCS
        if tag == self.context.doc_type:
            first_page_children = section_map['index']['children']
            for filename, child_map in first_page_children.items():
                if child_map.get("element").tag.endswith("legalnotice"):
                    section_map[filename] = child_map
                    del first_page_children[filename]


class XMLFeedPageBuilder(object):
    """
    A helper instance to build a XML Feeds <page> element.

    :param context: The feed builder build contextual data
    :type context: XMLFeedBuilderContext
    :param src_chunkable_ele: The source XML element to build the page from.
    :type src_chunkable_ele: etree.ElementBase
    :param filename: The filename for the pages HTML content.
    :type filename: str
    :param weight: The pages weight in the XML Feed
    :type weight: int
    :param parent_page_ele: The parent page element to build the page for.
    :type parent_page_ele: etree.ElementBase
    :param trans_chunkable_ele: The translated XML element to build the page from.
    :type trans_chunkable_ele: etree.ElementBase
    """

    def __init__(self, context, src_chunkable_ele, filename, weight, parent_page_ele=None, trans_chunkable_ele=None):
        self.log = logging.getLogger(self.__module__ + "." + self.__class__.__name__)
        self.context = context
        self.src_chunkable_ele = src_chunkable_ele
        self.trans_chunkable_ele = trans_chunkable_ele or src_chunkable_ele
        self.filename = filename
        self.parent_page_ele = parent_page_ele
        self.weight = weight
        self.indent = 2

        self._cache = {}

    def build_page(self):
        """
        Builds an entire page element for a XML Feed from the source elements passed in the constructor.
        :return:
        """
        page_ele = create_element("page", None)
        page_ele.text = "\n" + (4 * " ")

        # Add the id/parent/weight
        self.add_page_id(page_ele)
        self.add_page_parent(page_ele)
        self.add_page_weight(page_ele)
        self.add_page_keywords(page_ele)

        # Add an empty menu element for legacy purposes
        add_new_element(page_ele, "menu", None, indent=self.indent)

        # Add the content from the html
        self.add_html_data(page_ele)

        # Add the url slug
        if self.context.protocol == PROTOCOL_V2:
            self.add_page_url_slug(page_ele)
        else:
            self.add_page_url_token(page_ele)

        return page_ele

    def _get_src_id(self, src_ele, ignore_generated_ids=True):
        """
        Look up the source XML id, which could be located on the passed element or the child title element.
        """
        title_ele = publican_utils.find_ele(src_ele, "title")
        for ele in [src_ele, title_ele]:
            if ele is not None:
                ele_id = publican_utils.get_ele_id(ele)
                if ele_id is not None:
                    # ignore remap/auto generated id's
                    if ignore_generated_ids and ele.get('remap', '').startswith("_"):
                        continue
                    else:
                        return ele_id

        return None

    def add_page_id(self, page_ele):
        """
        Looks up a page id from the source XML element and adds it to the passed page. If an id wasn't specified then one is generated by
        using the source XML elements title.
        """
        if self.src_chunkable_ele.tag.endswith(self.context.doc_type):
            page_id = self.context.doc_id
        else:
            page_id = self._get_src_id(self.src_chunkable_ele)

            # Check we got a page id, if not generate one
            if page_id is None:
                title_ele = publican_utils.find_ele(self.src_chunkable_ele, "title")
                # Use the filename if no title was found or the element is a Preface or Legal Notice. Otherwise generate an id using the
                # title and generate a warning
                if self.src_chunkable_ele.tag.endswith("preface") or self.src_chunkable_ele.tag.endswith("legalnotice"):
                    title = self.filename
                elif title_ele is not None:
                    title = utils.get_element_text(title_ele).strip()
                    self.log.warning("No persistent id was specified in the source markup for the \"%s\" page. " +
                                     "Generating a temporary id from the title to use instead.",
                                     title)
                else:
                    title = self.filename

                # Get the id to use by checking if an auto generated id exists or if one doesn't then generate one from the title.
                generated_page_id = self._get_src_id(self.src_chunkable_ele, ignore_generated_ids=False)
                if generated_page_id:
                    page_id = generated_page_id
                else:
                    # Generate the page id from the title and then add a count after the id if it's not unique
                    base_page_id = page_id = utils.create_xml_id(title).lower()
                    count = 1
                    while page_id in self.context.used_page_ids:
                        count += 1
                        page_id = base_page_id + "_" + str(count)

            # Cache the page id in the build context, so we know not to use it again
            page_id = page_id.lower()
            self.context.used_page_ids.append(page_id)

            # Prepend the doc id to the page id
            page_id = self.context.doc_id + "-" + page_id

        # Create the ele and add it to the page
        add_new_element(page_ele, "id", page_id.lower(), indent=self.indent)

    def add_page_url_slug(self, page_ele):
        """
        Creates a url slug and adds it to the passed page.
        """
        page_url_slug = self.context.page_slug(self.filename)
        add_new_element_after_ele(page_ele, "title", "page_slug", page_url_slug, indent=self.indent)

    def add_page_url_token(self, page_ele):
        """
        Generates a page url token to be associated with the pages and adds it to the passed page.
        """
        url = self.context.page_url_token(self.filename)
        # Create the ele and add it to the page
        add_new_element(page_ele, "url", url, indent=self.indent)

    def add_page_weight(self, page_ele):
        # Create the ele and add it to the page
        add_new_element(page_ele, "weight", str(self.weight), indent=self.indent)

    def add_page_keywords(self, page_ele):
        # Find the info element
        info_ele = publican_utils.find_info_ele(self.src_chunkable_ele)
        # Add the keywords
        keywords = None
        if info_ele is not None:
            keywords_list = publican_utils.get_keywords(info_ele)
            if len(keywords_list) > 0:
                keywords = ",".join(keywords_list)

        add_new_element(page_ele, "keywords", keywords, indent=self.indent)

    def add_page_parent(self, page_ele):
        """
        Adds the pages parent url to the passed page. If no parent exists, then add an empty field.
        """
        if self.parent_page_ele is not None:
            if self.context.protocol == PROTOCOL_V2:
                parent_id = self.parent_page_ele.find("id").text
            else:
                parent_id = self.parent_page_ele.find("url").text
        else:
            parent_id = None
        # Create the ele and add it to the page
        add_new_element(page_ele, "parent", parent_id, indent=self.indent)

    def _clean_body_content(self, body_ele):
        """
        Cleans a passed HTML body element to remove the initial heading (since Drupal adds this) and also to update links between pages to
        use the generated url token. Lastly images are updated to have the drupal path prefixed to the image path.
        """
        # Remove the title header as it's displayed by drupal
        title = body_ele.find(".//*[@class='titlepage']//*[@class='title']")
        if title is not None:
            # Find the top level parent element of the title and remove it
            while len(title.getparent()) == 1:
                title = title.getparent()
            title.getparent().remove(title)

        # Remove any table of contents
        tocs = body_ele.xpath(".//*[local-name()='div'][contains(@class,'toc')]")
        if len(tocs) > 0:
            for toc in tocs:
                toc.getparent().remove(toc)

        # Replace links to other pages and image paths
        for element, attribute, link, pos in body_ele.iterlinks():
            if attribute == "href":
                fixed_link = fix_page_link(self.context, link)
                element.set(attribute, fixed_link)
            elif element.tag in ['img', 'object']:
                # Image link
                element.set(attribute, "/sites/default/files/documentation/" + self.context.doc_id + "/" + link)

    def add_html_data(self, page_ele):
        """
        Adds the relevant data (title and XHTML body) from the generated XHTML content to the page.
        """
        # parse the html files
        src_html_file = self.context.html_file_path(self.filename + ".html", use_translation=False)
        src_html_ele = utils.parse_xhtml(src_html_file)
        if self.context.is_translation:
            trans_html_file = self.context.html_file_path(self.filename + ".html", use_translation=True)
            trans_html_ele = utils.parse_xhtml(trans_html_file)
            root_ele = trans_html_ele
        else:
            root_ele = src_html_ele

        # Add the title
        title = root_ele.head.find("title").text_content()
        title_attrs = {}
        if self.context.is_translation:
            title_attrs['base'] = src_html_ele.head.find("title").text_content()
        else:
            title_attrs['base'] = title
        add_new_element_after_ele(page_ele, "id", "title", title, title_attrs, indent=self.indent, default_index=0)

        # Get the body content and clean it
        body = root_ele.body
        self._clean_body_content(body)

        # Add the body
        body_ele = add_new_element(page_ele, "body", None)
        for child_ele in body.iterchildren():
            body_ele.append(child_ele)


class DocBookHTMLTransformer(object):
    block_html_tags = ["div"]

    def transform_toc_to_xml(self, toc_ele):
        """
        Transforms an Element that represents a HTML table of contents, into an XML representation of the table of contents.

        :param toc_ele: The element representing the toc to be converted.
        :type toc_ele: etree.ElementBase
        :return: The transformed table of contents
        :rtype: etree.ElementBase
        """
        # Extract the nodes from the root
        tree = self.extract_toc_tree(toc_ele)

        # Build the new menu structure
        return self.transform_tree_to_xml(tree)

    def transform_toc_to_html(self, toc_ele):
        """
        Transforms an Element that represents a HTML table of contents, into a consistent table of contents for Drupal.

        :param toc_ele: The element representing the toc to be converted.
        :type toc_ele: etree.ElementBase
        :return: The transformed table of contents
        :rtype: etree.ElementBase
        """
        # Extract the nodes from the root
        tree = self.extract_toc_tree(toc_ele)

        # Build the new menu structure
        return self.transform_tree_to_html(tree)

    def generate_toc_from_html(self, html_ele, toc_eles=DEFAULT_TOC_ELES, max_section_depth=None):
        """
        Generates an XML representation of the table of contents for the given HTML element.

        :param html_ele:
        :type html_ele: html.HTMLElement
        :param toc_eles: A list of element names that should be included in the ToC.
        :type toc_eles: list[str]
        :param max_section_depth: The maximum depth to generate visible ToC section elements for.
        :type max_section_depth: int
        :return: The generated table of contents
        :rtype: etree.ElementBase
        """
        # Extract the toc tree from the html elements
        tree = self.extract_toc_tree_from_html(html_ele, toc_eles)

        # Build the new menu structure
        return self.transform_tree_to_xml(tree, max_section_depth=max_section_depth)

    def get_html_ele_id(self, html_ele):
        """
        Look up the DocBook element id, which could be located on the passed element or the child title element.
        """
        title_ele = html_ele.find(".//*[@class='titlepage']//*[@class='title']")
        for ele in [html_ele, title_ele, html_ele.find("./a")]:
            if ele is not None:
                ele_id = ele.attrib.get("id")
                if ele_id is not None:
                    return ele_id

        return None

    def extract_toc_tree(self, toc_ele):
        root_ele = self._get_root_toc_ele(toc_ele)

        # Extract the nodes from the root
        return self._extract_toc_children(root_ele)

    def _get_root_toc_ele(self, toc_container_ele):
        raise NotImplementedError()

    def _extract_toc_children(self, parent_ele):
        raise NotImplementedError()

    def _get_html_ele_link(self, html_ele):
        page_filename = html_ele.base_url.rsplit("/", 1)[1]
        # Determine the elements href
        ele_id = self.get_html_ele_id(html_ele)
        if ele_id:
            return page_filename + "#" + ele_id
        else:
            return page_filename

    def _get_html_ele_title(self, html_ele):
        # Determine the elements title
        title_eles = html_ele.xpath("./*[@class='titlepage']//*[starts-with(local-name(), 'h') and @class='title']")
        if len(title_eles) == 0:
            # Some times the title isn't wrapped in a "titlepage" (ie legalnotice), so look for just a normal heading
            title_eles = html_ele.xpath("./*[self::h1 or self::h2 or self::h3 or self::h4 or self::h5 or self::h6]")

        if len(title_eles) > 0:
            title_ele = title_eles[0]
        else:
            # Fallback to the html page title, as a last resort
            title_ele = html_ele.head.find("title")

        return utils.get_element_text(title_ele)

    def extract_toc_tree_from_html(self, html_ele, toc_eles=DEFAULT_TOC_ELES):
        retvalue = []

        for child_ele in html_ele.iterchildren():
            tag = child_ele.tag
            classes = child_ele.attrib.get("class", "").split()

            # Ignore non html elements
            if not isinstance(child_ele, html.HtmlElement):
                continue
            # Ignore any HTML generated toc content
            elif "toc" in classes:
                continue

            matched_toc_types = list(set(classes).intersection(set(toc_eles)))
            if tag in self.block_html_tags and len(matched_toc_types) >= 1:
                ele_type = matched_toc_types[0]
                # Add the elements details to the tree
                node = {
                    'title': self._get_html_ele_title(child_ele),
                    'href': self._get_html_ele_link(child_ele),
                    'type': ele_type
                }

                # Look for any child nodes, if we aren't in a standalone element
                if ele_type not in TOC_STANDALONE_ELES:
                    child_nodes = self.extract_toc_tree_from_html(child_ele, toc_eles)
                    if len(child_nodes) > 0:
                        node['children'] = child_nodes

                # Add the node to the return list
                retvalue.append(node)
            else:
                retvalue.extend(self.extract_toc_tree_from_html(child_ele, toc_eles))

        return retvalue

    def transform_tree_to_html(self, toc_tree):
        """
        Builds the table of contents from a representation of the TOC using lists and dictionaries.

        :param toc_tree: The mapped representation of the TOC.
        :type toc_tree: list [dict]
        :return: A new element containing the built TOC.
        :rtype: etree.ElementBase
        """
        # Create the root element
        menu_ele = etree.Element('ol', {'class': 'menu'})

        # iterate over the top nodes and add them
        for count, node in enumerate(toc_tree):
            title = node['title']
            href = node['href']

            # Build up the css class attribute
            if count == 0 and count == len(toc_tree) - 1:
                css_classes = ['first', 'last']
            elif count == 0:
                css_classes = ['first']
            elif count == len(toc_tree) - 1:
                css_classes = ['last']
            else:
                css_classes = []

            if 'children' in node:
                css_classes.append('children')
            else:
                css_classes.append('leaf')

            # Create the menu element
            sub_menu_ele = etree.Element('li', {'class': " ".join(css_classes)})

            # Set the title and href
            anchor = etree.SubElement(sub_menu_ele, 'a', href=href)
            anchor.text = title

            # Build up the children leaf
            if 'children' in node:
                child_menu = self.transform_tree_to_html(node['children'])
                sub_menu_ele.append(child_menu)

            # Add the new node
            menu_ele.append(sub_menu_ele)

        return menu_ele

    def transform_tree_to_xml(self, toc_tree, indent=1, section_depth=0, max_section_depth=2):
        """
        Builds the table of contents from a representation of the TOC using lists and dictionaries.

        :param toc_tree: The mapped representation of the TOC.
        :type toc_tree: list [dict]
        :param indent:
        :param section_depth:
        :param max_section_depth:
        :return: A new element containing the built TOC.
        :rtype: etree.ElementBase
        """
        max_section_depth = 2 if max_section_depth is None else max_section_depth
        item_indent = indent + 1

        # Create the root element
        children_ele = create_element('children', "\n" + ((2 * item_indent) * " "), indent=indent-1)

        # iterate over the top nodes and add them
        for count, node in enumerate(toc_tree):
            title = node['title']
            href = node['href']
            node_type = node.get('type')
            anchor_url = urlparse(href)
            page_slug = anchor_url.path
            anchor = anchor_url.fragment

            # If we are dealing with a section node, increase the section depth count
            if node_type in SECTION_ELES:
                current_section_depth = section_depth + 1
            else:
                current_section_depth = section_depth

            # Create the toc item element
            sub_item_indent = indent + 2
            item_attrs = {
                "visible": str(current_section_depth <= max_section_depth)
            }
            if count == len(toc_tree) - 1:
                sub_menu_ele = add_new_element(children_ele, 'item', children_ele.text + (2 * " "), attrs=item_attrs, indent=indent)
            else:
                sub_menu_ele = add_new_element(children_ele, 'item', children_ele.text + (2 * " "), attrs=item_attrs, indent=item_indent)

            # Set the item elements
            add_new_element(sub_menu_ele, 'title', title, indent=sub_item_indent)
            add_new_element(sub_menu_ele, 'page_slug', page_slug, indent=sub_item_indent)

            # Build up the toc children
            if 'children' in node:
                add_new_element(sub_menu_ele, 'anchor', anchor, indent=sub_item_indent)
                child_items = self.transform_tree_to_xml(node['children'],
                                                         indent=sub_item_indent,
                                                         section_depth=current_section_depth,
                                                         max_section_depth=max_section_depth)
                sub_menu_ele.append(child_items)
            else:
                add_new_element(sub_menu_ele, 'anchor', anchor, indent=item_indent)

            # Add the new node
            children_ele.append(sub_menu_ele)

        return children_ele


class DocBookHTML4Transformer(DocBookHTMLTransformer):
    def _get_root_toc_ele(self, toc_container_ele):
        return toc_container_ele.find('dl')

    def _extract_toc_children(self, parent_ele):
        retvalue = []

        # Loop over each child and build the tree
        # child_ele will either be dd, or dt
        for child_ele in parent_ele.iterchildren():
            if child_ele.tag == 'dt':
                node = {}
                # Get the anchor
                anchor = child_ele.find('./span/a')

                # Add the anchor details to the tree
                node['title'] = utils.get_element_text(anchor)
                node['href'] = anchor.get('href')

                # Add the node to the tree
                retvalue.append(node)
            elif child_ele.tag == 'dd':
                # dd should follow a dt element, so use the last element in retvalue
                node = retvalue[-1]
                dl_ele = child_ele.find('dl')
                node['children'] = self._extract_toc_children(dl_ele)

        return retvalue


class DocBookHTML5Transformer(DocBookHTMLTransformer):
    block_html_tags = ["section", "div"]

    def _get_root_toc_ele(self, toc_container_ele):
        return toc_container_ele.find('ul')

    def _extract_toc_children(self, parent_ele):
        retvalue = []

        # Loop over each child and build the tree
        # child_ele should be the <li> element
        for child_ele in parent_ele.iterchildren():
            if child_ele.tag == 'li':
                node = {}
                # Get the anchor
                anchor = child_ele.find('./span/a')

                # Add the anchor details to the tree
                node['title'] = utils.get_element_text(anchor)
                node['href'] = anchor.get('href')

                # Find the child_ele has a <ul> component, it has children
                ul_ele = child_ele.find('./ul')
                if ul_ele is not None:
                    node['children'] = self._extract_toc_children(ul_ele)

                # Add the node to the tree
                retvalue.append(node)

        return retvalue
