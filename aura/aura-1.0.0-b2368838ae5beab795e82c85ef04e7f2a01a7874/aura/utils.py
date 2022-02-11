import errno
import hashlib
import logging
import os
import re
import shutil
import tarfile
import tempfile

from lxml import etree, html, objectify
import num2words

from aura import compat
from aura.compat import unicode, urllib, RawConfigParser

log = logging.getLogger("aura.utils")
XML_ID_CLEAN_RE = re.compile(r"[^\w.-]", re.UNICODE)


def save_config(config, filename, mode=0o644):
    """
    Save any configuration settings in a ConfigParser object to file.

    :param config: The ConfigParser object to save.
    :param filename: The path/filename of where to save the configuration to.
    :param mode: The permissions mode to save as.
    :return:
    """
    # Make sure the parent directory exists
    parent_dir = os.path.dirname(filename)
    if not os.path.exists(parent_dir):
        os.makedirs(parent_dir, 0o700)

    umask = 0o777 - mode
    old_umask = os.umask(umask)
    try:
        with open(filename, 'w', mode) as f:
            config.write(f)
    finally:
        os.umask(old_umask)


def find_file_for_type(dirpath, extension, prefix=None):
    """Finds the first file that uses the extension and returns the filename"""
    for filename in os.listdir(dirpath):
        if filename.endswith("." + extension) and (prefix is None or filename.startswith(prefix)):
            return filename

    return None


def clean_for_rpm_name(val, remove_dups=False):
    """Removes spaces and other key characters so a value can be used in a rpm name"""
    if val is None or len(val) == 0:
        return val
    else:
        # Note: [0-9a-zA-Z_-.+] should be the only characters allowed in an rpm name.
        rv = re.sub("[^0-9a-zA-Z _\-.+]+", "", replace_nbsp(val))
        # Replace spaces with an underscore
        rv = re.sub("\s", "_", rv)
        # Remove any duplicate underscores if required
        if remove_dups:
            rv = re.sub("__+", "_", rv)
        return rv


def replace_nbsp(val):
    """Replaces non breaking spaces with a regular space"""
    if val is not None:
        # Check if the string is unicode
        if isinstance(val, unicode):
            return val.replace(u'\xa0', ' ')
        else:
            return val.replace('\xc2\xa0', ' ')
    else:
        return None


def find_element_value(xml_ele, name, default=None):
    """
    Finds a child element with the specified name and returns the text based value. If the element cannot be found,
    the default value is returned.
    """
    # Get the title/product/version from the info xml
    found_ele = xml_ele.find(".//" + get_ns_tag_name(xml_ele, name))
    return default if found_ele is None else get_element_text(found_ele).strip()


def get_element_text(ele):
    return etree.tostring(ele, encoding='UTF-8', method='text').decode("UTF-8")


def get_element_xml(ele):
    return etree.tostring(ele, encoding='UTF-8', method='xml').decode("UTF-8")


def create_xml_id(val):
    # Replace spaces with underscores
    xml_id = re.sub("\s+", "_", val)

    # Remove any leading hyphens, underscores or decimals
    xml_id = re.sub("^[_.-]+", "", xml_id)

    # If it now starts with a number, change the number to a word
    if re.match("^[0-9]+", xml_id):
        def convert_num_to_word(match):
            num = int(match.group(0))
            return num2words.num2words(num)

        xml_id = re.sub("^[0-9]+", convert_num_to_word, xml_id)

    # Remove any invalid chars
    xml_id = XML_ID_CLEAN_RE.sub("", xml_id)

    return xml_id


def read_bytes_from_file(filename, chunksize=8192):
    """
    Reads a file into memory and returns the content using a Generator.

    :param filename: The file to read from.
    :param chunksize: The buffer size to use when reading.
    :return: A generator that contains the file contents.
    """
    with open(filename, "rb") as f:
        chunk = f.read(chunksize)
        while chunk:
            for b in chunk:
                yield b
            chunk = f.read(chunksize)


