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
        option_url = f"https://fem.encar.com/cars/option/{clean_id}"
        detail_url = f"https://fem.encar.com/cars/detail/{clean_id}"
        
        with st.spinner("옵션표 캡처 및 사진 데이터를 수집 중입니다..."):
            try:
                option_screenshot_bytes = None
                raw_img_urls = []

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
                    
                    # 천천히 스크롤하여 지연 로딩 사진 유도
                    page.evaluate("window.scrollTo(0, 800)")
                    time.sleep(1)
                    page.evaluate("window.scrollTo(0, 0)")
                    time.sleep(1)
                    
                    # DOM 순서대로 모든 img 추출
                    img_elements = page.query_selector_all("img")
                    exclude_keywords = ["profile", "dealer", "user", "avatar", "empl", "icon", "logo", "banner"]

                    for img in img_elements:
                        possible_attrs = ["src", "data-src", "data-original", "srcset"]
                        for attr in possible_attrs:
                            val = img.get_attribute(attr)
                            if val:
                                url_candidate = val.split()[0].strip().lower()
                                
                                is_car_photo = any(pattern in url_candidate for pattern in ["carpicture", "file.encar.com", "ci.encar.com"])
                                is_not_profile = not any(ex in url_candidate for ex in exclude_keywords)
                                
                                if is_car_photo and is_not_profile:
                                    original_val = val.split()[0].strip()
                                    if not original_val.startswith("http"):
                                        if original_val.startswith("//"):
                                            original_val = "https:" + original_val
                                        else:
                                            original_val = "https://fem.encar.com" + original_val
                                            
                                    if original_val not in raw_img_urls and not original_val.endswith(".gif"):
                                        raw_img_urls.append(original_val)
                                
                    browser.close()

                # --- 💥 [외관 1~4번 절대 고정 + 나머지 정렬 파이프라인] ---
                def extract_number(url):
                    # _001, _002 등 3자리 번호 파싱
                    match = re.search(r'[\_\-\.](\d{3})\.(?:jpg|png|jpeg)', url, re.IGNORECASE)
                    if match:
                        return int(match.group(1))
                    return None

                # 1단계: 명확히 _001 ~ _004 번호를 가진 컷 선점
                fixed_top4 = [None, None, None, None]
                remains = []

                for url in raw_img_urls:
                    num = extract_number(url)
                    if num is not None and 1 <= num <= 4:
                        fixed_top4[num - 1] = url
                    else:
                        remains.append(url)

                # 2단계: 파일명 번호가 없던 경우, DOM에서 최초 검출된 순서대로 1~4번 빈자리 채움
                final_top4 = []
                for idx in range(4):
                    if fixed_top4[idx]:
                        final_top4.append(fixed_top4[idx])
                    else:
                        if remains:
                            final_top4.append(remains.pop(0))

                # 3단계: 5번 이후 나머지 사진 정렬 (_005, _006... 순서대로)
                def sort_remains(url):
                    num = extract_number(url)
                    return num if num is not None else 999

                sorted_remains = sorted(remains, key=sort_remains)

                # 4단계: 최종 리스트 합치기 (1~4번 고정 + 나머지)
                img_urls = final_top4 + sorted_remains

                # --- 결과 출력 ---
                st.success(f"차량 ID [{clean_id}] 수집 완료!")
                
                tab_option, tab_photos = st.tabs(["📋 옵션표 (전체 캡처)", f"📸 차량 사진 ({len(img_urls)}장)"])
                
                with tab_option:
                    st.subheader("차량 옵션표")
                    if option_screenshot_bytes:
                        image = Image.open(io.BytesIO(option_screenshot_bytes))
                        st.image(image, use_container_width=True)
                    
                with tab_photos:
                    st.subheader("수집된 차량 사진 (1~4번 외관컷 절대 고정)")
                    if img_urls:
                        for i in range(0, len(img_urls), 2):
                            cols = st.columns(2)
                            with cols[0]:
                                caption_text = f"사진 {i+1} (외관 핵심)" if i < 4 else f"사진 {i+1}"
                                st.image(img_urls[i], use_container_width=True, caption=caption_text)
                            if i + 1 < len(img_urls):
                                with cols[1]:
                                    caption_text = f"사진 {i+2} (외관 핵심)" if (i+1) < 4 else f"사진 {i+2}"
                                    st.image(img_urls[i+1], use_container_width=True, caption=caption_text)
                    else:
                        st.info("추출된 차량 사진이 없습니다.")

            except Exception as e:
                st.error(f"데이터 수집 중 오류가 발생했습니다: {e}")