import os.path

import pytest
from aura.compat import StringIO
from aura.transformers import tf_asciidoc
from aura.transformers.tf_asciidoc import AsciiDocPublicanTransformer
from lxml import etree

import base


DOCBOOK_NS = "http://docbook.org/ns/docbook"
XML_NS = "http://www.w3.org/XML/1998/namespace"
XLINK_NS = "http://www.w3.org/1999/xlink"
NS_MAP = {None: DOCBOOK_NS, 'xml': XML_NS, 'xlink': XLINK_NS}


class TestAsciiDocTransformer(base.TestBase):
    def test_clean_product(self):
        # Given some product names
        test1 = ".NET Core"
        test2 = "Red\xc2\xa0Hat Enterprise Linux"
        test3 = "Red Hat Mobile Application Platform, Hosted"

        # When cleaning the product name
        result1 = tf_asciidoc.clean_product(test1)
        result2 = tf_asciidoc.clean_product(test2)
        result3 = tf_asciidoc.clean_product(test3)

        # The make sure the results were correct
        assert result1 == "NET Core"
        assert result2 == "Red Hat Enterprise Linux"
        assert result3 == "Red Hat Mobile Application Platform Hosted"

    def test_clean_version(self):
        # Given some version names
        test1 = "6.9"
        test2 = "7.4 Beta"
        test3 = "7.0.0.beta"
        test4 = None

        # When cleaning the version name
        result1 = tf_asciidoc.clean_version(test1)
        result2 = tf_asciidoc.clean_version(test2)
        result3 = tf_asciidoc.clean_version(test3)
        result4 = tf_asciidoc.clean_version(test4)

        # The make sure the results were correct
        assert result1 == "6.9"
        assert result2 == "7.4-Beta"
        assert result3 == "7.0.0.beta"
        assert result4 == "0.1"  # Publican default version

    def test_clean_title(self):
        # Given some title names
        test1 = "Integration with Red Hat Ceph Storage (x86_64)"
        test2 = "Installing Red\xc2\xa0Hat OpenStack Platform"

        # When cleaning the title name
        result1 = tf_asciidoc.clean_title(test1)
        result2 = tf_asciidoc.clean_title(test2)

        # The make sure the results were correct
        assert result1 == "Integration with Red Hat Ceph Storage x86_64"
        assert result2 == "Installing Red Hat OpenStack Platform"

    def test_get_attribute_value(self, tmpdir):
        # Given an AsciiDoc file with some attributes
        adoc_file = tmpdir.join('master.adoc')
        adoc_file.write('= Document Title\n' +
                        ':some-attr: Blah\n' +
                        ':nested-attr: {some-attr} Blah\n' +
                        ':imagesdir: images/\n' +
                        '\n' +
                        '////\n' +
                        ':comment-attr: test\n' +
                        '////\n'
                        '\n' +
                        '== Some Chapter\n' +
                        ':imagesdir-saved: {imagesdir}\n' +
                        ':imagesdir: new-images/\n' +
                        '\n' +
                        'Some content with an image:test.png[]\n' +
                        ':imagesdir: {imagesdir-saved}')

        # When getting the AsciiDoc attributes values
        result1 = tf_asciidoc.get_attribute_value(str(adoc_file), 'some-attr')
        result2 = tf_asciidoc.get_attribute_value(str(adoc_file), 'nested-attr')
        result3 = tf_asciidoc.get_attribute_value(str(adoc_file), 'comment-attr')
        result4 = tf_asciidoc.get_attribute_value(str(adoc_file), 'imagesdir')

        # Then make sure the values match
        assert result1 == "Blah"
        assert result2 == "Blah Blah"
        assert result3 is None
        assert result4 == "images/"


