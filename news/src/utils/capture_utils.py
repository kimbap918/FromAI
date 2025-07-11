# utils/capture_utils.py

import os
import time
import io
from datetime import datetime
from PIL import Image
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from news.src.utils.driver_utils import initialize_driver
from news.src.utils.clipboard_utils import copy_image_to_clipboard


# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 기능 : 네이버 검색에서 환율 차트를 찾아 캡처하고 저장하는 함수(환율 차트)
# ------------------------------------------------------------------
def make_exchange_keyword(keyword: str) -> str:
    keyword = keyword.strip()
    if keyword.endswith("환율"):
        return keyword
    return f"{keyword}환율"

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-10
# 기능 : 네이버 검색에서 환율 차트를 찾아 캡처하고 저장하는 함수(환율 차트)
# ------------------------------------------------------------------
def capture_exchange_chart(keyword: str, progress_callback=None) -> str:
    """
    네이버 검색에서 환율 차트를 찾아 캡처하고 저장
    :param keyword: 검색어 (예: "달러환율" 또는 "달러")
    :param progress_callback: 진행상황 콜백 함수 (옵션)
    :return: 저장된 이미지 경로
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
        time.sleep(0.3)  # 페이지 로딩을 위한 대기 시간 증가

        # 환율 차트 영역 찾기
        if progress_callback:
            progress_callback("차트 영역 찾는 중...")
        top = None
        bottom = None
        try:
            top = driver.find_element(By.CSS_SELECTOR, "div.exchange_top.up")
            bottom = driver.find_element(By.CSS_SELECTOR, "div.invest_wrap")
        except:
            pass
        if not top:
            try:
                top = driver.find_element(By.CSS_SELECTOR, "div.exchange_top")
                bottom = driver.find_element(By.CSS_SELECTOR, "div.invest_wrap")
            except:
                pass
        if not top:
            try:
                top = driver.find_element(By.CSS_SELECTOR, "[class*='exchange']")
                bottom = driver.find_element(By.CSS_SELECTOR, "[class*='invest']")
            except:
                pass
        if not top:
            try:
                elements = driver.find_elements(By.XPATH, "//*[contains(text(), '환율') or contains(text(), '달러') or contains(text(), '엔화')]")
                if elements:
                    top = elements[0]
                    bottom = driver.find_element(By.CSS_SELECTOR, "div.invest_wrap")
            except:
                pass
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
        image = Image.open(io.BytesIO(screenshot))

        top_coord = max(0, start_y)
        bottom_coord = min(image.height, end_y - 20)
        left_offset = 395
        crop_width = 670

        if progress_callback:
            progress_callback("차트 이미지 잘라내기...")
        cropped = image.crop((left_offset, top_coord, left_offset + crop_width, bottom_coord))

        currency = top.text.split('\n')[0].strip().replace(' ', '') or "환율"
        today = datetime.now().strftime('%Y%m%d')
        current_dir = os.getcwd()
        folder = os.path.join(current_dir, "환율차트", f"환율{today}")
        os.makedirs(folder, exist_ok=True)
        filename = f"{today}_{currency}_환율차트.png"
        output_path = os.path.join(folder, filename)
        cropped.save(output_path)
        
        if progress_callback:
            progress_callback("이미지를 클립보드에 복사 중...")
        copy_image_to_clipboard(output_path)
        
        return output_path

    finally:
        driver.quit()

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 기능 : 네이버 금융 종목 상세 페이지에서 wrap_company 영역을 캡처하고 저장하는 함수(주식 차트)
# ------------------------------------------------------------------
def capture_wrap_company_area(stock_code: str, progress_callback=None) -> str:
    """
    네이버 금융 종목 상세 페이지에서 wrap_company 영역을 캡처
    :param stock_code: 종목 코드 (예: 005930)
    :param progress_callback: 진행상황 콜백 함수 (옵션)
    :return: 저장된 이미지 경로
    """
    if progress_callback:
        progress_callback("네이버 금융 상세 페이지 접속 중...")
    driver = initialize_driver()
    try:
        url = f"https://finance.naver.com/item/main.naver?code={stock_code}"
        driver.get(url)
        if progress_callback:
            progress_callback("페이지 로딩 대기 중...")
        # 페이지 로딩 후, 차트 영역이 등장할 때까지 대기
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.wrap_company"))
        )
        time.sleep(0.3)  # 0.1초에서 0.3초로 복원
        
        if progress_callback:
            progress_callback("차트 영역 찾는 중...")
        
        # 회사명 추출
        try:
            company_name_element = driver.find_element(By.CSS_SELECTOR, "div.wrap_company h2 a")
            company_name = company_name_element.text.strip()
            if not company_name:
                company_name = "Unknown"
        except:
            company_name = "Unknown"
        clean_company_name = company_name.replace(" ", "").replace("/", "_").replace("\\", "_")
        
        # KRX 탭 유무에 따른 크기 설정
        def has_tab_elements(driver):
            return bool(driver.find_elements(By.CSS_SELECTOR, "a.top_tab_link"))
        
        def click_krx_tab(driver):
            elements = driver.find_elements(By.CSS_SELECTOR, "a.top_tab_link")
            for el in elements:
                if ("KRX" in el.text.upper() or "NTX" in el.text.upper()) and el.is_displayed():
                    if "KRX" in el.text.upper():
                        try:
                            el.click()
                            # KRX 탭 클릭 후에도 차트 영역이 다시 등장할 때까지 대기
                            WebDriverWait(driver, 2).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, "div.wrap_company"))
                            )
                            return True
                        except Exception as e:
                            print(f"KRX 탭 클릭 실패: {e}")
                    break
            return False
        
        if has_tab_elements(driver):
            width, height = 700, 505
            # LLM 탑재 후에 width 965로 수정할것
            click_krx_tab(driver)
            time.sleep(0.3)  # 0.1초에서 0.3초로 복원
        else:
            width, height = 700, 465
            # LLM 탑재 후에 width 965로 수정할것
        
        # wrap_company 요소 찾기
        el = driver.find_element(By.CSS_SELECTOR, "div.wrap_company")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.3)  # 0.1초에서 0.3초로 복원
        
        if progress_callback:
            progress_callback("화면 전체 스크린샷 캡처 중...")
        screenshot_path = os.path.abspath("full_screenshot.png")
        driver.save_screenshot(screenshot_path)
        
        location = el.location
        zoom = driver.execute_script("return window.devicePixelRatio || 1;")
        start_x = int(location['x'] * zoom)
        start_y = int(location['y'] * zoom)
        
        # 좌표 계산 및 경계 검사
        left = max(0, start_x)
        top = max(0, start_y)
        right = left + width
        bottom = top + height
        
        image = Image.open(screenshot_path)
        right = min(right, image.width)
        bottom = min(bottom, image.height)
        left = max(0, right - width)
        top = max(0, bottom - height)
        
        if progress_callback:
            progress_callback("차트 이미지 잘라내기...")
        cropped = image.crop((left, top, right, bottom))
        
        today = datetime.now().strftime("%Y%m%d")
        current_dir = os.getcwd()
        folder = os.path.join(current_dir, "주식차트", f"주식{today}")
        os.makedirs(folder, exist_ok=True)
        filename = f"{stock_code}_{clean_company_name}.png"
        output_path = os.path.join(folder, filename)
        cropped.save(output_path)
        
        if os.path.exists(screenshot_path):
            os.remove(screenshot_path)
            
        if progress_callback:
            progress_callback("이미지를 클립보드에 복사 중...")
        copy_image_to_clipboard(output_path)
        return output_path
        
    except Exception as e:
        print(f"오류 발생: {e}")
        return None
    finally:
        try:
            driver.quit()
        except:
            pass


# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-10
# 기능 : 네이버 검색에서 외국 주식 차트를 찾아 캡처하고 저장하는 함수(외국 주식 차트)
# ------------------------------------------------------------------
def capture_foreign_stock_chart(keyword: str, progress_callback=None) -> str:
    """
    구글 검색 결과에서 외국주식 차트+시세(구글 파이낸스 위젯) 영역을 캡처합니다.
    :param keyword: 예) '팔란티어 주가', 'AAPL', '테슬라 주가'
    :return: 저장된 이미지 경로 (또는 None)
    """
    # '구글' 또는 '구글주가'는 '알파벳 주가'로 변환
    if keyword.replace(' ', '') in ['구글', '구글주가']:
        keyword = '알파벳 주가'
    elif '주가' not in keyword:
        keyword = f"{keyword} 주가"
    if progress_callback:
        progress_callback("구글 검색 페이지 접속 중...")
    print(f"[DEBUG] capture_foreign_stock_chart 진입: {keyword}")
    driver = initialize_driver()
    try:
        # 구글 검색 결과 페이지로 이동
        url = f"https://www.google.com/search?q={keyword}"
        driver.get(url)
        if progress_callback:
            progress_callback("페이지 로딩 대기 중...")
        WebDriverWait(driver, 3).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        time.sleep(0.5)  # 위젯 로딩 대기

        if progress_callback:
            progress_callback("차트 영역 찾는 중...")
        # 구글 파이낸스 위젯 영역 찾기
        try:
            chart_el = driver.find_element(By.CSS_SELECTOR, "div.aviV4d")
            print("[DEBUG] selector 성공: div.aviV4d")
        except Exception as e:
            print(f"[DEBUG] selector 실패: div.aviV4d / {e}")
            chart_el = None

        if not chart_el:
            if progress_callback:
                progress_callback("❌ 구글에서 차트 영역을 찾을 수 없습니다.")
            print("❌ 구글에서 차트 영역을 찾을 수 없습니다.")
            return None

        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", chart_el)
        time.sleep(0.5)

        zoom = driver.execute_script("return window.devicePixelRatio || 1;")
        location = chart_el.location
        size = chart_el.size

        top_offset = 55
        bottom_offset = 100

        start_y = int(location['y'] * zoom) - top_offset
        end_y = int((location['y'] + size['height']) * zoom) - bottom_offset
        left = int(location['x'] * zoom)
        width = int(size['width'] * zoom)

        if progress_callback:
            progress_callback("화면 전체 스크린샷 캡처 중...")
        screenshot = driver.get_screenshot_as_png()
        image = Image.open(io.BytesIO(screenshot))
        if progress_callback:
            progress_callback("차트 이미지 잘라내기...")
        cropped = image.crop((left, start_y, left + width, end_y))

        today = datetime.now().strftime('%Y%m%d')
        safe_keyword = "".join(c for c in keyword if c.isalnum() or c in ('_', '-'))
        # 한국 주식과 동일하게 저장
        folder = os.path.join(os.getcwd(), "주식차트", f"주식{today}")
        os.makedirs(folder, exist_ok=True)
        filename = f"{today}_{safe_keyword}_구글해외주식.png"
        output_path = os.path.join(folder, filename)
        cropped.save(output_path)

        if progress_callback:
            progress_callback("이미지를 클립보드에 복사 중...")
        copy_image_to_clipboard(output_path)
        print(f"✅ 구글 차트 캡처 및 클립보드 복사 완료: {output_path}")
        return output_path

    except Exception as e:
        print(f"[ERROR] 구글 해외주식 캡처 중 예외 발생: {e}")
        return None
    finally:
        driver.quit()


# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-10
# 기능 : 네이버 검색에서 주식 종목 코드 추출 후 차트 캡처하는 함수
# ------------------------------------------------------------------
def capture_stock_chart(keyword: str, progress_callback=None) -> str:
    # '구글' 또는 '구글주가'는 '알파벳 주가'로 변환, 그 외 '주가'가 없으면 자동으로 붙임
    try:
        print(f"[DEBUG] capture_stock_chart 진입, 입력값: {keyword}")
        # '구글' 또는 '구글주가'는 '알파벳 주가'로 변환
        if keyword.replace(' ', '') in ['구글', '구글주가']:
            keyword = '알파벳 주가'
        stock_code = get_stock_info_from_search(keyword)
        print(f"[DEBUG] get_stock_info_from_search 결과: {stock_code}")
        if stock_code:
            print(f"[DEBUG] 한국주식 코드로 캡처 시도")
            return capture_wrap_company_area(stock_code, progress_callback=progress_callback)
        else:
            print(f"[DEBUG] 외국주식 캡처 시도")
            # '구글' 또는 '구글주가'는 '알파벳 주가'로 변환
            if keyword.replace(' ', '') in ['구글', '구글주가']:
                keyword = '알파벳 주가'
            elif '주가' not in keyword:
                keyword = f"{keyword} 주가"
            return capture_foreign_stock_chart(keyword, progress_callback=progress_callback)
    except Exception as e:
        print(f"[ERROR] capture_stock_chart에서 예외 발생: {e}")
        return None



# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 기능 : 네이버 검색에서 주식 종목 코드 추출
# ------------------------------------------------------------------
def get_stock_info_from_search(keyword: str):
    import re
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    import time
    # '주가'가 없으면 자동으로 붙임 (중복 방지)
    if '주가' not in keyword:
        search_keyword = f"{keyword} 주가"
    else:
        search_keyword = keyword

    if search_keyword.isdigit() and len(search_keyword) == 6:
        return search_keyword

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,1024")

    driver = webdriver.Chrome(options=options)

    try:
        search_url = f"https://search.naver.com/search.naver?query={search_keyword}+주식"
        driver.get(search_url)
        time.sleep(0.3)

        finance_links = driver.find_elements(
            "css selector", "a[href*='finance.naver.com/item/main']"
        )
        for link in finance_links:
            href = link.get_attribute('href')
            match = re.search(r"code=(\d{6})", href)
            if match:
                stock_code = match.group(1)
                return stock_code
        return None
    except Exception as e:
        return None
    finally:
        driver.quit()