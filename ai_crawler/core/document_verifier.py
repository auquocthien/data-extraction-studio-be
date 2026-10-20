"""
Bidirectional Verification Engine for Document Extraction.
Cross-validates extracted CSV data against original page coordinates & cropped visuals.
Detects:
- Truncated text (e.g., missing currency symbol or leading/trailing digits)
- Mismatched fields (e.g. tax percentage instead of total amount)
- Empty or abnormal patterns
- Layout drift
Provides:
- Status: 'valid' | 'warning' | 'error'
- Diagnosis reason
- Suggested fix value and expanded coordinates
"""

import re
import io
import base64
import logging
from typing import Dict, Any, List, Optional
from PIL import Image

from ai_crawler.utils.regex_utils import (
    extract_digits,
    clean_email_address,
    has_digits,
    has_whitespace,
    sanitize_identifier,
)

logger = logging.getLogger("document_verifier")


class DocumentVerifier:
    def __init__(self, ollama_host: Optional[str] = None):
        self.ollama_host = ollama_host

    @staticmethod
    def verify_cell_heuristic(
        field_name: str,
        value: str,
        coords: List[float],
        page_width: float,
        page_height: float,
        raw_box_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fast heuristic validation (offline, 0ms, free).
        Flags potential anomalies in extracted field values.
        """
        val_clean = str(value).strip() if value else ""
        field_lower = field_name.lower()

        status = "valid"
        diagnosis = "Khớp và hợp lệ"
        suggested_val = None
        suggested_coords = None

        # 1. Check for empty values
        if not val_clean:
            return {
                "status": "error",
                "diagnosis": "Vùng chọn không có chữ hoặc rỗng",
                "suggested_value": None,
                "suggested_coords": None
            }

        # 2. Check for Phone Number format
        if any(k in field_lower for k in ["sđt", "phone", "tel", "di động", "fax"]):
            digits = extract_digits(val_clean)
            if len(digits) < 7:
                status = "warning"
                diagnosis = f"Số điện thoại quá ngắn ({len(digits)} số), nghi ngờ bị cắt hụt"
            elif len(digits) > 15:
                status = "warning"
                diagnosis = f"Số điện thoại quá dài ({len(digits)} số), có thể dính cả văn bản lân cận"

        # 3. Check for Email format
        elif "email" in field_lower or "mail" in field_lower:
            if "@" not in val_clean or "." not in val_clean:
                status = "error"
                diagnosis = "Định dạng email không hợp lệ (thiếu @ hoặc tên miền)"
            elif has_whitespace(val_clean):
                status = "warning"
                diagnosis = "Email chứa khoảng trắng, có thể do OCR tách rời ký tự"
                suggested_val = clean_email_address(val_clean)

        # 4. Check for Total / Amount format
        elif any(k in field_lower for k in ["tiền", "amount", "total", "giá", "price"]):
            # Check if value accidentally captured % (Tax instead of Total)
            if "%" in val_clean:
                status = "error"
                diagnosis = "Giá trị chứa ký tự %, nghi ngờ bị trôi lệch vào ô Thuế suất (Tax)"
            elif not has_digits(val_clean):
                status = "error"
                diagnosis = "Không tìm thấy số tiền hợp lệ trong ô dữ liệu"

        # 5. Check for Date format
        elif "ngày" in field_lower or "date" in field_lower:
            has_numbers = has_digits(val_clean)
            has_separator = any(sep in val_clean for sep in ['/', '-', '.'])
            if not (has_numbers and has_separator):
                status = "warning"
                diagnosis = "Không đúng định dạng ngày tháng thông thường (DD/MM/YYYY)"

        # 6. Check for boundary cutoffs (box touching edge or very small height)
        box_w = abs(coords[2] - coords[0])
        box_h = abs(coords[3] - coords[1])
        if box_h < 8:
            status = "warning"
            diagnosis = "Chiều cao vùng chọn quá nhỏ (< 8pt), có thể cắt ngang thân chữ"
            # Suggest expanding height slightly
            suggested_coords = [
                coords[0],
                max(0.0, coords[1] - 4),
                coords[2],
                min(page_height, coords[3] + 4)
            ]

        return {
            "status": status,
            "diagnosis": diagnosis,
            "suggested_value": suggested_val,
            "suggested_coords": suggested_coords
        }

    def verify_batch(
        self,
        extracted_rows: List[Dict[str, Any]],
        template_coords: Dict[str, List[float]],
        page_dimensions: List[tuple],
        page_coords: Optional[Dict[str, Dict[str, List[float]]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Runs verification over all extracted records and outputs structured review items.
        Safely casts page indices and coordinates to prevent runtime type errors.
        """
        review_items = []
        for row in extracted_rows:
            raw_page_num = row.get("page_number", 1)
            try:
                page_num = int(raw_page_num)
            except (ValueError, TypeError):
                page_num = 1

            page_idx = page_num - 1
            pw, ph = (612.0, 792.0)
            if 0 <= page_idx < len(page_dimensions):
                pw, ph = page_dimensions[page_idx]

            try:
                dx = float(row.get("_offset_dx", 0.0))
                dy = float(row.get("_offset_dy", 0.0))
            except (ValueError, TypeError):
                dx, dy = 0.0, 0.0

            # Determine coordinates for this specific page
            active_coords_map = template_coords
            if page_coords:
                page_key_str = str(page_idx)
                if page_key_str in page_coords:
                    active_coords_map = page_coords[page_key_str]
                elif str(page_num) in page_coords:
                    active_coords_map = page_coords[str(page_num)]

            for field_name, value in row.items():
                if field_name.startswith("_") or field_name == "page_number":
                    continue

                # Base coordinates for this field
                raw_coords = active_coords_map.get(field_name, template_coords.get(field_name, [0.0, 0.0, 100.0, 30.0]))
                try:
                    base_coords = [float(c) for c in raw_coords]
                except (ValueError, TypeError):
                    base_coords = [0.0, 0.0, 100.0, 30.0]

                actual_coords = [
                    round(base_coords[0] + dx, 2),
                    round(base_coords[1] + dy, 2),
                    round(base_coords[2] + dx, 2),
                    round(base_coords[3] + dy, 2)
                ]

                check = self.verify_cell_heuristic(
                    field_name=field_name,
                    value=value,
                    coords=actual_coords,
                    page_width=pw,
                    page_height=ph
                )

                item_id = f"p{page_num}_{sanitize_identifier(field_name)}"
                review_items.append({
                    "id": item_id,
                    "page_number": page_num,
                    "field_name": field_name,
                    "extracted_value": str(value) if value is not None else "",
                    "status": check["status"],
                    "diagnosis": check["diagnosis"],
                    "suggested_value": check["suggested_value"],
                    "suggested_coords": check["suggested_coords"],
                    "coords": actual_coords
                })

        return review_items
