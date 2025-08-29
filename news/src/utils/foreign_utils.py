# ------------------------------------------------------------------
# 작성자 : 최준혁
# 기능 : 해외 주식 관련 유틸 모듈
# ------------------------------------------------------------------
import os
import time
import io
import traceback
from datetime import datetime
from typing import Tuple, Dict, Optional, Callable
from PIL import Image
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from news.src.utils.driver_utils import initialize_driver
from news.src.utils.common_utils import safe_filename 
from news.src.utils.driver_utils import remove_powerlink


W = WebDriverWait

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-08-01
# 기능 : 드라이버를 초기화하고 설정하는 함수
# ------------------------------------------------------------------
def _setup_driver(progress_callback: Optional[Callable[[str], None]] = None) -> WebDriver:
    """웹드라이버를 초기화하고 설정합니다."""
    if progress_callback:
        progress_callback("드라이버 초기화 중...")
    driver = initialize_driver(headless= True)
    driver.set_window_size(1920, 1080)
    return driver

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-08-01
# 기능 : 차트 섹션을 캡처하고 이미지 파일로 저장하는 함수
# ------------------------------------------------------------------
def _capture_chart_section(driver: WebDriver, keyword: str, progress_callback: Optional[Callable[[str], None]] = None, custom_save_dir: Optional[str] = None) -> str:
    """차트 섹션을 캡처하고 이미지 파일로 저장합니다."""
    if progress_callback:
        progress_callback(f"네이버 검색 페이지 이동: {keyword}")

    if keyword == '비트마인 이머션 테크놀로지스':
        keyword = '비트마인'
        search_url = f"https://search.naver.com/search.naver?query={keyword}+주가"
        driver.get(search_url)
        remove_powerlink(driver)
    
    else:
        search_url = f"https://search.naver.com/search.naver?query={keyword}+주가"
        driver.get(search_url)
        remove_powerlink(driver)

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

    if custom_save_dir:
        folder = custom_save_dir
    else:
        today_str = datetime.now().strftime('%Y%m%d')
        folder = os.path.join(os.getcwd(), "생성된 기사", f"기사{today_str}")
    os.makedirs(folder, exist_ok=True)
    screenshot_path = os.path.join(folder, f"{safe_filename(keyword)}_chart.png")
    
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
    
    # 시간 정보 및 마감 상태 확인
    try:
        # 마감 상태 확인
        market_status = ""
        try:
            # 실시간 상태 (GraphMain_status__knYp9)
            market_status_elem = driver.find_element(By.CSS_SELECTOR, ".GraphMain_status__knYp9")
            market_status = market_status_elem.text.strip()
            
            # 마감 상태인지 확인 (GraphMain_close__atwpF 클래스 포함 여부)
            try:
                if market_status_elem.get_attribute("class").find("GraphMain_close__atwpF") != -1:
                    market_status += " (마감)"
            except:
                pass
                
        except NoSuchElementException:
            pass
            
        time_elements = driver.find_elements(
            By.CSS_SELECTOR, 
            "div.GraphMain_date__GglkR span.GraphMain_date__GglkR"
        )
<<<<<<< HEAD
        
        if len(time_elements) >= 2:
            # 현재 년도 가져오기
            current_year = datetime.now().year
            korea_time = time_elements[0].text.replace("\n", " ")
            us_time_text = time_elements[1].text.replace('\n', ' ')
            us_time = f"{us_time_text} {current_year}"
=======
        print(f"time_elements: {time_elements}")

        if len(time_elements) >= 0:
            # 현재 년도 가져오기
            current_year = datetime.now().year
>>>>>>> 36d599f (통합 뉴스 도구v1.1.6)
            
            us_time_text = time_elements[0].text.strip()
            us_time = f"현재시각: {current_year}.{us_time_text}"
            
            print(f"미국 주식 시간 : {us_time}")

            # 마감 상태가 감지된 경우
            if market_status and "마감" in market_status:
                us_time = f"{us_time} (장 마감)"
            
            stock_data["us_time"] = us_time
            
        else:
            # 시간 요소가 없을 경우 (장 마감 후 등) - 변동점 : 미국동부시간 가져오기 or 처리 못하면 PASS
            now = datetime.now()
            current_year = now.year
<<<<<<< HEAD
            korea_time = now.strftime('한국 %m.%d. %H:%M')
            us_time = now.strftime(f'해외 %m.%d. %H:%M {current_year}')
