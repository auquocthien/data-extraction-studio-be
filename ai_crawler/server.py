"""
FastAPI Server for Data Extraction Studio.
Provides unified REST API for both Document Scan Mode and Website Scan Mode.
Run with: python -m ai_crawler.server or uvicorn ai_crawler.server:app --port 8000 --reload
"""

import os
import io
import json
import logging
import shutil
from typing import Dict, Any, List, Optional
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field

from ai_crawler.config import DOCUMENTS_DIR, TEMPLATES_DIR, EXPORTS_DIR
from ai_crawler.core.document_engine import DocumentEngine
from ai_crawler.core.document_verifier import DocumentVerifier
from ai_crawler.core.pipeline import CrawlerPipeline
from ai_crawler.utils.regex_utils import sanitize_identifier

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("server")

app = FastAPI(
    title="Data Extraction Studio API",
    description="Unified API for Document & Website Data Extraction",
    version="2.0.0"
)

# Enable CORS for Angular frontend (development ports 4200, 4300, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global in-memory DocumentEngine state
active_engine = DocumentEngine()
active_verifier = DocumentVerifier()


# --- Pydantic Request Models ---

class FieldCoordinate(BaseModel):
    name: str
    coords: List[float] = Field(..., description="[x1, y1, x2, y2] in PDF points")


class PreviewRequest(BaseModel):
    page_index: int = Field(0, description="0-indexed page index")
    fields: List[FieldCoordinate]


class BatchExtractRequest(BaseModel):
    template_coords: Dict[str, List[float]]
    start_page: int = Field(0, description="0-indexed start page")
    end_page: int = Field(0, description="0-indexed end page")
    auto_align: bool = Field(True, description="Enable layout drift offset calculation")
    clean_data: bool = Field(True, description="Apply Vietnamese/Chinese, Phone/Fax cleaning")
    source_page_index: int = Field(0, description="Template source page for alignment")
    page_coords: Optional[Dict[str, Dict[str, List[float]]]] = Field(None, description="Per-page coordinates mapping")


class VerificationRequest(BaseModel):
    extracted_rows: List[Dict[str, Any]]
    template_coords: Dict[str, List[float]]
    page_coords: Optional[Dict[str, Dict[str, List[float]]]] = Field(None, description="Per-page coordinates mapping")


class ExportCsvRequest(BaseModel):
    data: List[Dict[str, Any]]
    filename: Optional[str] = "Export_Data_Full.csv"
    columns: Optional[List[str]] = None


class TemplateSaveRequest(BaseModel):
    name: str
    template_data: Dict[str, Any]


class CropRequest(BaseModel):
    page_index: int
    coords: List[float]
    dpi: int = 144


class CrawlerRequest(BaseModel):
    url: str
    headless: bool = False
    wait_time_sec: int = 5
    query_description: Optional[str] = None


# --- Health & Status ---

@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": "Data Extraction Studio API v2.0"}


# --- Document Scan Mode Endpoints ---

