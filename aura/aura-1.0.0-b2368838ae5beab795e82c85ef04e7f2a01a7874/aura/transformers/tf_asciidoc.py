from __future__ import print_function
import fileinput
import os
import re
import shutil
import subprocess
import sys
from collections import OrderedDict
from datetime import date

import click
import requests
from lxml import etree
from lxml.etree import XMLSyntaxError, XIncludeError

from aura import utils
from aura.compat import urljoin, StringIO
from aura.exceptions import InvalidInputException
from aura.transformers.tf_publican import PublicanTransformer
from aura.transformers.publican import utils as publican_utils


BOOK_DOCTYPE = '<!DOCTYPE book [\n\
<!ENTITY % sgml.features "IGNORE">\n\
<!ENTITY % xml.features "INCLUDE">\n\
<!ENTITY % DOCBOOK_ENTS PUBLIC "-//OASIS//ENTITIES DocBook Character Entities V4.5//EN" \
"http://www.oasis-open.org/docbook/xml/4.5/dbcentx.mod">\n\
%DOCBOOK_ENTS;\n\
]>'

XML_NS = "http://www.w3.org/XML/1998/namespace"
DOCBOOK_NS = "http://docbook.org/ns/docbook"
LXML_DOCBOOK_NS = "{" + DOCBOOK_NS + "}"
LXML_XML_NS = "{" + XML_NS + "}"
ID_RE = re.compile("xml:id=\"([a-zA-Z0-9_:\.-]+)\"")
URL_RE = re.compile("^(http|ftp)s?://")
URL_OR_COMMON_CONTENT_RE = re.compile(r"^((http|ftp)s?://|(\./)?Common_Content(\\|/)).*")
URL_OR_IMAGES_PATH_RE = re.compile(r"^((http|ftp)s?://|(\./)?(images|Common_Content)(\\|/)).*")
INVALID_COLWIDTH_RE = re.compile("^\d+\.\d+\*$")
UNCONVERTED_XREF_LINK_HREF_RE = re.compile(r"(.*\.xml)#(.*)")
__DOC_ATTR_CACHE = {}


def clean_product(product):
    product = utils.replace_nbsp(product)
    if isinstance(product, unicode):
        product = product.encode('UTF-8')
    # Publican requires the products to match ^[0-9a-zA-Z_\-\.\+]+$
    # also, don't start a title with a decimal, as it'll be treated as a hidden file
    return re.sub("^\.+|[^0-9a-zA-Z _\-\.]*", "", product)


def clean_version(version):
    if version is None:
        # If the version is none, then revert to the publican default value
        return "0.1"
    else:
        version = utils.replace_nbsp(version)
        if isinstance(version, unicode):
            version = version.encode('UTF-8')
        # Publican requires the version to match ^[0-9][^\p{IsSpace}]*$
        # so replace spaces with a hyphen
        return re.sub("\s+", "-", version)


def clean_title(title):
    title = utils.replace_nbsp(title)
    if isinstance(title, unicode):
        title = title.encode('UTF-8')
    # Replace "C++" with "CPP" since it's a special case CCS-1043
    title = title.replace("C++", "CPP")
    # Publican requires the title to match ^[0-9a-zA-Z_\-\.\+]+$
    # also, don't start a title with a decimal, as it'll be treated as a hidden file
    return re.sub("^\.+|[^0-9a-zA-Z _\-\.]*", "", title)


def get_npv_from_docinfo(docinfo_file):
    """

    :param docinfo_file:
    :return:
    """
    # Make sure the file exists
    if not os.path.exists(docinfo_file):
        raise IOError("Unable to read the AsciiDoc docinfo file: " + docinfo_file)

    # Open the file, wrap the contents so it can be parsed as xml
    with open(docinfo_file, 'r') as f:
        docinfo = "<info>" + f.read() + "</info>"

    # Convert the xml config to a tree
    tree = etree.parse(StringIO(docinfo))

    # Extract the npv from the tree
    return publican_utils.get_npv_from_xml(tree)


def validate_xml_info(docinfo_file, error_callback=None):
    # Parse the XML content
    tree = utils.parse_xml(docinfo_file)

    return validate_xml_info_from_tree(tree, error_callback)


def validate_xml_info_from_tree(tree, error_callback=None):
    # Find the info content
    xml_root = tree.getroot()
    info_ele = xml_root.find("./" + LXML_DOCBOOK_NS + "info")

    # Ensure that title, productname, subtitle and abstract have been defined.
    error = False
    for tag in ('title', 'productname', 'subtitle', 'abstract'):
        if info_ele.find(LXML_DOCBOOK_NS + tag) is None:
            error = True

            # Call the callback for the missing tag
            if error_callback:
                error_callback(tag)

    return not error


def migrate_authors(info_ele, author_group_file):
    """
    Moves <author> elements from an <info> block to an <authorgroup> file.

    :param info_ele: The <info> ele to move authors from.
    :param author_group_file: The authorgroup file to move <authors> to.
    :return:
    """

    # Parse the author group XML
    tree = utils.parse_xml(author_group_file)

    # Get the root elements
    author_root = tree.getroot()

    # Remove the publican authors
    for author in author_root.iterchildren():
        author_root.remove(author)

    # Check to make sure we have items to move
    if info_ele.find(LXML_DOCBOOK_NS + "author") is not None or info_ele.find(LXML_DOCBOOK_NS + "authorgroup") is not None:
        # Build up the xi:include
        include = etree.Element("{http://www.w3.org/2001/XInclude}include", nsmap={'xi': 'http://www.w3.org/2001/XInclude'},
                                href="Author_Group.xml")
        include.tail = "\n"

        # Add an xi:include to the first element
        author_groups = info_ele.findall(".//" + LXML_DOCBOOK_NS + "authorgroup")
        authors = info_ele.findall(".//" + LXML_DOCBOOK_NS + "author")
        if len(author_groups) > 0:
            author_groups[0].addprevious(include)
        else:
            if authors[0].getparent().xpath('local-name()') == "authorgroup":
                authors[0].getparent().addprevious(include)
            else:
                authors[0].addprevious(include)

        # Move all the author groups over to Author_Group.xml
        for author_group in author_groups:
            for child in author_group:
                author_root.append(child)

        # Move all the floating authors over to Author_Group.xml
        for author in authors:
            if author.getparent().xpath('local-name()') != "authorgroup" and author.getparent().xpath('local-name()') != "revision":
                author_root.append(author)

        # Clean up any left over empty <authorgroup> elements
        for authorgroup in info_ele.findall(".//" + LXML_DOCBOOK_NS + "authorgroup"):
            if len(authorgroup) == 0:
                authorgroup.getparent().remove(authorgroup)
    else:
        # No authors defined in the asciidoc source, so clean up the default publican author
        author_ele = etree.SubElement(author_root, 'orgname')
        author_ele.text = "Red Hat Customer Content Services"

    # Save the changes
    doctype = utils.read_xml_doctype(author_group_file)
    with open(author_group_file, 'w') as f:
        xml = etree.tostring(tree, encoding="UTF-8", xml_declaration=True, doctype=doctype)
        f.write(xml)