def remove_tar_gz_files(tar_file, files):
    """
    Removes a list of files from a tar.gz file, by recreating the file and skipping any files in the input list.

    :param tar_file: The tar file to remove files from
    :param files:
    :return:
    """
    # Open the source file
    source = tarfile.open(tar_file, mode='r')
    # Create a temporary dest file
    fd, tmp = tempfile.mkstemp()
    tmp_file = os.fdopen(fd, "w")
    dest = tarfile.open(fileobj=tmp_file, mode='w|gz')

    # Copy all resources, except the file to remove
    for member in source:
        if not (member.isreg() and member.name in files):
            dest.addfile(member, source.extractfile(member))

    # Close the streams
    dest.close()
    source.close()
    tmp_file.close()

    # Copy the temp file to the original and delete the tmp
    shutil.copy(tmp, tar_file)
    os.remove(tmp)


def add_tar_gz_files(tar_file, files, path=""):
    """
    Adds a list of files to the "path" directory in the tar.gz file, by recreating the file to allow compression.

    :param tar_file: The tar file to add files ti
    :param files:
    :param path: The path in the tar file to add the files to.
    :return:
    """
    # Open the source file
    source = tarfile.open(tar_file, mode='r')
    # Create a temporary dest file
    fd, tmp = tempfile.mkstemp()
    tmp_file = os.fdopen(fd, "w")
    dest = tarfile.open(fileobj=tmp_file, mode='w|gz')

    # Copy all current resources
    for member in source:
        dest.addfile(member, source.extractfile(member))

    # Add the new files
    for new_file in files:
        dest.add(new_file, os.path.join(path, os.path.basename(new_file)))

    # Close the streams
    dest.close()
    source.close()
    tmp_file.close()

    # Copy the temp file to the original and delete the tmp
    shutil.copy(tmp, tar_file)
    os.remove(tmp)


# Improved version of shutils.move, to handle merging. See
def move(src, dst, overwrite=None):
    if os.path.exists(dst):
        # Fix the destination when moving files
        if os.path.isdir(dst):
            dst = _real_dest(src, dst)

        if os.path.isdir(src):
            if not os.path.exists(dst):
                os.makedirs(dst)

            for item in os.listdir(src):
                item_path = os.path.join(src, item)
                move(item_path, dst)
            os.rmdir(src)
        else:
            if os.path.isfile(dst):
                if not overwrite or overwrite(dst):
                    os.remove(dst)
                    shutil.move(src, dst)
            else:
                shutil.move(src, dst)
    else:
        shutil.move(src, dst)


def _real_dest(src, dst):
    real_dest = os.path.basename(src.rstrip(os.path.sep))
    return os.path.join(dst, real_dest)


def read_xml_doctype(xml_file):
    """
    Reads and returns the DOCTYPE content for an XML file.

    :param xml_file:
    :return:
    """
    doctype = None
    reading_doctype = False
    with open(xml_file, 'r') as f:
        for line in f:
            if line.strip().startswith("<!DOCTYPE"):
                reading_doctype = True
                doctype = ""
            elif reading_doctype and "]>" in line:
                doctype += line.split("]>")[0] + "]>"
                break

            if reading_doctype:
                doctype += line

    return doctype


def fix_empty_html_elements(xml_ele):
    """
    Fixes up any self closing html elements, that cannot be empty in HTML, by adding a comment.

    :param xml_ele:
    :return:
    """
    valid_empty_eles = ['area', 'base', 'basefont', 'br', 'hr', 'input', 'img', 'link', 'meta']

    # Fix up anchors, so that they don't self close as that is invalid html
    for empty_ele in xml_ele.xpath(".//*[not(text())][not(node())]"):
        if len(empty_ele) == 0 and empty_ele.tag not in valid_empty_eles:
            empty_ele.append(etree.Comment("Empty"))


def wrap_children_in_cdata(xml_ele):
    # Convert each child element to a string and remove the element from the parent
    text = xml_ele.text if xml_ele.text is not None else ""
    for child in xml_ele.iterchildren():
        text += etree.tostring(child, encoding="UTF-8")
        xml_ele.remove(child)

    # Set the text of the xml element as the converted CDATA
    if not isinstance(text, unicode):
        text = unicode(text, 'UTF-8')
    xml_ele.text = etree.CDATA(text)


