"""
Playwright Scraper for AI Crawler.
Supports opening a visible browser window (headless=False) for user interaction,
network interception (capturing JSON APIs), auto-scrolling, and screenshot captures.
"""

import time
import json
import random
from typing import List, Dict, Any, Optional, Callable
from playwright.sync_api import sync_playwright, Page, Response, BrowserContext, Browser
from ai_crawler.config import (
    DEFAULT_HEADLESS,
    DEFAULT_TIMEOUT_MS,
    DEFAULT_VIEWPORT,
    USER_AGENTS,
    INTERCEPT_KEYWORDS,
    SCREENSHOTS_DIR
)

try:
    from playwright_stealth import stealth_sync
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False

class PlaywrightScraper:
    def __init__(
        self,
        headless: bool = DEFAULT_HEADLESS,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        progress_callback: Optional[Callable[[str, int], None]] = None
    ):
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.callback = progress_callback or (lambda msg, pct: None)
        self.intercepted_json: List[Dict[str, Any]] = []

    def _notify(self, message: str, percent: int = 0):
        print(f"[Scraper] {message}")
        try:
            self.callback(message, percent)
        except Exception:
            pass

    def _on_response(self, response: Response):
        """Intercept XHR / Fetch responses and extract valid JSON payloads."""
        try:
            content_type = response.headers.get("content-type", "").lower()
            if "application/json" in content_type:
                url_lower = response.url.lower()
                # Check if URL matches any intercept keywords or has query/api in path
                matches_keyword = any(kw in url_lower for kw in INTERCEPT_KEYWORDS)
                
                # Also accept any JSON payload if status is 200 and not a telemetry ping
                if response.status == 200 and not any(ign in url_lower for kw in ["telemetry", "analytics", "tracking", "log", "metric"] for ign in [kw]):
                    try:
                        data = response.json()
                        # Only keep non-empty objects/lists
                        if data and isinstance(data, (dict, list)):
                            # Filter out tiny status pings like {"ok": true}
                            serialized = json.dumps(data)
                            if len(serialized) > 40:
                                self._notify(f"⚡ Bắt được gói tin API JSON từ: {response.url[:60]}...", 35)
                                self.intercepted_json.append({
                                    "url": response.url,
                                    "payload": data
                                })
                    except Exception:
                        pass
        except Exception:
            pass

    def human_scroll(self, page: Page, max_scrolls: int = 4):
        """Simulate natural human scrolling to trigger lazy loading / infinite scroll."""
        self._notify("Mô phỏng cuộn trang người dùng...", 45)
        for i in range(max_scrolls):
            scroll_y = (i + 1) * 450
            page.evaluate(f"window.scrollTo({{ top: {scroll_y}, behavior: 'smooth' }});")
            time.sleep(random.uniform(0.6, 1.2))

    def scrape(
        self,
        target_url: str,
        wait_seconds: int = 5,
        take_screenshot: bool = True
    ) -> Dict[str, Any]:
        """
        Main scraping routine.
        Opens browser (visible if headless=False), navigates, intercepts network requests,
        and extracts DOM text / screenshot.
        """
        self.intercepted_json = []
        result: Dict[str, Any] = {
            "url": target_url,
            "title": "",
            "intercepted_json": [],
            "dom_text": "",
            "hydration_data": None,
            "screenshot_path": None,
            "status": "pending"
        }

        mode_str = "chế độ hiển thị cửa sổ (Visible Window)" if not self.headless else "chế độ nền (Headless)"
        self._notify(f"Đang khởi động trình duyệt Playwright ở {mode_str}...", 10)

        with sync_playwright() as p:
            # Launch Chromium (full GUI window when headless=False)
            browser: Browser = p.chromium.launch(
                headless=self.headless,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars"
                ]
            )

            user_agent = random.choice(USER_AGENTS)
            context: BrowserContext = browser.new_context(
                viewport=DEFAULT_VIEWPORT,
                user_agent=user_agent
            )

            page: Page = context.new_page()

            # Apply stealth plugin if available
            if STEALTH_AVAILABLE:
                try:
                    stealth_sync(page)
                except Exception:
                    pass

            # Attach network interception listener
            page.on("response", self._on_response)

            self._notify(f"Đang tải trang: {target_url}...", 20)
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                result["title"] = page.title()
                self._notify(f"Đã mở trang: '{result['title']}'", 30)

                # Simulate human interaction / scroll
                self.human_scroll(page, max_scrolls=3)

                # Wait for user observation/interaction or network calls to settle
                if wait_seconds > 0:
                    self._notify(f"Giữ cửa sổ trình duyệt mở để tương tác và đón gói tin API...", 50)
                    time.sleep(wait_seconds)

                # Check for Hydration Script Data (e.g. __NEXT_DATA__, __INITIAL_STATE__)
                hydration_json = page.evaluate("""
                    () => {
                        const nextData = document.getElementById('__NEXT_DATA__');
                        if (nextData) {
                            try { return JSON.parse(nextData.textContent); } catch(e){}
                        }
                        if (window.__INITIAL_STATE__) {
                            return window.__INITIAL_STATE__;
                        }
                        return null;
                    }
                """)
                if hydration_json:
                    result["hydration_data"] = hydration_json
                    self._notify("✨ Tìm thấy dữ liệu Hydration (JSON nhúng sẵn trong HTML)!", 60)

                # Extract structured DOM repeating items & cleaned visible text
                dom_result = page.evaluate("""
                    () => {
                        const items = [];
                        const selectors = ['.quote', '.product', '.item', '.card', 'article', '.post', '.entry', 'tr'];
                        for (const sel of selectors) {
                            const elements = document.querySelectorAll(sel);
                            if (elements.length >= 2) {
                                for (let i = 0; i < Math.min(elements.length, 25); i++) {
                                    const el = elements[i];
                                    const rec = {};
                                    const titleEl = el.querySelector('h1, h2, h3, h4, h5, .title, .name, .text, a strong');
                                    if (titleEl) rec['title'] = titleEl.innerText.trim();
                                    
                                    const subEl = el.querySelector('.price, .author, .date, .byline, .meta, small');
                                    if (subEl) rec['detail'] = subEl.innerText.trim();
                                    
                                    const linkEl = el.querySelector('a[href]');
                                    if (linkEl && linkEl.href) rec['link'] = linkEl.href;
                                    
                                    if (!rec['title'] && !rec['detail']) {
                                        const lines = el.innerText.split('\\n').map(s => s.trim()).filter(s => s.length > 2);
                                        if (lines.length > 0) rec['content'] = lines.slice(0, 3).join(' | ');
                                    }
                                    if (rec['title'] || rec['detail'] || rec['content']) {
                                        items.push(rec);
                                    }
                                }
                                if (items.length >= 2) break;
                            }
                        }

                        // Also extract cleaned plain text for AI fallback
                        const clone = document.body.cloneNode(true);
                        const removeTags = ['script', 'style', 'noscript', 'svg', 'canvas', 'iframe', 'nav', 'footer'];
                        removeTags.forEach(tag => {
                            clone.querySelectorAll(tag).forEach(el => el.remove());
                        });
                        const text = clone.innerText.slice(0, 2500) || '';

                        return {
                            items: items,
                            text: text
                        };
                    }
                """)
                result["dom_items"] = dom_result.get("items", [])
                result["dom_text"] = dom_result.get("text", "").strip()

                # Take screenshot if required
                if take_screenshot:
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    screenshot_file = SCREENSHOTS_DIR / f"snap_{timestamp}.png"
                    page.screenshot(path=str(screenshot_file), full_page=False)
                    result["screenshot_path"] = str(screenshot_file)
                    self._notify("📸 Đã chụp ảnh màn hình lưu trữ.", 70)

                result["intercepted_json"] = self.intercepted_json
                result["status"] = "success"

            except Exception as e:
                self._notify(f"Lỗi khi cào dữ liệu: {str(e)}", 100)
                result["status"] = "error"
                result["error"] = str(e)
            finally:
                self._notify("Đóng phiên trình duyệt...", 85)
                browser.close()

        return result
