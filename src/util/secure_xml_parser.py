"""Secure XML and YAML parsing utilities to prevent XXE vulnerabilities.

This module provides safe parsing functions with external entity processing disabled
and proper validation to prevent XML External Entity (XXE) attacks.
"""

import logging
from typing import Any, Optional
from xml.etree.ElementTree import Element

import defusedxml.ElementTree as ET
import yaml

logger = logging.getLogger(__name__)


def parse_xml_string(
    xml_string: str, forbid_dtd: bool = True, forbid_entities: bool = True
) -> Optional[Element]:
    """
    Safely parse an XML string with XXE protection.

    Args:
        xml_string: The XML content as a string
        forbid_dtd: Whether to forbid DTD (Document Type Definition) processing
        forbid_entities: Whether to forbid entity expansion

    Returns:
        Parsed XML Element or None if parsing fails

    Raises:
        ET.ParseError: If the XML is malformed
        ValueError: If DTD or entities are detected when forbidden
    """
    try:
        # defusedxml automatically disables external entity processing
        root = ET.fromstring(
            xml_string, forbid_dtd=forbid_dtd, forbid_entities=forbid_entities
        )
        logger.debug("Successfully parsed XML string")
        return root
    except ET.ParseError as exc:
        logger.error("XML parse error: %s", exc)
        raise
    except ValueError as exc:
        logger.error("XML validation error (DTD/entity check): %s", exc)
        raise


def parse_xml_file(
    file_path: str, forbid_dtd: bool = True, forbid_entities: bool = True
) -> Optional[Element]:
    """
    Safely parse an XML file with XXE protection.

    Args:
        file_path: Path to the XML file
        forbid_dtd: Whether to forbid DTD processing
        forbid_entities: Whether to forbid entity expansion

    Returns:
        Parsed XML Element or None if parsing fails

    Raises:
        FileNotFoundError: If the file doesn't exist
        ET.ParseError: If the XML is malformed
        ValueError: If DTD or entities are detected when forbidden
    """
    try:
        tree = ET.parse(
            file_path, forbid_dtd=forbid_dtd, forbid_entities=forbid_entities
        )
        root = tree.getroot()
        logger.info("Successfully parsed XML file: %s", file_path)
        return root
    except FileNotFoundError:
        logger.error("XML file not found: %s", file_path)
        raise
    except ET.ParseError as exc:
        logger.error("XML parse error in %s: %s", file_path, exc)
        raise
    except ValueError as exc:
        logger.error("XML validation error in %s: %s", file_path, exc)
        raise


def safe_yaml_load(content: str) -> Any:
    """
    Safely load YAML content using yaml.safe_load to prevent arbitrary code execution.

    This function is a wrapper around yaml.safe_load that adds logging and
    consistent error handling. It prevents loading of arbitrary Python objects.

    Args:
        content: YAML content as a string

    Returns:
        Parsed YAML data (typically dict, list, or primitive types)

    Raises:
        yaml.YAMLError: If the YAML is malformed
    """
    try:
        data = yaml.safe_load(content)
        logger.debug("Successfully parsed YAML content")
        return data
    except yaml.YAMLError as exc:
        logger.error("YAML parse error: %s", exc)
        raise


def safe_yaml_load_file(file_path: str) -> Any:
    """
    Safely load YAML content from a file.

    Args:
        file_path: Path to the YAML file

    Returns:
        Parsed YAML data

    Raises:
        FileNotFoundError: If the file doesn't exist
        yaml.YAMLError: If the YAML is malformed
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        logger.info("Successfully loaded YAML file: %s", file_path)
        return data
    except FileNotFoundError:
        logger.error("YAML file not found: %s", file_path)
        raise
    except yaml.YAMLError as exc:
        logger.error("YAML parse error in %s: %s", file_path, exc)
        raise
    except IOError as exc:
        logger.error("IO error reading YAML file %s: %s", file_path, exc)
        raise


def validate_xml_content_type(content_type: Optional[str]) -> bool:
    """
    Validate if a content type indicates XML content.

    Args:
        content_type: HTTP Content-Type header value

    Returns:
        True if content type is XML-based, False otherwise
    """
    if not content_type:
        return False
    xml_types = [
        "application/xml",
        "text/xml",
        "application/xhtml+xml",
        "application/rss+xml",
        "application/atom+xml",
    ]
    content_type_lower = content_type.lower().split(";")[0].strip()
    return content_type_lower in xml_types