class TestAsciiDocPublicanTransformer(base.TestBase):

    def test_invalid_id_refs(self, tmpdir):
        # Given a mocked up DocBook book
        mock_book = etree.Element("{" + DOCBOOK_NS + "}book", nsmap=NS_MAP)
        mock_preface = etree.SubElement(mock_book, "{" + DOCBOOK_NS + "}preface", nsmap=NS_MAP)
        mock_preface_para = etree.SubElement(mock_preface, "{" + DOCBOOK_NS + "}para", nsmap=NS_MAP)
        # with an invalid endterm and linkend
        etree.SubElement(mock_preface_para, "{" + DOCBOOK_NS + "}link", attrib={"linkend": "test1"}, nsmap=NS_MAP)
        etree.SubElement(mock_preface_para, "{" + DOCBOOK_NS + "}link", attrib={"endterm": "test2"}, nsmap=NS_MAP)
        # and a transformer instance
        transformer = AsciiDocPublicanTransformer(str(tmpdir))

        # When validating the ids
        transformer._validate_docbook_idrefs(mock_book.getroottree())

        # Then check that a error was printed for each invalid link
        logs = self.get_logs()
        assert "Unknown ID or title \"test1\", used as an internal cross reference" in logs
        assert "Unknown ID or title \"test2\", used as an internal cross reference" in logs

    def test_valid_id_ref(self, tmpdir):
        # Given a mocked up DocBook book
        mock_book = etree.Element("{" + DOCBOOK_NS + "}book", nsmap=NS_MAP)
        mock_preface = etree.SubElement(mock_book, "{" + DOCBOOK_NS + "}preface", nsmap=NS_MAP)
        mock_preface_para = etree.SubElement(mock_preface, "{" + DOCBOOK_NS + "}para",
                                             attrib={"{http://www.w3.org/XML/1998/namespace}id": "test1"}, nsmap=NS_MAP)
        # with a valid endterm and linkend
        etree.SubElement(mock_preface_para, "{" + DOCBOOK_NS + "}link", attrib={"linkend": "test1"}, nsmap=NS_MAP)
        etree.SubElement(mock_preface_para, "{" + DOCBOOK_NS + "}link", attrib={"endterm": "test1"}, nsmap=NS_MAP)
        # and a transformer instance
        transformer = AsciiDocPublicanTransformer(str(tmpdir))

        # When validating the ids
        transformer._validate_docbook_idrefs(mock_book.getroottree())

        # Then check that no error was printed for each link
        logs = self.get_logs()
        assert "Unknown ID or title \"test1\", used as an internal cross reference" not in logs

    def test_check_duplicate_ids(self, tmpdir):
        # Given some XML with duplicate ids
        xml = "<book>\n" \
              "<para xml:id=\"id1\">Some text</para>\n" \
              "<para xml:id=\"id1\">Some other content</para>\n" \
              "<para xml:id=\"id\">One last para</para>\n" \
              "</book>"
        # and a transformer instance
        transformer = AsciiDocPublicanTransformer(str(tmpdir))

        # When checking for duplicate ids
        dup_ids = transformer._check_for_duplicate_ids(xml)

        # Then the "id1" id should be in the list and "id" shouldn't be in the list
        assert "id1" in dup_ids, "\"id1\" not detected as a duplicate"
        assert "id" not in dup_ids, "\"id\" incorrectly detected as a duplicate"

    def test_convert_html_to_xml_ids(self, tmpdir):
        # Given some xml with an id that has colons and some references to that id
        xml = "<book>\n" \
              "<para xml:id=\"OS::Nova\">A para with an ID that isn't an NCNAME</para>\n" \
              "<link linkend=\"OS::Nova\"/>\n" \
              "<link endterm=\"OS::Nova\"/>\n" \
              "</book>"
        # and a transformer instance
        transformer = AsciiDocPublicanTransformer(str(tmpdir))

        # When converting the ids
        fixed_xml = transformer._convert_html_ids_to_xml(xml)

        # Then the fixed xml should equal the source xml, with all references to the ID replaced
        assert fixed_xml == xml.replace("OS::Nova", "OS-Nova")

    def test_clean_build_dir(self, tmpdir):
        # Given an existing build directory
        build_dir = tmpdir.mkdir("build")
        # and a transformer instance
        transformer = AsciiDocPublicanTransformer(str(tmpdir))

        # When cleaning the build files
        result = transformer.clean_build_files()

        # Then the result should be true
        assert result, "The build failed"
        # and the build directory doesn't exist
        assert not os.path.exists(str(build_dir))

    def test_copy_asciidoctor_diagram_already_in_images(self, tmpdir):
        # Given an existing build directory
        build_dir = tmpdir.mkdir("build")
        # a language directory
        build_lang_dir = build_dir.mkdir("en-US")
        build_lang_images_dir = build_lang_dir.mkdir("images")
        # a image created by asciidoctor diagram
        image = build_lang_images_dir.join("09cead17456ba84.png")
        image.write("blah")
        # a transformer instance
        transformer = AsciiDocPublicanTransformer(str(tmpdir))
        # and some content that had an asciidoctor image
        xml = etree.parse(StringIO("<article xmlns=\"http://docbook.org/ns/docbook\" version=\"5.0\">" +
                                   "  <section>" +
                                   "    <mediaobject>" +
                                   "      <imageobject><imagedata fileref=\"images/09cead17456ba84.png\" format=\"PNG\" /></imageobject>" +
                                   "    </mediaobject>" +
                                   "  </section>" +
                                   "</article>"))

        # When copying static files
        transformer._copy_static_files(xml, str(build_dir), str(build_lang_dir))

        # Then make sure the image still exists
        assert image.check(), "The asciidoctor diagram image no longer exists"
        # and the content is the same
        assert image.read() == "blah", "The asciidoctor diagram image was overwritten"

    def test_fix_revnumber(self):
        # Given a revision element that has a revision number without a release
        revision_ele = etree.fromstring("<revision xmlns=\"http://docbook.org/ns/docbook\">" +
                                        "  <revnumber>1.0</revnumber>" +
                                        "  <date>2016-02-12</date>" +
                                        "  <authorinitials>RL</authorinitials>" +
                                        "</revision>")

        # When attempting to fix it
        tf_asciidoc.fix_revision(revision_ele)

        # Then check that the revision number has been added
        assert revision_ele.find("./{http://docbook.org/ns/docbook}revnumber").text == "1.0-0"

    def test_fix_revnumber_no_element(self):
        # Given a revision element that has no revnumber
        revision_ele = etree.fromstring("<revision xmlns=\"http://docbook.org/ns/docbook\">" +
                                        "  <date>2016-02-12</date>" +
                                        "  <authorinitials>RL</authorinitials>" +
                                        "</revision>")

        # When attempting to fix it
        try:
            tf_asciidoc.fix_revision(revision_ele)
        except Exception:
            # Then an exception shouldn't have been thrown
            pytest.fail("An exception shouldn't have been thrown")

    def test_fix_unconverted_xref(self, tmpdir):
        # Given an unconverted link
        mock_book = etree.Element("{" + DOCBOOK_NS + "}book", nsmap=NS_MAP)
        unconverted_link = etree.SubElement(mock_book, "{" + DOCBOOK_NS + "}link", attrib={'{' + XLINK_NS + '}href': '../ch-mtu.xml#sec-mtu'}, nsmap=NS_MAP)
        unconverted_link.text = "Test"
        unconverted_xref = etree.SubElement(mock_book, "{" + DOCBOOK_NS + "}link", attrib={'{' + XLINK_NS + '}href': '../ch-mtu.xml#sec-mtu'}, nsmap=NS_MAP)
        unconverted_xref.text = "../ch-mtu.xml"
        # and a regular link
        regular_link = etree.SubElement(mock_book, "{" + DOCBOOK_NS + "}link", attrib={'linkend': 'id2'}, nsmap=NS_MAP)
        regular_link.text = "Test2"
        regular_link2 = etree.SubElement(mock_book, "{" + DOCBOOK_NS + "}link", attrib={'{' + XLINK_NS + '}href': 'http://www.example.com/'}, nsmap=NS_MAP)
        regular_link2.text = "Test 3"
        # and a transformer instance
        transformer = AsciiDocPublicanTransformer(str(tmpdir))

        # When attempting to fix the unconverted link
        transformer._fix_uncoverted_xrefs_with_file_paths(mock_book.getroottree())

        # Then the unconverted link should have been fixed
        link = mock_book[0]
        assert link.tag == "{" + DOCBOOK_NS + "}link"
        assert link.get("linkend") == "sec-mtu"
        assert link.get("{" + XLINK_NS + "}href") is None
        # and the xref should have been converted
        xref = mock_book[1]
        assert xref.tag == "{" + DOCBOOK_NS + "}xref", "The link wasn't converted to an xref"
        assert xref.get("linkend") == "sec-mtu"
        assert xref.text is None
        # and the regular links weren't changed
        link2 = mock_book[2]
        assert link2.tag == "{" + DOCBOOK_NS + "}link"
        assert link2.get("linkend") == "id2"
        assert link2.text == "Test2"
        link3 = mock_book[3]
        assert link3.tag == "{" + DOCBOOK_NS + "}link"
        assert link3.get('{' + XLINK_NS + '}href') == "http://www.example.com/"
        assert link3.text == "Test 3"