def migrate_revisions(info_ele, revhistory_file):
    """
    Moves <revision> elements from an <info> block to a <revhistory> file.

    :param info_ele: The <info> ele to move revisions from.
    :param revhistory_file: The revision history file to move <revision>'s to.
    :return:
    """
    # Parse the Revision History XML
    tree = utils.parse_xml(revhistory_file)

    # Get the root elements
    revhistory_root = tree.getroot()
    revhistory_ele = revhistory_root.find(LXML_DOCBOOK_NS + "revhistory")

    # Check to make sure we have items to move
    if info_ele.find(LXML_DOCBOOK_NS + "revision") is not None or info_ele.find(LXML_DOCBOOK_NS + "revhistory") is not None:
        # Remove the default revisions
        for revision in revhistory_ele.iterchildren():
            revhistory_ele.remove(revision)

        # Build up the xi:include and add it to the last element before the index
        include = etree.Element("{http://www.w3.org/2001/XInclude}include", nsmap={'xi': 'http://www.w3.org/2001/XInclude'},
                                href="Revision_History.xml")
        include.tail = "\n"
        parent = info_ele.getparent()
        appendixes = parent.findall(LXML_DOCBOOK_NS + "appendix")
        index = parent.find(LXML_DOCBOOK_NS + "index")
        if len(appendixes) > 0:
            last_appendix = appendixes[-1]
            last_appendix.addnext(include)
        elif index:
            index.addprevious(include)
        else:
            parent.append(include)

        # Move all the revisions over to the revhistory and fix them to comply with publican
        for revision in info_ele.findall(".//" + LXML_DOCBOOK_NS + "revision"):
            revhistory_ele.append(revision)
            fix_revision(revision)

        # Clean up any left over empty <revhistory> elements
        for revhistory in info_ele.findall(".//" + LXML_DOCBOOK_NS + "revhistory"):
            if len(revhistory) == 0:
                revhistory.getparent().remove(revhistory)
    else:
        # Nothing to migrate, so lets clean up the default revision a little
        revision_ele = revhistory_ele.find(LXML_DOCBOOK_NS + "revision")
        revnumber_ele = revision_ele.find(LXML_DOCBOOK_NS + "revnumber")
        author_ele = revision_ele.find(LXML_DOCBOOK_NS + "author")
        member_ele = revision_ele.find("./" + LXML_DOCBOOK_NS + "revdescription//" + LXML_DOCBOOK_NS + "member")

        # Set the revision to 1.0-0
        revnumber_ele.text = "1.0-0"

        # Set the author to "Red Hat Customer Content Services"
        for ele in author_ele.iterchildren():
            author_ele.remove(ele)
        authorinitials_ele = etree.Element('authorinitials')
        authorinitials_ele.text = "Red Hat CCS"
        author_ele.addprevious(authorinitials_ele)
        revision_ele.remove(author_ele)

        # Set the member text to initial creation
        member_ele.text = "Initial document creation"

    # Save the changes
    doctype = utils.read_xml_doctype(revhistory_file)
    with open(revhistory_file, 'w') as f:
        xml = etree.tostring(tree, encoding="UTF-8", xml_declaration=True, doctype=doctype)
        f.write(xml)


def fix_revision(revision_ele):
    """
    Fixes a revision element up so that it can be used in Publican.

    :param revision_ele: The revision element to be fixed
    """
    # Get the date and revnumber
    # date_ele = revision_ele.find(DOCBOOK_NS + "date")
    revnumber_ele = revision_ele.find(LXML_DOCBOOK_NS + "revnumber")

    # Fix up the revision number
    # TODO try to flesh this out to handle more possible issues.
    if revnumber_ele is not None and "-" not in revnumber_ele.text:
        revnumber_ele.text += "-0"


def resolve_attribute(value, attrs):
    """
    Resolves an attribute value to replace any internal attribute reference with their actual value.

    :param value: The value of the attribute to resolve
    :param attrs: The list of attributes available.
    :return: The resolved attribute value.
    """
    for re_match in re.finditer(r"\{([^\}]+)\}", value):
        name = re_match.group(1)
        attr_value = attrs.get(name)
        if attr_value is not None:
            attr_value = resolve_attribute(attr_value, attrs)
            value = value.replace(re_match.group(0), attr_value)

    return value


def _get_file_attributes(filename, attrs=None, process_includes=False, recursive_includes=False):
    """
    Reads an asciidoc file and gets/resolves all defined attributes

    :param filename:
    :param process_includes: Process the include directives in the file.
    :param recursive_includes: Recursively process include directives.
    """
    attrs = attrs or OrderedDict()
    in_comment = False
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            for line in f:
                # Check to see if a comment is being started/ended
                if line.startswith("////"):
                    in_comment = not in_comment
                elif not in_comment:
                    # Not in a comment block, so handle includes and attribute definitions
                    if line.startswith("include::") and process_includes:
                        include_file = line.replace("include::", "").split("[")[0]
                        include_filepath = os.path.join(os.path.dirname(filename), include_file)
                        attrs.update(_get_file_attributes(include_filepath, attrs, recursive_includes, recursive_includes))
                    elif re.match(r'^:\S+:.*', line):
                        attr_vars = line.split(":", 2)
                        attrs[attr_vars[1]] = resolve_attribute(attr_vars[2].strip(), attrs)

    return attrs