def get_ns_tag_name(root_ele, tag_name):
    """
    Returns the tag name with the default XML namespace prefixed. This is helpful where the tag name has to be used in find or findall.

    Example:

    <book xmlns="http://docbook.org/ns/docbook">
      <info/>
    </book>

    the return value if the tag_name was "info" would be {http://docbook.org/ns/docbook}info

    :param root_ele: The root element to get the default namespace from.
    :type root_ele: etree._Element
    :param tag_name: The local-name of the tag
    :type tag_name: str
    :return: The namespace plus local-name of the tag if a default namespace exists, otherwise just the tag name as is.
    """
    if None in root_ele.nsmap:
        return "{" + root_ele.nsmap[None] + "}" + tag_name
    else:
        return tag_name


def copy_dir_contents(src_dir, dest_dir):
    """
    Recursively copies all files and sub directories from a source directory to a destination directory.

    Note: This function is similar to shutil.copytree, except that it only copies the content inside src_dir and not src_dir itself.

    :param src_dir:  The source directory to copy from.
    :param dest_dir: The destination directory to copy to.
    """
    # Make sure the destination directory exists
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)

    files = os.listdir(src_dir)
    for filename in files:
        abs_file = os.path.join(src_dir, filename)
        abs_dest_file = os.path.join(dest_dir, filename)
        if os.path.isdir(abs_file):
            if os.path.exists(abs_dest_file):
                copy_dir_contents(abs_file, abs_dest_file)
            else:
                shutil.copytree(abs_file, os.path.join(dest_dir, filename))
        else:
            shutil.copy2(abs_file, dest_dir)


def get_git_latest_commit_sha(git_dir):
    """
    Get the latest commit SHA1 from a directory under git control.

    :param git_dir: A directory under git control.
    :return: The hexadecimal representation of the latest commit
    :raises git.InvalidGitRepositoryError: Raised when the git_dir isn't inside of a git repository.
    """
    # Create repository object and look up the current head commit
    repo = compat.init_git_repo(git_dir)
    return repo.head.commit.hexsha


def backup_and_write_file(filepath, content, suffix=".backup"):
    """
    Backups a file and then overwrites the file using the content provided.

    :param filepath: The path to the file to backup and write to.
    :param content: The content to write to the file.
    :param suffix: The backup files suffix.
    :return: Returns the path to the backed up file.
    """
    # Backup the file
    backup_file = filepath + suffix
    log.debug("Backing up %s to %s", filepath, backup_file)
    shutil.copy2(filepath, backup_file)

    # Save/overwrite the content
    with open(filepath, 'w') as f:
        f.write(content)

    return backup_file


def which(program):
    """
    Find the full path of a program if it exists on the system.

    :param program: The name of the progam to find.
    :return: The path of the program if it exists, other None
    """
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None


def clean_path_for_akamai_netstorage(path):
    """
    Cleans a file/url path to remove any leading decimals because Akamai NetStorage doesn't support them. CCS-1056

    :param path: The path to be cleaned.
    :return: The cleaned path with any path components having been stripped of leading decimals.
    """
    fixed_path_components = []
    for path_component in path.split("/"):
        fixed_path_components.append(path_component.lstrip("."))
    return "/".join(fixed_path_components)


def split_additional_args(additional_args, delimiter=" ", escape_char="\\"):
    """
    Splits additional arguments that are passed as a single string

    :param additional_args: The additional arguments string
    :param delimiter: The character to use when splitting the arguments
    :return: A list of the additional arguments, broken up using the delimiter
    """
    additional_args = re.split(r'(?<!' + re.escape(escape_char) + ')' + re.escape(delimiter) + '+', additional_args)
    return [additional_arg.replace(escape_char + delimiter, delimiter)
            for additional_arg in additional_args if len(additional_arg.strip()) > 0]


def convert_num_to_alpha(num):
    """
    Converts a numeric number to an alpha list item. ie 1 -> a, 27 -> aa

    :param num:
    :return:
    """
    dividend = num
    alpha = ""

    while dividend > 0:
        mod = (dividend - 1) % 26
        alpha = chr(97 + mod) + alpha
        dividend = int((dividend - mod) / 26)

    return alpha


def parse_xml(xml_filepath, parser=None):
    """
    Parses a XML file from the specified path while also ensuring that any DTD is loaded
    and the custom XMLEntityResolver is enabled.

    :param xml_filepath: The path to the XML file to parse.
    :type xml_filepath: str
    :param parser: A custom XML parser to use when parsing.
    :type parser: etree.XMLParser
    :return: The parsed lxml tree object.
    :rtype: etree._ElementTree
    """
    if parser is None:
        parser = etree.XMLParser(load_dtd=True)
    parser.resolvers.add(XMLEntityResolver())
    return etree.parse(xml_filepath, parser)


