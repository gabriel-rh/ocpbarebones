import os
import shutil
import subprocess
import sys
import tarfile
import time

from lxml import etree, html
from lxml.etree import XMLSyntaxError, XIncludeError

from .base import XMLFeedTransformer
from aura import compat, utils
from aura.compat import StringIO
from aura.exceptions import InvalidInputException
from aura.transformers import DocsMetadata
from aura.transformers.publican import utils as publican_utils
from aura.transformers.publican.builder import (add_new_element,
                                                XMLFeedBuilder, XMLFeedBuilderContext, PROTOCOL_V1, PROTOCOL_V2,
                                                DocBookHTML5Transformer, DocBookHTML4Transformer)
from aura.transformers.publican.utils import XML_FEED_FORMAT, LXML_DOCBOOK_NS


class PublicanTransformer(XMLFeedTransformer):
    valid_formats = ["html", "html-single", "html-desktop", "pdf", "epub", "xml", "txt"]
    single_file_formats = ["pdf", "epub", "txt"]
    formats_sep = ","
    allows_multiple_formats = True

    def __init__(self, source_dir=None, feed_protocol=PROTOCOL_V1):
        super(PublicanTransformer, self).__init__(feed_protocol=feed_protocol)
        self.source_dir = os.getcwd() if source_dir is None else os.path.abspath(source_dir)
        self._doc_id_cache = {}
        self._build_root_dir_cache = {}
        self._build_dir_cache = {}
        self.source_markup = "docbook"

    def _get_config_path(self, config=None):
        # Fix the config to use the default value
        fixed_publican_cfg = "publican.cfg" if config is None else config
        abs_source_dir = os.path.abspath(self.source_dir)
        if fixed_publican_cfg.startswith(abs_source_dir):
            return fixed_publican_cfg
        else:
            return os.path.join(abs_source_dir, fixed_publican_cfg)

    def _resolve_source_language(self, src_lang=None, config=None):
        # If no source language is passed, then try to load from the config if available.
        # As a last resort, default to en-US
        if src_lang is None:
            if config is not None:
                abs_config_path = self._get_config_path(config)
                return publican_utils.get_xml_lang(abs_config_path)
            else:
                return "en-US"
        else:
            return src_lang

    def _run_publican_build(self, lang, build_format, config=None, additional_args=None):
        # Build the base command
        publican_cmd = ['publican', 'build', "--formats", build_format, "--langs", lang]

        # Set publican to use the specified config
        if config is not None:
            publican_cmd.extend(['--config', config])

        # Add the additional publican arguments
        if additional_args:
            publican_cmd.extend(utils.split_additional_args(additional_args))

        # Execute the command
        return subprocess.call(publican_cmd, cwd=self.source_dir)

    def _check_config_exists(self, config):
        fixed_config = self._get_config_path(config)

        # Make sure the config file exists
        if not os.path.isfile(fixed_config):
            config_filename = os.path.basename(fixed_config) if config is None else config
            raise InvalidInputException("Config file not found: {0}".format(config_filename))

    def _check_valid_build_format(self, build_formats):
        # Check that the format is a valid option
        for bformat in build_formats:
            if bformat != "drupal-book" and bformat not in self.valid_formats:
                raise InvalidInputException("\"{0}\" is not a valid format".format(bformat))

    def get_doc_id(self, config=None, lang=None):
        """
        Gets the book id from the XML and publican configuration stored in a book directory

        :param config: The publican.cfg file to use.
        :param lang: The language that is currently being built.
        :return: The documents natural id. eg Product-Version-Title-Lang
        """
        if lang not in self._doc_id_cache:
            # Fix the config to use the default value
            abs_publican_cfg = self._get_config_path(config)

            try:
                title, product, version, src_lang = publican_utils.get_npv_and_lang_from_dir(self.source_dir, abs_publican_cfg)
                if lang is None:
                    lang = src_lang
                doc_id = publican_utils.get_doc_id_from_npv(title, product, version, lang)
                self._doc_id_cache[lang] = doc_id
            except (XMLSyntaxError, XIncludeError) as e:
                self.log.error(e)
                self.log.error("Unable to determine the title, product and version due to XML errors.")
                sys.exit(-1)
            except IOError as e:
                self.log.error("%s: %s", e.strerror, e.filename)
                self.log.error("Unable to determine the title, product and version due to XML errors.")
                sys.exit(-1)

        return self._doc_id_cache[lang]

    def set_doc_id(self, doc_id, lang):
        self._doc_id_cache[lang] = doc_id

    def get_npv(self, config=None):
        # Fix the config to use the default value
        abs_publican_cfg = self._get_config_path(config)
        title, product, version, src_lang = publican_utils.get_npv_and_lang_from_dir(self.source_dir, abs_publican_cfg, False)
        return title, product, version

    def get_source_additional_file(self, filepath, base_lang, lang=None):
        # Check the translation path first
        if lang is not None:
            fullpath = os.path.join(lang, filepath)
            if os.path.exists(fullpath) and os.path.isfile(fullpath):
                return fullpath

        # Return the original source path
        return os.path.join(base_lang, filepath)

    def get_build_root_dir(self, config=None):
        """
        Gets the name of the publican temporary directory from a publican configuration file.

        :param config: The publican configuration file.
        :return: The directory path for the temp configuration file
        """
        # Fix the config to use the default value
        fixed_publican_cfg = "publican.cfg" if config is None else config

        # Init the value if it hasn't been built before
        if fixed_publican_cfg not in self._build_root_dir_cache:
            abs_publican_cfg = self._get_config_path(fixed_publican_cfg)
            # Parse the configuration file
            try:
                publican_config = publican_utils.load_publican_config(abs_publican_cfg)
            except IOError:
                # If we get an IO error just return tmp, as it means the file doesn't exist, so the default should be used
                return os.path.join(self.source_dir, "tmp")

            # Get the tmp_dir setting and save it in the cache
            root_build_dir = publican_utils.get_config_val(publican_config, "tmp_dir")
            root_build_dir = os.path.join(self.source_dir, root_build_dir)
            self._build_root_dir_cache[fixed_publican_cfg] = root_build_dir

        return self._build_root_dir_cache[fixed_publican_cfg]

    def get_build_dir(self, lang, build_format=XML_FEED_FORMAT, config=None):
        """
        Gets the name of the directory where all build files are stored using the configuration file provided.

        :param lang: The language of the build.
        :param build_format: The builds format.
        :param config: The configuration file.
        :return: The directory path for the build files directory.
        """
        # Fix the config to use the default value
        fixed_publican_cfg = "publican.cfg" if config is None else config

        # Generate the cache key
        key = fixed_publican_cfg + "-" + build_format + "-" + lang

        # Init the value if it hasn't been built before
        if key not in self._build_dir_cache:
            publican_tmp_dir = self.get_build_root_dir(fixed_publican_cfg)
            self._build_dir_cache[key] = os.path.join(publican_tmp_dir, lang, build_format) + os.path.sep

        return self._build_dir_cache[key]

    def get_build_additional_files_dir(self, lang, build_format=XML_FEED_FORMAT, config=None):
        """
        Finds the directory where video files are stored in the build directory.

        :param lang: The language of the build.
        :param build_format: The builds format.
        :param config: The configuration file.
        :return: The directory path for the build video files directory.
        """
        build_dir = self.get_build_dir(lang, build_format, config)

        # drupal-book stores the files in a deeper directory, base on the Product/Version/Title/Lang
        if build_format == "drupal-book":
            doc_id = self.get_doc_id(config, lang)

            # Check the build directories sub directories, for one that starts with the doc id. ie Product-Version-Title-Lang
            sub_dirs = next(os.walk(build_dir))[1]
            additional_files_dir = [name for name in sub_dirs if name.startswith(doc_id)][0]
            return os.path.join(build_dir, additional_files_dir) + os.sep
        else:
            return build_dir

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
        build_dir = self.get_build_root_dir(config)
        return os.path.join(build_dir, "archives")

    def _before_build_format(self, src_lang, lang, build_formats, config=None, additional_args=None):
        # Make sure the config file exist
        config = self._get_config_path(config)
        self._check_config_exists(config)

        # Check that the format is a valid option
        self._check_valid_build_format(build_formats)

        # Make sure the type in the config matches root element of the source content
        doctype = publican_utils.get_type(config).lower()
        mainfile = os.path.join(self.source_dir, publican_utils.get_mainfile(config))
        if mainfile is not None:
            # Parse the main file and get the root element name
            parser = etree.XMLParser(load_dtd=False, resolve_entities=False, recover=True)
            xml_root = utils.parse_xml(mainfile, parser=parser).getroot()
            root_element_name = xml_root.tag.replace(LXML_DOCBOOK_NS, "")

            if root_element_name != doctype:
                error_msg = "The document type specified in the configuration ({0}), " \
                            "doesn't match the source content type ({1})".format(doctype.title(), root_element_name.title())
                raise InvalidInputException(error_msg)

    def _after_build_format(self, exit_status, src_lang, lang, build_formats, config=None, additional_args=None):
        pass

    def build_format(self, src_lang, lang, build_format, config=None, additional_args=None, main_file=None, doctype=None):
        """Runs publican using the passed arguments
        :param src_lang:
        :param doctype:
        """
        # Warn about passed parameters that will be ignored
        if src_lang:
            self.log.warning("Ignoring the passed source language argument, as it cannot be used in Publican builds.")
        if main_file:
            self.log.warning("Ignoring the passed mainfile argument, as it cannot be used in Publican builds.")
        if doctype is not None:
            self.log.warning("Ignoring the passed doctype argument as it cannot be specified in Publican builds. Please " +
                             "change the type in your publican.cfg and XML files instead.")

        # Run any setup items before doing the build
        build_formats = build_format.split(self.formats_sep)
        self._before_build_format(src_lang, lang, build_formats, config, additional_args)

        # Run publican
        exit_status = self._run_publican_build(lang, build_format, config, additional_args)

        # Run any post process after doing the build if it was successful
        self._after_build_format(exit_status, src_lang, lang, build_formats, config, additional_args)

        return exit_status == 0

    def build_formats(self, src_lang, lang, build_formats, config=None, additional_args=None, main_file=None, doctype=None):
        return self.build_format(src_lang, lang, ",".join(build_formats), config, additional_args, main_file, doctype)

    def build_xml_feed(self, doc_uuid, src_lang, lang, config=None, additional_args=None, additional_formats=None, main_file=None,
                       doctype=None, archive=False):
        # Print a warning if a source lang is specified and unset the src_lang setting so it'll be loaded from publican.cfg
        if src_lang is not None:
            self.log.warning("Ignoring the passed source language argument, as it cannot be used in Publican builds.")
            src_lang = None

        # Check the config file exists
        self._check_config_exists(config)

        # Clean any previous build files
        self.clean_build_files()

        return self._build_xml_feed(doc_uuid, src_lang, lang, config, additional_args, additional_formats,
                                    main_file=main_file,
                                    doctype=doctype,
                                    archive=archive)

    def _build_xml_feed(self, doc_uuid, src_lang, lang, config=None, additional_args=None, additional_formats=None, main_file=None,
                        doctype=None, archive=False):
        # Do any pre build setup
        if not self._before_build_xml_feed(doc_uuid, src_lang, lang, config, additional_args, main_file, doctype):
            return False

        # Build the feed
        formats = ['html-single']
        if additional_formats:
            formats.extend(additional_formats)
        formats.append(XML_FEED_FORMAT)

        # Build the drupal html and additional formats
        if self.build_formats(src_lang, lang, formats, config, additional_args, main_file, doctype):
            xml_file = self.get_build_main_file(lang, XML_FEED_FORMAT, config)
            # If no source language is passed, resolve to en-US. Do this here, as we need the passed src lang up until this point
            src_lang = self._resolve_source_language(src_lang, config)

            # Build the XML Feed
            feed_tree = self._generate_xml_feed(doc_uuid, src_lang, lang, config)

            # Add the additional format files to the tar and XML feed, if the build was successful.
            rv = self._after_build_xml_feed(doc_uuid, src_lang, lang, feed_tree, config, additional_formats)

            # Save the xml feed
            with open(xml_file, 'w') as f:
                xml = etree.tostring(feed_tree, encoding="UTF-8", xml_declaration=True)
                f.write(xml)

            # Remove the publican built tar containing images and files, as it is useless
            build_dir = self.get_build_dir(lang, XML_FEED_FORMAT, config)
            publican_tar = utils.find_file_for_type(build_dir, "tar.gz")
            publican_tar = os.path.join(build_dir, publican_tar)
            if os.path.exists(publican_tar):
                os.remove(publican_tar)

            # Archive the contents
            if archive:
                self._archive_xml_feed(doc_uuid, src_lang, lang, config, main_file, doctype)

            return rv
        else:
            return False

    def _before_build_xml_feed(self, doc_uuid, src_lang, lang, config, additional_args, main_file, doctype):
        """
        This method is called just before the XML feed is built.

        :param doc_uuid: A UUID to identify the document being built.
        :type doc_uuid: uuid.UUID
        :param src_lang: The source language of the document.
        :type src_lang: str
        :param lang: The language to build the XML feed for.
        :type lang: str
        :param config: A configuration file to use when building.
        :type config: str
        :param additional_args:
        :param main_file:
        :param doctype:
        :return:
        """
        # Translation builds need to add the "base" attribute, so build the source lang drupal-book
        fixed_src_lang = self._resolve_source_language(src_lang, config)
        if fixed_src_lang != lang:
            if not self.build_format(src_lang, fixed_src_lang, 'drupal-book', config, additional_args, main_file, doctype):
                return False

        return True

    def _generate_xml_feed(self, doc_uuid, src_lang, lang, config):
        """
        Generates the XML feed using the source XML and publican built html files

        :param doc_uuid:
        :param src_lang:
        :param lang:
        :param config:
        :return: A XML Tree
        :rtype: lxml.etree.ElementTree
        """
        abs_publican_cfg = self._get_config_path(config)

        # Parse the source XML so we can get the element ids
        try:
            src_xml = self.get_build_main_file(src_lang, "xml", config)
            self.log.debug("Parsing the source XML...")
            parser = etree.XMLParser(load_dtd=True, strip_cdata=False)

            # Parse the source language xml
            src_tree = utils.parse_xml(src_xml, parser)
            src_tree.xinclude()

            # Parse the translated source
            if src_lang != lang:
                self.log.debug("Parsing the translated XML...")
                trans_xml = self.get_build_main_file(lang, "xml", config)
                parser = etree.XMLParser(load_dtd=True, strip_cdata=False)
                trans_tree = utils.parse_xml(trans_xml, parser)
                trans_tree.xinclude()
            else:
                trans_tree = None
        except (XMLSyntaxError, XIncludeError) as e:
            self.log.error(e)
            self.log.error("Unable to parse the source XML")
            sys.exit(-1)
        except IOError as e:
            self.log.error("%s: %s", e.strerror, e.filename)
            self.log.error("Unable to parse the source XML")
            sys.exit(-1)

        # Create the builder and build the feed
        context = XMLFeedBuilderContext(self, doc_uuid, src_tree, src_lang, lang, abs_publican_cfg,
                                        trans_tree=trans_tree,
                                        protocol=self.feed_protocol)
        return XMLFeedBuilder(context).build_from_source()

    def _after_build_xml_feed(self, doc_uuid, src_lang, lang, feed_tree, config, additional_formats):
        """
        This method is called right after the XML Feed is successfully built by Publican. It will adjust the default XML feed produced
        by adding additional format files, html-single and toc elements and also replace the Legal Notice to the end of the book.

        :param doc_uuid: A UUID to identify the document being built.
        :type doc_uuid: uuid.UUID
        :param src_lang: The source language of the document.
        :type src_lang: str
        :param lang: The language to build the XML feed for.
        :type lang: str
        :param feed_tree:
        :type feed_tree:
        :param config: A configuration file to use when building.
        :type config: str
        :param additional_formats: A list of any additional formats to build alongside the XML feed.
        :type additional_formats: list [str]
        :return:
        """
        # Find the DocBook version and build the transform helper
        abs_publican_cfg = self._get_config_path(config)
        docbook_ver = publican_utils.get_dtdver(abs_publican_cfg)
        if docbook_ver >= (5, 0):
            transformer = DocBookHTML5Transformer()
        else:
            transformer = DocBookHTML4Transformer()

        self._adjust_xml_feed(src_lang, lang, feed_tree, transformer, abs_publican_cfg, additional_formats)

        return True

    def _archive_xml_feed(self, doc_uuid, src_lang, lang, config=None, mainfile=None, doctype=None):
        """
        Build the archive containing the XML Feed and additional files.

        :param doc_uuid:
        :param src_lang: The source language of the document.
        :type src_lang: str
        :param lang: The language to build the XML feed for.
        :type lang: str
        :param config: A configuration file to use when building.
        :type config: str
        :param mainfile: The main file to build from.
        :type mainfile: str
        :param doctype: The type of document that is being built. (book|article)
        :type doctype: str
        """
        doc_nat_id = self.get_doc_id(config)
        build_dir = self.get_build_dir(lang, XML_FEED_FORMAT, config)
        archives_dir = self.get_build_archives_dir(lang, config)
        xml_file = self.get_build_main_file(lang, XML_FEED_FORMAT, config)
        additional_files_dir = self.get_build_additional_files_dir(lang, XML_FEED_FORMAT, config)
        title, product, version, lang = publican_utils.get_npv_and_lang_from_dir(self.source_dir, config)

        # Make sure the archive directory exists
        if not os.path.exists(archives_dir):
            os.makedirs(archives_dir)

        # Create the metadata.ini
        metadata = DocsMetadata()
        metadata.source.lang = src_lang
        metadata.source.mainfile = mainfile
        metadata.source.type = doctype if doctype is not None else "book"
        metadata.source.markup = self.source_markup
        metadata.title = title
        metadata.product = product
        metadata.version = version
        metadata_str = str(metadata)

        # Create a ZIP file handle to write to
        archive_filename = os.path.join(archives_dir, doc_nat_id + ".tar.gz")
        self.log.info("Writing archive to %s", archive_filename)
        with tarfile.open(archive_filename, 'w:gz') as archive:
            # Add the metadata.ini
            tarinfo = tarfile.TarInfo('metadata.ini')
            tarinfo.size = len(metadata_str)
            tarinfo.mtime = time.time()
            archive.addfile(tarinfo, StringIO(metadata_str))

            # Add the xml file
            archive.add(xml_file, os.path.basename(xml_file))

            # Add in all the additional files
            for root, dirs, files in os.walk(additional_files_dir):
                archive_root = root.replace(build_dir, "")
                for filename in files:
                    archive.add(os.path.join(root, filename), os.path.join(archive_root, filename))

    def _adjust_xml_feed(self, src_lang, lang, feed_tree, transformer, config, additional_formats):
        # Add in the commit SHA1 if it's a git repository
        self._add_git_info(feed_tree)

        # Add the single page content to the feed
        self._add_singlepage_to_feed(lang, feed_tree, transformer, config)

        # Add the additional formats to the tree
        self._add_additional_formats_to_feed(lang, feed_tree, config, additional_formats)

    def _add_git_info(self, feed_tree):
        import git
        try:
            # Create repository object and look up the current head commit
            repo = compat.init_git_repo(self.source_dir)
            sha = repo.head.commit.hexsha
            repo_url = repo.remotes.origin.url
        except git.InvalidGitRepositoryError:
            # We aren't building from a git repository, so treat it as there is no commit/repo url
            sha = None
            repo_url = None

        # Build the repo url element
        repo_url_ele = etree.Element("repourl")
        repo_url_ele.text = repo_url
        repo_url_ele.tail = "\n  "

        # Build the commit element
        commit_ele = etree.Element("commit")
        commit_ele.text = sha
        commit_ele.tail = "\n  "

        # Add the commit before the first page object
        xml_root = feed_tree.getroot()
        first_page = xml_root.find(".//page")
        if first_page is not None:
            first_page.addprevious(repo_url_ele)
            first_page.addprevious(commit_ele)
        else:
            xml_root.append(commit_ele)
            xml_root.append(repo_url_ele)

    def _add_additional_formats_to_feed(self, lang, xml_feed, config=None, additional_formats=None):
        """
        Adds the additional formats to the XML Feed.

        :param lang:               The language of the build.
        :type lang:                str
        :param xml_feed:           The xml feed ElementTree to add the additional formats to.
        :type xml_feed:            etree._ElementTree
        :param config:             The configuration file for the build.
        :type config:              str
        :param additional_formats: A list of additional formats to add to the XML feed.
        :type additional_formats:  list [str]
        """
        additional_files_dir = self.get_build_additional_files_dir(lang, XML_FEED_FORMAT, config)
        xml_root = xml_feed.getroot()

        additional_files = []
        for additional_format in additional_formats:
            format_file = self.get_build_main_file(lang, additional_format, config)
            additional_files.append(format_file)

            # Build the new element and add it to the root
            format_ele = etree.SubElement(xml_root, additional_format)
            format_ele.text = os.path.basename(format_file)
            format_ele.tail = "\n"

        # Move the files to the build additional files dir
        for additional_file in additional_files:
            new_path = os.path.join(additional_files_dir, os.path.basename(additional_file))
            shutil.copy2(additional_file, new_path)

    def _add_single_page_toc_anchor(self, feed_toc_item, single_page_anchor):
        anchor_ele = feed_toc_item.find("anchor")
        idx = -1 if anchor_ele is None else feed_toc_item.index(anchor_ele) + 1
        singlepage_anchor_ele = add_new_element(feed_toc_item, "singlePageAnchor", single_page_anchor, index=idx)
        singlepage_anchor_ele.tail = anchor_ele.tail
        if idx == len(feed_toc_item) - 1:
            anchor_ele.tail += 2 * " "

    def _merge_singlepage_toc(self, xml_feed_toc, single_toc):
        """
        Merges a single pages feed Table of Content elements in with an existing feeds Table of Content elements, based on indexes.

        :param xml_feed_toc: The XML Feeds toc element that contains a list of "item" elements
        :type xml_feed_toc: etree._Element
        :param single_toc: The Single Pages toc element that contains a list of "item" elements
        :type single_toc: etree._Element
        """
        for single_idx, single_toc_item in enumerate(single_toc.iterchildren("item")):
            single_toc_item_anchor = single_toc_item.find("anchor").text
            for feed_idx, feed_toc_item in enumerate(xml_feed_toc.iterchildren("item")):
                if single_idx == feed_idx:
                    # Create the new singlePageAnchor element and add it to the existing feed item after the existing anchor
                    self._add_single_page_toc_anchor(feed_toc_item, single_toc_item_anchor)

                    # Add the children toc items
                    singlepage_toc_children = single_toc_item.find("children")
                    feed_toc_children = feed_toc_item.find("children")
                    if singlepage_toc_children is not None and feed_toc_children is not None:
                        self._merge_singlepage_toc(feed_toc_children, singlepage_toc_children)

                    # Don't keep looping since a match was found
                    break

    def _add_singlepage_toc(self, xml_root, html_body_ele, transformer):
        """

        :param xml_root:        The xml feeds root element to add the html-single table of contents to.
        :type xml_root:         etree._Element
        :param html_body_ele:   The single pages html body element to get the table of contents from.
        :type html_body_ele:    html.HTMLElement
        :param transformer:     The DocBook transformer instance, that can be used to transform DocBook produced HTML into a consistent
                                Drupal XHTML/XML format.
        :type transformer:      DocBookHTMLTransformer
        """
        # Add in the single page toc
        if self.feed_protocol == PROTOCOL_V2:
            feed_toc = xml_root.find("toc")
            if feed_toc is not None:
                # Generate the toc tree and move the top level children up one level
                # as we want the doc title, to be at the same level as the rest of the content
                toc_tree = transformer.extract_toc_tree_from_html(html_body_ele)

                if len(toc_tree) > 0:
                    index_page_node = toc_tree[0]
                    index_page_node["href"] = "index"
                    toc_tree.extend(index_page_node.pop("children", []))

                    # Generate the toc xml feed representation for the page
                    transformed_toc = transformer.transform_tree_to_xml(toc_tree)
                    self._merge_singlepage_toc(feed_toc, transformed_toc)
        else:
            # Find the toc element in the html
            main_tocs = html_body_ele.xpath(".//*[local-name()='div'][contains(@class,'toc')]")
            if len(main_tocs) > 0:
                main_toc = main_tocs[0]

                toc_ele = etree.Element('toc')
                toc_ele.tail = "\n"
                xml_root.append(toc_ele)

                # Transform the singlepage TOC to the required html markup
                transformed_toc = transformer.transform_toc_to_html(main_toc)
                toc_ele.append(transformed_toc)

    def _add_singlepage_to_feed(self, lang, xml_feed, transformer, config=None):
        """
        Adds the html-single content of a build to the XML feed. Additionally before adding the content to the field, it scrubs the HTML to
        to split out the TOC and also remove unwanted content (ie the HTML head).

        :param lang:        The language of the build.
        :type lang:         str
        :param xml_feed:    The xml feed ElementTree to add the html-single content to.
        :type xml_feed:     etree._ElementTree
        :param transformer: The DocBook transformer instance, that can be used to transform DocBook produced HTML into a consistent
                            Drupal XHTML/XML format.
        :type transformer:  DocBookHTMLTransformer
        :param config:      The configuration file for the build.
        :type config:       str
        """
        html_single_file = self.get_build_main_file(lang, 'html-single', config)

        # Parse the html content and extract the content needed
        try:
            parser = html.XHTMLParser(ns_clean=True)
            html_ele = utils.parse_xhtml(html_single_file, parser)

            # Find the body and toc content
            body = html_ele.body

            # Move down the body if the html-single contains id="chrometwo" and id="main"
            div_name = utils.get_ns_tag_name(body, "div")
            main = body.find("./" + div_name + "[@id='chrometwo']/" + div_name + "[@id='main']")
            if main is not None:
                body = main

            # Scrub the html to remove unwanted content
            publican_utils.scrub_html(body)

            # Fix the images/additional file relative links
            self._fix_html_relative_paths(body)

            # Add/update the feeds table of contents
            xml_root = xml_feed.getroot()
            self._add_singlepage_toc(xml_root, body, transformer)

            # Add the single page elements to the xml feed
            html_single_ele = etree.Element('singlepage')
            html_single_ele.tail = "\n"
            xml_root.append(html_single_ele)

            # Add the html and toc to the singlepage elements
            for child in body.iterchildren():
                html_single_ele.append(child)
        except IOError as e:
            self.log.error("%s: %s", e.strerror, e.filename)
            self.log.error("Unable to parse the html-single content")
            sys.exit(-1)

    def _fix_html_relative_paths(self, html_ele, prefix='/sites/default/files/documentation/'):
        """
        Fixes any relative paths, to ensure that they are prefixed with the prefix attribute

        :param html_ele: The HTML element to resolve the relative paths for.
        :type html_ele:  lxml.html.HtmlElement
        :param prefix: The file path prefix to add to the relative url.
        :type prefix:  str
        """
        # Find all the images that need fixing
        image_eles = self._get_images_from_html_ele(html_ele)

        # Add the prefix to the paths
        for image in image_eles:
            if image.tag == 'object':
                source_attr = 'data'
            else:
                source_attr = 'src'
            image_src = image.get(source_attr)

            if image_src.startswith('images/') or image_src.startswith('Common_Content/images/'):
                image.set(source_attr, prefix + image_src)

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
        if src_lang:
            self.log.warning("Ignoring the passed source language parameter, as it cannot be used in Publican builds.")
        if main_file:
            self.log.warning("Ignoring the passed mainfile parameter, as it cannot be used in Publican builds.")
        if doctype:
            self.log.warning("Ignoring the passed doctype parameter, as it cannot be used in Publican builds.")

        # Build the base command
        langs = ",".join(langs)
        publican_pot_cmd = ['publican', 'update_pot']
        publican_po_cmd = ['publican', 'update_po', "--langs", langs, "--firstname", "Red", "--surname", "Hat",
                           "--email", "no-reply@redhat.com"]

        # Set publican to use the specified config
        if config is not None:
            publican_pot_cmd.extend(['--config', config])
            publican_po_cmd.extend(['--config', config])

        # Execute the commands
        exit_pot_status = exit_po_status = 0
        if not po_only:
            self.log.info("Creating the POT files...")
            exit_pot_status = subprocess.call(publican_pot_cmd, cwd=self.source_dir)
        if not pot_only:
            self.log.info("Creating the PO files...")
            exit_po_status = subprocess.call(publican_po_cmd, cwd=self.source_dir)
        return exit_pot_status == 0 and exit_po_status == 0

    def get_build_main_file(self, lang, build_format=XML_FEED_FORMAT, config=None):
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
        build_dir = self.get_build_dir(lang, build_format, config)
        build_file = None
        if build_format == "html" or build_format == "html-single" or build_format == "html-desktop":
            build_file = os.path.join(build_dir, "index.html")
        elif build_format == "pdf":
            pdf_filename = utils.find_file_for_type(build_dir, "pdf")
            if pdf_filename is not None:
                build_file = os.path.join(build_dir, pdf_filename)
            else:
                self.log.error("Unable to find the PDF build. This is likely a bug, so please report it.")
                sys.exit(-1)
        elif build_format == "epub":
            build_root_dir = self.get_build_root_dir(config)
            build_lang_dir = os.path.join(build_root_dir, lang) + os.path.sep
            epub_filename = utils.find_file_for_type(build_lang_dir, "epub")
            if epub_filename is not None:
                build_file = os.path.join(build_lang_dir, epub_filename)
            else:
                self.log.error("Unable to find the epub build. This is likely a bug, so please report it.")
                sys.exit(-1)
        elif build_format == "drupal-book":
            doc_id = self.get_doc_id(config, lang)
            xml_filename = utils.find_file_for_type(build_dir, "xml", doc_id)
            build_file = os.path.join(build_dir, xml_filename)
        elif build_format == "txt":
            txt_filename = utils.find_file_for_type(build_dir, "txt")
            if txt_filename is not None:
                build_file = os.path.join(build_dir, txt_filename)
            else:
                self.log.error("Unable to find the txt build. This is likely a bug, so please report it.")
                sys.exit(-1)
        elif build_format == "xml":
            fixed_config = self._get_config_path(config)
            mainfile = os.path.basename(publican_utils.get_mainfile(fixed_config))
            build_file = os.path.join(build_dir, mainfile)

        return build_file

    def get_videos_from_feed(self, xml_feed):
        """
        Gets a list of local videos used in the book/article from the Drupal XML Feed.

        :param xml_feed: An Element tree for the Drupal XML feed.
        :type xml_feed:  etree._ElementTree
        :return: A list of video elements in the XML feed.
        :rtype:  list [etree.ElementBase]
        """
        # Find any "mediaobject" nodes
        media_objects = xml_feed.getroot().xpath(".//div[@class=\"mediaobject\"] | .//span[@class=\"inlinemediaobject\"]")

        # Extract the paths
        video_eles = []
        for media_object in media_objects:
            for child in list(media_object):
                # DB 4.5 output from publican is an embed tag, while DB 5.0 is an iframe.
                if (child.tag == "iframe" and "videodata" in child.get("class")) or child.tag == "embed":
                    video_eles.append(child)

        return video_eles

    def get_images_from_feed(self, xml_feed):
        """
        Gets a list of local images used in the book/article from the Drupal XML Feed.

        :param xml_feed: An Element tree for the Drupal XML feed.
        :type xml_feed:  etree._ElementTree
        :return: A list of image elements in the XML feed.
        :rtype:  list [etree.ElementBase]
        """
        return self._get_images_from_html_ele(xml_feed.getroot())

    def _get_images_from_html_ele(self, xml_ele):
        """
        Gets a list of local images used in the book/article from a lxml Element.

        :return: A list of image elements in the XML feed.
        :rtype:  list [etree.ElementBase]
        """
        # Find any "mediaobject" nodes
        media_objects = xml_ele.xpath(".//div[@class=\"mediaobject\"] | .//span[@class=\"inlinemediaobject\"]")

        # Extract the paths
        image_eles = []
        for media_object in media_objects:
            for child in list(media_object):
                if child.tag == "img" or (child.tag == "object" and 'image' in child.get('type')):
                    image_eles.append(child)

                    # Handle fallbacks for objects
                    if child.tag == "object":
                        for object_child in list(child):
                            if object_child.tag == "img":
                                image_eles.append(object_child)

        return image_eles

    def get_file_links_from_feed(self, xml_feed):
        """
        Gets a list of elements that link to local additional files used in the book/article from the Drupal XML Feed.

        :param xml_feed: An Element tree for the Drupal XML feed.
        :type xml_feed:  etree._ElementTree
        :return: A list of link elements in the XML feed.
        :rtype: list [lxml.etree.ElementBase]
        """
        return xml_feed.getroot().xpath(".//a[starts-with(@href,'files/')]")

    def clean_build_files(self, config=None):
        """
        Clean any temporary build files on the local machine.

        :return: True if the build files were clean successfully, otherwise False.
        :rtype: bool
        """
        # Build the base command
        publican_cmd = ['publican', 'clean']

        if config:
            publican_cmd.extend(["--config", config])

        # Execute the command
        exit_status = subprocess.call(publican_cmd, cwd=self.source_dir)
        return exit_status == 0
