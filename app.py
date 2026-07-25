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
        # 옵션 페이지 및 상세 페이지 URL
        option_url = f"https://fem.encar.com/cars/option/{clean_id}"
        detail_url = f"https://fem.encar.com/cars/detail/{clean_id}"
        
        with st.spinner("옵션표 캡처 및 사진 데이터를 수집 중입니다..."):
            try:
                option_screenshot_bytes = None
                img_urls = []

                with sync_playwright() as p:
                    browser = p.chromium.launch(
                        headless=True,
                        args=["--no-sandbox", "--disable-dev-shm-usage"]
                    )
                    
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
                    
                    # 1. [옵션표 캡처] https://fem.encar.com/cars/option/{clean_id}
                    page.goto(option_url, wait_until="networkidle", timeout=30000)
                    time.sleep(2)
                    
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                    time.sleep(1)
                    page.evaluate("window.scrollTo(0, 0)")
                    time.sleep(1)
                    
                    option_screenshot_bytes = page.screenshot(full_page=True)
                    
                    # 2. [사진 수집] fem.encar.com/cars/detail/{clean_id}
                    page.goto(detail_url, wait_until="networkidle", timeout=30000)
                    time.sleep(2)
                    
                    # 스크롤 동작
                    page.evaluate("window.scrollTo(0, 800)")
                    time.sleep(1)
                    page.evaluate("window.scrollTo(0, 0)")
                    time.sleep(1)
                    
                    # DOM 내 모든 img 태그 검색
                    img_elements = page.query_selector_all("img")
                    
                    # 제외하고 싶은 키워드 목록 (프로필, 딜러, 아이콘 등)
                    exclude_keywords = ["profile", "dealer", "user", "avatar", "empl", "icon", "logo", "banner"]

                    for img in img_elements:
                        possible_attrs = ["src", "data-src", "data-original", "srcset"]
                        for attr in possible_attrs:
                            val = img.get_attribute(attr)
                            if val:
                                url_candidate = val.split()[0].strip().lower()
                                
                                # 1) 차량 사진 패턴인지 확인
                                is_car_photo = any(pattern in url_candidate for pattern in ["carpicture", "file.encar.com", "ci.encar.com"])
                                
                                # 2) 프로필/딜러/아이콘 키워드가 없는지 확인
                                is_not_profile = not any(ex in url_candidate for ex in exclude_keywords)
                                
                                if is_car_photo and is_not_profile:
                                    # 원본 URL 복원 (대소문자 유지)
                                    original_val = val.split()[0].strip()
                                    if not original_val.startswith("http"):
                                        if original_val.startswith("//"):
                                            original_val = "https:" + original_val
                                        else:
                                            original_val = "https://fem.encar.com" + original_val
                                            
                                    if original_val not in img_urls and not original_val.endswith(".gif"):
                                        img_urls.append(original_val)
                                
                    browser.close()

                # --- 결과 출력 ---
                st.success(f"차량 ID [{clean_id}] 수집 완료!")
                
                tab_option, tab_photos = st.tabs(["📋 옵션표 (전체 캡처)", f"📸 차량 사진 ({len(img_urls)}장)"])
                
                with tab_option:
                    st.subheader("차량 옵션표")
                    if option_screenshot_bytes:
                        image = Image.open(io.BytesIO(option_screenshot_bytes))
                        st.image(image, use_container_width=True)
                    
                with tab_photos:
                    st.subheader("수집된 차량 사진")
                    if img_urls:
                        # 순서대로 2열 출력
                        for i in range(0, len(img_urls), 2):
                            cols = st.columns(2)
                            with cols[0]:
                                st.image(img_urls[i], use_container_width=True, caption=f"사진 {i+1}")
                            if i + 1 < len(img_urls):
                                with cols[1]:
                                    st.image(img_urls[i+1], use_container_width=True, caption=f"사진 {i+2}")
                    else:
                        st.info("추출된 차량 사진이 없습니다.")

            except Exception as e:
                st.error(f"데이터 수집 중 오류가 발생했습니다: {e}")