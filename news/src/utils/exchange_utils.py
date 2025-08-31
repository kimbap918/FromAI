# ------------------------------------------------------------------
# 작성자 : 최준혁
# 기능 : 네이버 금융 환율 정보 검색 및 차트 캡처 유틸리티 모듈
# ------------------------------------------------------------------
import os
import time
import io
from datetime import datetime
from PIL import Image
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from news.src.utils.driver_utils import initialize_driver
from news.src.utils.clipboard_utils import copy_image_to_clipboard

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 기능 : 환율 검색어 생성
# ------------------------------------------------------------------
def make_exchange_keyword(keyword: str) -> str:
    """
    환율 정보 검색을 위한 검색어 생성
    :param keyword: 변환할 원본 키워드 (예: '달러')
    :return: '환율'이 접미사로 붙은 검색어 (예: '달러환율')
    """
    keyword = keyword.strip()
    if keyword.endswith("환율"):
        return keyword
    return f"{keyword}환율"

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 기능 : 환율 차트 캡처
# ------------------------------------------------------------------
def capture_exchange_chart(keyword: str, progress_callback=None) -> str:
    """
    네이버 검색에서 환율 차트를 찾아 캡처 및 저장
    :param keyword: 검색할 환율 키워드 (예: '달러', '유로')
    :param progress_callback: 진행 상태를 전달할 콜백 함수
    :return: 캡처된 이미지 파일의 전체 경로
    """
    if progress_callback:
        progress_callback("네이버 검색 페이지 접속 중...")

    keyword = make_exchange_keyword(keyword)
    driver = initialize_driver()

    try:
        url = f"https://search.naver.com/search.naver?query={keyword}"
        driver.get(url)
        
        if progress_callback:
            progress_callback("페이지 로딩 대기 중...")
            
        WebDriverWait(driver, 3).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        time.sleep(0.5)
        
        if progress_callback:
            progress_callback("차트 영역 찾는 중...")
            
        # 차트 영역 찾기 시도
        selectors = [
            ("div.exchange_top.up", "div.invest_wrap"),
            ("div.exchange_top", "div.invest_wrap"),
            ("[class*='exchange']", "[class*='invest']")
        ]
        
        top = bottom = None
        for top_selector, bottom_selector in selectors:
            try:
                top = driver.find_element(By.CSS_SELECTOR, top_selector)
                bottom = driver.find_element(By.CSS_SELECTOR, bottom_selector)
                if top and bottom:
                    break
            except:
                continue
                
        if not top or not bottom:
            if progress_callback:
                progress_callback("❌ 환율 차트 영역을 찾을 수 없습니다.")
            raise Exception(f"환율 차트 요소를 찾을 수 없습니다. 검색어: {keyword}")
            
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", top)
        time.sleep(0.3)
        
        zoom = driver.execute_script("return window.devicePixelRatio || 1;")
        start_y = int(top.location['y'] * zoom)
        end_y = int((bottom.location['y'] + bottom.size['height']) * zoom)
        
        if progress_callback:
            progress_callback("화면 전체 스크린샷 캡처 중...")
            
        screenshot = driver.get_screenshot_as_png()
        
        with Image.open(io.BytesIO(screenshot)).convert("RGB") as image:
            top_coord = max(0, start_y)
            bottom_coord = min(image.height, end_y - 20)
            left_offset = 395
            crop_width = 670
            
            if progress_callback:
                progress_callback("차트 이미지 잘라내기...")
                
            cropped = image.crop((left_offset, top_coord, left_offset + crop_width, bottom_coord))
            currency = top.text.split('\n')[0].strip().replace(' ', '') or "환율"
            today = datetime.now().strftime('%Y%m%d')
            folder = os.path.join(os.getcwd(), "환율차트", f"환율{today}")
            os.makedirs(folder, exist_ok=True)
            output_path = os.path.join(folder, f"{currency}_환율차트.png")
            cropped.save(output_path, format="PNG")
            
        if progress_callback:
            progress_callback("이미지를 클립보드에 복사 중...")
            
        copy_image_to_clipboard(output_path)
        return output_path
        
    finally:
        driver.quit()