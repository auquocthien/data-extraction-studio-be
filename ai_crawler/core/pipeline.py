"""
Crawler Pipeline Orchestrator for AI Crawler.
Coordinates Tiered Extraction:
  Tier 1: Network API Interception (Instant, Clean JSON)
  Tier 2: DOM Hydration Data Extraction
  Tier 3: DOM Visible Text + Local Ollama Parser
  Tier 4: Screenshot + Tesseract OCR + Local Ollama Parser
"""

import time
from typing import List, Dict, Any, Optional, Callable
from urllib.parse import urlparse

from ai_crawler.config import DEFAULT_HEADLESS, IS_CLOUD_RUN, HAS_DISPLAY
from ai_crawler.core.scraper import PlaywrightScraper
from ai_crawler.core.ocr_engine import OCREngine
from ai_crawler.core.ai_parser import AIParser
from ai_crawler.utils.exporter import DataExporter

class CrawlerPipeline:
    def __init__(
        self,
        headless: bool = DEFAULT_HEADLESS,
        progress_callback: Optional[Callable[[str, int], None]] = None
    ):
        self.headless = headless
        self.callback = progress_callback or (lambda msg, pct: None)
        self.ocr_engine = OCREngine()
        self.ai_parser = AIParser()
        self.exporter = DataExporter()

    def _notify(self, msg: str, pct: int):
        try:
            self.callback(msg, pct)
        except Exception:
            pass

    def run(
        self,
        url: str,
        fields: Optional[List[str]] = None,
        headless: Optional[bool] = None,
        wait_seconds: int = 5,
        wait_time_sec: Optional[int] = None,
        query_description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute the full tiered extraction pipeline.
        """
        start_time = time.time()
        effective_wait = wait_time_sec if wait_time_sec is not None else wait_seconds
        if IS_CLOUD_RUN or not HAS_DISPLAY:
            is_headless = True
        else:
            is_headless = self.headless if headless is None else headless

        if query_description and not fields:
            fields = [f.strip() for f in query_description.split(",") if f.strip()]

        self._notify(f"Bắt đầu quy trình cào dữ liệu cho: {url}", 5)

        scraper = PlaywrightScraper(
            headless=is_headless,
            progress_callback=self.callback
        )
        scrape_res = scraper.scrape(url, wait_seconds=effective_wait, take_screenshot=True)

        if scrape_res.get("status") == "error":
            return {
                "success": False,
                "url": url,
                "error": scrape_res.get("error", "Lỗi không xác định khi truy cập trang."),
                "message": f"Thất bại khi cào trang: {scrape_res.get('error')}"
            }

        extracted_records: List[Dict[str, Any]] = []
        method = "none"
        method_display = "Không xác định"

        # =========================================================================
        # TIER 1: Network Interception (API JSON)
        # =========================================================================
        intercepted = scrape_res.get("intercepted_json", [])
        if intercepted:
            self._notify(f"Đang bóc tách dữ liệu từ {len(intercepted)} gói tin API JSON...", 75)
            for item in intercepted:
                payload = item.get("payload")
                if isinstance(payload, list):
                    for sub in payload:
                        if isinstance(sub, dict):
                            extracted_records.append(sub)
                elif isinstance(payload, dict):
                    # Check if there is an inner list like {"data": [...], "products": [...], "items": [...]}
                    found_list = False
                    for key, val in payload.items():
                        if isinstance(val, list) and val and isinstance(val[0], dict):
                            extracted_records.extend(val)
                            found_list = True
                            break
                    if not found_list:
                        extracted_records.append(payload)

            if extracted_records:
                method = "network_json"
                method_display = "⚡ Bắt gói tin API JSON trực tiếp (Network Interception)"
                self._notify(f"✅ Bóc tách thành công {len(extracted_records)} bản ghi từ API JSON!", 85)

        # =========================================================================
        # TIER 2: Hydration Script Data
        # =========================================================================
        if not extracted_records and scrape_res.get("hydration_data"):
            self._notify("Bóc tách dữ liệu từ Hydration Script...", 75)
            hyd_data = scrape_res.get("hydration_data")
            if isinstance(hyd_data, dict):
                # Search for arrays in hydration data
                for k, v in hyd_data.items():
                    if isinstance(v, list) and v and isinstance(v[0], dict):
                        extracted_records.extend(v)
                        break
            if extracted_records:
                method = "hydration_json"
                method_display = "✨ Dữ liệu Hydration Script HTML"

        # =========================================================================
        # TIER 2.5: Smart DOM Repeater Extraction (Zero CPU Overhead)
        # =========================================================================
        dom_items = scrape_res.get("dom_items", [])
        if not extracted_records and dom_items:
            extracted_records = dom_items
            method = "dom_repeater"
            method_display = "⚡ Bóc tách DOM lặp lại thông minh (Smart DOM Cards)"
            self._notify(f"✅ Đã trích xuất {len(extracted_records)} mục cấu trúc từ DOM!", 85)

        # =========================================================================
        # TIER 3: DOM Visible Text + Local Ollama AI Parser
        # =========================================================================
        dom_text = scrape_res.get("dom_text", "")
        if not extracted_records and len(dom_text) > 100:
            self._notify("Không có API JSON. Đang chuyển sang Tầng 3: Bóc tách văn bản DOM qua Local AI...", 80)
            if self.ai_parser.is_available():
                parsed = self.ai_parser.parse_to_structured_json(
                    dom_text,
                    target_entity="sản phẩm / bài viết / mục thông tin",
                    fields=fields
                )
                if parsed:
                    extracted_records = parsed
                    method = "dom_ai"
                    method_display = "📄 Bóc tách DOM + Local AI (Ollama)"
                    self._notify(f"✅ Local AI đã cấu trúc hóa thành công {len(extracted_records)} mục!", 88)
            else:
                self._notify("⚠️ Cảnh báo: Ollama local chưa bật, tạo bản ghi văn bản thô.", 85)
                extracted_records = [{"title": scrape_res.get("title"), "raw_content": dom_text[:500]}]
                method = "dom_raw"
                method_display = "📄 Văn bản thô DOM (Ollama offline)"

        # =========================================================================
        # TIER 4: Screenshot + Tesseract OCR + Local Ollama Parser
        # =========================================================================
        screenshot_path = scrape_res.get("screenshot_path")
        if not extracted_records and screenshot_path:
            self._notify("Đang kích hoạt Tầng 4: Chụp màn hình + OCR Tesseract...", 80)
            if self.ocr_engine.is_available():
                ocr_res = self.ocr_engine.extract_text(screenshot_path)
                ocr_text = ocr_res.get("text", "")
                if ocr_text:
                    self._notify(f"OCR hoàn tất ({len(ocr_text)} ký tự). Đưa qua AI chuẩn hóa...", 88)
                    if self.ai_parser.is_available():
                        extracted_records = self.ai_parser.parse_to_structured_json(ocr_text, fields=fields)
                    else:
                        extracted_records = [{"ocr_text": ocr_text[:600]}]
                    method = "ocr_ai"
                    method_display = "👁️ Nhận diện ảnh màn hình (Tesseract OCR + AI)"
            else:
                self._notify("Tesseract OCR chưa sẵn sàng trên máy.", 85)

        # Fallback if still empty: preserve page title and url
        if not extracted_records:
            extracted_records = [{
                "url": url,
                "title": scrape_res.get("title", ""),
                "note": "Trang đã được tải thành công, không tìm thấy danh sách lặp hoặc dữ liệu có cấu trúc."
            }]
            method = "basic_info"
            method_display = "ℹ️ Thông tin trang cơ bản"

        # =========================================================================
        # Export Data to CSV and JSON
        # =========================================================================
        self._notify("Đang lưu kết quả ra file CSV và JSON...", 92)
        parsed_url = urlparse(url)
        domain_name = parsed_url.netloc.replace(".", "_") or "crawl_result"
        json_path, csv_path = self.exporter.export(extracted_records, base_filename=domain_name)
        preview_table = self.exporter.create_preview_table(extracted_records, max_rows=5)

        elapsed = round(time.time() - start_time, 2)
        self._notify(f"🎉 Hoàn tất cào dữ liệu trong {elapsed}s!", 100)

        return {
            "success": True,
            "url": url,
            "title": scrape_res.get("title", ""),
            "method": method,
            "method_display": method_display,
            "records_count": len(extracted_records),
            "data": extracted_records,
            "preview": preview_table,
            "json_path": json_path,
            "csv_path": csv_path,
            "screenshot_path": screenshot_path,
            "duration_seconds": elapsed,
            "message": f"Đã thu thập thành công {len(extracted_records)} bản ghi bằng '{method_display}' trong {elapsed} giây."
        }
