"""
Document Extraction Engine
Extracted and enhanced from pdf_to_text.py for standalone server and API use.
Includes:
- PyMuPDF fast rendering (UI Point 72 DPI & OpenCV 216 DPI)
- OpenCV table grid morphology cell detection
- pdfplumber native text extraction with auto-coordinate clamping
- Layout drift auto-alignment calculation (dx, dy)
- Data cleaning pipeline (Vietnamese/Chinese text, phone/fax formatting, email)
- Visual thumbnail cropping for Review & Visual Inspector
"""

import os
import io
import re
import json
import logging
from typing import List, Dict, Tuple, Optional, Any
from pathlib import Path
from PIL import Image

import pymupdf  # PyMuPDF
import pdfplumber
import cv2
import numpy as np
import pandas as pd

from ai_crawler.utils.regex_utils import (
    clean_ocr_noise,
    remove_cjk_characters,
    clean_phone_number,
    format_phone_fax,
    clean_email_address,
)

logger = logging.getLogger("document_engine")


class DocumentEngine:
    def __init__(self, pdf_path: Optional[str] = None):
        self.pdf_path: Optional[str] = None
        self.doc_fitz: Optional[pymupdf.Document] = None
        self.doc_plumber: Optional[pdfplumber.PDF] = None
        self.num_pages: int = 0
        self.page_dimensions: List[Tuple[float, float]] = []

        if pdf_path:
            self.load_pdf(pdf_path)

    def load_pdf(self, pdf_path: str):
        """Loads a PDF document for processing."""
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found at: {pdf_path}")

        self.close()
        self.pdf_path = pdf_path
        self.doc_fitz = pymupdf.open(pdf_path)
        self.doc_plumber = pdfplumber.open(pdf_path)
        self.num_pages = len(self.doc_fitz)
        self.page_dimensions = []

        for p in range(self.num_pages):
            page = self.doc_fitz.load_page(p)
            rect = page.rect
            self.page_dimensions.append((float(rect.width), float(rect.height)))

        logger.info(f"Loaded PDF: {pdf_path} ({self.num_pages} pages)")

    def close(self):
        """Release open PDF handles."""
        if self.doc_fitz:
            try:
                self.doc_fitz.close()
            except Exception:
                pass
            self.doc_fitz = None

        if self.doc_plumber:
            try:
                self.doc_plumber.close()
            except Exception:
                pass
            self.doc_plumber = None

    def get_info(self) -> Dict[str, Any]:
        """Returns metadata about the currently loaded document."""
        if not self.doc_fitz:
            return {"loaded": False, "num_pages": 0, "pages": []}

        pages_meta = []
        for idx, (w, h) in enumerate(self.page_dimensions):
            pages_meta.append({
                "page_number": idx + 1,
                "width": round(w, 2),
                "height": round(h, 2)
            })

        return {
            "loaded": True,
            "filename": Path(self.pdf_path).name if self.pdf_path else "",
            "num_pages": self.num_pages,
            "pages": pages_meta
        }

    def render_page_image(self, page_index: int, dpi: int = 72, image_format: str = "PNG") -> bytes:
        """
        Renders a page at specified DPI.
        DPI 72 matches PDF Point coordinate scale 1:1.
        """
        if not self.doc_fitz:
            raise ValueError("No PDF loaded")
        if not (0 <= page_index < self.num_pages):
            raise IndexError(f"Page index {page_index} out of range (0..{self.num_pages-1})")

        page = self.doc_fitz.load_page(page_index)
        pix = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        buf = io.BytesIO()
        img.save(buf, format=image_format.upper())
        return buf.getvalue()

    def crop_region_image(
        self, 
        page_index: int, 
        coords: List[float], 
        dpi: int = 144, 
        padding: int = 6
    ) -> bytes:
        """
        Crops an image at the specified [x1, y1, x2, y2] coordinates (in PDF points).
        Useful for Visual Inspector thumbnails.
        """
        if not self.doc_fitz:
            raise ValueError("No PDF loaded")
        if not (0 <= page_index < self.num_pages):
            raise IndexError("Page index out of range")

        page = self.doc_fitz.load_page(page_index)
        w, h = self.page_dimensions[page_index]

        x1, x2 = sorted([coords[0], coords[2]])
        y1, y2 = sorted([coords[1], coords[3]])

        # Add slight padding and clamp to boundaries
        safe_rect = pymupdf.Rect(
            max(0.0, x1 - padding),
            max(0.0, y1 - padding),
            min(w, x2 + padding),
            min(h, y2 + padding)
        )

        pix = page.get_pixmap(dpi=dpi, clip=safe_rect)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()

    def detect_table_cells(self, page_index: int, cv2_dpi: int = 216) -> List[List[float]]:
        """
        Uses OpenCV morphology to detect table cell bounding boxes on the page.
        Returns coordinates scaled to PDF Points (72 DPI).
        """
        if not self.doc_fitz:
            raise ValueError("No PDF loaded")
        if not (0 <= page_index < self.num_pages):
            return []

        page = self.doc_fitz.load_page(page_index)
        pix_cv2 = page.get_pixmap(dpi=cv2_dpi)
        img_cv2_pil = Image.frombytes("RGB", [pix_cv2.width, pix_cv2.height], pix_cv2.samples)

        scale = cv2_dpi / 72.0

        img_cv = cv2.cvtColor(np.array(img_cv2_pil), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)

        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2
        )

        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 1))
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 10))

        h_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel, iterations=2)
        v_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel, iterations=2)

        grid = cv2.addWeighted(h_lines, 0.5, v_lines, 0.5, 0.0)
        _, grid = cv2.threshold(grid, 50, 255, cv2.THRESH_BINARY)

        contours, _ = cv2.findContours(grid, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        cells = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            # Filter noise / tiny contours and full page borders
            if w > 25 and h > 12 and (w * h < img_cv.shape[0] * img_cv.shape[1] * 0.9):
                # Scale back to 72 DPI (PDF point units)
                bx1 = round(x / scale, 2)
                by1 = round(y / scale, 2)
                bx2 = round((x + w) / scale, 2)
                by2 = round((y + h) / scale, 2)
                cells.append([bx1, by1, bx2, by2])

        # Sort top-to-bottom, left-to-right (grid order)
        cells = sorted(cells, key=lambda b: (b[1] // 15, b[0]))
        return cells

    def extract_text_native_from_page(self, page_index: int, coords: List[float]) -> str:
        """
        Extracts text from coordinates [x1, y1, x2, y2] using native PDF text layer.
        """
        if not self.doc_plumber:
            raise ValueError("No PDF loaded")
        if not (0 <= page_index < self.num_pages):
            return ""

        page_obj = self.doc_plumber.pages[page_index]
        w, h = float(page_obj.width), float(page_obj.height)

        x1, x2 = sorted([coords[0], coords[2]])
        y1, y2 = sorted([coords[1], coords[3]])

        safe_coords = (
            max(0.0, min(w, x1)),
            max(0.0, min(h, y1)),
            max(0.0, min(w, x2)),
            max(0.0, min(h, y2))
        )

        if safe_coords[2] <= safe_coords[0] or safe_coords[3] <= safe_coords[1]:
            return ""

        try:
            cropped = page_obj.crop(safe_coords)
            text = cropped.extract_text(layout=True)
            return " ".join(text.replace("\n", " ").split()).strip() if text else ""
        except Exception as e:
            logger.warning(f"Failed to extract native text at {safe_coords}: {e}")
            return ""

    @staticmethod
    def calculate_alignment_offset(
        source_boxes: List[List[float]], 
        target_boxes: List[List[float]]
    ) -> Tuple[float, float]:
        """
        Calculates (dx, dy) offset between a template page and target page
        to compensate for layout drift.
        """
        if not source_boxes or not target_boxes:
            return 0.0, 0.0

        ref_box = source_boxes[0]
        closest_box = min(
            target_boxes, 
            key=lambda b: (b[0] - ref_box[0]) ** 2 + (b[1] - ref_box[1]) ** 2
        )
        dx = closest_box[0] - ref_box[0]
        dy = closest_box[1] - ref_box[1]

        # Only accept reasonable shifts (< 50 points)
        if abs(dx) < 50.0 and abs(dy) < 50.0:
            return round(dx, 2), round(dy, 2)
        return 0.0, 0.0

    def batch_extract(
        self,
        template_coords: Dict[str, List[float]],
        start_page: int,
        end_page: int,
        auto_align: bool = True,
        source_page_idx: int = 0,
        page_coords: Optional[Dict[str, Dict[str, List[float]]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Extracts fields across a range of pages using template coordinates or page-specific coordinates.
        Supports layout drift auto-alignment.
        """
        if not self.doc_plumber or not self.doc_fitz:
            raise ValueError("No PDF loaded")

        results = []
        source_boxes = []

        if auto_align and (0 <= source_page_idx < self.num_pages):
            source_boxes = self.detect_table_cells(source_page_idx)

        for p in range(max(0, start_page), min(self.num_pages, end_page + 1)):
            page_data: Dict[str, Any] = {"page_number": p + 1}
            dx, dy = 0.0, 0.0

            if auto_align and source_boxes and p != source_page_idx:
                target_boxes = self.detect_table_cells(p)
                dx, dy = self.calculate_alignment_offset(source_boxes, target_boxes)

            # Store the computed offset for inspection
            page_data["_offset_dx"] = dx
            page_data["_offset_dy"] = dy

            # Check if this page has dedicated coordinates
            active_coords = template_coords
            if page_coords:
                if str(p) in page_coords and page_coords[str(p)]:
                    active_coords = page_coords[str(p)]
                elif str(p + 1) in page_coords and page_coords[str(p + 1)]:
                    active_coords = page_coords[str(p + 1)]

            for field_name, coords in active_coords.items():
                try:
                    c = [float(x) for x in coords]
                except (ValueError, TypeError):
                    continue
                nx1 = c[0] + dx
                ny1 = c[1] + dy
                nx2 = c[2] + dx
                ny2 = c[3] + dy
                text = self.extract_text_native_from_page(p, [nx1, ny1, nx2, ny2])
                page_data[field_name] = text

            results.append(page_data)

        return results

    # --- Data Cleaning Methods (Delegated to ai_crawler.utils.regex_utils) ---

    @staticmethod
    def clean_text(text: Any) -> str:
        """General text cleanup: remove OCR noise and multiple spaces."""
        return clean_ocr_noise(text)

    @staticmethod
    def remove_chinese(text: Any) -> str:
        """Remove CJK Unified Ideographs (Chinese characters)."""
        return remove_cjk_characters(text)

    @staticmethod
    def clean_phone_fax(text: Any) -> str:
        """Extract and format Tel & Fax from mixed text."""
        return format_phone_fax(text)

    @staticmethod
    def clean_simple_phone(phone: Any) -> str:
        """Extract clean phone number for individual contacts."""
        return clean_phone_number(phone)

    @staticmethod
    def clean_email(email: Any) -> str:
        """Clean email (remove all whitespace)."""
        return clean_email_address(email)

    def clean_extracted_data(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Applies smart cleaning rules across standard company/invoice fields.
        """
        cleaned = []
        for row in data:
            new_row = dict(row)
            for k, v in new_row.items():
                if k.startswith("_"):
                    continue
                k_lower = k.lower()

                # General text cleanup first
                val = self.clean_text(v)

                # Chinese removal for company names
                if "tên công ty" in k_lower or "company" in k_lower:
                    val = self.remove_chinese(val)

                # Tel/Fax parsing
                elif "fax" in k_lower or "văn phòng - sđt" in k_lower or "nhà máy - sđt" in k_lower:
                    val = self.clean_phone_fax(val)

                # Individual phone
                elif "sđt" in k_lower or "phone" in k_lower or "tel" in k_lower or "di động" in k_lower:
                    val = self.clean_simple_phone(val)

                # Email
                elif "email" in k_lower or "mail" in k_lower:
                    val = self.clean_email(val)

                new_row[k] = val

            cleaned.append(new_row)
        return cleaned

    @staticmethod
    def export_to_csv(
        data: List[Dict[str, Any]], 
        output_filepath: str, 
        columns: Optional[List[str]] = None
    ) -> str:
        """
        Exports data to CSV with utf-8-sig encoding for perfect Vietnamese character support in Excel.
        """
        df = pd.DataFrame(data)
        # Drop internal debug columns starting with '_'
        drop_cols = [c for c in df.columns if c.startswith("_")]
        if drop_cols:
            df.drop(columns=drop_cols, inplace=True)

        if columns:
            valid_cols = [c for c in columns if c in df.columns]
            df = df[valid_cols]

        os.makedirs(os.path.dirname(output_filepath), exist_ok=True)
        df.to_csv(output_filepath, index=False, encoding='utf-8-sig')
        logger.info(f"Exported {len(df)} rows to CSV: {output_filepath}")
        return output_filepath
