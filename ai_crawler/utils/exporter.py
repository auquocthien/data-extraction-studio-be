"""
Data Exporter for AI Crawler.
Exports structured data to CSV, JSON, and creates tabular previews.
"""

import json
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple
import pandas as pd
from ai_crawler.config import EXPORTS_DIR

class DataExporter:
    def __init__(self, exports_dir: Path = EXPORTS_DIR):
        self.exports_dir = exports_dir
        self.exports_dir.mkdir(parents=True, exist_ok=True)

    def export(self, data: List[Dict[str, Any]], base_filename: str = "crawl_data") -> Tuple[str, str]:
        """
        Export list of dictionaries to both .json and .csv files.
        Returns: (json_filepath, csv_filepath)
        """
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in base_filename)[:40]
        
        json_path = self.exports_dir / f"{safe_name}_{timestamp}.json"
        csv_path = self.exports_dir / f"{safe_name}_{timestamp}.csv"

        # 1. Export JSON
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # 2. Export CSV using Pandas
        try:
            df = pd.json_normalize(data)
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        except Exception:
            # Fallback if normalization fails
            pd.DataFrame(data).to_csv(csv_path, index=False, encoding="utf-8-sig")

        return str(json_path), str(csv_path)

    def create_preview_table(self, data: List[Dict[str, Any]], max_rows: int = 5) -> Dict[str, Any]:
        """Generate summary columns and preview rows for UI display."""
        if not data:
            return {"columns": [], "rows": [], "total": 0}

        try:
            df = pd.json_normalize(data)
            columns = list(df.columns[:8])  # Max 8 columns for clean UI
            preview_rows = df[columns].head(max_rows).fillna("").to_dict(orient="records")
            return {
                "columns": columns,
                "rows": preview_rows,
                "total": len(df)
            }
        except Exception:
            return {
                "columns": list(data[0].keys()) if isinstance(data[0], dict) else ["data"],
                "rows": data[:max_rows],
                "total": len(data)
            }
