import sys
import asyncio
import os
import subprocess
import streamlit as st

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

from playwright.sync_api import sync_playwright
import re
import time
from PIL import Image
import io

# Page Config (모바일 레이아웃 최적화)
st.set_page_config(
    page_title="엔카 차량 옵션 & 사진 조회",
    page_icon="🚗",
    layout="centered"
)

st.title("🚗 엔카 차량 옵션 & 사진 수집기")

# 입력창 (value=""로 기본값 비움)
car_id_input = st.text_input(
    "엔카 Car ID 입력", 
    value="", 
    placeholder="예: 42153179",
    help="엔카 차량 상세 URL의 carid 숫자를 입력하세요."
)

if st.button("조회하기", type="primary", use_container_width=True):
    clean_id = re.sub(r"\D", "", car_id_input)
    
    if not clean_id:
        st.warning("올바른 차량 ID(숫자)를 입력해주세요.")
    else:
        with st.spinner("엔카 데이터를 가져오는 중입니다... (약 10~15초 소요)"):
            try:
                target_url = f"https://fem.encar.com/cars/detail/{clean_id}"
                
                with sync_playwright() as p:
                    browser = p.chromium.launch(
                        headless=True,
                        args=["--no-sandbox", "--disable-dev-shm-usage"]
                    )
                    # 모바일 에뮬레이션 설정 (iPhone 12 크기)
                    context = browser.new_context(
                        viewport={"width": 390, "height": 844},
                        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
                    )
                    page = context.new_page()
                    
                    # 1. 페이지 이동
                    page.goto(target_url, wait_until="networkidle", timeout=30000)
                    time.sleep(2)  # 기본 스크립트 실행 대기
                    
                    # 2. 지연 로딩 요소를 유도하기 위한 스크롤 다운/업
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")
                    time.sleep(1)
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                    time.sleep(1)
                    
                    # 3. 옵션 관련 요소가 로드될 때까지 렌더링 대기
                    # (엔카 모바일 페이지의 주요 셀렉터 대기)
                    try:
                        page.wait_for_selector(".DetailOption", timeout=5000)
                    except Exception:
                        pass # 셀렉터 이름이 달라져도 계속 진행
                    
                    time.sleep(1.5) # 최종 렌더링 안정화 대기
                    
                    # 4. 옵션표 캡처 (전체 페이지 또는 지정 스크롤 위치)
                    option_screenshot_bytes = page.screenshot(full_page=False)
                    
                    # 5. 차량 이미지 URL 수집
                    # 엔카 모바일 페이지 이미지 추출
                    img_elements = page.query_selector_all("img")
                    img_urls = []
                    for img in img_elements:
                        src = img.get_attribute("src") or img.get_attribute("data-src")
                        if src and ("carpicture" in src or "file.encar.com" in src):
                            if not src.startswith("http"):
                                src = "https:" + src
                            if src not in img_urls:
                                img_urls.append(src)
                                
                    browser.close()

                # --- 결과 출력 UI (탭 분리 모바일 최적화) ---
                st.success(f"차량 ID [{clean_id}] 데이터 수집 완료!")
                
                # 모바일 화면을 위해 탭으로 옵션과 사진 분리
                tab_option, tab_photos = st.tabs(["📋 옵션 표 캡처", f"📸 차량 사진 ({len(img_urls)}장)"])
                
                with tab_option:
                    st.subheader("차량 옵션표 캡처")
                    image = Image.open(io.BytesIO(option_screenshot_bytes))
                    st.image(image, use_column_width=True)
                    
                with tab_photos:
                    st.subheader("수집된 차량 사진")
                    if img_urls:
                        # 모바일에서는 2열 배치가 가장 보기 좋습니다.
                        cols = st.columns(2)
                        for idx, url in enumerate(img_urls):
                            with cols[idx % 2]:
                                st.image(url, use_column_width=True, caption=f"사진 {idx+1}")
                    else:
                        st.info("추출된 차량 사진이 없습니다.")

            except Exception as e:
                st.error(f"데이터를 가져오는 중 오류가 발생했습니다: {e}")