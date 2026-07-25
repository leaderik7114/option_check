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
user_input = st.text_input(
    "엔카 URL, Car ID 또는 차량번호 입력", 
    value="", 
    placeholder="예: 42153179 또는 123가4567 또는 엔카 URL",
    help="차량 ID(숫자), 엔카 상세 URL, 또는 차량번호(예: 123가4567)를 입력하세요."
)

if st.button("조회하기", type="primary", use_container_width=True):
    raw_text = user_input.strip()
    
    if not raw_text:
        st.warning("조회할 차량번호, Car ID 또는 URL을 입력해주세요.")
    else:
        with st.spinner("입력 데이터를 분석하고 엔카 매물 정보를 조회 중입니다..."):
            clean_id = None
            
            # 1. 차량번호 형태 검사 (예: 12가3456, 123가4567 등)
            car_num_match = re.search(r'\d{2,3}\s*[가-힣]\s*\d{4}', raw_text)
            
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

                # 차량번호인 경우 -> 엔카 검색을 통해 Car ID 도출
                if car_num_match:
                    target_car_num = car_num_match.group(0).replace(" ", "")
                    st.info(f"🔍 차량번호 [{target_car_num}]로 매물을 검색 중입니다...")
                    
                    # 모바일 엔카 검색 페이지 이용
                    search_url = f"https://m.encar.com/ca/carsearchlist.do?carType=for&searchType=action&searchWord={target_car_num}"
                    page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(2)
                    
                    # 검색 결과에서 Car ID 링크 추출
                    link_element = page.query_selector("a[href*='carid='], a[href*='/cars/detail/']")
                    if link_element:
                        href = link_element.get_attribute("href")
                        id_match = re.search(r'(\d{7,8})', href)
                        if id_match:
                            clean_id = id_match.group(1)
                    
                    if not clean_id:
                        st.error(f"❌ 차량번호 [{target_car_num}]에 해당하는 판매 중인 매물을 찾을 수 없습니다.")
                        browser.close()
                        st.stop()
                else:
                    # Car ID 또는 URL인 경우 숫자만 추출
                    digits = re.sub(r"\D", "", raw_text)
                    if digits:
                        clean_id = digits
                    else:
                        st.error("❌ 올바른 차량 ID, URL 또는 차량번호를 입력해주세요.")
                        browser.close()
                        st.stop()

                # 2. 추출된 clean_id 기반 데이터 수집 진행
                option_url = f"https://fem.encar.com/cars/option/{clean_id}"
                detail_url = f"https://fem.encar.com/cars/detail/{clean_id}"
                
                option_screenshot_bytes = None
                raw_img_urls = []

                # --- 2-1. [옵션표 캡처] ---
                page.goto(option_url, wait_until="networkidle", timeout=30000)
                time.sleep(2)
                
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                time.sleep(1)
                page.evaluate("window.scrollTo(0, 0)")
                time.sleep(1)
                
                option_screenshot_bytes = page.screenshot(full_page=True)
                
                # --- 2-2. [사진 수집] ---
                page.goto(detail_url, wait_until="networkidle", timeout=30000)
                time.sleep(2)
                
                page.evaluate("window.scrollTo(0, 800)")
                time.sleep(1)
                page.evaluate("window.scrollTo(0, 0)")
                time.sleep(1)
                
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

            # --- 💥 [외관 1~4번 절대 고정 + 정렬 파이프라인] ---
            def extract_number(url):
                match = re.search(r'[\_\-\.](\d{3})\.(?:jpg|png|jpeg)', url, re.IGNORECASE)
                if match:
                    return int(match.group(1))
                return None

            fixed_top4 = [None, None, None, None]
            remains = []

            for url in raw_img_urls:
                num = extract_number(url)
                if num is not None and 1 <= num <= 4:
                    fixed_top4[num - 1] = url
                else:
                    remains.append(url)

            final_top4 = []
            for idx in range(4):
                if fixed_top4[idx]:
                    final_top4.append(fixed_top4[idx])
                else:
                    if remains:
                        final_top4.append(remains.pop(0))

            def sort_remains(url):
                num = extract_number(url)
                return num if num is not None else 999

            sorted_remains = sorted(remains, key=sort_remains)
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