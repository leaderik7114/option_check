import sys
import asyncio
import os
import subprocess
import streamlit as st

# Streamlit Cloud (Linux) 환경에서 Playwright 브라우저 자동 설치
@st.cache_resource
def install_playwright_browsers():
    try:
        # headless chromium 설치 (--with-deps 포함)
        subprocess.run(["playwright", "install", "--with-deps", "chromium"], check=True)
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

# --- Page Config (모바일 레이아웃 및 검색 엔진 차단 최적화) ---
st.set_page_config(
    page_title="엔카 차량 정보 간편 조회",
    page_icon="🚗",
    layout="centered" #Centered로 하여 모바일에서 볼때 중앙 정렬
)

st.title("🚗 엔카 차량 옵션 & 사진 수집기")

# --- UI 설명 ---
st.markdown("""
<div style="background-color:#f0f2f6; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
<b>[필독] 서비스 안내</b><br/>
본 서비스는 엔카의 <b>모바일 상세 페이지</b> 정보를 기반으로 작동합니다.<br/>
PC 버전 URL을 입력해도 자동으로 모바일 URL로 변환하여 데이터를 요청하므로, 
해외 서버 접속 차단 문제를 완회하여 안정적인 데이터를 제공합니다.<br/>
(단, 엔카 사이트의 일시적인 보안 강화 시 차단될 수 있습니다)
</div>
""", unsafe_allow_html=True)

# --- 입력창 ---
car_id_input = st.text_input(
    "엔카 차량 URL 또는 Car ID 입력", 
    value="", 
    placeholder="예: https://www.encar.com/dc/dc_cardetailview.do?carid=42153179 또는 42153179",
    help="주소창의 URL을 그대로 붙여넣거나, 숫자로 된 차량 ID를 입력하세요."
)

# --- 조회 버튼 ---
if st.button("조회하기", type="primary", use_container_width=True):
    # 숫자 ID만 추출 (URL 입력 시에도 ID만 추출)
    clean_id = re.sub(r"\D", "", car_id_input)
    
    if not clean_id:
        st.warning("올바른 차량 ID(숫자) 또는 URL을 입력해주세요.")
    else:
        # --- 최종 모바일 URL 구성 ---
        # 이 부분이 해외 차단을 우회하는 핵심입니다.
        target_url = f"https://fem.encar.com/cars/detail/{clean_id}"
        
        with st.spinner("엔카 보안 우회 및 데이터 수집 중... (약 10~15초 소요)"):
            try:
                # 데이터를 담을 변수 초기화
                option_screenshot_bytes = None
                img_urls = []

                with sync_playwright() as p:
                    # 브라우저 실행 (headless=True)
                    browser = p.chromium.launch(
                        headless=True,
                        args=["--no-sandbox", "--disable-dev-shm-usage"]
                    )
                    
                    # --- 모바일 에뮬레이션 설정 (iPhone 12 크기) ---
                    # 보안 시스템이 실제 모바일 기기로 인식하도록 User Agent 설정
                    context = browser.new_context(
                        viewport={"width": 390, "height": 844},
                        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
                    )
                    page = context.new_page()
                    
                    # 1. 페이지 이동 및 기본 네트워크 안정화 대기
                    # wait_until="networkidle"로 주요 리소스 로딩까지 대기
                    page.goto(target_url, wait_until="networkidle", timeout=45000)
                    time.sleep(3)  # 초기 JS 실행 및 로딩 애니메이션 대기

                    # 2. 보안 차단 여부 1차 확인 (보안 문구/Captcha 감지)
                    # 만약 차단 화면이라면 "Verify you are human" 등의 문구가 포함될 확률이 높음
                    page_content = page.content()
                    if "Verify you are human" in page_content or "Cloudflare" in page_content or "접속이 제한되었습니다" in page_content:
                         st.error(f"죄송합니다. 엔카 보안 시스템에 의해 서버 IP가 차단되었습니다.<br/>모바일 URL을 사용해도 차단되는 경우, 엔카의 보안 정책이 매우 강화된 상태입니다.<br/>잠시 후 다시 시도해주시거나, 다른 차량 ID를 입력해보세요.<br/>(캡처된 차단 화면: below)", unsafe_allow_html=True)
                         option_screenshot_bytes = page.screenshot() # 차단 화면 캡처
                         browser.close()
                         raise Exception("Network Blocked by Encar Security") # 예외 발생시켜 중단
                    
                    # 3. 지연 로딩(옵션표 등)을 유도하기 위한 스크롤 다운
                    # 엔카 모바일은 스크롤 시 옵션 데이터가 그려집니다.
                    st.info("옵션표 로딩을 위해 페이지를 스크롤 중입니다...")
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")
                    time.sleep(1)
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                    time.sleep(1)

                    # 4. 옵션 관련 요소가 로드될 때까지 렌더링 대기
                    st.info("옵션표 렌더링 완료를 기다리는 중...")
                    # 실제 모바일 페이지의 옵션 영역 셀렉터 대기 (.DetailOption)
                    try:
                        page.wait_for_selector(".DetailOption", timeout=10000)
                    except Exception:
                        # 셀렉터를 찾지 못하더라도 계속 진행 (차단 안된 경우)
                        pass
                    
                    time.sleep(2) # 최종 렌더링 안정화 대기
                    
                    # 5. 옵션표 캡처 (탭 메뉴에 표시할 최종 화면)
                    option_screenshot_bytes = page.screenshot(full_page=False)
                    
                    # 6. 차량 이미지 URL 수집
                    st.info("차량 사진 URL 추출 중...")
                    img_elements = page.query_selector_all("img")
                    for img in img_elements:
                        src = img.get_attribute("src") or img.get_attribute("data-src")
                        if src and ("carpicture" in src or "file.encar.com" in src):
                            if not src.startswith("http"):
                                src = "https:" + src
                            if src not in img_urls:
                                img_urls.append(src)
                                
                    browser.close()

                # --- 결과 출력 UI (탭 분리 모바일 최적화) ---
                if option_screenshot_bytes and img_urls:
                    st.success(f"차량 ID [{clean_id}] 데이터 수집 완료!")
                    
                    # 모바일 화면을 위해 탭으로 옵션과 사진 분리
                    tab_option, tab_photos = st.tabs(["📋 옵션 정보 (캡처)", f"📸 차량 사진 ({len(img_urls)}장)"])
                    
                    with tab_option:
                        st.subheader("옵션 정보")
                        image = Image.open(io.BytesIO(option_screenshot_bytes))
                        # 모바일 앱에서 캡처한 것처럼 중앙에 깔끔하게 표시
                        st.image(image, use_column_width=True)
                        
                    with tab_photos:
                        st.subheader("수집된 차량 사진")
                        # 모바일에서는 2열 배치가 가시성이 좋습니다.
                        cols = st.columns(2)
                        for idx, url in enumerate(img_urls):
                            with cols[idx % 2]:
                                st.image(url, use_column_width=True, caption=f"사진 {idx+1}")
                elif option_screenshot_bytes: # 차단 화면만 캡처된 경우 (오류 처리 탭)
                     st.image(Image.open(io.BytesIO(option_screenshot_bytes)), use_column_width=True)

            except Exception as e:
                if "Network Blocked" not in str(e):
                    st.error(f"데이터 수집 중 예상치 못한 오류가 발생했습니다: {e}")