"""
Unit tests for ai_crawler.utils.regex_utils
"""

import unittest
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


class TestRegexUtils(unittest.TestCase):

    def test_clean_ocr_noise(self):
        raw = " Công  ty   TNHH   ABC !!! ###  123/4 @ Đường 5 - Q.1 (HCM)  "
        cleaned = clean_ocr_noise(raw)
        self.assertEqual(cleaned, "Công ty TNHH ABC 123/4 @ Đường 5 - Q.1 (HCM)")
        self.assertEqual(clean_ocr_noise(None), "")
        self.assertEqual(clean_ocr_noise(12345), "12345")

    def test_remove_cjk_characters(self):
        text = "Công ty TNHH Hóa Chất 广州化工厂 Vietnam Chemical"
        cleaned = remove_cjk_characters(text)
        self.assertEqual(cleaned, "Công ty TNHH Hóa Chất Vietnam Chemical")
        self.assertEqual(remove_cjk_characters("No Chinese Here"), "No Chinese Here")

    def test_clean_phone_number(self):
        raw = "  (+84) 028-3822 9999 [ext: 12]  "
        cleaned = clean_phone_number(raw)
        self.assertEqual(cleaned, "(+84) 028-3822 9999 12")

    def test_split_and_format_phone_fax(self):
        combined = "Tel: 028.3822.1111   FAX: (028) 3822.2222"
        tel, fax = split_phone_fax(combined)
        self.assertEqual(tel, "02838221111")
        self.assertIn("38222222", fax)

        # Realistic case
        text = "024 3822 1234 Fax: 024 3822 5678"
        tel, fax = split_phone_fax(text)
        self.assertEqual(tel, "024 3822 1234")
        self.assertEqual(fax, "024 3822 5678")

        formatted = format_phone_fax(text)
        self.assertEqual(formatted, "Tel: 024 3822 1234 Fax: 024 3822 5678")

    def test_clean_email_address(self):
        noisy_email = "  contact @ company .com.vn   "
        self.assertEqual(clean_email_address(noisy_email), "contact@company.com.vn")
        self.assertEqual(clean_email_address(None), "")

    def test_extract_digits(self):
        self.assertEqual(extract_digits("INV-2024-9982!"), "20249982")
        self.assertEqual(extract_digits("No digits"), "")
        self.assertEqual(extract_digits(99000), "99000")

    def test_has_digits_and_whitespace(self):
        self.assertTrue(has_digits("Order #123"))
        self.assertFalse(has_digits("No Numbers Here"))
        self.assertTrue(has_whitespace("has space"))
        self.assertFalse(has_whitespace("nospaces"))

    def test_is_valid_email_basic(self):
        self.assertTrue(is_valid_email_basic("user@test.org"))
        self.assertTrue(is_valid_email_basic("sales.dept@company.com.vn"))
        self.assertFalse(is_valid_email_basic("invalid email@test.com"))
        self.assertFalse(is_valid_email_basic("missing_at_domain.com"))
        self.assertFalse(is_valid_email_basic(""))

    def test_sanitize_identifier(self):
        self.assertEqual(sanitize_identifier("Invoice Total ($)"), "Invoice_Total")
        self.assertEqual(sanitize_identifier("Mã Số Thuế 2024"), "M_S_Thu_2024")
        self.assertEqual(sanitize_identifier("Valid_Name-123"), "Valid_Name-123")

    def test_markdown_and_json_parsing(self):
        llm_response = """
Here is the JSON output:
```json
[
  {"field": "Tax", "value": "10%"},
  {"field": "Total", "value": "1,000,000"}
]
```
Thank you.
"""
        stripped = strip_markdown_code_fence(llm_response)
        self.assertNotIn("```json", stripped)
        self.assertNotIn("```", stripped)

        array_match = extract_json_array_fallback(stripped)
        self.assertIsNotNone(array_match)
        self.assertIn('"field": "Tax"', array_match)

        objects = extract_json_objects_fallback(stripped)
        self.assertEqual(len(objects), 2)


if __name__ == "__main__":
    unittest.main()
