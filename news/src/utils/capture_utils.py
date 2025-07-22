# utils/capture_utils.py

import os
import time
import io
from datetime import datetime, timedelta
try:
    from zoneinfo import ZoneInfo
    def get_today_kst_str():
        return datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y%m%d %H:%M')
    def get_today_kst_date_str():
        return datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y%m%d')
except ImportError:
    import pytz
    def get_today_kst_str():
        return datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y%m%d %H:%M')
    def get_today_kst_date_str():
        return datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y%m%d')
from PIL import Image
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from news.src.utils.driver_utils import initialize_driver
from news.src.utils.clipboard_utils import copy_image_to_clipboard

import re
import FinanceDataReader as fdr
import pandas as pd

# ------------------------------------------------------------------
# 작성자 : 곽은규
# 작성일 : 2025-07-22
# 기능 : 주식 종목 코드 받아오기 위한 연결 라이브러리
# ------------------------------------------------------------------
def finance(stock_name):
    """
    FinanceDataReader를 사용하여 종목명에 정확히 일치하는 종목 코드를 검색합니다.
    """
    try:
        df_krx = fdr.StockListing('KRX') # 한국 거래소 상장 종목 전체 리스트
    except Exception: # 더 이상 상세 오류 메시지를 출력하지 않습니다.
        return None

    # 종목명에 정확히 일치하는 종목을 검색 (대소문자 무시)
    matching_stocks = df_krx[df_krx['Name'].str.fullmatch(stock_name, case=False)]

    if not matching_stocks.empty:
        # 정확히 일치하는 종목이 여러 개 발견될 경우, 첫 번째 코드를 반환합니다.
        return matching_stocks.iloc[0]['Code']
    else:
        return None

def parse_chart_text(chart_text):
    info = {}
    patterns = [
        ("현재가", r"([\d,]+)\s*전일대비"),
        ("전일대비", r"전일대비\s*([\-\+\d,\.]+%)"),
        ("전일", r"전일\s*((?:[\d,]\s*)+)"),
        ("고가", r"고가\s*((?:[\d,]\s*)+)"),
        ("상한가", r"상한가\s*((?:[\d,]\s*)+)"),
        ("저가", r"저가\s*((?:[\d,]\s*)+)"),
        ("하한가", r"하한가\s*((?:[\d,]\s*)+)"),
        ("시가", r"시가\s*((?:[\d,]\s*)+)"),
        ("거래량", r"거래량\s*((?:[\d,]\s*)+)"),
        ("거래대금", r"거래대금\s*((?:[\d,]\s*)+)\s*백만"),
    ]
    for key, pat in patterns:
        m = re.search(pat, chart_text)
        if m:
            cleaned_value = re.sub(r'\s', '', m.group(1))
            if key == "거래대금":
                info[key] = f"{cleaned_value}백만"
            else:
                info[key] = cleaned_value
    return info

