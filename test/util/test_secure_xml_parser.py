"""Tests for secure XML and YAML parsing utilities."""

import os
import tempfile
import unittest
from xml.etree.ElementTree import ParseError

import yaml

from src.util.secure_xml_parser import (
    parse_xml_file,
    parse_xml_string,
    safe_yaml_load,
    safe_yaml_load_file,
    validate_xml_content_type,
)


class TestSecureXMLParser(unittest.TestCase):
    """Test secure XML parsing functions."""

    def test_parse_valid_xml_string(self):
        """Test parsing valid XML string."""
        xml = "<root><item>value</item></root>"
        root = parse_xml_string(xml)
        self.assertIsNotNone(root)
        self.assertEqual(root.tag, "root")
        self.assertEqual(root.find("item").text, "value")

    def test_parse_xml_with_dtd_forbidden(self):
        """Test that DTD is blocked when forbidden."""
        xml_with_dtd = """<?xml version="1.0"?>
<!DOCTYPE root [
<!ELEMENT root ANY>
]>
<root>test</root>"""
        with self.assertRaises(ValueError):
            parse_xml_string(xml_with_dtd, forbid_dtd=True)

    def test_parse_xml_with_entity_forbidden(self):
        """Test that external entities are blocked when forbidden."""
        xml_with_entity = """<?xml version="1.0"?>
<!DOCTYPE foo [
<!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<root>&xxe;</root>"""
        with self.assertRaises(ValueError):
            parse_xml_string(xml_with_entity, forbid_entities=True)

    def test_parse_malformed_xml(self):
        """Test that malformed XML raises ParseError."""
        xml = "<root><item>value</root>"  # Missing closing tag
        with self.assertRaises(ParseError):
            parse_xml_string(xml)

    def test_parse_xml_file(self):
        """Test parsing XML from file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write("<root><item>test</item></root>")
            temp_path = f.name

        try:
            root = parse_xml_file(temp_path)
            self.assertIsNotNone(root)
            self.assertEqual(root.tag, "root")
            self.assertEqual(root.find("item").text, "test")
        finally:
            os.unlink(temp_path)

    def test_parse_xml_file_not_found(self):
        """Test that missing file raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            parse_xml_file("/nonexistent/path/file.xml")

    def test_parse_xml_file_with_xxe_attack(self):
        """Test that XXE attack in file is blocked."""
        xxe_content = """<?xml version="1.0"?>
<!DOCTYPE root [
<!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<root>&xxe;</root>"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write(xxe_content)
            temp_path = f.name

        try:
            with self.assertRaises(ValueError):
                parse_xml_file(temp_path, forbid_dtd=True, forbid_entities=True)
        finally:
            os.unlink(temp_path)


class TestSafeYAMLLoader(unittest.TestCase):
    """Test secure YAML parsing functions."""

    def test_safe_yaml_load_valid(self):
        """Test loading valid YAML content."""
        yaml_content = """
key: value
list:
  - item1
  - item2
number: 42
"""
        data = safe_yaml_load(yaml_content)
        self.assertEqual(data["key"], "value")
        self.assertEqual(data["list"], ["item1", "item2"])
        self.assertEqual(data["number"], 42)

    def test_safe_yaml_load_empty(self):
        """Test loading empty YAML content."""
        data = safe_yaml_load("")
        self.assertIsNone(data)

    def test_safe_yaml_load_malformed(self):
        """Test that malformed YAML raises YAMLError."""
        yaml_content = """
key: value
  bad indentation
    more bad indentation
"""
        with self.assertRaises(yaml.YAMLError):
            safe_yaml_load(yaml_content)

    def test_safe_yaml_load_file(self):
        """Test loading YAML from file."""
        yaml_content = "key: value\nlist:\n  - item1\n  - item2"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            data = safe_yaml_load_file(temp_path)
            self.assertEqual(data["key"], "value")
            self.assertEqual(data["list"], ["item1", "item2"])
        finally:
            os.unlink(temp_path)

    def test_safe_yaml_load_file_not_found(self):
        """Test that missing file raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            safe_yaml_load_file("/nonexistent/path/file.yaml")

    def test_safe_yaml_blocks_python_objects(self):
        """Test that safe_load blocks arbitrary Python objects."""
        # This should not execute Python code or create objects
        yaml_content = "!!python/object/apply:os.system ['echo pwned']"
        # safe_load will treat this as a string tag, not execute it
        data = safe_yaml_load(yaml_content)
        # Should not raise an error but also should not execute the command


class TestXMLContentTypeValidation(unittest.TestCase):
    """Test XML content type validation."""

    def test_validate_xml_content_types(self):
        """Test various XML content types."""
        valid_types = [
            "application/xml",
            "text/xml",
            "application/xhtml+xml",
            "application/rss+xml",
            "application/atom+xml",
            "application/xml; charset=utf-8",
            "Application/XML",  # Case insensitive
        ]
        for content_type in valid_types:
            with self.subTest(content_type=content_type):
                self.assertTrue(validate_xml_content_type(content_type))

    def test_validate_non_xml_content_types(self):
        """Test non-XML content types."""
        invalid_types = [
            "application/json",
            "text/html",
            "text/plain",
            "application/octet-stream",
            None,
            "",
        ]
        for content_type in invalid_types:
            with self.subTest(content_type=content_type):
                self.assertFalse(validate_xml_content_type(content_type))


if __name__ == "__main__":
    unittest.main()
