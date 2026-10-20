"""
Utils module for AI Crawler.
"""

from ai_crawler.utils.exporter import DataExporter
from ai_crawler.utils.regex_utils import (
    clean_ocr_noise,
    remove_cjk_characters,
    clean_phone_number,
    split_phone_fax,
    format_phone_fax,
    clean_email_address,
    extract_digits,
    has_digits,
    has_whitespace,
    is_valid_email_basic,
    sanitize_identifier,
    strip_markdown_code_fence,
    extract_json_array_fallback,
    extract_json_objects_fallback,
)

__all__ = [
    "DataExporter",
    "clean_ocr_noise",
    "remove_cjk_characters",
    "clean_phone_number",
    "split_phone_fax",
    "format_phone_fax",
    "clean_email_address",
    "extract_digits",
    "has_digits",
    "has_whitespace",
    "is_valid_email_basic",
    "sanitize_identifier",
    "strip_markdown_code_fence",
    "extract_json_array_fallback",
    "extract_json_objects_fallback",
]
