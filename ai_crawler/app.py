"""
AI Crawler - Standalone Streamlit Web Interface.
Run with: streamlit run ai_crawler/app.py
"""

import os
import glob
import json
import streamlit as st
import pandas as pd
from pathlib import Path

from ai_crawler.core.pipeline import CrawlerPipeline
from ai_crawler.config import EXPORTS_DIR, SCREENSHOTS_DIR

st.set_page_config(
    page_title="AI Web Crawler",
    page_icon="🕷️",
    layout="wide"
)

st.title("🕷️ AI Web Crawler (Local & Lightweight)")
st.caption("Tối ưu hóa phần cứng Arch Linux • Tự động bắt API JSON • Fallback DOM/OCR AI")

# Sidebar: System & Settings
with st.sidebar:
    st.header("⚙️ Cấu hình Crawler")
    
    headless_mode = st.checkbox(
        "Chạy ẩn (Headless Mode)",
        value=False,
        help="Bỏ chọn để mở cửa sổ trình duyệt Chromium thật sự giúp bạn nhìn thấy và tương tác."
    )
    
    wait_time = st.slider(
        "Thời gian dừng quan sát (giây)",
        min_value=2,
        max_value=20,
        value=5,
        help="Số giây giữ trình duyệt mở để tương tác và đón gói tin API."
    )
    
    st.markdown("---")
    st.subheader("📁 File đã xuất gần đây")
    recent_csvs = sorted(glob.glob(str(EXPORTS_DIR / "*.csv")), key=os.path.getmtime, reverse=True)[:5]
    if recent_csvs:
        for f in recent_csvs:
            st.text(f"📄 {Path(f).name}")
    else:
        st.info("Chưa có file xuất nào.")

# Main Crawl Form
url_input = st.text_input(
    "🌐 Nhập URL cần cào dữ liệu:",
    placeholder="https://quotes.toscrape.com",
    help="Nhập địa chỉ trang web bạn muốn trích xuất dữ liệu."
)

col1, col2 = st.columns([1, 5])
with col1:
    btn_start = st.button("🚀 Bắt đầu cào", type="primary", use_container_width=True)

if btn_start:
    if not url_input.strip():
        st.warning("Vui lòng nhập đường dẫn URL hợp lệ.")
    else:
        status_box = st.status("Đang chuẩn bị khởi động trình duyệt...", expanded=True)
        progress_bar = st.progress(0)

        def on_progress(msg: str, pct: int):
            status_box.write(f"▶ {msg}")
            progress_bar.progress(min(pct, 100))

        pipeline = CrawlerPipeline(headless=headless_mode, progress_callback=on_progress)
        
        try:
            res = pipeline.run(url_input.strip(), headless=headless_mode, wait_seconds=wait_time)
            
            if res.get("success"):
                progress_bar.progress(100)
                status_box.update(label="🎉 Cào dữ liệu hoàn tất!", state="complete", expanded=False)
                
                st.success(res.get("message"))

                # Metrics
                m1, m2, m3 = st.columns(3)
                m1.metric("Số bản ghi", res.get("records_count", 0))
                m2.metric("Thời gian cào", f"{res.get('duration_seconds', 0)}s")
                m3.metric("Phương pháp", res.get("method_display", ""))

                # Data Preview
                data = res.get("data", [])
                if data:
                    st.subheader("📊 Dữ liệu trích xuất được")
                    try:
                        df = pd.json_normalize(data)
                        st.dataframe(df, use_container_width=True)
                    except Exception:
                        st.json(data)

                    # Download Buttons
                    d1, d2 = st.columns(2)
                    csv_path = res.get("csv_path")
                    json_path = res.get("json_path")

                    if csv_path and os.path.exists(csv_path):
                        with open(csv_path, "rb") as f:
                            d1.download_button(
                                label="📥 Tải về CSV",
                                data=f,
                                file_name=Path(csv_path).name,
                                mime="text/csv",
                                use_container_width=True
                            )

                    if json_path and os.path.exists(json_path):
                        with open(json_path, "rb") as f:
                            d2.download_button(
                                label="📥 Tải về JSON",
                                data=f,
                                file_name=Path(json_path).name,
                                mime="application/json",
                                use_container_width=True
                            )

                # Screenshot Preview
                screenshot_path = res.get("screenshot_path")
                if screenshot_path and os.path.exists(screenshot_path):
                    with st.expander("📸 Xem ảnh chụp màn hình lúc cào"):
                        st.image(screenshot_path, caption="Ảnh chụp trang web")

            else:
                status_box.update(label="❌ Lỗi khi cào dữ liệu", state="error", expanded=True)
                st.error(res.get("message"))

        except Exception as e:
            status_box.update(label="❌ Ngoại lệ hệ thống", state="error")
            st.error(f"Lỗi: {e}")