def parse_xhtml(html_filepath, parser=None, strip_namespace=True):
    """
    Parses a XHTML file from the specified path and strips the XHTML namespace.

    :param html_filepath: The path to the HTML file to parse.
    :type html_filepath: str
    :param parser: A custom XHTML parser to use when parsing.
    :type parser: html.XHTMLParser
    :param strip_namespace: Whether or not to strip out the xhtml namespace.
    :type strip_namespace: bool
    :return: The root element of the parsed HTML file
    :rtype: lxml.html.HtmlMixin
    """
    if parser is None:
        parser = html.xhtml_parser
    html_tree = etree.parse(html_filepath, parser=parser)
    root_ele = html_tree.getroot()
    # Strip out the XHTML namespace
    if strip_namespace:
        html.xhtml_to_html(root_ele)
        objectify.deannotate(root_ele, cleanup_namespaces=True)
    return root_ele


def ensure_lxml_element(xml_ele):
    """
    Ensures that the XML element is an Element and not an ElementTree
    """
    try:
        xml_ele = xml_ele.getroot()
    except AttributeError:
        pass
    return xml_ele


def generate_hash_for_file(filepath):
    """
    Generates a MD5 hash for the content of the specified file
    """
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def generate_hash(value):
    """
    Generates a MD5 hash for the value passed

    :param value:
    :type value: str
    :return: A hexadecimal MD5 string of the value
    :rtype: str
    """
    hash_md5 = hashlib.md5()
    hash_md5.update(value.encode('utf-8'))
    return hash_md5.hexdigest()


class XMLEntityResolver(etree.Resolver):
    def __init__(self):
        super(XMLEntityResolver, self).__init__()

    def resolve(self, url, public_id, context):
        if self.is_file_url(url):
            filepath = urllib.unquote(re.sub(r"^file:(/{2,3}?)?(/|[A-Za-z])", r"\2", url))

            # Log the debug message
            if not url.startswith("file:/"):
                log.debug("Resolving file '%s'", filepath)

            # Resolve the url
            if os.path.exists(filepath):
                return self.resolve_filename(urllib.quote(filepath), context)
            elif "Common_Content" in url:
                # Common Content is something publican pulls in and shouldn't contain anything of use (assuming we aren't validating),
                # so just return an empty xml file for now
                return self.resolve_string("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<element></element>", context)
            else:
                raise IOError(errno.ENOENT, "No such file or directory", filepath)
        else:
            return super(XMLEntityResolver, self).resolve(url, public_id, context)

    def is_file_url(self, url):
        return "file:/" in url or '://' not in url


class TermIOWrapper(object):
    _ansi_vt100_re = re.compile('(\033|\x1b)\[(([0-9,A-Z]{1,2}(;[0-9]{1,2})?(;[0-9]{3})?)?[m|K]?)|(\?[0-9]{1,2}[lh])')

    def __init__(self, stream):
        self.stream = stream
        self._isatty = stream.isatty()

    def isatty(self):
        return True

    def write(self, data):
        if not self._isatty:
            # Strip ansi escape characters if we aren't writing to a terminal
            data = self._ansi_vt100_re.sub('', data)
        return self.stream.write(data)

    def __getattr__(self, attr):
        return getattr(self.stream, attr)


class INIConfigParser(RawConfigParser):
    def _read(self, fp, fpname):
        RawConfigParser._read(self, fp, fpname)

        # Add some basic support for quoted/escaped values
        # TODO there are probably a few other edge cases that should be handled, try to find them
        all_sections = [self._defaults]
        all_sections.extend(self._sections.values())
        for options in all_sections:
            for name, val in options.items():
                if val is not None and (isinstance(val, str) or isinstance(val, unicode)):
                    # Strip quoted chars
                    if val.startswith('"'):
                        val = val.lstrip('"').rstrip('"').replace('\\"', '"')
                    else:
                        # Strip new line markers
                        val = re.sub(r'\s*\\\s*(\r?\n|$)', r'\1', val)
                    options[name] = val