def parse_invest_info_text(invest_info_text):
    info = {}
    patterns = [
        ("시가총액", r"시가총액[\s|:|l|\|]*([\d,조억\s]+원)"),
        ("시가총액순위", r"시가총액순위[\s|:|l|\|]*([\w\d\s]+)"),
        ("상장주식수", r"상장주식수[\s|:|l|\|]*([\d,]+)"),
        ("액면가", r"액면가[\s|:|l|\|\d]*([\d,]+원)"),
        ("외국인한도주식수", r"외국인한도주식수\(A\)[\s|:|l|\|]*([\d,]+)"),
        ("외국인보유주식수", r"외국인보유주식수\(B\)[\s|:|l|\|]*([\d,]+)"),
        ("외국인소진율", r"외국인소진율\(B/A\)[\s|:|l|\|]*([\d\.]+%)"),
        ("투자의견", r"투자의견[\s|:|l|\|\d\.]*([\d\.]+매수)"),
        ("목표주가", r"목표주가[\s|:|l|\|]*([\d,]+)"),
        ("52주최고", r"52주최고[\s|:|l|\|\d\.]*([\d,]+)"),
        ("52주최저", r"52주최저[\s|:|l|\|\d\.]*([\d,]+)"),
        ("PER", r"PER[\s|:|l|\|\(\)\d\.]*([\d\.]+)배"),
        ("EPS", r"EPS[\s|:|l|\|\(\)\d\.]*([\d,]+)원"),
        ("추정PER", r"추정PER[\s|:|l|\|\(\)\d\.]*([\d\.]+)배"),
        ("추정EPS", r"추정EPS[\s|:|l|\|\(\)\d\.]*([\d,]+)원"),
        ("PBR", r"PBR[\s|:|l|\|\(\)\d\.]*([\d\.]+)배"),
        ("BPS", r"BPS[\s|:|l|\|\(\)\d\.]*([\d,]+)원"),
        ("배당수익률", r"배당수익률[\s|:|l|\|\d\.]*([\d\.]+%)"),
        ("동일업종 PER", r"동일업종 PER[\s|:|l|\|]*([\d\.]+)배"),
        ("동일업종 등락률", r"동일업종 등락률[\s|:|l|\|]*([\-\+\d\.]+%)"),
    ]
    for key, pat in patterns:
        m = re.search(pat, invest_info_text)
        if m:
            info[key] = m.group(1).strip()
    print(f"[DEBUG] invest_info 파싱 결과(보강): {info}")
    return info

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
        time.sleep(0.5)  # 페이지 로딩을 위한 대기 시간 증가

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
        today = get_today_kst_date_str()
        current_dir = os.getcwd()
        folder = os.path.join(current_dir, "환율차트", f"환율{today}")
        os.makedirs(folder, exist_ok=True)
        filename = f"{get_today_kst_str()}_{currency}_환율차트.png"
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
def capture_wrap_company_area(stock_code: str, progress_callback=None) -> (str, bool, str, str, dict, dict):
    """
    네이버 금융 종목 상세 페이지에서 wrap_company 영역을 캡처
    :param stock_code: 종목 코드 (예: 005930)
    :param progress_callback: 진행상황 콜백 함수 (옵션)
    :return: 저장된 이미지 경로, 성공 여부, 차트 영역 텍스트, 투자정보 텍스트, 차트 딕셔너리, 투자정보 딕셔너리
    """
    def log(msg):
        with open("capture_log.txt", "a", encoding="utf-8") as f:
            f.write(f"[capture_wrap_company_area] {msg}\n")

    if progress_callback:
        progress_callback("네이버 금융 상세 페이지 접속 중...")

    driver = initialize_driver()
    chart_text = ""
    invest_info_text = ""
    chart_info = {}
    invest_info = {}

    try:
        url = f"https://finance.naver.com/item/main.naver?code={stock_code}"
        driver.get(url)

        if progress_callback:
            progress_callback("페이지 로딩 대기 중...")

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.wrap_company"))
        )
        time.sleep(0.3)

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

        clean_company_name = company_name.replace(" ","").replace("/", "_").replace("\\", "_")

        def has_tab_elements(driver):
            return bool(driver.find_elements(By.CSS_SELECTOR, "a.top_tab_link"))

        def click_krx_tab(driver):
            elements = driver.find_elements(By.CSS_SELECTOR, "a.top_tab_link")
            for el in elements:
                if ("KRX" in el.text.upper() or "NTX" in el.text.upper()) and el.is_displayed():
                    if "KRX" in el.text.upper():
                        try:
                            el.click()
                            WebDriverWait(driver, 2).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, "div.wrap_company"))
                            )
                            return True
                        except Exception as e:
                            log(f"KRX 탭 클릭 실패: {e}")
                    break
            return False

        if has_tab_elements(driver):
            width, height = 965, 505
            click_krx_tab(driver)
            time.sleep(0.3)
        else:
            width, height = 965, 465

        el = driver.find_element(By.CSS_SELECTOR, "div.wrap_company")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.3)

        # 차트 영역 텍스트 추출
        try:
            chart_area_el = driver.find_element(By.CSS_SELECTOR, "div#chart_area")
            chart_text = chart_area_el.text.strip()
            print(f"[DEBUG] chart_text 원본: {chart_text}")
            chart_info = parse_chart_text(chart_text)
            print(f"[DEBUG] chart_info 파싱 결과: {chart_info}")
        except Exception as e:
            chart_text = ""
            chart_info = {}
            log(f"chart_area 텍스트 추출 실패: {e}")

        # 투자정보 영역 텍스트 추출
        try:
            invest_info_el = driver.find_element(By.CSS_SELECTOR, "div.aside_invest_info")
            invest_info_text = invest_info_el.text.strip()
            print(f"[DEBUG] invest_info_text 원본: {invest_info_text}")
            invest_info = parse_invest_info_text(invest_info_text)
            print(f"[DEBUG] invest_info 파싱 결과: {invest_info}")
        except Exception as e:
            invest_info_text = ""
            invest_info = {}
            log(f"aside_invest_info 텍스트 추출 실패: {e}")

        # 투자경고/주의/위험, 날짜 정보 추가 추출
        try:
            special_status = []
            for cls in ["warning", "caution", "danger"]:
                for el in driver.find_elements(By.CSS_SELECTOR, f"em.{cls}"):
                    text = el.text.strip()
                    if text:
                        special_status.append(text)
            if special_status:
                # chart_info에 특이상태로 추가
                chart_info["특이상태"] = special_status
        except Exception as e:
            pass
        try:
            date_els = driver.find_elements(By.CSS_SELECTOR, "em.date")
            for el in date_els:
                date_text = el.text.strip()
                if date_text:
                    chart_info["기준일"] = date_text
                    break
        except Exception as e:
            pass

        # 현재가: div.rate_info p.no_today em 내부의 모든 span 합침 (no_down, no_up, no_change 모두 대응, 보강)
        import re
        try:
            ems = driver.find_elements(By.CSS_SELECTOR, "div.rate_info p.no_today em")
            price_str = ""
            for em in ems:
                spans = em.find_elements(By.TAG_NAME, "span")
                if spans:
                    for span in spans:
                        print(f"[DEBUG] 현재가 span 텍스트: '{span.text.strip()}'")
                        price_str += span.text.strip()
                else:
                    print(f"[DEBUG] 현재가 em 텍스트(백업): '{em.text.strip()}'")
                    price_str += re.sub(r"[^\d,]", "", em.text)
            price_str = re.sub(r"[^\d,]", "", price_str)
            print(f"[DEBUG] em 합친 price_str: '{price_str}'")
            if price_str and price_str != '0':
                chart_info["현재가"] = price_str
                print(f"[DEBUG] 현재가(모든 span 합침): {price_str}")
            else:
                print(f"[DEBUG] 현재가 추출 실패, price_str: '{price_str}'")
        except Exception as e:
            print(f"[DEBUG] 현재가(모든 span 합침) 추출 실패: {e}")

        if progress_callback:
            progress_callback("화면 전체 스크린샷 캡처 중...")

        screenshot_path = os.path.abspath("full_screenshot.png")
        driver.save_screenshot(screenshot_path)
        log(f"스크린샷 저장: {screenshot_path}, 존재여부: {os.path.exists(screenshot_path)}")

        location = el.location
        zoom = driver.execute_script("return window.devicePixelRatio || 1;")
        start_x = int(location['x'] * zoom)
        start_y = int(location['y'] * zoom)
        left = max(0, start_x)
        top = max(0, start_y)
        right = left + width
        bottom = top + height

        image = Image.open(screenshot_path)
        log(f"이미지 열기 성공: {screenshot_path}, 크기: {image.size}")

        right = min(right, image.width)
        bottom = min(bottom, image.height)
        left = max(0, right - width)
        top = max(0, bottom - height)

        if progress_callback:
            progress_callback("차트 이미지 잘라내기...")

        cropped = image.crop((left, top, right, bottom))
        log(f"이미지 크롭: left={left}, top={top}, right={right}, bottom={bottom}")

        today = get_today_kst_date_str()
        current_dir = os.getcwd()
        folder = os.path.join(current_dir, "주식차트", f"주식{today}")
        os.makedirs(folder, exist_ok=True)
        filename = f"{stock_code}_{clean_company_name}.png"
        output_path = os.path.join(folder, filename)
        cropped.save(output_path)
        log(f"크롭 이미지 저장: {output_path}, 존재여부: {os.path.exists(output_path)}")

        if os.path.exists(screenshot_path):
            os.remove(screenshot_path)
            log(f"스크린샷 파일 삭제: {screenshot_path}")

        if progress_callback:
            progress_callback("이미지를 클립보드에 복사 중...")

        try:
            copy_image_to_clipboard(output_path)
            log(f"클립보드 복사 성공: {output_path}")
        except Exception as e:
            log(f"클립보드 복사 실패: {e}")

        return output_path, True, chart_text, invest_info_text, chart_info, invest_info

    except Exception as e:
        log(f"오류 발생: {e}")
        print(f"오류 발생: {e}")
        return None, False, chart_text, invest_info_text, chart_info, invest_info

    finally:
        try:
            driver.quit()
        except Exception as e:
            log(f"드라이버 종료 실패: {e}")


# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-10
# 기능 : 네이버 검색에서 외국 주식 차트를 찾아 캡처하고 저장하는 함수(외국 주식 차트)
# ------------------------------------------------------------------
def capture_foreign_stock_chart(keyword: str, progress_callback=None) -> (str, bool):
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
            return None, False

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

        today = get_today_kst_date_str()
        safe_keyword = "".join(c for c in keyword if c.isalnum() or c in ('_', '-'))
        # 한국 주식과 동일하게 저장
        folder = os.path.join(os.getcwd(), "주식차트", f"주식{today}")
        os.makedirs(folder, exist_ok=True)
        filename = f"{get_today_kst_str()}_{safe_keyword}_구글해외주식.png"
        output_path = os.path.join(folder, filename)
        cropped.save(output_path)

        if progress_callback:
            progress_callback("이미지를 클립보드에 복사 중...")
        copy_image_to_clipboard(output_path)
        print(f"✅ 구글 차트 캡처 및 클립보드 복사 완료: {output_path}")
        return output_path, True

    except Exception as e:
        print(f"[ERROR] 구글 해외주식 캡처 중 예외 발생: {e}")
        return None, False
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

    # ------------------------------------------------------------------
    # 작성자 : 곽은규
    # 작성일 : 2025-07-22
    # 기능 : 주식 종목 코드 연결한 IF문 추가
    # ------------------------------------------------------------------
    # --- finance 함수를 이용한 종목명 검색 우선 시도 ---
    clean_keyword = keyword.replace(' 주가','').strip()
    clean_keyword_2 = clean_keyword.replace('주가','').strip()
    found_code = finance(clean_keyword_2) # finance 함수 호출

    if found_code:
        print(f"DEBUG: FinanceDataReader로 찾은 종목 코드: {found_code}")
        return found_code # finance 함수가 코드를 찾으면 즉시 반환
    # --- finance 함수 통합 부분 끝 ---

    # finance 함수로 코드를 찾지 못했거나 오류가 발생했을 경우,
    # 기존의 Selenium 기반 검색 로직으로 넘어갑니다.

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
        search_url = f"https://search.naver.com/search.naver?query={search_keyword}"
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

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-14
# 기능 : 주식 키워드로 차트 이미지를 캡처하고, LLM에 기사 생성을 요청하는 함수
# ------------------------------------------------------------------
def capture_and_generate_news(keyword: str, domain: str = "stock", progress_callback=None):
    """
    키워드와 도메인에 따라 정보성 뉴스를 생성한다.
    :param keyword: 종목명/통화명/코인명 등
    :param domain: "stock", "fx", "coin" 등
    :param progress_callback: 진행상황 콜백 함수(옵션)
    :return: LLM이 생성한 기사(제목, 본문, 해시태그)
    """
    from news.src.services.info_LLM import generate_info_news_from_text
    info_dict = {}
    is_stock = (domain == "stock")
    if domain == "stock":
        stock_code = get_stock_info_from_search(keyword)
        if not stock_code:
            if progress_callback:
                progress_callback("주식 코드를 찾을 수 없습니다.")
            return None
        image_path, is_stock, chart_text, invest_info_text, chart_info, invest_info = capture_wrap_company_area(stock_code, progress_callback=progress_callback)
        if not image_path:
            if progress_callback:
                progress_callback("이미지 캡처에 실패했습니다.")
            return None
        # chart_info와 invest_info를 합쳐 info_dict로 만들고 전체를 print로 출력
        info_dict = {**chart_info, **invest_info}
        print(f"[DEBUG] info_dict 전체: {info_dict}")
    # else: (환율, 코인 등) info_dict만 만들면 됨
    # info_dict = ... (환율/코인 크롤링 및 파싱 결과)
    if progress_callback:
        progress_callback("LLM 기사 생성 중...")
    news = generate_info_news_from_text(keyword, info_dict, domain)
    return news

