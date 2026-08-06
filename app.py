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
    모바일 촬영 화면 비율(20:9)의 캔버스를 만든 후, 
    중앙에 원본 사진을 넣고 모바일 가이드라인을 정확히 합성하는 함수
    """
    try:
        if isinstance(image_input, str):
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            response = requests.get(image_input, headers=headers, timeout=10)
            response.raise_for_status()
            raw_img = Image.open(io.BytesIO(response.content)).convert("RGBA")
        else:
            raw_img = image_input.convert("RGBA")
    except Exception:
        return image_input

    # 1. 모바일 촬영 전체 화면 기준 캔버스 생성 (20:9 비율 / 2400 x 1080)
    CANVAS_W = 2400
    CANVAS_H = 1080
    
    # 2. 배경 캔버스 (카메라 화면 바탕)
    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), (20, 20, 20, 255))
    
    # 3. 원본 사진을 캔버스 높이(1080px)에 맞춰 비율 유지하며 중앙에 배치
    raw_w, raw_h = raw_img.size
    scale = CANVAS_H / raw_h
    new_w = int(raw_w * scale)
    new_h = CANVAS_H
    
    resized_img = raw_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    
    # 중앙에 사진 붙이기
    offset_x = (CANVAS_W - new_w) // 2
    canvas.paste(resized_img, (offset_x, 0))

    # 4. 모바일 화면 센티미터(40.2cm x 22.5cm) 스케일 가이드선 그리기
    overlay = Image.new("RGBA", (CANVAS_W, CANVAS_H), (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    SLIDE_W = 40.2
    SLIDE_H = 22.5

    def x_px(cm): return int((cm / SLIDE_W) * CANVAS_W)
    def y_px(cm): return int((cm / SLIDE_H) * CANVAS_H)

    line_thick = 4

    # Color 정의
    RED = (235, 35, 35, 230)
    ORANGE = (245, 150, 20, 230)
    GREEN_LIGHT = (160, 210, 140, 220)
    GREEN_DARK = (80, 150, 70, 230)
    WHITE_SUB = (240, 240, 240, 180)

    # 1. 흰색 수평 구도 보조선
    draw.line([(0, y_px(9.8)), (CANVAS_W, y_px(9.8))], fill=WHITE_SUB, width=2)
    draw.line([(0, y_px(12.7)), (CANVAS_W, y_px(12.7))], fill=WHITE_SUB, width=2)

    # 2. 초록색 수직 가이드선 (대형 차량 사이드)
    draw.line([(x_px(5.6), 0), (x_px(5.6), CANVAS_H)], fill=GREEN_LIGHT, width=line_thick)
    draw.line([(x_px(6.5), 0), (x_px(6.5), CANVAS_H)], fill=GREEN_DARK, width=line_thick)
    draw.line([(x_px(33.1), 0), (x_px(33.1), CANVAS_H)], fill=GREEN_DARK, width=line_thick)
    draw.line([(x_px(33.8), 0), (x_px(33.8), CANVAS_H)], fill=GREEN_LIGHT, width=line_thick)

    # 3. 주황색 수직/수평 중심 가이드선 (중형 차량 사이드 & 중앙선)
    draw.line([(x_px(8.6), 0), (x_px(8.6), CANVAS_H)], fill=ORANGE, width=line_thick)
    draw.line([(x_px(31.2), 0), (x_px(31.2), CANVAS_H)], fill=ORANGE, width=line_thick)
    draw.line([(x_px(19.8), 0), (x_px(19.8), CANVAS_H)], fill=ORANGE, width=line_thick + 1)
    draw.line([(0, y_px(11.4)), (CANVAS_W, y_px(11.4))], fill=ORANGE, width=line_thick + 1)

    # 4. 빨간색 외곽 테두리 & 타이어 바닥 접지선
    draw.rectangle([x_px(4.8), y_px(0.8), x_px(35.4), y_px(21.7)], outline=RED, width=line_thick + 2)
    draw.line([(0, y_px(19.3)), (CANVAS_W, y_px(19.3))], fill=RED, width=line_thick + 2)

    # 합쳐서 반환
    combined = Image.alpha_composite(canvas, overlay)
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