@app.post("/api/document/upload")
async def upload_document(file: UploadFile = File(...)):
    """Uploads a PDF file to the server and initializes the DocumentEngine."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    dest_path = DOCUMENTS_DIR / file.filename
    try:
        with open(dest_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        active_engine.load_pdf(str(dest_path))
        info = active_engine.get_info()
        return {
            "message": "File uploaded and loaded successfully",
            "document": info
        }
    except Exception as e:
        logger.error(f"Error uploading PDF: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/document/info")
def get_document_info():
    """Returns metadata for the currently active document."""
    return active_engine.get_info()


@app.get("/api/document/page/{page_index}/image")
def get_page_image(page_index: int, dpi: int = Query(72, ge=36, le=300)):
    """Renders a PDF page as PNG binary."""
    try:
        img_bytes = active_engine.render_page_image(page_index, dpi=dpi, image_format="PNG")
        return Response(content=img_bytes, media_type="image/png")
    except Exception as e:
        logger.error(f"Error rendering page image: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/document/crop-thumbnail")
def get_crop_thumbnail(req: CropRequest):
    """Crops a region from the PDF page for Visual Inspector thumbnail."""
    try:
        crop_bytes = active_engine.crop_region_image(req.page_index, req.coords, dpi=req.dpi)
        return Response(content=crop_bytes, media_type="image/jpeg")
    except Exception as e:
        logger.error(f"Error cropping thumbnail: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/document/detect-grid")
def detect_grid_cells(page_index: int = Query(0, ge=0)):
    """Runs OpenCV morphology table detection to discover all cell boxes."""
    try:
        cells = active_engine.detect_table_cells(page_index)
        return {
            "page_index": page_index,
            "total_cells": len(cells),
            "cells": cells  # List of [x1, y1, x2, y2]
        }
    except Exception as e:
        logger.error(f"Error detecting grid: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/document/preview")
def preview_single_page(req: PreviewRequest):
    """Extracts native text for each given field box on the specified page."""
    try:
        results = {}
        for f in req.fields:
            text = active_engine.extract_text_native_from_page(req.page_index, f.coords)
            results[f.name] = text
        return {
            "page_index": req.page_index,
            "extracted": results
        }
    except Exception as e:
        logger.error(f"Error in preview: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/document/batch-extract")
def batch_extract_document(req: BatchExtractRequest):
    """Extracts range of pages using template coordinates and optional auto-alignment."""
    try:
        raw_results = active_engine.batch_extract(
            template_coords=req.template_coords,
            start_page=req.start_page,
            end_page=req.end_page,
            auto_align=req.auto_align,
            source_page_idx=req.source_page_index,
            page_coords=req.page_coords
        )

        final_results = raw_results
        if req.clean_data:
            final_results = active_engine.clean_extracted_data(raw_results)

        return {
            "total_processed": len(final_results),
            "start_page": req.start_page + 1,
            "end_page": req.end_page + 1,
            "results": final_results
        }
    except Exception as e:
        logger.error(f"Error in batch extraction: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/document/batch-extract-stream")
async def batch_extract_stream(req: BatchExtractRequest):
    """
    Streams extraction progress page-by-page via Server-Sent Events (SSE).
    """
    async def event_generator():
        if not active_engine.doc_plumber or not active_engine.doc_fitz:
            yield f"event: error\ndata: {json.dumps({'error': 'No PDF loaded'})}\n\n"
            return

        start = max(0, req.start_page)
        end = min(active_engine.num_pages - 1, req.end_page)
        total_to_process = max(1, end - start + 1)
        all_results = []

        source_boxes = []
        if req.auto_align and (0 <= req.source_page_index < active_engine.num_pages):
            source_boxes = active_engine.detect_table_cells(req.source_page_index)

        info = active_engine.get_info()
        dimensions = [(p["width"], p["height"]) for p in info.get("pages", [])]

        for idx, p in enumerate(range(start, end + 1)):
            page_num = p + 1
            dx, dy = 0.0, 0.0
            if req.auto_align and source_boxes and p != req.source_page_index:
                target_boxes = active_engine.detect_table_cells(p)
                dx, dy = active_engine.calculate_alignment_offset(source_boxes, target_boxes)

            active_coords = req.template_coords
            if req.page_coords:
                if str(p) in req.page_coords and req.page_coords[str(p)]:
                    active_coords = req.page_coords[str(p)]
                elif str(page_num) in req.page_coords and req.page_coords[str(page_num)]:
                    active_coords = req.page_coords[str(page_num)]

            page_data: Dict[str, Any] = {
                "page_number": page_num,
                "_offset_dx": dx,
                "_offset_dy": dy
            }

            for field_name, coords in active_coords.items():
                try:
                    c = [float(x) for x in coords]
                except (ValueError, TypeError):
                    continue
                nx1 = c[0] + dx
                ny1 = c[1] + dy
                nx2 = c[2] + dx
                ny2 = c[3] + dy
                text = active_engine.extract_text_native_from_page(p, [nx1, ny1, nx2, ny2])
                page_data[field_name] = text

            if req.clean_data:
                cleaned_list = active_engine.clean_extracted_data([page_data])
                page_data = cleaned_list[0] if cleaned_list else page_data

            all_results.append(page_data)
            percent = int(((idx + 1) / total_to_process) * 100)

            progress_payload = {
                "page": page_num,
                "current": idx + 1,
                "total_pages": total_to_process,
                "percent": percent,
                "status_message": f"Processed page {page_num} of {end + 1}",
                "row": page_data
            }
            yield f"event: progress\ndata: {json.dumps(progress_payload, ensure_ascii=False)}\n\n"

        # Verification step
        review_items = active_verifier.verify_batch(
            extracted_rows=all_results,
            template_coords=req.template_coords,
            page_dimensions=dimensions,
            page_coords=req.page_coords
        )

        complete_payload = {
            "total_processed": len(all_results),
            "start_page": start + 1,
            "end_page": end + 1,
            "results": all_results,
            "review_items": review_items
        }
        yield f"event: complete\ndata: {json.dumps(complete_payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/document/verify")
def verify_extracted_data(req: VerificationRequest):
    """
    Bidirectional verification: Cross-checks extracted CSV values against
    field rules, layout coordinates, and visual boundaries.
    """
    try:
        info = active_engine.get_info()
        dimensions = [(p["width"], p["height"]) for p in info.get("pages", [])]
        review_items = active_verifier.verify_batch(
            extracted_rows=req.extracted_rows,
            template_coords=req.template_coords,
            page_dimensions=dimensions,
            page_coords=req.page_coords
        )

        # Summary statistics
        total = len(review_items)
        errors = sum(1 for it in review_items if it["status"] == "error")
        warnings = sum(1 for it in review_items if it["status"] == "warning")
        valid = sum(1 for it in review_items if it["status"] == "valid")

        return {
            "summary": {
                "total": total,
                "valid": valid,
                "warnings": warnings,
                "errors": errors
            },
            "items": review_items
        }
    except Exception as e:
        logger.error(f"Error during verification: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/document/export-csv")
def export_csv(req: ExportCsvRequest):
    """Exports data to CSV with utf-8-sig encoding and returns the file."""
    try:
        filename = req.filename or "Export_Data_Full.csv"
        if not filename.endswith(".csv"):
            filename += ".csv"
        out_path = str(EXPORTS_DIR / filename)

        active_engine.export_to_csv(req.data, out_path, columns=req.columns)

        return FileResponse(
            path=out_path,
            filename=filename,
            media_type="text/csv"
        )
    except Exception as e:
        logger.error(f"Error exporting CSV: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# --- Template JSON Operations (Compatible with pdf_to_text.py roi_coords.json) ---

@app.post("/api/document/templates/save")
def save_template(req: TemplateSaveRequest):
    """Saves ROI coordinates and labels template to JSON."""
    try:
        sanitized_name = sanitize_identifier(req.name)
        file_path = TEMPLATES_DIR / f"{sanitized_name}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(req.template_data, f, indent=2, ensure_ascii=False)
        return {"message": f"Template '{sanitized_name}' saved successfully", "path": str(file_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/document/templates/list")
def list_templates():
    """Lists all saved coordinate templates."""
    templates = []
    for f in TEMPLATES_DIR.glob("*.json"):
        templates.append({"name": f.stem, "filename": f.name})
    return {"templates": templates}


@app.get("/api/document/templates/{name}")
def get_template(name: str):
    """Loads a specific coordinate template."""
    file_path = TEMPLATES_DIR / f"{name}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Template not found")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


# --- Website Crawler Mode Endpoints ---

@app.post("/api/crawler/crawl")
def run_web_crawl(req: CrawlerRequest):
    """Runs website crawling pipeline via Playwright."""
    pipeline = CrawlerPipeline()
    result = pipeline.run(
        url=req.url,
        headless=req.headless,
        wait_seconds=req.wait_time_sec,
        query_description=req.query_description
    )
    return result


@app.get("/api/crawler/recent-exports")
def get_recent_exports():
    """Lists recently exported crawler CSV files."""
    csvs = sorted(EXPORTS_DIR.glob("*.csv"), key=os.path.getmtime, reverse=True)[:10]
    return {
        "files": [{"name": f.name, "size": f.stat().st_size} for f in csvs]
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    is_dev = os.environ.get("K_SERVICE") is None
    uvicorn.run("ai_crawler.server:app", host="0.0.0.0", port=port, reload=is_dev)