def build_stock_prompt(today_kst):
    # 다양한 포맷 지원: '2025년 7월 1일', '20250701', '2025-07-01', '2025.07.01' 등
    date_obj = None
    for fmt in ["%Y년 %m월 %d일", "%Y%m%d", "%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%Y %m %d"]:
        try:
            date_obj = datetime.strptime(today_kst.split()[0], fmt)
            break
        except Exception:
            continue
    if not date_obj:
        date_obj = datetime.now()
    today_day = str(date_obj.day)
    yesterday = date_obj - timedelta(days=1)
    before_yesterday = date_obj - timedelta(days=2)
    yesterday_day = str(yesterday.day)
    before_yesterday_day = str(before_yesterday.day)
    stock_prompt = (
        "[Special Rules for Stock-Related News]\n"
        f"- 주식 기사 제목 작성 시 규칙\n"
        f"   - 5.제목 작성 방식에 따라 제목을 작성하되, 아래의 내용을 추가로 고려합니다.\n"
        f"   - 금액에는 반드시 콤마(,)를 표기할 것 (예: 64,600원)\n"
        f"   - 날짜는 \"7월 8일\"과 같이 \"월 일\" 형식으로 기입할 것\n"
        f"   - 가격과 등락률을 표시할때는 함께 표기할 것\n"
        f"   - 예시: \"(키워드) O월 O일 주가 00,000원, 0.00% 하락/상승/보합\"\n\n"
        f"- 시제는 기사 작성 시점을 현재 시간 및 이미지 차트에 표기된 기준일과 시점을 아래의 기준으로 구분합니다.\n"
        f"   - 예시:\n"
        f"   - 장중 (오전 9:00 ~ 오후 3:30): \"장중\"\n"
        f"   - 장 마감 후 (오후 3:30 이후): \"장 마감 후\"\n\n"
        f"- 국내 주식의 경우, (KST, Asia/Seoul) 기준으로 종가 및 날짜 비교 시 매주 월요일에는 지난주 금요일 종가와 비교합니다.\n"
        f"   - 예시:\n"
        f"   - (오늘이 2025년 7월 14일이 월요일인 경우) 지난 11일 종가는 31,300원이었으며, 14일은 이에 비해 소폭 하락한 상태다.\n"
        f"   - (오늘이 2025년 7월 15일이 화요일인 경우) 지난 14일 종가는 31,300원이었으며, 15일은 이에 비해 소폭 하락한 상태다.\n\n"
        f"- 거래대금은 반드시 **억 단위, 천만 단위로 환산**하여 정확히 표기합니다.\n"
        f"   - 예시: \"135,325백만\" → \"1,353억 2,500만 원\" / \"15,320백만\" → \"153억 2,000만 원\" / \"3,210백만\" → \"32억 1,000만 원\" / \"850백만\" → \"8억 5,000만 원\"\n\n"
       
        f"[Style and Content Guidance for Stock News]\n"
        f"- **객관적인 사실을 기반으로 작성하되, 필요에 따라 '으로 해석된다', '으로 보인다', '가능성이 있다' 등 조심스러운 추측성 표현을 사용하여 독자의 이해를 돕고 문맥을 풍부하게 합니다.**\n"
        f"- 투자 권유나 확정적인 예측은 엄격히 금지합니다. 이는 [News Generation Process]의 '객관성 유지' 지침을 주식 뉴스에 한해 오버라이드합니다.\n"
        f"  - **주식 변동의 핵심 요약:** 기사 첫 문단에 주가(종가), 등락률 등 가장 중요한 정보를 제시합니다.\n"
        f"  - **장중 주가 흐름:** 시가, 고가, 저가를 언급하며 하루 동안의 주가 추이를 설명합니다.\n"
        f"  - **거래 동향 분석:** 거래량과 거래대금 수치를 제시하고, 이 수치가 주가 변동에 어떤 의미를 가지는지 분석합니다.\n"
        f"  - **주요 재무 지표 해설:** PER, PBR, 배당수익률 등 주요 지표를 제시하고 그 의미를 간략히 설명합니다. 서술은 문장의 연결이 자연스럽게 이어지게 하며 해당 수치를 너무 나열하듯이 서술하지 않습니다.\n"
        f"  - **기업 개요 및 시장 위치:** 해당 기업의 주요 사업 분야와 시장 내 위치(예: 코스피 시총 1위)를 언급하여 기업에 대한 이해를 돕습니다. 구체적 정보를 파악하기 힘든 경우, 서술하지 않습니다.\n"
        f"  - **주가 변동의 배경 및 향후 전망 (조심스러운 추측):** 오늘 주가 변동의 가능한 원인(예: 단기 투자 심리 위축)을 분석하고, 시장 전문가의 견해나 업황을 토대로 향후 주가 흐름에 대한 조심스러운 전망을 제시합니다.\n"
    )
    return stock_prompt