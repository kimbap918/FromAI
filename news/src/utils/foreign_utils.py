# ------------------------------------------------------------------
# 작성자 : 최준혁
# 기능 : 해외 주식 관련 유틸 모듈
# ------------------------------------------------------------------
import os
import time
import io
import traceback
from typing import Tuple, Dict, Optional, Callable
from PIL import Image
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from news.src.utils.driver_utils import initialize_driver

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-08-01
# 기능 : 드라이버를 초기화하고 설정하는 함수
# ------------------------------------------------------------------
def _setup_driver(progress_callback: Optional[Callable[[str], None]] = None) -> WebDriver:
    """웹드라이버를 초기화하고 설정합니다."""
    if progress_callback:
        progress_callback("드라이버 초기화 중...")
    driver = initialize_driver(headless=True)
    driver.set_window_size(1920, 1080)
    return driver

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-08-01
# 기능 : 차트 섹션을 캡처하고 이미지 파일로 저장하는 함수
# ------------------------------------------------------------------
def _capture_chart_section(driver: WebDriver, keyword: str, progress_callback: Optional[Callable[[str], None]] = None) -> str:
    """차트 섹션을 캡처하고 이미지 파일로 저장합니다."""
    if progress_callback:
        progress_callback(f"네이버 검색 페이지 이동: {keyword}")
    
    search_url = f"https://search.naver.com/search.naver?query={keyword}+주가"
    driver.get(search_url)
    
    # 차트 섹션 찾기
    chart_section = WebDriverWait(driver, 5).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "section.sc_new.cs_stock"))
    )
    
    # 캔버스 로드 대기 (에러는 무시하고 계속 진행)
    try:
        WebDriverWait(chart_section, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div#stock_normal_chart3 canvas"))
        )
        time.sleep(0.5)
    except TimeoutException as e:
        if progress_callback:
            progress_callback(f"⚠️ 캔버스를 찾지 못했습니다: {e}")
    
    # 스크린샷 촬영
    wrap_elem = driver.find_element(By.CSS_SELECTOR, "div.api_cs_wrap")
    screenshot_path = f"{keyword}_chart.png"
    
    # 스크린샷 저장 시도 (두 가지 방법으로 시도)
    try:
        if not wrap_elem.screenshot(screenshot_path):
            raise Exception("Failed to save screenshot using element.screenshot()")
    except Exception:
        png_bytes = wrap_elem.screenshot_as_png
        Image.open(io.BytesIO(png_bytes)).save(screenshot_path)
    
    # 이미지 크롭을 위한 영역 계산
    try:
        invest_elem = driver.find_element(By.CSS_SELECTOR, "div.invest_wrap._button_scroller")
        rel_invest_bottom = (invest_elem.location['y'] - wrap_elem.location['y']) + invest_elem.size['height']
    except NoSuchElementException:
        try:
            more_view_elem = driver.find_element(By.CSS_SELECTOR, "div.more_view")
            rel_invest_bottom = more_view_elem.location['y'] - wrap_elem.location['y']
        except NoSuchElementException:
            rel_invest_bottom = wrap_elem.size['height']
    
    # 이미지 크롭 및 저장
    dpr = driver.execute_script("return window.devicePixelRatio")
    img = Image.open(screenshot_path)
    right = int(wrap_elem.size['width'] * dpr)
    bottom = int(rel_invest_bottom * dpr)
    img = img.crop((0, 0, right, bottom))
    img.save(screenshot_path)
    
    if progress_callback:
        progress_callback("✅ 차트 캡처 완료")
    
    return screenshot_path, chart_section

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-08-01
# 기능 : 해외 주식 상세 정보를 추출하는 함수
# ------------------------------------------------------------------
def _extract_stock_data(driver: WebDriver, keyword: str) -> Dict:
    """해외 주식 상세 정보를 추출합니다."""
    stock_data = {"keyword": keyword}
    
    # 기본 정보 추출
    stock_data["name"] = driver.find_element(By.CSS_SELECTOR, ".GraphMain_name__cEsOs").text
    stock_data["price"] = driver.find_element(By.CSS_SELECTOR, ".GraphMain_price__H72B2").text
    
    # 가격 변동 정보
    change_el = driver.find_element(By.CSS_SELECTOR, "div[class*='VGap_stockGap']")
    stock_data["change"] = change_el.text.replace("\n", " ")
    
    # 시간 정보
    time_elements = driver.find_elements(
        By.CSS_SELECTOR, 
        ".GraphMain_date__GglkR .GraphMain_time__38Tp2"
    )
    if len(time_elements) >= 2:
        stock_data["korea_time"] = time_elements[0].text.replace("\n", " ")
        stock_data["us_time"] = time_elements[1].text.replace("\n", " ")
    
    # 추가 정보 펼치기 시도
    try:
        more_info_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "a.StockInfo_btnFold__XEUUS"))
        )
        driver.execute_script("arguments[0].click();", more_info_button)
        time.sleep(0.5)
    except TimeoutException:
        pass
    
    # 재무 정보 추출
    financial_items = driver.find_elements(
        By.CSS_SELECTOR, 
        "ul.StockInfo_list__V96U6 > li.StockInfo_item__puHWj"
    )
    for idx, item in enumerate(financial_items):
        parts = item.text.split("\n")
        # 값이 N/A인 경우 예외 처리
        if any(p.strip() == "N/A" for p in parts):
            stock_data[parts[0].strip()] = "N/A"
            print(" 재무 정보 : ", parts[0].strip(), "N/A")
        elif len(parts) >= 2:
            if 8 <= idx <= 15 and len(parts) >= 3:
                stock_data[parts[0].strip()] = parts[2].strip()
                print(" 재무 정보 : ", parts[0].strip(), parts[2].strip())
            else:
                stock_data[parts[0].strip()] = " ".join(parts[1:]).strip()
                print(" 재무 정보 : ", parts[0].strip(), " ".join(parts[1:]).strip())
        else:
            stock_data[parts[0].strip()] = ""
            print(" 재무 정보 : ", parts[0].strip())
    
    # 기업 개요 추출
    try:
        overview = driver.find_element(By.CSS_SELECTOR, "div.Overview_text__zT3AI")
        stock_data["기업 개요"] = overview.text.strip()
    except NoSuchElementException:
        pass
    
    return stock_data

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-08-01
# 기능 : 네이버에서 해외 주식 차트 캡처 및 상세 정보 크롤링 함수
# ------------------------------------------------------------------
def capture_naver_foreign_stock_chart(
    keyword: str, 
    progress_callback: Optional[Callable[[str], None]] = None
) -> Tuple[Optional[str], Dict, bool]:
    """
    네이버에서 해외 주식 차트 캡처 및 상세 정보 크롤링 함수
    
    Args:
        keyword: 검색할 주식 키워드
        progress_callback: 진행 상황을 알리기 위한 콜백 함수
        
    Returns:
        tuple: (screenshot_path, stock_data, success)
            - screenshot_path: 저장된 차트 이미지 경로 (실패 시 None)
            - stock_data: 추출된 주식 데이터 (실패 시 빈 dict)
            - success: 작업 성공 여부
    """
    driver = None
    stock_data = {}
    screenshot_path = f"{keyword}_chart.png"

    try:
        # 1. 드라이버 설정 및 초기 페이지 로드
        driver = _setup_driver(progress_callback)
        
        # 2. 차트 캡처
        screenshot_path, chart_section = _capture_chart_section(driver, keyword, progress_callback)
        
        # 3. 상세 페이지로 이동
        more_view = chart_section.find_element(By.CSS_SELECTOR, "div.more_view a")
        before_handles = driver.window_handles
        driver.execute_script("arguments[0].click();", more_view)
        
        # 새 창으로 전환
        time.sleep(0.5)
        new_window = [h for h in driver.window_handles if h not in before_handles]
        if new_window:
            driver.switch_to.window(new_window[0])
        
        # 4. 상세 데이터 추출
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".GraphMain_name__cEsOs"))
        )
        
        stock_data = _extract_stock_data(driver, keyword)
        
        if progress_callback:
            progress_callback("✅ 데이터 추출 완료")
            
        return screenshot_path, stock_data, True
        
    except Exception as e:
        if progress_callback:
            progress_callback(f"❌ 오류 발생: {str(e)}")
        print(f"❌ 오류: {e}")
        traceback.print_exc()
        return None, {}, False
        
    finally:
        if driver:
            driver.quit()