=======
            korea_time = now.strftime(f'현재시각: 한국 {current_year}.%m.%d. %H:%M')
            us_time = now.strftime(f'현재시각: 해외 {current_year}.%m.%d. %H:%M ')
            # Us 타임만 변경 
>>>>>>> 36d599f (통합 뉴스 도구v1.1.6)
            
            # 마감 상태가 감지된 경우
            if market_status and "마감" in market_status:
                us_time = f"{us_time} (장 마감)"
                
            stock_data["korea_time"] = korea_time
            stock_data["us_time"] = us_time
            
    except Exception as e:
        # 예외 발생 시 기본값 설정
        now = datetime.now()
        current_year = now.year
<<<<<<< HEAD
        stock_data["korea_time"] = now.strftime('한국 %m.%d. %H:%M')
        stock_data["us_time"] = now.strftime(f'해외 %m.%d. %H:%M {current_year}')
=======
        stock_data["korea_time"] = now.strftime(f'현재시각: 한국 {current_year}.%m.%d. %H:%M')
        stock_data["us_time"] = now.strftime(f'현재시각: 해외 {current_year}.%m.%d. %H:%M ')
        # US 타임으로 변경
>>>>>>> 36d599f (통합 뉴스 도구v1.1.6)
        print(f"시간 정보 추출 중 오류 발생: {e}")
    
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
    # try:
    #     overview = driver.find_element(By.CSS_SELECTOR, "div.Overview_text__zT3AI")
    #     stock_data["기업 개요"] = overview.text.strip()
    # except NoSuchElementException:
    #     pass

    try:
        # After Market 정보 컨테이너 대기
        box = WebDriverWait(driver, 3).until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "div[class*='StockInfoPreAfter_article']")
        ))

        # find_elements를 사용하여 요소가 없어도 오류가 나지 않도록 처리
        price_elems = box.find_elements(By.CSS_SELECTOR, "span[class*='StockInfoPreAfter_num']")
        change_amt_elems = box.find_elements(By.CSS_SELECTOR, "span[class*='StockInfoPreAfter_numGap'] div:nth-of-type(1)")
        change_pct_elems = box.find_elements(By.CSS_SELECTOR, "span[class*='StockInfoPreAfter_numGap'] div:nth-of-type(2)")
        status_elems = box.find_elements(By.CSS_SELECTOR, "span[class*='marketStatus']")


        # 요소가 존재하는 경우에만 텍스트 추출
        price = price_elems[0].text.strip() if price_elems else "N/A"
        change_amt = change_amt_elems[0].text.strip() if change_amt_elems else "N/A"
        change_pct = change_pct_elems[0].text.strip() if change_pct_elems else "N/A"
        status = status_elems[0].text.strip() if status_elems else "N/A"

        # 시간 정보 파싱
        # times = {}
        # if time_elems:
        #     for t in time_elems:
        #         txt = t.text.strip()
        #         if '한국' in txt:
        #             times['한국'] = txt.replace('한국', '').strip()
        #         elif '미국' in txt:
        #             time_part = txt.split('•')[0]
        #             times['미국'] = time_part.replace('미국', '').strip()
        
        # 모든 정보가 수집되었을 때만 딕셔너리에 추가
        if price != "N/A":
            stock_data["시간 외 거래"] = {
                "상태": status,
                "가격": price,
                "전일대비": change_amt,
                "등락률": change_pct
                # "시간": times
            }

    except Exception as e:
        print(f"[DEBUG] 시간 외 거래 정보를 찾을 수 없거나 처리 중 오류 발생: {e}")
        pass
    return stock_data

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-08-01
# 기능 : 네이버에서 해외 주식 차트 캡처 및 상세 정보 크롤링 함수
# ------------------------------------------------------------------
def capture_naver_foreign_stock_chart(
    keyword: str, 
    progress_callback: Optional[Callable[[str], None]] = None,
    custom_save_dir: Optional[str] = None
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

    try:
        # 1. 드라이버 설정 및 초기 페이지 로드
        driver = _setup_driver(progress_callback)
        
        # 2. 차트 캡처
        screenshot_path, chart_section = _capture_chart_section(driver, keyword, progress_callback, custom_save_dir)

        if not screenshot_path or not os.path.exists(screenshot_path):
            print(f"[WARNING] 스크린샷 파일 없음: {screenshot_path}")
            return None, {}, False

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
