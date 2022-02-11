import os

import mock
import pytest
from aura.exceptions import InvalidInputException
from aura.transformers.tf_publican import PublicanTransformer

import base
from base import StringContaining


class TestPublicanTransformer(base.TestBase):
    def test_get_publican_tmp_dir(self, publican_info):
        # Given a publican config with a tmp_dir value
        publican_cfg = publican_info['cfg']
        publican_cfg.write("xml_lang: en-US\n"
                           "type: Book\n"
                           "tmp_dir: build")
        # and a helper instance
        helper = PublicanTransformer()

        # When getting the tmp directory
        tmp_dir = helper.get_build_root_dir(str(publican_cfg))

        # Then the tmp_dir should be "build"
        assert tmp_dir == os.path.join(os.getcwd(), "build")

    def test_get_publican_tmp_dir_no_config_value(self, publican_info):
        # Given a publican config with no tmp_dir value
        publican_cfg = publican_info['cfg']
        publican_cfg.write("xml_lang: en-US\n"
                           "type: Book")
        # and a helper instance
        helper = PublicanTransformer()

        # When getting the tmp directory
        tmp_dir = helper.get_build_root_dir(str(publican_cfg))

        # Then the tmp_dir should be "tmp"
        assert tmp_dir == os.path.join(os.getcwd(), "tmp")

    def test_get_publican_tmp_dir_no_file(self):
        # Given a non existent publican config
        # and a helper instance
        helper = PublicanTransformer()

        # When getting the tmp directory
        tmp_dir = helper.get_build_root_dir()

        # Then the tmp_dir should be "tmp"
        assert tmp_dir == os.path.join(os.getcwd(), "tmp")

    def test_get_publican_build_dir(self):
        # Given a drupal-book format (the default) and a lang
        lang = "ja-JP"
        # and a helper instance
        helper = PublicanTransformer()
        # and no publican config values

        # When getting the build directory
        build_dir = helper.get_build_dir(lang)

        # Then the build directory should be tmp/ja-JP/drupal-book/
        assert build_dir == os.path.join(os.getcwd(), "tmp/ja-JP/drupal-book/")

    def test_get_publican_build_dir_html(self):
        # Given a html format and lang
        build_format = "html"
        lang = "ja-JP"
        # and a helper instance
        helper = PublicanTransformer()
        # and no publican config values

        # When getting the build directory
        build_dir = helper.get_build_dir(lang, build_format)

        # Then the build directory should be tmp/ja-JP/html/
        assert build_dir == os.path.join(os.getcwd(), "tmp/ja-JP/html/")

    def test_get_publican_build_dir_pdf(self):
        # Given a pdf format and lang
        build_format = "pdf"
        lang = "ja-JP"
        # and a helper instance
        helper = PublicanTransformer()
        # and no publican config values

        # When getting the build directory
        build_dir = helper.get_build_dir(lang, build_format)

        # Then the build directory should be tmp/ja-JP/pdf/
        assert build_dir == os.path.join(os.getcwd(), "tmp/ja-JP/pdf/")

    @mock.patch("os.walk")
    def test_get_publican_build_additional_files_dir_drupal_book(self, mock_walk):
        # Given a drupal-book format (the default) and a lang
        lang = "ja-JP"
        # and a helper instance
        helper = PublicanTransformer()
        # and a cached build directory
        helper._build_root_dir_cache["publican.cfg"] = "tmp/"
        # and a cached doc_id
        doc_id = "Red_Hat_Enterprise_Linux-7-Installation_Guide-" + lang
        helper._doc_id_cache = {"ja-JP": doc_id}
        # and an existing additional files sub directory
        mock_walk.return_value = iter([("tmp/ja-JP/drupal-book", [doc_id + "-7.0-2"], [])])
        # and no publican config values

        # When getting the build additional files directory
        additional_files_dir = helper.get_build_additional_files_dir(lang)

        # Then the additional files directory should be tmp/ja-JP/drupal-book/Red_Hat_Enterprise_Linux-7-Installation_Guide-ja-JP-7.0-2/
        assert additional_files_dir == "tmp/ja-JP/drupal-book/Red_Hat_Enterprise_Linux-7-Installation_Guide-ja-JP-7.0-2/"

    def test_get_doc_id_from_xml_only(self, publican_info):
        # Given a valid publican.cfg, that doesn't have a docname, product or version
        publican_cfg = publican_info['cfg']
        publican_cfg.write("xml_lang: en-US\n"
                           "type: Book")
        # and an Info XML file that contains some valid xml
        book_xml_file = publican_info['book_xml']
        book_xml_file.write("<bookinfo>\n"
                            "  <title>My Book</title>\n"
                            "  <productname>Product</productname>\n"
                            "  <productnumber>5</productnumber>\n"
                            "</bookinfo>")
        # and a helper instance
        helper = PublicanTransformer(str(publican_info['book_dir']))

        # When the getting the doc id from the file
        doc_id = helper.get_doc_id()

        # Then the doc_id should be Product-My_Book-5
        assert doc_id == "Product-5-My_Book-en-US"

    def test_get_doc_id_from_xml_and_cfg(self, publican_info):
        # Given a valid publican.cfg, that has overrides for docname, product or version
        publican_cfg = publican_info['cfg']
        publican_cfg.write("xml_lang: en-US\n"
                           "type: Book\n"
                           "docname: My Book Override\n"
                           "product: Product Override\n"
                           "version: 1")
        # and an Info XML file that contains some valid xml
        book_xml_file = publican_info['book_xml']
        book_xml_file.write("<bookinfo>\n"
                            "  <title>My Book</title>\n"
                            "  <productname>Product</productname>\n"
                            "</bookinfo>")
        # and a helper instance
        helper = PublicanTransformer(str(publican_info['book_dir']))

        # When the getting the doc id from the file
        doc_id = helper.get_doc_id()

        # Then the doc_id should be Product_Override-My_Book_Override-1
        assert doc_id == "Product_Override-1-My_Book_Override-en-US"

    def test_get_doc_id_from_invalid_xml(self, publican_info):
        # Given a valid publican.cfg, that has overrides for docname, product or version
        publican_cfg = publican_info['cfg']
        publican_cfg.write("xml_lang: en-US\n"
                           "type: Book")
        # and an Info XML file that contains some invalid xml
        book_xml_file = publican_info['book_xml']
        book_xml_file.write("<bookinfo></book>")
        # and a helper instance
        helper = PublicanTransformer(str(publican_info['book_dir']))

        # When the getting the doc id from the file, an exception should be raised and the program should exit
        try:
            helper.get_doc_id()
        except SystemExit as e:
            assert e.code == -1

        # Then the exception should exist
        logs = self.get_logs()
        assert "Opening and ending tag mismatch" in logs
        # and another help message should be printed
        assert "Unable to determine the title, product and version due to XML errors." in logs

    def test_get_doc_id_from_nonexistent_file(self, publican_info):
        # Given a valid publican.cfg, that uses a non existent info file
        publican_cfg = publican_info['cfg']
        publican_cfg.write("xml_lang: en-US\n"
                           "type: Book\n"
                           "info_file: Info.xml")
        # and a helper instance
        helper = PublicanTransformer(str(publican_info['book_dir']))

        # When the getting the doc id from the file, an exception should be raised and the program should exit
        try:
            helper.get_doc_id()
        except SystemExit as e:
            assert e.code == -1

        # Then the exception should exist
        logs = self.get_logs()
        lang_dir = publican_info['lang_dir']
        assert "No such file or directory: " + str(lang_dir.join("Info.xml")) in logs
        # and another help message should be printed
        assert "Unable to determine the title, product and version due to XML errors." in logs

    @mock.patch("subprocess.call")
    def test_run_publican_success(self, mock_subprocess_call, publican_info):
        # Given the call to publican works
        mock_subprocess_call.return_value = 0
        # and we have some additional arguments
        lang = "en-US"
        build_format = "html"
        additional_args = "--nocolours"
        # and an existing publican.cfg
        publican_info['cfg'].write("mainfile: test")
        # and a Book_Info.xml file
        publican_info['book_xml'].write("<bookinfo></bookinfo>")
        # and a main file
        publican_info['lang_dir'].join("test.xml").write("<book></book>")
        # and a helper instance
        helper = PublicanTransformer(str(publican_info['book_dir']))

        # When running publican
        result = helper.build_format(None, lang, build_format, additional_args=additional_args)

        # Then the result should be a success
        assert result, "The result of the build_format was False, but was expected to be True"
        # and the options passed to publican include the build format and lang
        mock_subprocess_call.assert_called_once_with(
            ["publican", "build", "--formats", build_format, "--langs", lang, "--nocolours"], cwd=mock.ANY
        )

    @mock.patch("subprocess.call")
    def test_run_publican_failure(self, mock_subprocess_call, publican_info):
        # Given the call to publican fails
        mock_subprocess_call.return_value = 137
        # and we have some additional arguments
        lang = "en-US"
        build_format = "pdf"
        publican_cfg = "publican-beta.cfg"
        # and an existing publican.cfg
        publican_info['book_dir'].join(publican_cfg).write("mainfile: test")
        # and a Book_Info.xml file
        publican_info['book_xml'].write("<bookinfo></bookinfo>")
        # and a main file
        publican_info['lang_dir'].join("test.xml").write("<book></book>")
        # and a helper instance
        helper = PublicanTransformer(str(publican_info['book_dir']))

        # When running publican
        result = helper.build_format(None, lang, build_format, publican_cfg)

        # Then the result should not be a success
        assert not result, "The result of the build_format was True, but was expected to be False"
        # and the options passed to publican include the build format and lang
        mock_subprocess_call.assert_called_once_with(
            ["publican", "build", "--formats", build_format, "--langs", lang, "--config", StringContaining(publican_cfg)],
            cwd=mock.ANY
        )

    def test_build_invalid_format(self, publican_info):
        # Given a publican.cfg
        publican_cfg = publican_info['cfg']
        publican_cfg.write("type: Article\n"
                           "xml_lang: en-US\n"
                           "mainfile: test\n")
        # and an invalid build format
        build_format = "invalid-format"
        # and a helper instance
        helper = PublicanTransformer(str(publican_info['book_dir']))

        # When running publican
        try:
            helper.build_format(None, "en-US", build_format, str(publican_cfg))
            pytest.fail("An exception should have been raised.")
        except InvalidInputException as e:
            # Then an exception should be raised with a meaningful error message
            assert str(e) == "\"invalid-format\" is not a valid format"

    def test_matching_doctypes(self, publican_info):
        # Given a publican.cfg with a type set as Article
        publican_cfg = publican_info['cfg']
        publican_cfg.write("type: Article\n"
                           "xml_lang: en-US\n"
                           "mainfile: test\n")
        # and a main file that is a book
        publican_info['lang_dir'].join("test.xml").write("<book></book>")
        # and a helper instance
        helper = PublicanTransformer(str(publican_info['book_dir']))

        # When running publican
        try:
            helper.build_format(None, "en-US", "html-single", str(publican_cfg))
            pytest.fail("An exception should have been raised.")
        except InvalidInputException as e:
            # Then an exception should be raised with a meaningful error message
            assert str(e) == "The document type specified in the configuration (Article), doesn't match the source content type (Book)"

    def test_resolve_source_lang(self, publican_info):
        # Given a publican config with a xml_lang value
        publican_cfg = publican_info['cfg']
        publican_cfg.write("xml_lang: de-DE\n"
                           "type: Book")
        publican_cfg_path = str(publican_cfg)
        # and a helper instance
        helper = PublicanTransformer()

        # When resolving the source language
        result1 = helper._resolve_source_language(None)
        result2 = helper._resolve_source_language(src_lang="ja-JP")
        result3 = helper._resolve_source_language(config=publican_cfg_path)

        # Then make sure the correct data is returned
        assert result1 == "en-US"
        assert result2 == "ja-JP"
        assert result3 == "de-DE"
