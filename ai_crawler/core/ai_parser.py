"""
AI Parser for AI Crawler.
Uses local Ollama (Singleton pattern) to structure raw text or OCR output into clean JSON.
"""

import json
import re
from typing import List, Dict, Any, Optional
import requests
from ai_crawler.config import OLLAMA_HOST, DEFAULT_OLLAMA_MODEL
from ai_crawler.utils.regex_utils import (
    strip_markdown_code_fence,
    extract_json_array_fallback,
    extract_json_objects_fallback,
)

class AIParser:
    _instance = None

    def __new__(cls, *args, **kwargs):
        """Ensure Singleton instance to avoid reloading overhead."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, host: str = OLLAMA_HOST, model: str = DEFAULT_OLLAMA_MODEL):
        if self._initialized:
            return
        self.host = host.rstrip("/")
        self.model = model
        self._initialized = True

    def is_available(self) -> bool:
        """Check if local Ollama server is running."""
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=2.0)
            return r.status_code == 200
        except Exception:
            return False

    def parse_to_structured_json(
        self,
        raw_text: str,
        target_entity: str = "items",
        fields: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Send raw text to local Ollama with instructions to extract structured records.
        Returns a list of extracted dictionaries.
        """
        if not raw_text or not raw_text.strip():
            return []

        fields_hint = f"Các trường cần bóc tách: {', '.join(fields)}" if fields else "Bóc tách các trường chính (tiêu đề, giá, mô tả, ngày tháng, thông số, trích dẫn, tác giả, v.v.)."
        
        # Limit text to 900 characters to keep local inference ultra-speedy on i5-4200U
        truncated_text = raw_text[:900]

        prompt = f"""Bạn là AI chuyên trích xuất thông tin thực tế từ văn bản web thành dữ liệu có cấu trúc.
Hãy đọc văn bản thô bên dưới và trích xuất danh sách các mục chính (như tiêu đề, nội dung, trích dẫn, tác giả, giá cả, v.v.).
{fields_hint}

QUY TẮC BẮT BUỘC:
1. Chỉ trả về DUY NHẤT một mảng JSON: [ {{"title": "...", "detail": "..."}}, ... ].
2. Giá trị trong JSON phải là thông tin thực tế lấy từ văn bản bên dưới, KHÔNG dùng dữ liệu giả.
3. Không viết bất kỳ lời giải thích hay câu chữ nào ngoài mã JSON.
4. Nếu không có dữ liệu thực tế, trả về [].

Văn bản thô:
\"\"\"
{truncated_text}
\"\"\"
JSON Array:"""

        try:
            resp = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": 250,
                        "temperature": 0.1
                    }
                },
                timeout=90.0
            )

            if resp.status_code != 200:
                print(f"[AIParser] Ollama status error: {resp.status_code} - {resp.text}")
                return []

            content = resp.json().get("response", "").strip()
            return self._extract_json_array(content)
        except Exception as e:
            print(f"[AIParser] Inference error: {e}")
            return []

    def _extract_json_array(self, content: str) -> List[Dict[str, Any]]:
        """Safely extract list of dictionaries from LLM output."""
        if not content:
            return []

        # Remove markdown code fences if present
        clean = strip_markdown_code_fence(content)

        # 1. Try parsing full content as JSON
        try:
            parsed = json.loads(clean)
            if isinstance(parsed, list):
                return [item for item in parsed if isinstance(item, dict)]
            elif isinstance(parsed, dict):
                for v in parsed.values():
                    if isinstance(v, list) and v and isinstance(v[0], dict):
                        return v
                return [parsed]
        except Exception:
            pass

        # 2. Try regex search for a JSON array [ {...}, ... ]
        raw_array = extract_json_array_fallback(clean)
        if raw_array:
            try:
                res = json.loads(raw_array)
                if isinstance(res, list):
                    return [x for x in res if isinstance(x, dict)]
            except Exception:
                pass

        # 3. Try finding individual JSON objects { ... } line by line
        objects = []
        for obj_str in extract_json_objects_fallback(clean):
            try:
                obj = json.loads(obj_str)
                if isinstance(obj, dict) and obj:
                    objects.append(obj)
            except Exception:
                pass

        return objects
