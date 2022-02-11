import os.path

import mock
from aura import utils
from lxml import etree


@mock.patch("os.listdir")
def test_find_file_for_type(mock_listdir, tmpdir):
    # Given listdir will return a list of files
    mock_listdir.return_value = ["index.html", "book.pdf", "book.epub", "book2.pdf"]
    # and a base directory
    base_dir = str(tmpdir)

    # When find_file_for_type is called
    result = utils.find_file_for_type(base_dir, "pdf")

    # Then the result should be book.pdf
    assert result == "book.pdf"
    # and the listdir was called with the base directory
    mock_listdir.assert_called_once_with(base_dir)


@mock.patch("os.listdir")
def test_find_file_for_type_with_empty_dir(mock_listdir, tmpdir):
    # Given listdir will return a empty directory
    mock_listdir.return_value = []
    # and a base directory
    base_dir = str(tmpdir)

    # When find_file_for_type is called
    result = utils.find_file_for_type(base_dir, "epub")

    # Then the result should be None
    assert result is None
    # and the listdir was called with the base directory
    mock_listdir.assert_called_once_with(base_dir)


def test_get_element_text_with_child_elements():
    # Given a parent element
    parent = etree.Element("productname")
    # and some text for the parent
    parent.text = "Test "
    # and a child emphasis element, with tail text
    child = etree.Element("emphasis", attrib={'role': 'strong'})
    child.text = "Message"
    child.tail = " Title"
    parent.append(child)

    # When converting the parent element to text
    text = utils.get_element_text(parent)

    # Then the text should be the same as the parent + child text
    assert text == "Test Message Title"


def test_copy_directory(tmpdir):
    # Given a source and destination directory
    src_dir = tmpdir.mkdir("src")
    dest_dir = tmpdir.join("dest")
    # and some source files/dirs
    src_sub_dir = src_dir.mkdir("dir1")
    src_sub_file = src_sub_dir.join("dir1-file1.txt")
    src_sub_file.write("some content")
    src_file = src_dir.join("file1.txt")
    src_file.write("some content")

    # When copying content between directories
    utils.copy_dir_contents(str(src_dir), str(dest_dir))

    # The the dest directory should have been created
    assert os.path.isdir(str(dest_dir))
    # and the subdirectory exists
    assert os.path.isdir(str(dest_dir.join("dir1")))
    # and the sub files should have copied
    assert os.path.isfile(str(dest_dir.join("file1.txt")))
    assert os.path.isfile(str(dest_dir.join("dir1").join("dir1-file1.txt")))


def test_ensure_lxml_element():
    # Given an lxml ElementTree
    ele = etree.Element("book")
    tree = etree.ElementTree(ele)

    # When making sure the object passed is an element and not the elements tree
    result = utils.ensure_lxml_element(tree)

    # Then the element should be returned since the tree was passed
    assert result == ele


def test_clean_for_rpm():
    # Given some tests cases
    test1 = "Integration with  Red Hat OpenShift_Enterprise"
    test2 = "Integration with Red\xc2\xa0Hat OpenShift Enterprise"
    test3 = "Integration with Red Hat Ceph Storage (x86_64)"
    test4 = ".NET Core"

    # When cleaning for use in an RPM name
    result1 = utils.clean_for_rpm_name(test1)
    result2 = utils.clean_for_rpm_name(test2)
    result3 = utils.clean_for_rpm_name(test3)
    result4 = utils.clean_for_rpm_name(test4)

    # Then expect the correct output
    assert result1 == "Integration_with__Red_Hat_OpenShift_Enterprise"
    assert result2 == "Integration_with_Red_Hat_OpenShift_Enterprise"
    assert result3 == "Integration_with_Red_Hat_Ceph_Storage_x86_64"
    assert result4 == ".NET_Core"
