import asyncio
import io
import os
import re
import subprocess
import sys
import time
import requests
from PIL import Image, ImageDraw, ImageOps
import streamlit as st

# --- Streamlit Cloud Playwright 브라우저 설치 ---
@st.cache_resource
def install_playwright_browsers():
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True
        )
    except Exception as e:
        print(f"Playwright install error: {e}")

install_playwright_browsers()

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.sync_api import sync_playwright


def apply_guidelines(image_input):
    """
    1920x1080 표준 해상도 기준으로 완전 고정(Absolute Pixel Fix)된
    가이드라인을 그리는 함수
    """
    try:
        if isinstance(image_input, str):
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            response = requests.get(image_input, headers=headers, timeout=10)
            response.raise_for_status()
            img = Image.open(io.BytesIO(response.content)).convert("RGBA")
        else:
            img = image_input.convert("RGBA")
    except Exception:
        return image_input

    # 표준 규격 해상도 고정 (1920 x 1080)
    TARGET_W = 1920
    TARGET_H = 1080
    
    # 해상도가 다를 경우 표준 규격으로 리사이즈
    if img.size != (TARGET_W, TARGET_H):
        img = img.resize((TARGET_W, TARGET_H), Image.Resampling.LANCZOS)

    overlay = Image.new("RGBA", (TARGET_W, TARGET_H), (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    # --- [1920x1080 기준 절대 픽셀 좌표 (Absolute px Fix)] ---
    # 1. 수평선 높이 (px)
    Y_RED_BOTTOM = 950      # 하단 빨간 바퀴 접지선
    Y_RED_TOP = 20          # 상단 빨간 테두리
    Y_WHITE_TOP = 470       # 상단 흰색 보조선
    Y_WHITE_BOT = 610       # 하단 흰색 보조선
    Y_ORANGE_CENTER = 548   # 수평 중앙 주황선

    # 2. 수직선 위치 (px) - cm 비율 매핑
    X_RED_LEFT = 229        # 4.8cm
    X_RED_RIGHT = 1690      # 35.4cm
    
    X_GREEN_1 = 267         # 5.6cm
    X_GREEN_2 = 311         # 6.5cm
    X_GREEN_3 = 1580        # 33.1cm
    X_GREEN_4 = 1614        # 33.8cm

    X_ORANGE_LEFT = 411     # 8.6cm (중형 좌)
    X_ORANGE_RIGHT = 1490   # 31.2cm (중형 우)
    X_ORANGE_CENTER = 946   # 19.8cm (수직 중앙)

    # Line Style
    line_thick = 4

    RED = (235, 35, 35, 230)
    ORANGE = (245, 150, 20, 230)
    GREEN_LIGHT = (160, 210, 140, 220)
    GREEN_DARK = (80, 150, 70, 230)
    WHITE_SUB = (240, 240, 240, 180)

    # --- [선 그리기] ---
    # 1. 흰색 보조선
    draw.line([(0, Y_WHITE_TOP), (TARGET_W, Y_WHITE_TOP)], fill=WHITE_SUB, width=2)
    draw.line([(0, Y_WHITE_BOT), (TARGET_W, Y_WHITE_BOT)], fill=WHITE_SUB, width=2)

    # 2. 초록색 사이드선 (대형)
    draw.line([(X_GREEN_1, 0), (X_GREEN_1, TARGET_H)], fill=GREEN_LIGHT, width=line_thick)
    draw.line([(X_GREEN_2, 0), (X_GREEN_2, TARGET_H)], fill=GREEN_DARK, width=line_thick)
    draw.line([(X_GREEN_3, 0), (X_GREEN_3, TARGET_H)], fill=GREEN_DARK, width=line_thick)
    draw.line([(X_GREEN_4, 0), (X_GREEN_4, TARGET_H)], fill=GREEN_LIGHT, width=line_thick)

    # 3. 주황색 사이드선 (중형 & 중앙)
    draw.line([(X_ORANGE_LEFT, 0), (X_ORANGE_LEFT, TARGET_H)], fill=ORANGE, width=line_thick)
    draw.line([(X_ORANGE_RIGHT, 0), (X_ORANGE_RIGHT, TARGET_H)], fill=ORANGE, width=line_thick)
    draw.line([(X_ORANGE_CENTER, 0), (X_ORANGE_CENTER, TARGET_H)], fill=ORANGE, width=line_thick + 1)
    draw.line([(0, Y_ORANGE_CENTER), (TARGET_W, Y_ORANGE_CENTER)], fill=ORANGE, width=line_thick + 1)

    # 4. 빨간색 외곽 및 바퀴 하단선
    draw.rectangle([X_RED_LEFT, Y_RED_TOP, X_RED_RIGHT, Y_RED_BOTTOM], outline=RED, width=line_thick + 2)
    draw.line([(0, Y_RED_BOTTOM), (TARGET_W, Y_RED_BOTTOM)], fill=RED, width=line_thick + 2)

    combined = Image.alpha_composite(img, overlay)
    return combined.convert("RGB")

# --- Page Config ---
st.set_page_config(
    page_title="엔카 옵션표 & 사진 조회",
    page_icon="🚗",
    layout="centered"
)

st.title("Encar 광고 사진 & 옵션 리스트")

# --- 입력창 ---
user_input = st.text_input(
    "엔카 URL 또는 CarID 입력", 
    value="", 
    placeholder="예: 42153179 또는 엔카 차량 URL 전체 복사 붙여넣기",
    help="차량 ID 숫자를 입력하거나 엔카 매물 URL을 통째로 붙여넣으세요."
)

if st.button("조회하기", type="primary", use_container_width=True):
    raw_text = user_input.strip()
    clean_id = None
    
    if not raw_text:
        st.warning("차량 ID 또는 엔카 URL을 입력해주세요.")
    else:
        # --- 지능형 URL / Car ID 파싱 로직 ---
        if raw_text.isdigit():
            clean_id = raw_text
        else:
            match = re.search(r'(?:detail/|car[iI]d=)(\d{6,9})', raw_text)
            if match:
                clean_id = match.group(1)
            else:
                fallback_match = re.search(r'(\d{7,8})', raw_text)
                if fallback_match:
                    clean_id = fallback_match.group(1)
                else:
                    clean_id = re.sub(r"\D", "", raw_text)

        if not clean_id or len(clean_id) < 5:
            st.error("❌ 올바른 엔카 URL 또는 CarID를 인식하지 못했습니다. 다시 확인해주세요.")
        else:
            option_url = f"https://fem.encar.com/cars/option/{clean_id}"
            detail_url = f"https://fem.encar.com/cars/detail/{clean_id}"
            
            with st.spinner(f"차량 ID [{clean_id}] 옵션표 캡처 및 사진 데이터를 수집 중입니다..."):
                option_screenshot_bytes = None
                raw_img_urls = []

                try:
                    with sync_playwright() as p:
                        try:
                            browser = p.chromium.launch(
                                headless=True,
                                args=["--no-sandbox", "--disable-dev-shm-usage"]
                            )
                        except Exception:
                            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
                            browser = p.chromium.launch(
                                headless=True,
                                args=["--no-sandbox", "--disable-dev-shm-usage"]
                            )

                        try:
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
                            
                            # 1. [옵션표 캡처]
                            page.goto(option_url, wait_until="networkidle", timeout=30000)
                            time.sleep(1.5)
                            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                            time.sleep(0.5)
                            page.evaluate("window.scrollTo(0, 0)")
                            time.sleep(0.5)
                            
                            option_screenshot_bytes = page.screenshot(full_page=True)
                            
                            # 2. [사진 수집]
                            page.goto(detail_url, wait_until="networkidle", timeout=30000)
                            time.sleep(1.5)
                            
                            page.evaluate("window.scrollTo(0, 1200)")
                            time.sleep(0.5)
                            page.evaluate("window.scrollTo(0, 0)")
                            time.sleep(0.5)
                            
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
                        finally:
                            browser.close()

                    # --- [외관 1~4번 절대 고정 + 나머지 정렬 로직] ---
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
                    
                    tab_photos, tab_option = st.tabs([f"📸 차량 사진 ({len(img_urls)}장)", "📋 옵션표 (전체 캡처)"])
                    
                    # 1. 차량 사진 탭
                    with tab_photos:
                        st.subheader("광고 노출사진 (외관 가이드 적용)")
                        if img_urls:
                            for i in range(0, len(img_urls), 2):
                                cols = st.columns(2)
                                
                                # 좌측 컬럼
                                with cols[0]:
                                    is_top4 = i < 4
                                    caption_text = f"사진 {i+1} (외관 가이드 적용)" if is_top4 else f"사진 {i+1}"
                                    display_img = apply_guidelines(img_urls[i]) if is_top4 else img_urls[i]
                                    st.image(display_img, use_container_width=True, caption=caption_text)
                                
                                # 우측 컬럼
                                if i + 1 < len(img_urls):
                                    with cols[1]:
                                        is_top4 = (i + 1) < 4
                                        caption_text = f"사진 {i+2} (외관 가이드 적용)" if is_top4 else f"사진 {i+2}"
                                        display_img = apply_guidelines(img_urls[i+1]) if is_top4 else img_urls[i+1]
                                        st.image(display_img, use_container_width=True, caption=caption_text)
                        else:
                            st.info("추출된 차량 사진이 없습니다.")

                    # 2. 옵션표 탭
                    with tab_option:
                        st.subheader("차량 옵션표")
                        if option_screenshot_bytes:
                            image = Image.open(io.BytesIO(option_screenshot_bytes))
                            st.image(image, use_container_width=True)

                except Exception as e:
                    st.error(f"데이터 수집 중 오류가 발생했습니다: {e}")
