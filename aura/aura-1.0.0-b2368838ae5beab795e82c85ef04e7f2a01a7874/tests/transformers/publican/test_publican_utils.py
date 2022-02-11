# coding=utf-8
from lxml import etree

from aura.transformers.publican import utils

import base


class TestPublicanUtils(base.TestBase):
    def test_get_dtdver(self, publican_info):
        # Given a publican.cfg with a docbook 5.0 dtd
        publican_cfg = publican_info['cfg']
        publican_cfg.write("xml_lang: en-US\n"
                           "type: Book\n"
                           "dtdver: \"5.0\"")
        # and another without a dtdver specified
        publican_cfg2 = publican_info['book_dir'].join("no-dtdver.cfg")
        publican_cfg2.write("xml_lang: en-US\n"
                            "type: Book")

        # When get the dtd versions
        dtdver1 = utils.get_dtdver(str(publican_cfg))
        dtdver2 = utils.get_dtdver(str(publican_cfg2))

        # Then the first one should be (5, 0)
        assert dtdver1 == (5, 0)
        # and the second should be the default 4.5 version (4, 5)
        assert dtdver2 == (4, 5)

    def test_get_npv_and_lang_from_dir(self, publican_info):
        # Given we have a xml file with some valid content
        publican_info['book_xml'].write("<bookinfo>\n"
                                        "  <title>Test</title>\n"
                                        "  <productname>Product</productname>\n"
                                        "  <productnumber>Version</productnumber>\n"
                                        "</bookinfo>")
        # and a publican.cfg file
        publican_cfg = publican_info['cfg']
        publican_cfg.write("xml_lang: en-US\n"
                           "type: Book")

        # When getting the npv
        title, product, version, lang = utils.get_npv_and_lang_from_dir(str(publican_info['book_dir']))

        # Then the title should be "Test"
        assert title == "Test"
        # and then the product should be "Product"
        assert product == "Product"
        # and the version should be "Version"
        assert version == "Version"
        # and the lang should be "en-US"
        assert lang == "en-US"

    def test_load_publican_info_xml(self, publican_info):
        # Given we have a xml file with some valid content
        publican_info['article_xml'].write("<articleinfo>\n"
                                           "  <title>Test</title>\n"
                                           "  <productname>Product</productname>\n"
                                           "  <productnumber>Version</productnumber>\n"
                                           "</articleinfo>")
        # and a publican.cfg file
        publican_cfg = publican_info['cfg']
        publican_cfg.write("xml_lang: en-US\n"
                           "type: Article")

        # When loading the publican info xml
        info_ele = utils.load_publican_info_xml(str(publican_info['lang_dir']), str(publican_cfg))

        # Then the title should be "Test"
        assert info_ele.find("title").text == "Test"

    def test_is_ns_docbook_version(self):
        # Given some versions that use DTD's
        dtd_versions = ["4.1", (4, 5)]
        # and some namespaced versions
        ns_versions = [(5, 0), "5.1"]

        # When checking if the versions are namespaced
        # Then expect the dtd versions to return false
        for version in dtd_versions:
            assert utils.is_ns_docbook_ver(version) == False
        # and the ns versions to return true
        for version in ns_versions:
            assert utils.is_ns_docbook_ver(version) == True

    def test_get_xml_lang(self, publican_info):
        # Given a publican.cfg file, with a xml_lang set
        publican_cfg = publican_info['cfg']
        publican_cfg.write("xml_lang: ja-JP")
        publican_cfg_path = str(publican_cfg)

        # When getting the xml_lang
        xml_lang = utils.get_xml_lang(publican_cfg_path)

        # Then make sure the correct language is returned
        assert xml_lang == "ja-JP"

    def test_get_type(self, publican_info):
        # Given a publican.cfg file, with a xml_lang set
        publican_cfg = publican_info['cfg']
        publican_cfg.write("xml_lang: ja-JP\n"
                           "type: Article")
        publican_cfg_path = str(publican_cfg)

        # When getting the type
        doc_type = utils.get_type(publican_cfg_path)

        # Then make sure the correct type is returned
        assert doc_type == "Article"

    def test_get_brand(self, publican_info):
        # Given a publican.cfg file, with a xml_lang set
        publican_cfg = publican_info['cfg']
        publican_cfg.write("xml_lang: ja-JP\n"
                           "brand: RedHat-201405")
        publican_cfg_path = str(publican_cfg)

        # When getting the brand
        brand = utils.get_brand(publican_cfg_path)

        # Then make sure the correct type is returned
        assert brand == "RedHat-201405"

    def test_get_chunk_section_depth(self, publican_info):
        # Given a publican.cfg file, with a chunk_section_depth set
        publican_cfg = publican_info['cfg']
        publican_cfg.write("xml_lang: en-US\n"
                           "chunk_section_depth: 2")
        publican_cfg_path = str(publican_cfg)

        # When getting the chunk_section_depth
        chunk_section_depth = utils.get_chunk_section_depth(publican_cfg_path)

        # Then make sure the correct depth is returned
        assert chunk_section_depth == "2"

    def test_get_toc_section_depth(self, publican_info):
        # Given a publican.cfg file, with a toc_section_depth set
        publican_cfg = publican_info['cfg']
        publican_cfg.write("xml_lang: en-US\n"
                           "toc_section_depth: 1")
        publican_cfg_path = str(publican_cfg)

        # When getting the toc_section_depth
        toc_section_depth = utils.get_toc_section_depth(publican_cfg_path)

        # Then make sure the correct depth is returned
        assert toc_section_depth == "1"

    def test_get_keywords(self):
        # Given some info xml content with keywords
        info_ele = etree.fromstring("<sectioninfo>\n"
                                    "  <title>Test</title>\n"
                                    "  <keywordset>\n"
                                    "    <keyword>hornetq</keyword>\n"
                                    "    <keyword>messaging</keyword>\n"
                                    "  </keywordset>\n"
                                    "</sectioninfo>")

        # When extracting the keywords
        keywords_list = utils.get_keywords(info_ele)

        # Then expect the keywords list to contain the keywords
        assert keywords_list == ["hornetq", "messaging"]

    def test_strip_block_name_from_title(self):
        # Given some test data
        test_chapter = ("chapter", u"Chapter\xa01.\xa0Overview")
        test_appendix = ("appendix", u"Appendix\xa0C.\xa0Revision History")
        test_part = ("part", u"Part\xa0I.\xa0New Features")
        test_section = ("section", u"20.1.\xa0New Features and Updates")
        test_preface = ("preface", "Preface")

        # When stripping the block names
        chapter_result = utils.strip_block_name_from_title(*test_chapter)
        appendix_result = utils.strip_block_name_from_title(*test_appendix)
        part_result = utils.strip_block_name_from_title(*test_part)
        section_result = utils.strip_block_name_from_title(*test_section)
        preface_result = utils.strip_block_name_from_title(*test_preface)

        # Then expect the block name to have been removed, so it matches how ToC names are generated
        assert chapter_result == u"1. Overview"
        assert appendix_result == u"C. Revision History"
        assert part_result == u"I. New Features"
        assert section_result == u"20.1. New Features and Updates"
        assert preface_result == u"Preface"

    def test_strip_block_name_from_localized_title(self):
        # Given some test data for other languages
        test_chapter = ("chapter", u"1장. 개요", "ko-KR")
        test_appendix = ("appendix", u"付録C 改訂履歴", "ja-JP")
        test_part = ("part", u"パート\xa0I.\xa0新機能", "ja-JP")
        test_section = ("section", u"20.1. 新機能および更新", "ja-JP")
        test_preface = ("preface", u"서론", "ko-KR")

        # When stripping the block names
        chapter_result = utils.strip_block_name_from_title(*test_chapter)
        appendix_result = utils.strip_block_name_from_title(*test_appendix)
        part_result = utils.strip_block_name_from_title(*test_part)
        section_result = utils.strip_block_name_from_title(*test_section)
        preface_result = utils.strip_block_name_from_title(*test_preface)

        # Then expect the block name to have been removed, so it matches how ToC names are generated
        assert chapter_result == u"1. 개요"
        assert appendix_result == u"C. 改訂履歴"
        assert part_result == u"I. 新機能"
        assert section_result == u"20.1. 新機能および更新"
        assert preface_result == u"서론"
