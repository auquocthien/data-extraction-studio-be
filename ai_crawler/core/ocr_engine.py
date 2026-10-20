"""
OCR Engine for AI Crawler.
Wraps Tesseract OCR with image preprocessing for fallback text extraction.
"""

import os
import shutil
from typing import Optional, Dict, Any
from PIL import Image, ImageEnhance, ImageFilter

class OCREngine:
    def __init__(self):
        self.tesseract_available = bool(shutil.which("tesseract"))

    def is_available(self) -> bool:
        return self.tesseract_available

    def preprocess_image(self, image_path: str) -> Image.Image:
        """Enhance image contrast and convert to grayscale for optimal OCR accuracy."""
        img = Image.open(image_path).convert("L")  # Grayscale
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.8)  # Increase contrast
        img = img.filter(ImageFilter.SHARPEN)
        return img

    def extract_text(self, image_path: str, lang: str = "vie+eng") -> Dict[str, Any]:
        """
        Extract text from an image.
        Returns: {"success": bool, "text": str, "error": Optional[str]}
        """
        if not os.path.exists(image_path):
            return {"success": False, "text": "", "error": f"Không tìm thấy file ảnh: {image_path}"}

        if not self.tesseract_available:
            return {
                "success": False,
                "text": "",
                "error": "Tesseract OCR chưa được cài đặt trên hệ thống (sudo pacman -S tesseract tesseract-data-eng tesseract-data-vie)."
            }

        try:
            import pytesseract
            img = self.preprocess_image(image_path)
            
            # Check available languages
            try:
                available_langs = pytesseract.get_languages()
                chosen_lang = "eng"
                if "vie" in available_langs:
                    chosen_lang = "vie+eng"
            except Exception:
                chosen_lang = "eng"

            text = pytesseract.image_to_string(img, lang=chosen_lang)
            clean_text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
            return {"success": True, "text": clean_text, "error": None}
        except Exception as e:
            return {"success": False, "text": "", "error": f"Lỗi xử lý OCR: {str(e)}"}
