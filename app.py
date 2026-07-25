import sys
import asyncio
import os
import subprocess
import streamlit as st

# Streamlit Cloud (Linux) 환경 Playwright 브라우저 설치
@st.cache_resource
def install_playwright_browsers():
    try:
        subprocess.run(["playwright", "install", "--with-deps", "chromium"], check=True)
    except Exception as e:
        print(f"Playwright install error: {e}")

install_playwright_browsers()

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.sync_api import sync_playwright
import re
import time
from PIL import Image
import io

# --- Page Config ---
st.set_page_config(
    page_title="엔카 옵션표 & 사진 조회",
    page_icon="🚗",
    layout="centered"
)

st.title("🚗 엔카 옵션표 & 사진 수집기")

# --- 입력창 ---
car_id_input = st.text_input(
    "엔카 차량 URL 또는 Car ID 입력", 
    value="", 
    placeholder="예: 42153179",
    help="차량 ID 숫자를 입력하거나 URL을 붙여넣으세요."
)

if st.button("조회하기", type="primary", use_container_width=True):
    clean_id = re.sub(r"\D", "", car_id_input)
    
    if not clean_id:
        st.warning("올바른 차량 ID(숫자)를 입력해주세요.")
    else:
        # 📌 지정해주신 정확한 옵션 페이지 URL 및 상세 페이지 URL
        option_url = f"https://fem.encar.com/cars/option/{clean_id}"
        detail_url = f"https://fem.encar.com/cars/detail/{clean_id}"
        
        with st.spinner("옵션표(/cars/option) 페이지 캡처 및 사진 데이터 수집 중..."):
            try:
                option_screenshot_bytes = None
                img_urls = []

                with sync_playwright() as p:
                    browser = p.chromium.launch(
                        headless=True,
                        args=["--no-sandbox", "--disable-dev-shm-usage"]
                    )
                    
                    # 한국어 및 모바일 환경 고정 (수출 페이지 리다이렉트 방지)
                    context = browser.new_context(
                        viewport={"width": 390, "height": 844},
                        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
                        locale="ko-KR",
                        timezone_id="Asia/Seoul",
                        extra_http_headers={
                            "Accept-Language": "ko-KR,ko;q=0.9",
                            "Referer": "https://fem.encar.com/"
                        }
                    )
                    page = context.new_page()
                    
                    # 1. 🔥 [옵션표 캡처] 지정하신 https://fem.encar.com/cars/option/{clean_id} 접속
                    page.goto(option_url, wait_until="networkidle", timeout=30000)
                    time.sleep(2)
                    
                    # 스크롤을 내려 옵션 항목 전체 렌더링 유도
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                    time.sleep(1)
                    page.evaluate("window.scrollTo(0, 0)")
                    time.sleep(1)
                    
                    # 옵션표 전체 화면 캡처
                    option_screenshot_bytes = page.screenshot(full_page=True)
                    
                    # 2. 🔥 [사진 수집] 메인 상세 페이지로 이동하여 차량 사진 추출
                    page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(2)
                    
                    page.evaluate("window.scrollTo(0, 500)")
                    time.sleep(1)
                    
                    img_elements = page.query_selector_all("img")
                    for img in img_elements:
                        src = img.get_attribute("src") or img.get_attribute("data-src")
                        if src and ("carpicture" in src or "file.encar.com" in src):
                            if not src.startswith("http"):
                                src = "https:" + src
                            if src not in img_urls:
                                img_urls.append(src)
                                
                    browser.close()

                # --- 결과 출력 ---
                st.success(f"차량 ID [{clean_id}] 데이터 수집 완료!")
                
                tab_option, tab_photos = st.tabs(["📋 옵션표 (전체 캡처)", f"📸 차량 사진 ({len(img_urls)}장)"])
                
                with tab_option:
                    st.subheader("차량 옵션표 (fem.encar.com/cars/option)")
                    if option_screenshot_bytes:
                        image = Image.open(io.BytesIO(option_screenshot_bytes))
                        st.image(image, use_column_width=True)
                    
                with tab_photos:
                    st.subheader("수집된 차량 사진")
                    if img_urls:
                        cols = st.columns(2)
                        for idx, url in enumerate(img_urls):
                            with cols[idx % 2]:
                                st.image(url, use_column_width=True, caption=f"사진 {idx+1}")
                    else:
                        st.info("추출된 차량 사진이 없습니다.")

            except Exception as e:
                st.error(f"데이터 수집 중 오류가 발생했습니다: {e}")