def get_attribute_value(filename, attribute_name):
    """
    Gets a document attributes value from a specific file.

    :param attribute_name:
    :param filename:
    :return:
    """
    # Read in each line to try to find any macros in the file
    if filename not in __DOC_ATTR_CACHE:
        attributes = _get_file_attributes(filename, process_includes=True)

        # Resolve the attributes
        resolved_attrs = OrderedDict()
        for key, value in attributes.items():
            resolved_attrs[key] = resolve_attribute(value, attributes)
        __DOC_ATTR_CACHE[filename] = resolved_attrs

    cache = __DOC_ATTR_CACHE[filename]
    if attribute_name in cache:
        return cache[attribute_name]
    else:
        return None


class AsciiDocPublicanTransformer(PublicanTransformer):
    valid_formats = ["html", "html-single", "html-desktop", "pdf", "epub", "xml"]
    brand = "common-db5"

    def __init__(self, source_dir=None, build_dir=None, convert_always=True, feed_protocol=1):
        self.adoc_source_dir = os.getcwd() if source_dir is None else os.path.abspath(source_dir)
        self.build_dir = os.path.join(self.adoc_source_dir, "build") if build_dir is None else os.path.abspath(build_dir)
        super(AsciiDocPublicanTransformer, self).__init__(self.build_dir, feed_protocol=feed_protocol)
        self.convert_always = convert_always
        self.__last_converted_file = None
        self.source_markup = "asciidoc"

    def _init_build_dir(self, lang):
        # Make the build directory
        build_lang_dir = os.path.join(self.build_dir, lang)
        if not os.path.exists(self.build_dir):
            os.mkdir(self.build_dir)
        if not os.path.exists(build_lang_dir):
            os.mkdir(build_lang_dir)

        return build_lang_dir

    def _resolve_source_language(self, src_lang=None, config=None):
        # Override the default to ignore the configuration, as xml_lang isn't a variable
        # available in the config for AsciiDoc books
        return super(AsciiDocPublicanTransformer, self)._resolve_source_language(src_lang=src_lang, config=None)

    def build_format(self, src_lang, lang, build_format, config=None, additional_args=None, main_file=None, doctype=None):
        # Add a warning about using html-desktop
        if "html-desktop" in build_format:
            self.log.warn("WARNING: html-desktop is an unsupported format and only enabled for internal use,"
                          " so the output may not be as expected")

        # If no source language is passed, default to en-US
        src_lang = self._resolve_source_language(src_lang)

        # Make sure the build directory exists
        build_lang_dir = self._init_build_dir(src_lang)

        # Make sure we have a main file
        main_file = self._resolve_main_file(main_file)

        if self.convert_always or self.__last_converted_file != main_file:
            # Convert the AsciiDoc document to a Publican document
            if not self._convert_to_publican_doc(src_lang, build_lang_dir, config, additional_args, main_file, doctype):
                return False

        # Run any setup items before doing the build
        publican_cfg = os.path.join(self.build_dir, 'publican.cfg')
        build_formats = build_format.split(self.formats_sep)
        self._before_build_format(src_lang, lang, build_formats, publican_cfg, additional_args)

        # Copy translation files
        if lang != src_lang:
            self._copy_translation_files(self.adoc_source_dir, self.build_dir, [lang], group_langs=False)

        # Perform the Publican build
        exit_status = super(AsciiDocPublicanTransformer, self)._run_publican_build(lang, build_format, publican_cfg)

        # Run any post process after doing the build if it was successful
        self._after_build_format(exit_status, src_lang, lang, build_formats, publican_cfg, additional_args)

        return exit_status == 0

    def _convert_to_publican_doc(self, src_lang, build_dir, config=None, additional_args=None, main_file=None, doctype=None):
        # Convert the AsciiDoc content to DocBook XML
        if not self._build_docbook_src(main_file, build_dir, additional_args, doctype):
            return False

        # Get the main xml file
        (prefix, sep, suffix) = os.path.basename(main_file).rpartition('.')
        asciidoc_xml_file = os.path.join(build_dir, prefix + ".xml")

        # Do some adjustment/validation steps before parsing the XML
        self._before_xml_parse(asciidoc_xml_file)

        try:
            # Parse the XML content
            tree = utils.parse_xml(asciidoc_xml_file)
        except (XMLSyntaxError, XIncludeError) as e:
            self.log.error(e)
            self.log.error("Unable to parse the AsciiDoc built DocBook XML")
            return False

        # Create the publican directory
        if not self._build_publican_dir_from_asciidoc(src_lang, build_dir, main_file, tree, config, doctype):
            return False

        # Clean up the info file content
        self._clean_docbook_info(build_dir, tree)

        # Copy any static files (ie images)
        self._copy_static_files(tree, self.adoc_source_dir, build_dir)

        # Do additional steps after parsing the XML and creating the publican dir
        self._after_xml_parse(tree)

        # Save the updated XML
        with open(asciidoc_xml_file, 'w') as f:
            xml = etree.tostring(tree, encoding="UTF-8", xml_declaration=True, doctype=BOOK_DOCTYPE)
            f.write(xml)

        # Validate the AsciiDoc content is valid, since Publican validation is broken
        # TODO Figure out why RelaxNG validation doesn't work but DTD does.
        # if not self._validate_docbook_xml_relaxng(tree):
        #     raise InvalidInputException(asciidoc_xml_file + " fails to validate")
        self.log.verbose("Validating the DocBook XML to check cross references exist...")
        if not self._validate_docbook_xml_basic(build_dir, tree):
            raise InvalidInputException(asciidoc_xml_file + " fails to validate")

        self.__last_converted_file = main_file

        return True

    def _before_xml_parse(self, asciidoc_xml_file):
        """
        This method is called before the AsciiDoctor built XML is parsed. It will check for duplicate ids and also do some adjustments
        that may stop the xml from being parsed.

        :param asciidoc_xml_file: The path to the asciidoctor built xml file.
        """
        # TODO Try to find a way to do this on a line per line basis to reduce the memory footprint. The _convert_html_ids_to_xml function
        # will likely be the bigger issue since it needs to find content that maybe before or after the current line.
        with open(asciidoc_xml_file, "r") as f:
            xml_content = f.read()

        # Check that duplicate ids don't exist
        dup_ids = self._check_for_duplicate_ids(xml_content)
        if len(dup_ids) > 0:
            for dup_id in dup_ids:
                self.log.error("ID \"%s\" is duplicated in the source content", dup_id)
            raise InvalidInputException(asciidoc_xml_file + " fails to validate")

        # Asciidoc allows any id's, however we need valid XML id's, so attempt to fix some characters that are allowed for HTML
        xml_content = self._convert_html_ids_to_xml(xml_content)

        lines = xml_content.splitlines(True)
        xml_content = ""
        for line in lines:
            # Change the xl namespace back to xlink since it was renamed in AsciiDoctor 1.5.4 to workaround an internal issue
            line = line.replace("xmlns:xl=\"", "xmlns:xlink=\"").replace(" xl:href=\"", " xlink:href=\"")

            # Fix issues caused by the url detector in AsciiDoctor. Example broken string:
            # <link xlink:href="http://localhost:8180/odata4/&lt;vdb&gt;.&lt;version&gt;/&lt;model&gt;/&lt;view&gt">http://localhost:8180/odata4/&lt;vdb&gt;.&lt;version&gt;/&lt;model&gt;/&lt;view&gt</link>;
            if "<link" in line:
                line = line.replace("&gt\"", "&gt;\"").replace("&gt</link>;", "&gt;</link>")

            # Add the line back to the xml_content
            xml_content += line

        # Save the changes
        with open(asciidoc_xml_file, "w") as f:
            f.write(xml_content)

    def _after_xml_parse(self, xml_tree):
        """
        This method is called after the XML is parsed and the publican files have been created. It will adjust the XML ids to make them
        HTML4 compatible and fix up any misplaced image hrefs.

        :param xml_tree:            The parsed XML tree.
        """
        # Fix issues where AsciiDoctor doesn't convert xref's that use a file path correctly and therefore doesn't strip the path
        self._fix_uncoverted_xrefs_with_file_paths(xml_tree)

        # AsciiDoctor generates invalid colwidth attribute values, so fix them up
        self._fix_invalid_colwidths(xml_tree)

        # Fix up any relative images, that are not in the images directory
        self.log.verbose("Fixing misplaced image hrefs...")
        self._fix_misplaced_image_hrefs(xml_tree)

    def _resolve_main_file(self, main_file=None):
        """
        Resolves the main file to be used and raises an exception if one cannot be found.

        :param main_file: The main file to try use, if one is specified.
        :return: The absolute file path of the main file.
        :raises InvalidInputException: Raised when no main file exists.
        """
        if not main_file:
            for default_file in ("master.adoc", "master.asciidoc"):
                default_file = os.path.join(self.adoc_source_dir, default_file)
                if os.path.exists(default_file):
                    return default_file

            # If we reached here, then no main file exists
            raise InvalidInputException("There was no main file specified. Please specify a main build file and try again.")

        return os.path.abspath(main_file)

    def _build_docbook_src(self, main_src_file, build_lang_dir, additional_args=None, doctype=None):
        # Build the command
        asciidoc_cmd = ['asciidoctor', '-S', 'safe', '-r', 'asciidoctor-diagram', '-b', 'docbook', '-a', 'nolang', '-a', 'docinfo2',
                        '-a', 'noxmlns', '-a', 'idprefix=_', '-a', 'outdir=' + build_lang_dir]

        # Setup the preface title
        preface = get_attribute_value(main_src_file, "preface-title")
        if preface is None:
            asciidoc_cmd.extend(['-a', 'preface-title=Preface'])

        # Setup the doctype
        if doctype == 'article':
            asciidoc_cmd.extend(['-d', 'article'])
        else:
            asciidoc_cmd.extend(['-d', 'book'])

        # Add any additional arguments
        if additional_args:
            asciidoc_cmd.extend(utils.split_additional_args(additional_args))

        asciidoc_cmd.extend(['-D', build_lang_dir, main_src_file])

        # Execute it
        self.log.info("Transforming the AsciiDoc content to DocBook XML...")
        try:
            # AsciiDoctor sometimes doesn't return a non zero exit code when an error occurs, so check the output
            try:
                output = subprocess.check_output(asciidoc_cmd, cwd=self.adoc_source_dir, stderr=subprocess.STDOUT)
            except AttributeError:
                import aura.compat
                output = aura.compat.check_output(asciidoc_cmd, cwd=self.adoc_source_dir, stderr=subprocess.STDOUT)
            if output is not None and len(output) > 0:
                output = self._correct_asciidoctor_warnings(output)
                # Apply ANSI colouring to the asciidoctor output
                output_lines = output.strip().split("\n")
                for line in output_lines:
                    if "WARNING" in line:
                        click.secho(line, fg="yellow")
                    elif "ERROR" in line:
                        click.secho(line, fg="red", bold=True)
                    else:
                        print(line)
                if re.search("^asciidoctor: ERROR.*", output, flags=re.MULTILINE):
                    return False
            self.log.verbose("Successfully transformed the AsciiDoc content.")
        except subprocess.CalledProcessError as e:
            if e.output is not None:
                print(e.output, end="")
            return False

        # Add the doctype
        (prefix, sep, suffix) = os.path.basename(main_src_file).rpartition('.')
        asciidoc_xml_file = os.path.join(build_lang_dir, prefix + ".xml")
        for line in fileinput.input([asciidoc_xml_file], inplace=True):
            if "<?xml" in line:
                print(line + BOOK_DOCTYPE)
            else:
                print(line.replace("\n", ""))

        return True

    def _correct_asciidoctor_warnings(self, output):
        """Changes certain AsciiDoctor warnings to errors, as it makes little sense for our use case, for them to be warnings."""
        output = output.decode('utf-8')
        output_lines = output.split("\n")
        rv = None
        for line in output_lines:
            # Fix missing include file CCS-94
            if "include file not found:" in line:
                line = line.replace("WARNING", "ERROR")
            if "has illegal reference to ancestor of jail" in line:
                line = line.replace("WARNING", "ERROR").replace(", auto-recovering", "")

            if rv is None:
                rv = line
            else:
                rv += "\n" + line

        return rv

    def _build_publican_dir_from_asciidoc(self, src_lang, build_lang_dir, main_file, tree, config=None, doctype=None):
        """
        Builds up a Publican directory with all the additional resources required to build with Publican from an AsciiDoctor built
        DocBook XML file.

        :param src_lang:       The source language.
        :param build_lang_dir: The language directory of the build.
        :param main_file:      The AsciiDoctor built main XML file.
        :param tree:           The AsciiDoctor built DocBook XML tree.
        :param config:
        :param doctype:
        :return:               True if the publican directory was successfully setup, otherwise false.
        """
        # Get the main xml file
        (prefix, sep, suffix) = os.path.basename(main_file).rpartition('.')
        asciidoc_xml_file = os.path.join(build_lang_dir, prefix + ".xml")
        docinfo_filename = prefix + "-docinfo.xml"

        # Validate the docinfo and get title/version/product
        def callback(tag):
            self.log.error("<%s> is mandatory metadata and has not been defined in the %s file.", tag, docinfo_filename)

        if not validate_xml_info_from_tree(tree, callback):
            sys.exit(-1)

        # Get the product, version and title. Then clean the values for use in publican create
        # and the publican.cfg 'product', 'version' and 'docname' properties
        title, product, version = publican_utils.get_npv_from_xml(tree)
        cleaned_title = clean_title(title)
        cleaned_product = clean_product(product)
        cleaned_version = clean_version(version)

        # Figure the publican directory that will be created
        escaped_title = cleaned_title.replace(" ", "_")
        publican_dir = os.path.join(self.build_dir, escaped_title)

        # Make sure the publican tmp dir doesn't exist and if so remove it
        if os.path.exists(publican_dir):
            shutil.rmtree(publican_dir)

        # Run publican to create the core files
        publican_cmd = ['publican', 'create', '--name', cleaned_title, '--product', cleaned_product, '--version', cleaned_version,
                        '--brand', self.brand, '--lang', src_lang, '--dtdver', '5.0', '--quiet']

        # Add the doctype
        if doctype == "article":
            publican_cmd.extend(['--type', 'article'])
        else:
            publican_cmd.extend(['--type', 'book'])

        # Ensure the correct language environment variable, as Publican ignores the source lang and uses LANG if set
        env = os.environ.copy()
        env["LANG"] = src_lang.replace("-", "_") + ".utf8"

        exit_status = subprocess.call(publican_cmd, cwd=self.build_dir, env=env)
        if exit_status != 0:
            return False

        # Remove the Book_Info.xml, it'll be replaced later with the asciidoc files. Also remove some other un-used files.
        publican_lang_dir = os.path.join(publican_dir, src_lang)
        for filename in ("Chapter.xml", "Book_Info.xml", escaped_title + ".xml", escaped_title + ".ent", "Preface.xml"):
            file_path = os.path.join(publican_lang_dir, filename)
            if os.path.exists(file_path):
                os.remove(file_path)

        # Move the publican files up one directory
        files = os.listdir(publican_dir)
        for sub_file in files:
            utils.move(os.path.join(publican_dir, sub_file), self.build_dir)
        shutil.rmtree(publican_dir)

        # Update the entity file references
        old_entity_file = escaped_title + ".ent"
        new_entity_file = prefix + ".ent"
        for line in fileinput.input([os.path.join(build_lang_dir, "Author_Group.xml"),
                                     os.path.join(build_lang_dir, "Revision_History.xml")],
                                    inplace=True):
            line = line.decode("UTF-8")
            if old_entity_file in line:
                line = line.replace(old_entity_file, new_entity_file)
            print(line.replace("\n", "").encode("UTF-8"))

        # Build the book entity file
        ent_file = os.path.join(build_lang_dir, new_entity_file)
        entity_txt = self._build_entity_file(asciidoc_xml_file)
        with open(ent_file, 'w') as f:
            f.write(entity_txt)

        # Set the main file in publican.cfg
        publican_cfg = os.path.join(self.build_dir, 'publican.cfg')
        config_data = ""
        with open(publican_cfg, 'a') as f:
            # Check to see if a custom configuration file was specified
            if config and os.path.isfile(config):
                with open(config, 'r') as config_file:
                    config_data = self.__clean_user_config(config_file.read())
                    f.write(config_data + "\n")

            # Make sure the product doesn't start with a decimal otherwise hidden files will be created
            # and also Akamai doesn't support files/dirs starting with a decimal. CCS-1056
            # if product.startswith(".") and "product:" not in config_data:
            #     f.write('product: "' + product.lstrip(".") + '"\n')

            # Set the cleaned product/version value if the user didn't define one
            if "product:" not in config_data:
                f.write('product: "' + cleaned_product + '"\n')
            if "version:" not in config_data:
                f.write('version: "' + cleaned_version + '"\n')
            if "docname:" not in config_data:
                f.write('docname: "' + cleaned_title + '"\n')

            # Set the default chunking section depth to "0" if the user didn't define one
            if "chunk_section_depth" not in config_data:
                f.write('chunk_section_depth: 0\n')

            # Add the overrides to the publican configuration
            f.write('chunk_first: 0\n' +
                    'mainfile: "' + prefix + '"\n' +
                    'info_file: "' + prefix + '.xml"\n')

        return True

    def __clean_user_config(self, config):
        # Remove any commented out sections
        cleaned_config = re.sub("^#.*\n", "", config, flags=re.MULTILINE)
        # A user may try to override some crucial publican configuration, so strip it out.
        cleaned_config = re.sub("^(xml_lang|brand|mainfile|chunk_first|info_file|type|dtd_ver)\s*:.*\n", "", cleaned_config,
                                flags=re.IGNORECASE | re.MULTILINE)
        return cleaned_config.strip()

    def _build_entity_file(self, asciidoc_xml_file):
        """
        Builds up the text for the entity file.

        :param asciidoc_xml_file:
        :return:
        """
        try:
            # Parse the XML content
            parser = etree.XMLParser(load_dtd=True, resolve_entities=False)
            tree = utils.parse_xml(asciidoc_xml_file, parser)
        except (XMLSyntaxError, XIncludeError) as e:
            self.log.error(e)
            self.log.error("Unable to parse the AsciiDoc built DocBook XML")
            return False

        # Get the non escaped title/product/version
        title, product, version = publican_utils.get_npv_from_xml(tree)

        entity = '<!ENTITY PRODUCT "' + product + '">\n' + \
                 '<!ENTITY BOOKID "' + title + '">\n' + \
                 '<!ENTITY YEAR "' + str(date.today().year) + '">\n' + \
                 '<!ENTITY HOLDER "Red Hat, Inc">'
        return entity.encode('UTF-8')

    def _clean_docbook_info(self, build_lang_dir, tree):
        """
        Cleans up the docbook info, so that Author Group and Revision History entries are moved over to the Publican supported
        Author_Group.xml and Revision_History.xml files.

        :param build_lang_dir: The language directory of the build.
        :param tree:           The AsciiDoctor built DocBook XML tree.
        """
        # Find the info content
        xml_root = tree.getroot()
        info_ele = xml_root.find("./" + LXML_DOCBOOK_NS + "info")

        # Remove any duplicate titles
        count = 0
        for child_ele in info_ele.findall("./" + LXML_DOCBOOK_NS + 'title'):
            if count != 0:
                info_ele.remove(child_ele)
            count += 1

        # Move the subtitle, under the title to make it valid
        title_ele = info_ele.find("./" + LXML_DOCBOOK_NS + "title")
        subtitle_ele = info_ele.find("./" + LXML_DOCBOOK_NS + "subtitle")
        if subtitle_ele is not None and title_ele is not None:
            title_ele.addnext(subtitle_ele)

        # Copy author information from docinfo to Author_Group.xml
        migrate_authors(info_ele, os.path.join(build_lang_dir, "Author_Group.xml"))

        # Move the revision history, to Revision_History.xml
        migrate_revisions(info_ele, os.path.join(build_lang_dir, "Revision_History.xml"))

    def _copy_static_files(self, xmltree, source, dest):
        """
        Copies static resources (ie images, files) over to the relevant build directory.

        :param source:   The source location of the images/asciidoc content.
        :param dest:     The destination location of the built content.
        :param xmltree:  The AsciiDoctor built DocBook XML tree.
        """
        files_dir = os.path.join(source, "files")

        # Find all the images in the xml tree
        img_eles = self._get_images_from_xml_ele(xmltree.getroot())
        img_paths = []
        for img_ele in img_eles:
            img_path = img_ele.get("fileref")
            if not URL_OR_COMMON_CONTENT_RE.search(img_path):
                img_paths.append(img_path)

        # Make sure the build images directory exists
        build_images_dir = os.path.join(dest, 'images')
        if not os.path.exists(build_images_dir):
            os.makedirs(build_images_dir)

        # Copy the images
        for img_path in img_paths:
            abs_img_src = os.path.join(source, img_path)
            img_dest = os.path.join(build_images_dir, re.sub(r"^images(\\|/)", "", img_path))
            img_dest_dir = os.path.dirname(img_dest)

            # Make sure the image dest dir exists
            if not os.path.exists(img_dest_dir):
                os.makedirs(img_dest_dir)

            # Handle the possibility that the image was generated by asciidoctor-diagram. If so it'll be in the dest dir
            if not os.path.isfile(abs_img_src):
                abs_img_src = os.path.join(dest, img_path)

            # Copy the image
            if os.path.exists(abs_img_src) and abs_img_src != img_dest:
                shutil.copy2(abs_img_src, img_dest)

        # Copy the files
        if os.path.exists(files_dir):
            build_files_dir = os.path.join(dest, "files")
            utils.copy_dir_contents(files_dir, build_files_dir)

    def _fix_misplaced_image_hrefs(self, xmltree):
        """
        Fixes images references that are placed outside of an images folder in the source content.

        :param xmltree: The AsciiDoctor built DocBook XML tree.
        """
        image_eles = self._get_images_from_xml_ele(xmltree.getroot())

        for image_ele in image_eles:
            image_src = image_ele.get('fileref')

            # Skip any images that aren't local files or any that are in the Common_Content/images directory
            if not URL_OR_IMAGES_PATH_RE.match(image_src):
                image_ele.set('fileref', urljoin("images/", image_src))

    def _fix_invalid_colwidths(self, xmltree):
        """
        DocBook only allows integers for proportional colwidth values, however AsciiDoctor 1.5.4+ generates floats. This function will find
        all invalid values and round them so that they are an integer.

        :param xmltree: The parsed XML tree.
        """
        # Find all the colspec elements
        colspec_eles = xmltree.getroot().findall(".//" + LXML_DOCBOOK_NS + "colspec")

        # Adjust any colspecs that are in decimal format
        for colspec_ele in colspec_eles:
            colwidth = colspec_ele.get("colwidth")
            if INVALID_COLWIDTH_RE.match(colwidth):
                new_value = int(round(float(colwidth.rstrip("*"))))
                colspec_ele.set("colwidth", str(new_value) + "*")

    def _get_images_from_xml_ele(self, xml_ele):
        """
        Gets all the image elements that are children of the passed XML element.

        :param xml_ele: The xml element to look for images in.
        :return: A list of xml elements that represent images
        """
        return xml_ele.findall(".//" + LXML_DOCBOOK_NS + "imagedata")

    def _fix_uncoverted_xrefs_with_file_paths(self, xml_tree):
        """
        Looks over the XML to see if AsciiDoctor failed to convert any xrefs because of the path and if it finds any it converts them into
        a <xref> or <link> as it should have been done by AsciiDoctor.

        Examples:

        * <link xlink:href="../ch-mtu.xml#sec-mtu">Test</link>
        * <link xlink:href="../ch-mtu.xml#sec-mtu">../ch-mtu.xml</link>

        :param xml_tree: The parsed XML tree.
        """
        # Find all the links
        xmlroot = xml_tree.getroot()
        links = xmlroot.findall(".//" + LXML_DOCBOOK_NS + "link")

        for link in links:
            href = link.get("{http://www.w3.org/1999/xlink}href")
            if href is not None:
                re_match = UNCONVERTED_XREF_LINK_HREF_RE.match(href)
                if re_match is not None and URL_RE.search(href) is None:
                    file_path = re_match.group(1)
                    ele_id = re_match.group(2)
                    del link.attrib["{http://www.w3.org/1999/xlink}href"]
                    link.set("linkend", ele_id)
                    if file_path == link.text:
                        link.tag = "{" + DOCBOOK_NS + "}xref"
                        link.text = None

    def _check_for_duplicate_ids(self, xml_content):
        """
        Checks for duplicate XML ids and returns any that are duplicated

        :param xml_content: The build xml file content, to check against.
        :return: A list of duplicated xml ids.
        """
        ids = ID_RE.finditer(xml_content)
        invalid_xml_ids = []
        valid_xml_ids = []
        for xml_id in ids:
            xml_id = xml_id.group(1)
            if xml_id in valid_xml_ids:
                invalid_xml_ids.append(xml_id)
            else:
                valid_xml_ids.append(xml_id)

        return invalid_xml_ids

    def _convert_html_ids_to_xml(self, xml_content):
        """
        Converts HTML ids to valid XML ids.

        :param xml_content: The build xml file content, to replace the HTML ids for.
        :return: The xml content with the HTML ids replaced.
        """
        # Find all the invalid ids
        ids = ID_RE.finditer(xml_content)
        invalid_xml_ids = []
        for xml_id in ids:
            if ":" in xml_id.group(1):
                invalid_xml_ids.append(xml_id)

        # Replace the invalid xml ids and any references to it.
        for invalid_xml_id in invalid_xml_ids:
            text = invalid_xml_id.group(0)
            id_val = invalid_xml_id.group(1)
            fixed_id_val = re.sub(":+", "-", id_val)

            xml_content = xml_content.replace(text, "xml:id=\"" + fixed_id_val + "\"")\
                .replace("linkend=\"" + id_val + "\"", "linkend=\"" + fixed_id_val + "\"")\
                .replace("endterm=\"" + id_val + "\"", "endterm=\"" + fixed_id_val + "\"")

        return xml_content

    def build_xml_feed(self, doc_uuid, src_lang, lang, config=None, additional_args=None, additional_formats=None, main_file=None,
                       doctype=None, archive=False):
        # Make sure we have a main file
        main_file = self._resolve_main_file(main_file)

        # Clean any previous build files
        self.clean_build_files()

        return self._build_xml_feed(doc_uuid, src_lang, lang, config, additional_args, additional_formats, main_file, doctype, archive)

    def _after_build_xml_feed(self, doc_uuid, src_lang, lang, feed_tree, config, additional_formats):
        # Don't pass on the custom configuration to the post build process, as it is merged into the default config in the pre steps.
        return super(AsciiDocPublicanTransformer, self)._after_build_xml_feed(doc_uuid, src_lang, lang, feed_tree, None, additional_formats)

    def _generate_xml_feed(self, doc_uuid, src_lang, lang, config):
        # Don't pass on the custom configuration to the post build process, as it is merged into the default config in the pre steps.
        return super(AsciiDocPublicanTransformer, self)._generate_xml_feed(doc_uuid, src_lang, lang, None)

    def build_translation_files(self, langs, config=None, main_file=None, pot_only=False, po_only=False, src_lang=None, doctype=None):
        # If no source language is passed, default to en-US
        src_lang = self._resolve_source_language(src_lang)

        # Make sure we have a main file
        main_file = self._resolve_main_file(main_file)

        # Build the DocBook XML files
        if not self.build_format(src_lang, src_lang, "xml", config, None, main_file, doctype):
            return False

        if not super(AsciiDocPublicanTransformer, self).build_translation_files(langs, config, pot_only=pot_only, po_only=po_only):
            return False

        # Clean out the revision from the publican generated revision histories
        if not pot_only:
            self._clean_po_revision_history(langs)

        # Move the files
        self._copy_translation_files(self.build_dir, self.adoc_source_dir, langs, pot_only, po_only)

        return True

    def _clean_po_revision_history(self, langs):
        """
        Clean up the publican generated revision histories.

        :param langs: The po langs to be cleaned up.
        """
        for lang in langs:
            po_src_dir = os.path.join(self.build_dir, lang)
            rev_history = os.path.join(po_src_dir, "Revision_History.xml")

            try:
                # Parse the XML content
                tree = utils.parse_xml(rev_history)
            except (XMLSyntaxError, XIncludeError):
                continue

            revision = tree.find(".//" + LXML_DOCBOOK_NS + "revision")
            if revision is not None:
                revision.getparent().remove(revision)

            # Save the updated XML
            with open(rev_history, 'w') as f:
                rev_history_doctype = BOOK_DOCTYPE.replace("DOCTYPE book", "DOCTYPE appendix")
                xml = etree.tostring(tree, encoding="UTF-8", xml_declaration=True, doctype=rev_history_doctype)
                f.write(xml)

    def _copy_translation_files(self, source, dest, langs, pot_only=False, po_only=False, group_langs=True):
        """
        Copy the translation files (ie POT/PO files) from a source directory to a destination directory.

        :param source:      The source directory to find the pot/po files.
        :param dest:        The destination directory to place the pot/po files.
        :param langs:       The po langs to copy.
        :param pot_only:    Whether or not the pot only files should be copied.
        :param po_only:     Whether or not the po only files should be copied.
        :param group_langs: Whether or not the po files should be group under a po directory.
        """
        if not po_only:
            pot_src_dir = os.path.join(source, "pot")
            pot_dst_dir = os.path.join(dest, "pot")

            # Clean the pot directory
            if os.path.exists(pot_dst_dir):
                shutil.rmtree(pot_dst_dir)

            # Copy the files
            if os.path.exists(pot_src_dir):
                shutil.copytree(pot_src_dir, pot_dst_dir)
        if not pot_only:
            if group_langs:
                po_dst_dir = os.path.join(dest, "po")
                po_src_dir = source

                # Clean the po directory if it exists
                if os.path.exists(po_dst_dir):
                    shutil.rmtree(po_dst_dir)
                os.mkdir(po_dst_dir)
            else:
                po_dst_dir = dest
                po_src_dir = os.path.join(source, "po")

            # Copy each language
            for lang in langs:
                po_lang_src_dir = os.path.join(po_src_dir, lang)
                po_lang_dst_dir = os.path.join(po_dst_dir, lang)

                # Clean the po lang dest directory
                if os.path.exists(po_lang_dst_dir):
                    shutil.rmtree(po_lang_dst_dir)

                # Copy the files
                if os.path.exists(po_lang_src_dir):
                    shutil.copytree(po_lang_src_dir, po_lang_dst_dir)

    def clean_build_files(self, config=None):
        # Delete the build directory
        if os.path.exists(self.build_dir):
            shutil.rmtree(self.build_dir)

        return True

    def _validate_docbook_xml_basic(self, build_lang_dir, tree):
        """
        Perform some basic validation on the docbook xml produced to ensure authors and links will be valid.

        :param build_lang_dir: The language directory of the build.
        :type build_lang_dir: str
        :param tree: The LXML Tree that was parsed from the built DocBook XML.
        :type tree: etree._ElementTree
        :return: True if the DocBook XML is valid, otherwise false.
        :rtype: bool
        """
        error = False

        # Check any cross reference ids
        if not self._validate_docbook_idrefs(tree):
            error = True

        # Check that the Author_Group.xml is valid for publican
        if not self._validate_docbook_author_group(build_lang_dir):
            error = True

        return not error

    def _validate_docbook_xml_relaxng(self, tree):
        """
        Validates that the DocBook XML passes the DocBook 5.0 RelaxNG schema. Note that this doesn't ensure the additional Schematron rules,
        however that is because the DocBook 5.0 content is generated by AsciiDoctor and as such should never fail any Schematron rules.

        :param tree: The LXML Tree that was parsed from the built DocBook XML.
        :type tree: etree._ElementTree
        :return: True if the tree is valid, otherwise False.
        :rtype: bool
        """
        if os.path.exists("/usr/share/xml/docbook5/schema/rng/5.0/docbookxi.rng"):
            rng_tree = etree.parse("/usr/share/xml/docbook5/schema/rng/5.0/docbookxi.rng")
        else:
            res = requests.get("http://docbook.org/xml/5.0/rng/docbook.rng")
            rng_tree = etree.parse(res.content)
        relaxng = etree.RelaxNG(etree=rng_tree)

        if relaxng.validate(tree):
            return True
        else:
            for error in relaxng.error_log:
                self.log.error("line %s: Relax-NG validity error : %s", error.line, error.message.encode('UTF-8'))

            # lxml has a bug where it doesn't report on invalid IDREFs, so manually find them and report them
            self._validate_docbook_idrefs(tree)

            return False

    def _validate_docbook_idrefs(self, tree):
        error = False
        xmlroot = tree.getroot()
        id_eles = xmlroot.findall(".//*[@xml:id]", namespaces={'xml': XML_NS})
        ids = [ele.get(LXML_XML_NS + "id") for ele in id_eles]

        # Validate the linkend references
        linkend_eles = xmlroot.findall(".//*[@linkend]")
        for linkend_ele in linkend_eles:
            id_val = linkend_ele.get("linkend")
            if id_val not in ids:
                error = True
                self.log.error("Unknown ID or title \"%s\", used as an internal cross reference", id_val)

        # Validate the endterm references
        endterm_eles = xmlroot.findall(".//*[@endterm]")
        for endterm_ele in endterm_eles:
            id_val = endterm_ele.get("endterm")
            if id_val not in ids:
                error = True
                self.log.error("Unknown ID or title \"%s\", used as an internal cross reference", id_val)

        return not error

    def _validate_docbook_author_group(self, build_lang_dir):
        error = False
        author_group_file = os.path.join(build_lang_dir, "Author_Group.xml")

        try:
            # Parse the author group XML
            tree = utils.parse_xml(author_group_file)

            # If an author exists, check that a firstname and surname have been included
            authors = tree.findall(".//" + LXML_DOCBOOK_NS + "author")
            for author in authors:
                if author.find(".//" + LXML_DOCBOOK_NS + "firstname") is None:
                    self.log.error("Author's first name is missing, however it is a required attribute")
                    error = True
                if author.find(".//" + LXML_DOCBOOK_NS + "surname") is None:
                    self.log.error("Author's surname is missing, however it is a required attribute")
                    error = True
        except (XMLSyntaxError, XIncludeError) as e:
            self.log.error(e)
            self.log.error("Unable to parse the AsciiDoc built DocBook XML")
            return False

        return not error

    def _fix_titleless_initial_content(self, tree):
        xmlroot = tree.getroot()

        # Get all the prefaces
        prefaces = xmlroot.findall(".//" + LXML_DOCBOOK_NS + "preface")
        for preface in prefaces:
            title_ele = preface.find("./" + LXML_DOCBOOK_NS + "title")
            if title_ele.text == "" or title_ele.text is None:
                title_ele.text = "Preface"

    def _load_page_id_overrides(self, overrides_filepath):
        overrides_filepath = os.path.join(self.adoc_source_dir, os.path.basename(overrides_filepath))
        return super(AsciiDocPublicanTransformer, self)._load_page_id_overrides(overrides_filepath)

    def get_doc_id(self, config=None, lang=None):
        # Don't pass the config, as we merge the config during the build into the default publican.cfg
        return super(AsciiDocPublicanTransformer, self).get_doc_id(config=None, lang=lang)

    def get_npv(self, config=None):
        # Don't pass the config, as we merge the config during the build into the default publican.cfg
        return super(AsciiDocPublicanTransformer, self).get_npv(config=None)
