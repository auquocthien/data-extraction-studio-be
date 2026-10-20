"""
AI Crawler Package - Modular, Lightweight, and Hardware-Optimized.
"""

__version__ = "1.0.0"

from ai_crawler.core.pipeline import CrawlerPipeline
from ai_crawler.core.scraper import PlaywrightScraper
from ai_crawler.core.ai_parser import AIParser
from ai_crawler.core.ocr_engine import OCREngine
from ai_crawler.utils.exporter import DataExporter

__all__ = [
    "CrawlerPipeline",
    "PlaywrightScraper",
    "AIParser",
    "OCREngine",
    "DataExporter",
]
