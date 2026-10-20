"""
Configuration settings for AI Crawler.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
IS_CLOUD_RUN = bool(os.environ.get("K_SERVICE"))
HAS_DISPLAY = bool(os.environ.get("DISPLAY"))

# Use /tmp on Cloud Run (in-memory writable filesystem) or AI_CRAWLER_DATA_DIR if specified
if os.environ.get("AI_CRAWLER_DATA_DIR"):
    DATA_DIR = Path(os.environ["AI_CRAWLER_DATA_DIR"]).resolve()
elif IS_CLOUD_RUN:
    DATA_DIR = Path("/tmp/ai_crawler_data")
else:
    DATA_DIR = BASE_DIR / "data"

EXPORTS_DIR = DATA_DIR / "exports"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
DOCUMENTS_DIR = DATA_DIR / "documents"
TEMPLATES_DIR = DATA_DIR / "templates"

# Ensure directories exist
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

# Scraper Settings: Force headless when running on Cloud Run, Docker, or headless environment without X11 DISPLAY
_env_headless = os.environ.get("HEADLESS", "").lower()
if _env_headless in ("1", "true", "yes"):
    DEFAULT_HEADLESS = True
elif IS_CLOUD_RUN or not HAS_DISPLAY:
    DEFAULT_HEADLESS = True
else:
    DEFAULT_HEADLESS = False  # Open real visible browser window by default on local desktop
DEFAULT_TIMEOUT_MS = 45000
DEFAULT_VIEWPORT = {"width": 1280, "height": 800}

USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
]

# API Keywords for Network Interception
INTERCEPT_KEYWORDS = [
    "api", "graphql", "product", "item", "list", "search", 
    "query", "data", "catalog", "feed", "posts", "comments"
]

# Ollama Settings (Local AI)
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:1b")
