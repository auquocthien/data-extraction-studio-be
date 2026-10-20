# 🚀 Data Extraction Studio - Backend API

FastAPI Backend cho hệ thống trích xuất dữ liệu đa năng:
- **Document Scan Engine**: Trích xuất dữ liệu từ tài liệu PDF (hỗ trợ OCR Tesseract tiếng Việt/Anh, tự động căn chỉnh trôi lệch layout, nhận diện bảng OpenCV morphology, xuất CSV chuẩn utf-8-sig).
- **Website Crawler Engine**: Cào dữ liệu web tự động qua Playwright (bóc tách mạng API JSON, DOM repeating cards, DOM plain text qua AI).
- Sẵn sàng triển khai **Containerized trên Google Cloud Run**.

---

## 📁 Cấu Trúc Mã Nguồn

```text
data_extraction_studio_be/
├── ai_crawler/
│   ├── core/
│   │   ├── document_engine.py      # Xử lý PDF (PyMuPDF, pdfplumber, OpenCV)
│   │   ├── document_verifier.py    # Kiểm tra tính toàn vẹn dữ liệu
│   │   ├── scraper.py              # Playwright web scraper
│   │   ├── ocr_engine.py           # Tesseract OCR engine
│   │   ├── ai_parser.py            # Local Ollama fallback parser
│   │   └── pipeline.py             # Điều phối quy trình cào dữ liệu
│   ├── utils/
│   │   ├── exporter.py             # Xuất CSV/JSON
│   │   └── regex_utils.py          # Chuẩn hóa SĐT, Email, tiếng Việt/Hoa
│   ├── config.py                   # Cấu hình đường dẫn, Cloud Run env
│   └── server.py                   # FastAPI REST API endpoints
├── tests/                          # Unit tests
├── Dockerfile                      # Dockerfile deploy Google Cloud Run
├── requirements.txt                # Thư viện Python
└── deploy.sh                       # Script deploy tự động lên Cloud Run
```

---

## 🛠️ Chạy Thử Local

1. **Cài đặt thư viện**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Khởi chạy Server**:
   ```bash
   uvicorn ai_crawler.server:app --host 0.0.0.0 --port 8000 --reload
   ```
   - Swagger API Docs: `http://localhost:8000/docs`
   - Health check: `http://localhost:8000/api/health`

---

## 🐳 Chạy Bằng Docker

```bash
docker build -t ai-crawler-api:local .
docker run --rm -p 8080:8080 ai-crawler-api:local
```

---

## ☁️ Triển Khai Lên Google Cloud Run

Sử dụng script deploy tự động:
```bash
./deploy.sh be
```
Hoặc chạy lệnh gcloud trực tiếp:
```bash
gcloud run deploy ai-crawler-api \
    --source . \
    --project baogia-836e4 \
    --region asia-southeast1 \
    --platform managed \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --set-env-vars "HEADLESS=true,AI_CRAWLER_DATA_DIR=/tmp/ai_crawler_data"
```
