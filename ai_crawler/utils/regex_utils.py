"""
Regex Utilities for AI Crawler & Document Extraction Studio.
Provides centralized, reusable regex patterns and helper functions for
cleaning OCR noise, formatting phone/fax/email, validating data fields,
and parsing markdown/JSON structures.
"""

import re
from typing import Any, Optional, Tuple, List


# ----------------------------------------------------------------------
# 1. Text & OCR Cleaning Utilities
# ----------------------------------------------------------------------

# Pattern to keep valid alphanumeric, spaces, and common business punctuation
RE_VALID_TEXT_CHARS = re.compile(r'[^\w\s\.,/@\-&\(\)]')
RE_MULTI_SPACES = re.compile(r'\s+')
RE_CJK_CHARACTERS = re.compile(r'[\u4e00-\u9fff]+')


def clean_ocr_noise(text: Any) -> str:
    """
    Remove OCR noise characters and collapse consecutive spaces into a single space.
    Keeps letters, digits, standard punctuation, email symbols, and hyphens.
    """
    if not isinstance(text, str):
        return "" if text is None else str(text)
    cleaned = RE_VALID_TEXT_CHARS.sub('', text)
    return RE_MULTI_SPACES.sub(' ', cleaned).strip()


def remove_cjk_characters(text: Any) -> str:
    """
    Strip Chinese / Japanese / Korean (CJK) ideographs (\\u4e00 - \\u9fff)
    frequently mixed into company names or bilingual invoices.
    """
    if not isinstance(text, str):
        return "" if text is None else str(text)
    cleaned = RE_CJK_CHARACTERS.sub('', text)
    return RE_MULTI_SPACES.sub(' ', cleaned).strip()


# ----------------------------------------------------------------------
# 2. Contact Information Utilities (Phone, Fax, Email)
# ----------------------------------------------------------------------

RE_FAX_SPLIT = re.compile(r'(?i)fax', re.IGNORECASE)
RE_PHONE_ALLOWED_CHARS = re.compile(r'[^\d\+\-\s\(\)]')
RE_ONLY_DIGITS = re.compile(r'[^\d]')
RE_HAS_DIGITS = re.compile(r'\d')
RE_HAS_WHITESPACE = re.compile(r'\s')


def clean_phone_number(phone: Any) -> str:
    """
    Clean individual phone or mobile number string, preserving digits, +, -, and ().
    """
    if not isinstance(phone, str):
        return "" if phone is None else str(phone)
    cleaned = RE_PHONE_ALLOWED_CHARS.sub('', phone).strip()
    return RE_MULTI_SPACES.sub(' ', cleaned)


def split_phone_fax(text: Any) -> Tuple[str, str]:
    """
    Extracts Tel and Fax from mixed contact string (e.g., '028 3822 1234 Fax: 028 3822 5678').
    Returns tuple: (cleaned_tel, cleaned_fax).
    """
    if not isinstance(text, str):
        return ("", "")

    if RE_FAX_SPLIT.search(text):
        parts = RE_FAX_SPLIT.split(text, maxsplit=1)
        tel_raw, fax_raw = parts[0], parts[1]
    else:
        tel_raw, fax_raw = text, ""

    tel_clean = clean_phone_number(tel_raw)
    fax_clean = clean_phone_number(fax_raw)
    return (tel_clean, fax_clean)


def format_phone_fax(text: Any) -> str:
    """
    Formats combined phone and fax into readable string: 'Tel: ... Fax: ...'.
    """
    tel, fax = split_phone_fax(text)
    result = []
    if tel:
        result.append(f"Tel: {tel}")
    if fax:
        result.append(f"Fax: {fax}")
    return " ".join(result)


def clean_email_address(email: Any) -> str:
    """
    Remove all whitespace from email address (common OCR mistake around '@' or '.').
    """
    if not isinstance(email, str):
        return "" if email is None else str(email)
    return RE_MULTI_SPACES.sub('', email).strip()


def extract_digits(text: Any) -> str:
    """
    Extract only numerical digits (0-9) from text, discarding all formatting.
    """
    if not isinstance(text, str):
        return "" if text is None else str(text)
    return RE_ONLY_DIGITS.sub('', text)


# ----------------------------------------------------------------------
# 3. Validation & Check Helpers
# ----------------------------------------------------------------------

def has_digits(text: Any) -> bool:
    """Check if string contains at least one numerical digit."""
    if not isinstance(text, str):
        return False
    return bool(RE_HAS_DIGITS.search(text))


def has_whitespace(text: Any) -> bool:
    """Check if string contains any whitespace character."""
    if not isinstance(text, str):
        return False
    return bool(RE_HAS_WHITESPACE.search(text))


def is_valid_email_basic(email: Any) -> bool:
    """
    Check if text roughly matches standard email format (contains @, domain, and no whitespace).
    """
    if not isinstance(email, str) or not email.strip():
        return False
    email_clean = email.strip()
    if has_whitespace(email_clean):
        return False
    # Standard loose email pattern: non-spaces + @ + non-spaces + . + non-spaces
    return bool(re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email_clean))


# ----------------------------------------------------------------------
# 4. Identifier & Filename Sanitization
# ----------------------------------------------------------------------

RE_SAFE_IDENTIFIER = re.compile(r'[^a-zA-Z0-9_\-]')


def sanitize_identifier(name: str, replacement: str = '_') -> str:
    """
    Sanitize label names, filenames, or IDs to contain only safe alphanumeric and underscore/dash.
    Collapses multiple consecutive replacement characters into one and strips edges.
    """
    if not name:
        return "unnamed"
    cleaned = RE_SAFE_IDENTIFIER.sub(replacement, name)
    if replacement:
        cleaned = re.sub(re.escape(replacement) + r'+', replacement, cleaned)
    return cleaned.strip(replacement) or "unnamed"


# ----------------------------------------------------------------------
# 5. Markdown & AI Response Parsing Helpers
# ----------------------------------------------------------------------

RE_MD_CODE_START = re.compile(r"^```(json)?\s*", re.MULTILINE)
RE_MD_CODE_END = re.compile(r"```$", re.MULTILINE)
RE_JSON_ARRAY = re.compile(r"\[\s*\{.*?\}\s*\]", re.DOTALL)
RE_JSON_OBJECTS = re.compile(r"\{[^{}]*\}")


def strip_markdown_code_fence(content: str) -> str:
    """
    Strips ```json ... ``` code fence delimiters returned by LLMs.
    """
    if not content:
        return ""
    clean = RE_MD_CODE_START.sub("", content.strip())
    clean = RE_MD_CODE_END.sub("", clean.strip())
    return clean.strip()


def extract_json_array_fallback(text: str) -> Optional[str]:
    """
    Regex fallback to locate and extract a JSON array [ {...}, ... ] inside noisy text.
    """
    match = RE_JSON_ARRAY.search(text)
    return match.group(0) if match else None


def extract_json_objects_fallback(text: str) -> List[str]:
    """
    Finds all individual JSON-like objects {...} inside string.
    """
    return [m.group(0) for m in RE_JSON_OBJECTS.finditer(text)]
