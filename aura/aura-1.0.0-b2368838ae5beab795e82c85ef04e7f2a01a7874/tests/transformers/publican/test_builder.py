# coding=utf-8
import os
import time
import uuid

import mock
import pytest
from aura import utils
from aura.compat import StringIO
from aura.transformers.publican.builder import XMLFeedBuilder, XMLFeedPageBuilder, XMLFeedBuilderContext, PROTOCOL_V2
from aura.transformers.tf_publican import PublicanTransformer
from lxml import etree

import base


class TestPublicanXMLFeedBuilder(base.TestBase):
    @pytest.fixture(autouse=True)
    def init_transformer(self):
        # Init a transformer to be used
        self.transformer = PublicanTransformer()
        # and add a doc id for it
        self.lang = "en-US"
        self.src_lang = "en-US"
        doc_id = "Red_Hat_Enterprise_Linux-7-Installation_Guide-" + self.lang
        self.transformer._doc_id_cache = {self.lang: doc_id}

    def test_add_feed_id(self, publican_info):
        # Given some parsed source XML
        src_tree = etree.parse(StringIO("<book><title>Test Document</title></book>"))
        # and a basic XML Feed
        doc_ele = etree.Element("document")
        # and a publican config with a tmp_dir value
        publican_cfg = publican_info['cfg']
        publican_cfg.write("xml_lang: en-US\n"
                           "type: Book\n"
                           "tmp_dir: build")
        # and a builder instance
        doc_uuid = uuid.uuid4()
        context = XMLFeedBuilderContext(self.transformer, doc_uuid, src_tree, self.src_lang, self.lang, str(publican_cfg))
        builder = XMLFeedBuilder(context)

        # When attempting to add a feed id
        builder.add_feed_id(doc_ele)

        # Then the first element in the feed, should be the uuid and the second the id
        assert doc_ele[0].tag == "uuid"
        assert doc_ele[1].tag == "id"
        # and the uuid should be the value passed to the builder
        assert doc_ele[0].text == str(doc_uuid)
        # and the ids text should be a lower case form of the doc id
        assert doc_ele[1].text == "red_hat_enterprise_linux-7-installation_guide"

    def test_add_feed_type(self, publican_info):
        # Given a publican config, that specifies the doc is an article
        publican_cfg = publican_info['cfg']
        publican_cfg.write("xml_lang: " + self.lang + "\n"
                           "type: Article\n")
        # and a builder instance
        doc_uuid = uuid.uuid4()
        context = XMLFeedBuilderContext(self.transformer, doc_uuid, None, self.src_lang, self.lang, str(publican_cfg))
        builder = XMLFeedBuilder(context)
        # and a basic XML Feed
        doc_ele = etree.Element("document")
        doc_id_ele = etree.SubElement(doc_ele, "id")

        # When adding the type to the feed
        builder.add_type(doc_ele)

        # Then the type should have been added after the id element
        assert doc_id_ele.getnext().tag == "type"
        assert doc_ele[1].text == "article"

    def test_add_feed_name(self, publican_info):
        # Given some parsed source XML
        src_tree = etree.parse(StringIO("<book><bookinfo>" +
                                        "<title>Test Document</title>" +
                                        "<productname>Product</productname>" +
                                        "<productnumber>6.0 Beta</productnumber>" +
                                        "</bookinfo></book>"))
        # and a publican config
        publican_cfg = publican_info['cfg']
        publican_cfg.write("xml_lang: " + self.lang + "\n"
                           "type: Book\n")
        # and a builder instance
        doc_uuid = uuid.uuid4()
        context = XMLFeedBuilderContext(self.transformer, doc_uuid, src_tree, self.src_lang, self.lang, str(publican_cfg))
        builder = XMLFeedBuilder(context)
        # and pretend the Info XML has been loaded
        context._cache['src_info_ele'] = src_tree.getroot()
        # and a basic XML Feed
        doc_ele = etree.Element("document")

        # When adding the name to the feed
        builder.add_name(doc_ele)

        # Then the name should have been added after the id element
        assert doc_ele[0].tag == "name"
        assert doc_ele[0].text == "Product 6.0 Beta Test Document"

    def test_add_feed_name_db5(self, publican_info):
        # Given some parsed DocBook 5.0 source XML
        src_tree = etree.parse(StringIO("<book xmlns=\"http://docbook.org/ns/docbook\">" +
                                        "<title>Test Document</title>" +
                                        "<info>" +
                                        "<productname>Product</productname>" +
                                        "<productnumber>6.0 Beta</productnumber>" +
                                        "</info></book>"))
        # and a publican config
        publican_cfg = publican_info['cfg']
        publican_cfg.write("xml_lang: " + self.lang + "\n"
                           "type: Book\n"
                           "dtdver: 5.0")
        # and a builder instance
        doc_uuid = uuid.uuid4()
        context = XMLFeedBuilderContext(self.transformer, doc_uuid, src_tree, self.src_lang, self.lang, str(publican_cfg))
        builder = XMLFeedBuilder(context)
        # and pretend the Info XML has been loaded
        context._cache['src_info_ele'] = src_tree.getroot()
        # and a basic XML Feed
        doc_ele = etree.Element("document")

        # When adding the name to the feed
        builder.add_name(doc_ele)

        # Then the name should have been added after the id element
        assert doc_ele[0].tag == "name"
        assert doc_ele[0].text == "Product 6.0 Beta Test Document"

    def test_add_feed_created_datetime(self, publican_info):
        # Given a publican config, that specifies the doc is an article
        publican_cfg = publican_info['cfg']
        publican_cfg.write("xml_lang: " + self.lang + "\n"
                           "type: Article\n")
        # and a builder instance
        doc_uuid = uuid.uuid4()
        context = XMLFeedBuilderContext(self.transformer, doc_uuid, None, self.src_lang, self.lang, str(publican_cfg))
        builder = XMLFeedBuilder(context)
        # and a basic XML Feed
        doc_ele = etree.Element("document")

        # When adding the type to the feed
        before_timestamp = int(time.time())
        builder.add_created_datetime(doc_ele)
        after_timestamp = int(time.time())

        # Then the created datetime should have been added
        assert doc_ele[0].tag == "created"
        created_timestamp = int(doc_ele[0].text)
        assert before_timestamp <= created_timestamp <= after_timestamp

    def test_add_feed_info_metadata(self, publican_info):
        # Given some parsed source XML
        src_tree = etree.parse(StringIO("<book><bookinfo>" +
                                        "<title>Test Document</title>" +
                                        "<subtitle>Test Document Subtitle</subtitle>"
                                        "<productname>Product</productname>" +
                                        "<productnumber>1.3</productnumber>" +
                                        "<abstract><para>Some <emphasis>abstract</emphasis> text</para></abstract>" +
                                        "<keywordset><keyword>test</keyword><keyword>images</keyword></keywordset>" +
                                        "</bookinfo></book>"))
        # and a publican config
        publican_cfg = publican_info['cfg']
        publican_cfg.write("xml_lang: " + self.lang + "\n"
                           "type: Book\n")
        # and a builder instance
        doc_uuid = uuid.uuid4()
        context = XMLFeedBuilderContext(self.transformer, doc_uuid, src_tree, self.src_lang, self.lang, str(publican_cfg))
        builder = XMLFeedBuilder(context)
        # and pretend the Info XML has been loaded
        context._cache['src_info_ele'] = src_tree.getroot()
        # and a basic XML Feed
        doc_ele = etree.Element("document")

        # When adding the doc info metadata to the feed
        builder.add_info_metadata(doc_ele)

        # Then the title, subtitle, product, version, edition, abstract and keywords should have been set
        # Title
        doc_title_ele = doc_ele.find("title")
        assert doc_title_ele is not None
        assert doc_title_ele.text == "Test Document"
        assert doc_title_ele.get("base") == "Test Document"
        # Subtitle
        doc_subtitle_ele = doc_ele.find("subtitle")
        assert doc_subtitle_ele is not None
        assert doc_subtitle_ele.text == "Test Document Subtitle"
        assert doc_subtitle_ele.get("base") == "Test Document Subtitle"
        # Product
        doc_product_ele = doc_ele.find("product")
        assert doc_product_ele is not None
        assert doc_product_ele.text == "Product"
        assert doc_product_ele.get("base") == "Product"
        # Version
        doc_version_ele = doc_ele.find("version")
        assert doc_version_ele is not None
        assert doc_version_ele.text == "1.3"
        assert doc_version_ele.get("base") == "1.3"
        # Edition should be the default
        doc_edition_ele = doc_ele.find("edition")
        assert doc_edition_ele is not None
        assert doc_edition_ele.text == "1.0"
        # Abstract
        doc_abstract_ele = doc_ele.find("abstract")
        assert doc_abstract_ele is not None
        assert doc_abstract_ele.text == "Some abstract text"
        # Keywords
        doc_keywords_ele = doc_ele.find("keywords")
        assert doc_keywords_ele is not None
        assert doc_keywords_ele.text == "test,images"

    def test_add_feed_translation_info_metadata(self, publican_info):
        # Given some parsed source XML
        src_tree = etree.parse(StringIO("<book><bookinfo>" +
                                        "<title>Test Document</title>" +
                                        "<subtitle>Test Document Subtitle</subtitle>"
                                        "<productname>Product</productname>" +
                                        "<productnumber>1.3</productnumber>" +
                                        "<abstract><para>Some <emphasis>abstract</emphasis> text</para></abstract>" +
                                        "<keywordset><keyword>test</keyword><keyword>images</keyword></keywordset>" +
                                        "</bookinfo></book>"))
        # and some translated XML
        trans_tree = etree.parse(StringIO(u"<book><bookinfo>" +
                                          u"<title>テストドキュメント</title>" +
                                          u"<subtitle>テストドキュメントのサブタイトル</subtitle>"
                                          u"<productname>製品</productname>" +
                                          u"<productnumber>1.3</productnumber>" +
                                          u"<abstract><para>Some <emphasis>abstract</emphasis> text</para></abstract>" +
                                          u"<keywordset><keyword>test</keyword><keyword>images</keyword></keywordset>" +
                                          u"</bookinfo></book>"))
        self.transformer._doc_id_cache["ja-JP"] = self.transformer._doc_id_cache[self.src_lang].replace(self.src_lang, "ja-JP")
        # and a publican config
        publican_cfg = publican_info['cfg']
        publican_cfg.write("xml_lang: " + self.lang + "\n"
                           "type: Book\n")
        # and a builder instance
        doc_uuid = uuid.uuid4()
        context = XMLFeedBuilderContext(self.transformer, doc_uuid, src_tree, self.src_lang, "ja-JP", str(publican_cfg), trans_tree)
        builder = XMLFeedBuilder(context)
        # and pretend the Info XML has been loaded
        context._cache['src_info_ele'] = src_tree.getroot()
        context._cache['trans_info_ele'] = trans_tree.getroot()
        # and a basic XML Feed
        doc_ele = etree.Element("document")

        # When adding the doc info metadata to the feed
        builder.add_info_metadata(doc_ele)

        # Then the title, subtitle, product, version, edition, abstract and keywords should have been set
        # Title
        doc_title_ele = doc_ele.find("title")
        assert doc_title_ele is not None
        assert doc_title_ele.text == u"テストドキュメント"
        assert doc_title_ele.get("base") == "Test Document"
        # Subtitle
        doc_subtitle_ele = doc_ele.find("subtitle")
        assert doc_subtitle_ele is not None
        assert doc_subtitle_ele.text == u"テストドキュメントのサブタイトル"
        assert doc_subtitle_ele.get("base") == "Test Document Subtitle"
        # Product
        doc_product_ele = doc_ele.find("product")
        assert doc_product_ele is not None
        assert doc_product_ele.text == u"製品"
        assert doc_product_ele.get("base") == "Product"
        # Version
        doc_version_ele = doc_ele.find("version")
        assert doc_version_ele is not None
        assert doc_version_ele.text == "1.3"
        assert doc_version_ele.get("base") == "1.3"
        # Edition should be the default
        doc_edition_ele = doc_ele.find("edition")
        assert doc_edition_ele is not None
        assert doc_edition_ele.text == "1.0"
        # Abstract
        doc_abstract_ele = doc_ele.find("abstract")
        assert doc_abstract_ele is not None
        assert doc_abstract_ele.text == "Some abstract text"
        # Keywords
        doc_keywords_ele = doc_ele.find("keywords")
        assert doc_keywords_ele is not None
        assert doc_keywords_ele.text == "test,images"

    def test_add_feed_url_slugs(self, publican_info):
        # Given some parsed source XML
        src_tree = etree.parse(StringIO("<book><bookinfo>" +
                                        "<title>Test Document</title>" +
                                        "<productname>Red Hat Enterprise Linux</productname>" +
                                        "<productnumber>6 Beta</productnumber>" +
                                        "</bookinfo></book>"))
        # and a publican config with no overrides
        publican_cfg = publican_info['cfg']
        publican_cfg.write("xml_lang: " + self.lang + "\n"
                           "type: Book\n")
        # and a builder instance
        doc_uuid = uuid.uuid4()
        context = XMLFeedBuilderContext(self.transformer, doc_uuid, src_tree, self.src_lang, self.lang, str(publican_cfg))
        builder = XMLFeedBuilder(context)
        # and pretend the Info XML has been loaded
        context._cache['src_info_ele'] = src_tree.getroot()
        # and a basic XML Feed
        doc_ele = etree.Element("document")

        # When adding the slugs to the feed
        builder.add_url_slugs(doc_ele)

        # Then expect a product, title and version slug to have been appended
        assert doc_ele[0].tag == "title_slug"
        assert doc_ele[0].text == "Test_Document"
        assert doc_ele[1].tag == "product_slug"
        assert doc_ele[1].text == "Red_Hat_Enterprise_Linux"
        assert doc_ele[2].tag == "version_slug"
        assert doc_ele[2].text == "6_Beta"

    def test_add_feed_url_slugs_with_overrides(self, publican_info):
        # Given some parsed source XML
        src_tree = etree.parse(StringIO("<book><bookinfo>" +
                                        "<title>What's New?</title>" +
                                        "<productname>Red&#160;Hat Mobile Application Platform, Hosted</productname>" +
                                        "<productnumber>4.2</productnumber>" +
                                        "</bookinfo></book>"))
        # and a publican config with a product and title override
        publican_cfg = publican_info['cfg']
        publican_cfg.write("xml_lang: " + self.lang + "\n"
                           "type: Book\n"
                           "product: \"Red Hat Mobile Application Platform Hosted\"\n"
                           "docname: \"Whats_New\"\n")
        # and a builder instance
        doc_uuid = uuid.uuid4()
        context = XMLFeedBuilderContext(self.transformer, doc_uuid, src_tree, self.src_lang, self.lang, str(publican_cfg))
        builder = XMLFeedBuilder(context)
        # and pretend the Info XML has been loaded
        context._cache['src_info_ele'] = src_tree.getroot()
        # and a basic XML Feed
        doc_ele = etree.Element("document")

        # When adding the slugs to the feed
        builder.add_url_slugs(doc_ele)

        # Then expect a product, title and version slug to have been appended
        assert doc_ele[0].tag == "title_slug"
        assert doc_ele[0].text == "Whats_New"
        assert doc_ele[1].tag == "product_slug"
        assert doc_ele[1].text == "Red_Hat_Mobile_Application_Platform_Hosted"
        assert doc_ele[2].tag == "version_slug"
        assert doc_ele[2].text == "4.2"

    def test_add_pages(self, tmpdir):
        # Given a basic document has been rendered
        resources_dir = os.path.abspath("tests/resources/transformers/publican")
        fixtures_dir = os.path.join(resources_dir, "fixtures")
        self.transformer.source_dir = fixtures_dir
        self.transformer._doc_id_cache = {}
        publican_cfg = os.path.join(fixtures_dir, "publican.cfg")
        src_xml = self.transformer.get_build_main_file(self.lang, "xml", publican_cfg)
        # and a parsed XML source
        parser = etree.XMLParser(load_dtd=True, strip_cdata=False)
        src_tree = utils.parse_xml(src_xml, parser)
        src_tree.xinclude()
        # and a builder instance
        doc_uuid = uuid.uuid4()
        context = XMLFeedBuilderContext(self.transformer, doc_uuid, src_tree, self.src_lang, self.lang, publican_cfg,
                                        protocol=PROTOCOL_V2)
        builder = XMLFeedBuilder(context)
        # and a basic XML Feed
        doc_ele = etree.Element("document")
        doc_ele.text = "\n  "
        feed_tree = etree.ElementTree(doc_ele)

        # When adding the pages for the xml feed
        builder.add_pages(doc_ele)
        output_feed = tmpdir.join("feed.xml")
        with open(str(output_feed), "w") as f:
            f.write(etree.tostring(feed_tree, encoding="UTF-8", xml_declaration=True))

        # Then load the expected file content
        expected_feed_file = os.path.join(resources_dir, "expect", "Documentation-0.1-Test-en-US-0.0-0.base.xml")
        expected_feed = utils.parse_xml(expected_feed_file)
        actual_feed = utils.parse_xml(str(output_feed))
        # and make sure the toc elements match
        expected_toc = utils.get_element_xml(expected_feed.find("toc")).strip()
        actual_toc = utils.get_element_xml(actual_feed.find("toc")).strip()
        assert actual_toc == expected_toc
        # and each page element matches
        expected_pages = expected_feed.findall("page")
        actual_pages = actual_feed.findall("page")
        for idx, expected_page in enumerate(expected_pages):
            actual_page = actual_pages[idx]
            assert utils.get_element_xml(actual_page).strip() == utils.get_element_xml(expected_page).strip()


