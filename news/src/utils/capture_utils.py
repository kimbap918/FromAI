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


def capture_exchange_chart(keyword: str) -> str:
    """
    네이버 검색에서 환율 차트를 찾아 캡처하고 저장
    :param keyword: 검색어 (예: "달러환율" 또는 "달러")
    :return: 저장된 이미지 경로
    """
    keyword = make_exchange_keyword(keyword)
    driver = initialize_driver()
    try:
        url = f"https://search.naver.com/search.naver?query={keyword}"
        driver.get(url)
        WebDriverWait(driver, 3).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        time.sleep(0.3)  # 페이지 로딩을 위한 대기 시간 증가

        # 환율 차트 영역을 찾기 위한 여러 선택자 시도
        top = None
        bottom = None
        
        # 첫 번째 시도: 기존 선택자
        try:
            top = driver.find_element(By.CSS_SELECTOR, "div.exchange_top.up")
            bottom = driver.find_element(By.CSS_SELECTOR, "div.invest_wrap")
        except:
            pass
        
        # 두 번째 시도: 다른 가능한 선택자들
        if not top:
            try:
                top = driver.find_element(By.CSS_SELECTOR, "div.exchange_top")
                bottom = driver.find_element(By.CSS_SELECTOR, "div.invest_wrap")
            except:
                pass
        
        # 세 번째 시도: 더 일반적인 선택자
        if not top:
            try:
                top = driver.find_element(By.CSS_SELECTOR, "[class*='exchange']")
                bottom = driver.find_element(By.CSS_SELECTOR, "[class*='invest']")
            except:
                pass
        
        # 네 번째 시도: 환율 관련 텍스트가 포함된 요소 찾기
        if not top:
            try:
                elements = driver.find_elements(By.XPATH, "//*[contains(text(), '환율') or contains(text(), '달러') or contains(text(), '엔화')]")
                if elements:
                    top = elements[0]
                    # top 요소 아래의 적절한 영역을 bottom으로 설정
                    bottom = driver.find_element(By.CSS_SELECTOR, "div.invest_wrap")
            except:
                pass
        
        # 요소를 찾지 못한 경우 예외 발생
        if not top or not bottom:
            raise Exception(f"환율 차트 요소를 찾을 수 없습니다. 검색어: {keyword}")

        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", top)
        time.sleep(0.3)

        zoom = driver.execute_script("return window.devicePixelRatio || 1;")
        start_y = int(top.location['y'] * zoom)
        end_y = int((bottom.location['y'] + bottom.size['height']) * zoom)

        screenshot = driver.get_screenshot_as_png()
        image = Image.open(io.BytesIO(screenshot))

        top_coord = max(0, start_y - 10)
        bottom_coord = min(image.height, end_y - 20)
        left_offset = 395
        crop_width = 670

        cropped = image.crop((left_offset, top_coord, left_offset + crop_width, bottom_coord))

        currency = top.text.split('\n')[0].strip().replace(' ', '') or "환율"
        today = datetime.now().strftime('%Y%m%d')
        # 현재 작업 디렉토리를 기준으로 절대 경로 생성
        current_dir = os.getcwd()
        folder = os.path.join(current_dir, "환율차트", f"환율{today}")
        os.makedirs(folder, exist_ok=True)
        filename = f"{today}_{currency}_환율차트.png"
        output_path = os.path.join(folder, filename)
        cropped.save(output_path)
        return output_path

    finally:
        driver.quit()

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 기능 : 네이버 금융 종목 상세 페이지에서 wrap_company 영역을 캡처하고 저장하는 함수(주식 차트)
# ------------------------------------------------------------------
def capture_wrap_company_area(stock_code: str) -> str:
    """
    네이버 금융 종목 상세 페이지에서 wrap_company 영역을 캡처
    :param stock_code: 종목 코드 (예: 005930)
    :return: 저장된 이미지 경로
    """
    driver = initialize_driver()
    try:
        url = f"https://finance.naver.com/item/main.naver?code={stock_code}"
        driver.get(url)
        WebDriverWait(driver, 3).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        time.sleep(0.3)

        # KRX/NTX 탭 존재 여부 확인 및 KRX 클릭
        elements = driver.find_elements(By.CSS_SELECTOR, "a.top_tab_link")
        has_krx_ntx = False
        krx_clicked = False
        
        for el in elements:
            if ("KRX" in el.text.upper() or "NTX" in el.text.upper()) and el.is_displayed():
                has_krx_ntx = True
                # KRX 탭을 찾아서 클릭
                if "KRX" in el.text.upper():
                    try:
                        el.click()
                        krx_clicked = True
                        time.sleep(0.2)  # 클릭 후 잠시 대기
                        break
                    except Exception as e:
                        print(f"KRX 탭 클릭 실패: {e}")
                break

        # 회사명 추출
        try:
            company_name_element = driver.find_element(By.CSS_SELECTOR, "div.wrap_company h2 a")
            company_name = company_name_element.text.strip()
            if not company_name:
                company_name = "Unknown"
        except:
            company_name = "Unknown"
        
        # 파일명에서 사용할 수 있도록 회사명 정리 (특수문자 제거)
        clean_company_name = company_name.replace(" ", "").replace("/", "_").replace("\\", "_")
        
        el = driver.find_element(By.CSS_SELECTOR, "div.wrap_company")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.3)

        screenshot_path = os.path.abspath("full_screenshot.png")
        driver.save_screenshot(screenshot_path)

        location = el.location
        zoom = driver.execute_script("return window.devicePixelRatio || 1;")
        start_x = int(location['x'] * zoom)
        start_y = int(location['y'] * zoom)
        width = 965
        height = 515 if has_krx_ntx else 475  # KRX/NTX 탭이 없으면 높이 400

        image = Image.open(screenshot_path)
        cropped = image.crop((start_x, start_y, start_x + width, start_y + height))

        today = datetime.now().strftime("%Y%m%d")
        # 현재 작업 디렉토리를 기준으로 절대 경로 생성
        current_dir = os.getcwd()
        folder = os.path.join(current_dir, "주식차트", f"주식{today}")
        os.makedirs(folder, exist_ok=True)
        filename = f"{stock_code}_{clean_company_name}.png"
        output_path = os.path.join(folder, filename)
        cropped.save(output_path)

        if os.path.exists(screenshot_path):
            os.remove(screenshot_path)

        return output_path

    finally:
        driver.quit()

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
    if keyword.isdigit() and len(keyword) == 6:
        return keyword

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,1024")

    driver = webdriver.Chrome(options=options)

    try:
        search_url = f"https://search.naver.com/search.naver?query={keyword}+주식"
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