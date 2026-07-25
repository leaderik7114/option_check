import sys
import asyncio
import os
import subprocess

# Streamlit Cloud (Linux) 환경에서 Playwright 브라우저 자동 설치
@st.cache_resource
def install_playwright_browsers():
    try:
        subprocess.run(["playwright", "install", "chromium"], check=True)
    except Exception as e:
        print(f"Playwright install error: {e}")

install_playwright_browsers()

# Windows 환경 Playwright asyncio 충돌 방지 설정
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import streamlit as st
from playwright.sync_api import sync_playwright
import re
import time

# -----------------------------------------------------------------------------
# 1. 페이지 기본 설정
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="엔카 모바일 옵션 스냅샷 & 사진 추출기",
    page_icon="🚗",
    layout="wide"
)

st.title("🚗 엔카 모바일 옵션 스크린샷 & 사진 추출기")
st.write("왼쪽에는 **원본 사이즈 모바일 옵션 스크린샷**, 오른쪽에는 **차량 사진 목록**이 배치됩니다.")

# -----------------------------------------------------------------------------
# 2. 사용자 입력
# -----------------------------------------------------------------------------
col_input, col_grid, col_width = st.columns([3, 1, 1])
with col_input:
    car_id_input = st.text_input(
        "엔카 Car ID 입력", 
        value="42153179", 
        placeholder="예: 42153179",
        help="엔카 주소창의 숫자로 된 차량 ID를 입력하세요."
    )
with col_grid:
    grid_cols = st.selectbox("우측 사진 열 배치", [2, 3, 4], index=1)
with col_width:
    img_width = st.number_input("스크린샷 너비(px)", min_value=200, max_value=600, value=350, step=10)


# -----------------------------------------------------------------------------
# 3. Playwright 2단계 수집 함수
# -----------------------------------------------------------------------------
def capture_encar_mobile(car_id_str):
    option_url = f"https://fem.encar.com/cars/option/{car_id_str}"
    detail_url = f"https://fem.encar.com/cars/detail/{car_id_str}"
    
    screenshot_bytes = None
    img_urls = []
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            
            # 모바일(iPhone 13) 환경 설정
            context = browser.new_context(
                viewport={"width": 390, "height": 844},
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
            )
            
            page = context.new_page()
            
            # 1단계: /option 스크린샷 캡처
            page.goto(option_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
            screenshot_bytes = page.screenshot(full_page=True)
            
            # 2단계: /detail 사진 URL 수집
            page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(1.5)
            
            rendered_html = page.content()
            photo_matches = re.findall(r'(/carpicture/[^\s"\'\\]+\.(?:jpg|jpeg|png))', rendered_html, re.IGNORECASE)
            for path in photo_matches:
                img_urls.append(f"https://ci.encar.com{path}")

            browser.close()
            
    except Exception as e:
        st.error(f"브라우저 실행 중 오류 발생: {e}")

    img_urls = list(dict.fromkeys(img_urls))
    return screenshot_bytes, img_urls


# -----------------------------------------------------------------------------
# 4. 실행 및 양갈래 레이아웃 출력
# -----------------------------------------------------------------------------
if st.button("옵션 캡처 & 사진 가져오기", type="primary"):
    clean_id = car_id_input.strip()
    
    if not clean_id:
        st.warning("Car ID를 입력해 주세요.")
    else:
        with st.spinner("가상 브라우저가 옵션 캡처 및 사진을 수집 중입니다 (약 4~6초 소요)..."):
            screenshot_bytes, img_urls = capture_encar_mobile(clean_id)
            
            if screenshot_bytes or img_urls:
                st.success(f"매물 ID `{clean_id}` 수집 완료!")
                st.markdown(f"🔗 [엔카 옵션 페이지 직접 열기](https://fem.encar.com/cars/option/{clean_id})")
                st.divider()

                # 화면 비율 조정 (왼쪽 4 : 오른쪽 6)
                col_left, col_right = st.columns([4, 6], gap="large")

                # -------------------------------------------------------------
                # [왼쪽 컬럼] 모바일 옵션 스크린샷 (고정 너비)
                # -------------------------------------------------------------
                with col_left:
                    st.subheader("📱 엔카 모바일 옵션 스크린샷")
                    if screenshot_bytes:
                        # width=img_width를 주어 화면 맞춤 확대 방지 (기본 350px)
                        st.image(screenshot_bytes, caption="실제 모바일 크기 스크린샷", width=img_width)
                        
                        st.download_button(
                            label="🖼️ 옵션 스크린샷 다운로드",
                            data=screenshot_bytes,
                            file_name=f"encar_option_{clean_id}.png",
                            mime="image/png"
                        )
                    else:
                        st.warning("옵션 스크린샷을 찍지 못했습니다.")

                # -------------------------------------------------------------
                # [오른쪽 컬럼] 차량 사진 목록
                # -------------------------------------------------------------
                with col_right:
                    st.subheader(f"🖼️ 차량 사진 목록 (총 {len(img_urls)}장)")
                    if img_urls:
                        photo_cols = st.columns(grid_cols)
                        for idx, url in enumerate(img_urls):
                            with photo_cols[idx % grid_cols]:
                                st.image(url, caption=f"사진 {idx+1}", use_container_width=True)
                    else:
                        st.warning("사진을 읽어오지 못했습니다.")