class TestPublicanXMLFeedPageBuilder(base.TestBase):
    @pytest.fixture(autouse=True)
    def init_feed_builder(self, publican_info):
        # Init a transformer to be used
        self.transformer = PublicanTransformer()
        # and add a doc id for it
        self.lang = "en-US"
        self.src_lang = "en-US"
        self.doc_id = "Red_Hat_Enterprise_Linux-7-Installation_Guide-" + self.lang
        self.transformer._doc_id_cache = {self.lang: self.doc_id}
        # and a publican config
        publican_cfg = publican_info['cfg']
        publican_cfg.write("xml_lang: " + self.lang + "\n"
                           "type: Book\n")
        # and a build context
        doc_uuid = uuid.UUID("75dbb44f-b2ef-46c5-ac50-92a4c08fc5fb")
        self.context = XMLFeedBuilderContext(self.transformer, doc_uuid, None, self.src_lang, self.lang, str(publican_cfg))

    def test_generate_page_url_token(self):
        # Given some variations for the filename
        filename1 = "Installation-via-rpm"
        filename2 = "index"
        filename3 = "ix01"

        # When generating the url token
        url_token1 = self.context.page_url_token(filename1)
        url_token2 = self.context.page_url_token(filename2)
        url_token3 = self.context.page_url_token(filename3)

        # Then the url for filename 1 should be a concatenation of the two
        assert url_token1 == "Red_Hat_Enterprise_Linux-7-Installation_Guide-en-US-Installation-via-rpm"
        # just the doc id for the index for filename2
        assert url_token2 == self.doc_id
        # the doc id with "-index" appended for filename3
        assert url_token3 == "Red_Hat_Enterprise_Linux-7-Installation_Guide-en-US-index"

    def test_add_page_id(self):
        # Given a source element with an id and a title
        src_ele = etree.parse(StringIO("<section id=\"sect-test-id\"><title>Test Section</title></section>")).getroot()
        # and an associated filename
        filename = "sect-test-id"
        # and a builder instance
        page_builder = XMLFeedPageBuilder(self.context, src_ele, filename, -15)
        # and a page element
        page_ele = etree.Element("page")

        # When adding the page id
        page_builder.add_page_id(page_ele)

        # Then the id from the source xml should have been used in congunction with the doc id and transformed to lowercase
        assert page_ele[0].tag == "id"
        assert page_ele[0].text == "red_hat_enterprise_linux-7-installation_guide-en-us-sect-test-id"

    def test_add_page_id_with_no_src_id(self):
        # Given a source element without an id, but with a title
        src_ele = etree.parse(StringIO("<section><title>Test Section</title></section>")).getroot()
        # and an associated filename
        filename = "sect-test-id"
        # and a builder instance
        page_builder = XMLFeedPageBuilder(self.context, src_ele, filename, -15)
        # and a page element
        page_ele = etree.Element("page")

        # When adding the page id
        page_builder.add_page_id(page_ele)

        # Then the title from the source xml should have been used in conjunction with the doc id and transformed to lowercase
        assert page_ele[0].tag == "id"
        assert page_ele[0].text == "red_hat_enterprise_linux-7-installation_guide-en-us-test_section"
        # and a warning should have been logged
        assert "No persistent id was specified in the source markup" in self.get_logs()

    @mock.patch("os.listdir")
    def test_add_page_url_slug(self, mock_list_dir):
        # Given an associated filename
        filename = "some-Cr8zY-page-name"
        # and a builder instance
        page_builder = XMLFeedPageBuilder(self.context, None, filename, -15)
        # and a page element
        page_ele = etree.Element("page")
        # and we'll have a small list of html files that doesn't contain "legal-notice.html"
        mock_list_dir.return_value = iter(['ln01.html', 'index.html', 'chap-installation.html'])

        # When adding the page name
        page_builder.add_page_url_slug(page_ele)
        page_builder.filename = "ln01"
        page_builder.add_page_url_slug(page_ele)

        # Then expect a slug element to be added based on the filename
        assert page_ele[0].tag == "page_slug"
        assert page_ele[0].text == filename
        # and a second page slug should have been added, but it should use "legal-notice"
        assert page_ele[1].tag == "page_slug"
        assert page_ele[1].text == "legal-notice"

    def test_add_page_keywords(self):
        # Given a source element with some keywords
        src_ele = etree.parse(StringIO("<section id=\"sect-test-id\">\n"
                                       "  <sectioninfo>\n"
                                       "    <keywordset>\n"
                                       "      <keyword>databases</keyword>\n"
                                       "      <keyword>transactions</keyword>\n"
                                       "    </keywordset>\n"
                                       "  </sectioninfo>\n"
                                       "  <title>Test Section</title>\n"
                                       "</section>")).getroot()
        # and an associated filename
        filename = "sect-test-id"
        # and a builder instance
        page_builder = XMLFeedPageBuilder(self.context, src_ele, filename, -15)
        # and a page element
        page_ele = etree.Element("page")

        # When adding the page keywords
        page_builder.add_page_keywords(page_ele)

        # Then the keywords from the source xml should been included in the page element
        assert page_ele[0].tag == "keywords"
        assert page_ele[0].text == "databases,transactions"

    def test_add_page_keywords_no_content(self):
        # Given a source element with no keywords
        src_ele = etree.parse(StringIO("<section><sectioninfo></sectioninfo><title>Test Section</title></section>")).getroot()
        # and an associated filename
        filename = "sect-test-id"
        # and a builder instance
        page_builder = XMLFeedPageBuilder(self.context, src_ele, filename, -15)
        # and a page element
        page_ele = etree.Element("page")

        # When adding the page keywords
        page_builder.add_page_keywords(page_ele)

        # Then the keywords from the source xml should been included in the page element
        assert page_ele[0].tag == "keywords"
        assert page_ele[0].text is None
