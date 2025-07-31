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

# ------------------------------------------------------------------
# 작성자 : 곽은규
# 작성일 : 2025-07-22
# 기능 : 현재 KST 시간을 'DD일 오후 HH시 MM분' 또는 'DD일 오전 HH시 MM분' 형식으로 반환합니다.
# ------------------------------------------------------------------

def convert_get_today_kst_str() -> str:

    try:
        from zoneinfo import ZoneInfo
        now_kst = datetime.now(ZoneInfo('Asia/Seoul'))
    except ImportError:
        import pytz
        now_kst = datetime.now(pytz.timezone('Asia/Seoul'))
    if now_kst.hour > 15 or (now_kst.hour == 15 and now_kst.minute >= 30):
        return f"네이버페이증권에 따르면 {now_kst.day}일 KRX 장마감"

    am_pm = "오전" if now_kst.hour < 12 else "오후"
    hour_12 = now_kst.hour % 12
    if hour_12 == 0:
        hour_12 = 12
    
    return f"네이버페이증권에 따르면 {now_kst.day}일 {am_pm} {hour_12}시 {now_kst.minute}분"

# ------------------------------------------------------------------
# 작성자 : 곽은규
# 작성일 : 2025-07-22
# 기능 : 완성된 기사 메모장에 저장하고 파일열기 함수입니다.
# ------------------------------------------------------------------
import platform 

def save_news_to_file(keyword: str, domain: str, news_content: str, save_dir: str = "생성된 기사"):
    if not news_content or not news_content.strip():
            print("[WARNING] 저장할 뉴스 내용이 비어 있습니다. 파일 저장을 건너뜁니다.")
            return None
        
    current_dir = os.getcwd()
    today_date_str = get_today_kst_date_str() # "20250731" 형식의 오늘 날짜 문자열 가져오기
    base_save_dir = os.path.join(current_dir, save_dir)
    full_save_dir = os.path.join(base_save_dir, f"기사{today_date_str}")
    os.makedirs(full_save_dir, exist_ok=True)

    safe_k = safe_filename(keyword)
    
    # 파일명은 날짜/시간 없이 '키워드_도메인_news.txt'로 통일
    filename = f"{safe_k}_{domain}_news.txt"
    file_path = os.path.join(full_save_dir, filename)
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(news_content)
        # print(f"뉴스 기사 저장 경로: {os.path.abspath(file_path)}")
        try:
            current_os = platform.system()
            print(f"현재 운영체제: {current_os}")
            if platform.system() == "Windows":
                os.startfile(file_path)
            elif current_os == "Darwin": # macOS
                subprocess.run(["open", file_path])
            else:
                print(f"지원하지 않는 운영체제입니다. 파일 자동 열기를 건너뜁니다: {file_path}")
        except Exception as open_err:
            print(f"저장된 파일 열기 중 오류 발생: {open_err}")
        return os.path.abspath(file_path)
    except Exception as e:
        print(f"뉴스 기사 저장 중 오류 발생: {e}")
        return None


def parse_invest_info_text(invest_info_text, debug=False):
    info = {}
    
    # 입력값 검증
    if not invest_info_text or not isinstance(invest_info_text, str):
        if debug:
            print("[WARNING] 유효하지 않은 투자정보 텍스트가 입력되었습니다.")
        return info
    
    try:
        # 줄바꿈으로 분리하여 각 라인을 개별적으로 처리
        lines = invest_info_text.split('\n')
        
        for line in lines:
            if not isinstance(line, str) or not line.strip():
                continue
                
            line = line.strip()
            
            # 시가총액순위와 상장주식수를 별도로 처리
            if line.startswith('시가총액순위'):
                try:
                    parts = re.split(r'[\s\t]+', line, maxsplit=1)
                    if len(parts) > 1 and parts[1].strip():
                        info['시가총액순위'] = parts[1].strip()
                except Exception as e:
                    print(f"[WARNING] 시가총액순위 파싱 중 오류: {e}")
                continue
                    
            if line.startswith('상장주식수'):
                try:
                    parts = re.split(r'[\s\t]+', line, maxsplit=1)
                    if len(parts) > 1 and parts[1].strip():
                        info['상장주식수'] = parts[1].strip()
                except Exception as e:
                    print(f"[WARNING] 상장주식수 파싱 중 오류: {e}")
                continue
        
        # PER 처리 (N/A 또는 숫자 값 처리)
        try:
            # 'PER' 또는 'PERlEPS'로 시작하는 줄에서만 추출, '추정PER' 등은 제외
            per_match = re.search(r'^(PER(?:lEPS)?(?:\([^\)]*\))?)\s*[\n:|l|\|\s]*([\d\.,]+)\s*배', invest_info_text, re.MULTILINE)
            if per_match:
                info['PER'] = f"{per_match.group(2).replace(',', '')}배"
            elif re.search(r'^PER[^\n]*N/A', invest_info_text, re.MULTILINE):
                info['PER'] = 'N/A'
            else:
                if debug:
                    print("[INFO] PER 정보를 찾을 수 없습니다.")
        except Exception as e:
            if debug:
                print(f"[WARNING] PER 파싱 중 오류: {e}")
            info['PER'] = 'N/A'  # 오류 발생 시 N/A로 설정

        # 배당수익률 처리
        try:
            # '배당수익률'로 시작하는 줄의 다음~2번째 줄에서 %값 추출
            lines = invest_info_text.splitlines()
            found = False
            for i, line in enumerate(lines):
                if line.strip().startswith('배당수익률'):
                    # 다음 줄~2번째 줄까지 %값 찾기
                    for j in range(i+1, min(i+3, len(lines))):
                        m = re.search(r'([\d\.]+)%', lines[j])
                        if m:
                            info['배당수익률'] = f"{m.group(1)}%"
                            found = True
                            break
                    if not found:
                        # 혹시 N/A가 있으면
                        for j in range(i+1, min(i+3, len(lines))):
                            if 'N/A' in lines[j]:
                                info['배당수익률'] = 'N/A'
                                found = True
                                break
                    break
            if not found:
                if debug:
                    print("[INFO] 배당수익률 정보를 찾을 수 없습니다.")
        except Exception as e:
            if debug:
                print(f"[WARNING] 배당수익률 파싱 중 오류: {e}")
        
        # 나머지 패턴들은 기존 방식으로 처리
        patterns = [
            ("시가총액", r"시가총액[\s|:|l|\|]*([\d,조억\s]+원)"),
            ("액면가", r"액면가[\s|:|l|\|\d]*([\d,]+원)"),
            ("외국인한도주식수", r"외국인한도주식수\(A\)[\s|:|l|\|]*([\d,]+)"),
            ("외국인보유주식수", r"외국인보유주식수\(B\)[\s|:|l|\|]*([\d,]+)"),
            ("외국인소진율", r"외국인소진율\(B/A\)[\s|:|l|\|]*([\d\.]+%)"),
            ("거래량", r"거래량[\s|:|l|\|]*([\d,]+)"),
            ("지분가치\(EPS\)", r"지분가치\(EPS\)[\s|:|l|\|]*([\d,]+)원"),
            ("순이익\(EPS\)", r"순이익\(EPS\)[\s|:|l|\|]*([\d,]+)원"),
            ("영업이익\(EPS\)", r"영업이익\(EPS\)[\s|:|l|\|]*([\d,]+)원"),
            ("PBR", r"PBR[\s|:|l|\|\(\)\d\.]*([\d\.]+)배"),
            ("BPS", r"BPS[\s|:|l|\|\(\)\d\.]*([\d,]+)원"),
            ("동일업종 PER", r"동일업종 PER[\s|:|l|\|]*([\d\.]+)배"),
            ("동일업종 등락률", r"동일업종 등락률[\s|:|l|\|]*([\-\+\d\.]+%)"),
        ]
        
        for key, pat in patterns:
            try:
                if key not in info:  # 이미 추출한 정보는 덮어쓰지 않음
                    m = re.search(pat, invest_info_text)
                    if m and m.group(1):
                        info[key] = m.group(1).strip()
            except Exception as e:
                if debug:
                    print(f"[WARNING] {key} 파싱 중 오류: {e}")
        
    except Exception as e:
        if debug:
            print(f"[ERROR] 투자정보 파싱 중 치명적 오류: {e}")
    
    if debug:
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
def capture_wrap_company_area(stock_code: str, progress_callback=None, debug=False):
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
    summary_info_text = ""

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
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'})", el)
        time.sleep(0.3)
        
        # 요소의 위치 가져오기 (고정된 너비/높이 사용)
        location = el.location
        left = int(location['x']) 
        top_coord = int(location['y'])
        
        # 디버깅을 위한 로그 추가
        log(f"Element position - x: {left}, y: {top_coord}, width: {width}, height: {height}")

        # 차트 영역 텍스트 추출
        try:
            chart_area_el = driver.find_element(By.CSS_SELECTOR, "div#chart_area")
            chart_text = chart_area_el.text.strip()
            if debug:
                print(f"[DEBUG] chart_text 원본: {chart_text}")
            chart_info = parse_chart_text(chart_text)
            if debug:
                print(f"[DEBUG] chart_info 파싱 결과: {chart_info}")
        except Exception as e:
            chart_text = ""
            chart_info = {}
            log(f"chart_area 텍스트 추출 실패: {e}")

        # 투자정보 영역 텍스트 추출
        try:
            invest_info_el = driver.find_element(By.CSS_SELECTOR, "div.aside_invest_info")
            invest_info_text = invest_info_el.text.strip()
            if debug:
                print(f"[DEBUG] invest_info_text 원본: {invest_info_text}")
            invest_info = parse_invest_info_text(invest_info_text, debug=debug)
            if debug:
                print(f"[DEBUG] invest_info 파싱 결과: {invest_info}")
        except Exception as e:
            invest_info_text = ""
            invest_info = {}
            log(f"aside_invest_info 텍스트 추출 실패: {e}")

        # 기업개요(summary_info) 추출 (BeautifulSoup 활용)
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div#summary_info"))
            )
            summary_info_el = driver.find_element(By.CSS_SELECTOR, "div#summary_info")
            html = summary_info_el.get_attribute('innerHTML')
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            p_tags = soup.find_all('p')
            summary_info_text = "\n".join([p.get_text(strip=True) for p in p_tags if p.get_text(strip=True)])
            if debug:
                print(f"[DEBUG] summary_info_text: {summary_info_text}")
        except Exception as e:
            summary_info_text = ""
            if debug:
                print(f"[WARNING] summary_info(BeautifulSoup) 추출 실패: {e}")

        # # 투자경고/주의/위험, 날짜 정보 추가 추출
        # try:
        #     special_status = []
        #     for cls in ["warning", "caution", "danger"]:
        #         for el in driver.find_elements(By.CSS_SELECTOR, f"em.{cls}"):
        #             text = el.text.strip()
        #             if text:
        #                 special_status.append(text)
        #     if special_status:
        #         # chart_info에 특이상태로 추가
        #         chart_info["특이상태"] = special_status
        # except Exception as e:
        #     pass
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
                        if debug:
                            print(f"[DEBUG] 현재가 span 텍스트: '{span.text.strip()}'")
                        price_str += span.text.strip()
                else:
                    if debug:
                        print(f"[DEBUG] 현재가 em 텍스트(백업): '{em.text.strip()}'")
                    price_str += re.sub(r"[^\d,]", "", em.text)
            price_str = re.sub(r"[^\d,]", "", price_str)
            if debug:
                print(f"[DEBUG] em 합친 price_str: '{price_str}'")
            if price_str and price_str != '0':
                chart_info["현재가"] = price_str
                if debug:
                    print(f"[DEBUG] 현재가(모든 span 합침): {price_str}")
            else:
                if debug:
                    print(f"[DEBUG] 현재가 추출 실패, price_str: '{price_str}'")
        except Exception as e:
            if debug:
                print(f"[DEBUG] 현재가(모든 span 합침) 추출 실패: {e}")

        if progress_callback:
            progress_callback("화면 전체 스크린샷 캡처 중...")

        try:
            # 스크린샷 캡처 및 메모리에서 바로 처리
            screenshot = driver.get_screenshot_as_png()
            image = Image.open(io.BytesIO(screenshot))
            
            # 요소의 위치에 맞게 이미지 자르기
            cropped = image.crop((left, top_coord, left + width, top_coord + height))
            log(f"Cropped image size: {cropped.size}")
            
            # 이미지 저장 경로 설정
            today = get_today_kst_date_str()
            current_dir = os.getcwd()
            folder = os.path.join(current_dir, "주식차트", f"주식{today}")
            os.makedirs(folder, exist_ok=True)
            filename = f"{stock_code}_{clean_company_name}.png"
            output_path = os.path.join(folder, filename)
            
            # 이미지 저장
            cropped.save(output_path)
            log(f"이미지 저장 완료: {output_path}, 파일 존재 여부: {os.path.exists(output_path)}")
            
            # 메모리 정리
            del screenshot
            del image
            del cropped
            
        except Exception as e:
            log(f"스크린샷 처리 중 오류 발생: {str(e)}")
            raise

        if not os.path.exists(output_path):
            log(f"이미지 저장 실패: {output_path}")
            return "", False, chart_text, invest_info_text, chart_info, invest_info, summary_info_text

        if progress_callback:
            progress_callback("이미지를 클립보드에 복사 중...")

        try:
            import pyperclip
            pyperclip.copy(output_path)
            log("클립보드에 경로 복사 완료")
        except ImportError:
            log("pyperclip 모듈이 설치되어 있지 않아 클립보드 복사를 건너뜁니다.")
        except Exception as e:
            log(f"클립보드 복사 실패: {e}")

        return output_path, True, chart_text, invest_info_text, chart_info, invest_info, summary_info_text

    except Exception as e:
        log(f"오류 발생: {e}")
        print(f"오류 발생: {e}")
        return None, False, chart_text, invest_info_text, chart_info, invest_info, summary_info_text

    finally:
        try:
            driver.quit()
        except Exception as e:
            log(f"드라이버 종료 실패: {e}")


# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-31
# 기능 : 네이버에서 해외주식 차트와 텍스트 정보를 추출하는 함수 (test.py 기반)
# ------------------------------------------------------------------
def capture_naver_foreign_stock_chart(keyword: str, progress_callback=None):
    """
    네이버에서 해외주식 차트 캡처 및 상세 정보 크롤링
    """
    from PIL import Image
    import io, os, time, traceback
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import NoSuchElementException
    from news.src.utils.driver_utils import initialize_driver

    driver = None
    stock_data = {}

    try:
        if progress_callback:
            progress_callback("드라이버 초기화 중...")
        driver = initialize_driver(headless=True)
        driver.set_window_size(1920, 1080)

        search_url = f"https://search.naver.com/search.naver?query={keyword}+주가"
        if progress_callback:
            progress_callback(f"네이버 검색 페이지 이동: {search_url}")
        driver.get(search_url)

        # 1. 차트 영역 대기
        chart_section = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "section.sc_new.cs_stock"))
        )

        try:
            canvas = WebDriverWait(chart_section, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div#stock_normal_chart3 canvas"))
            )
            time.sleep(0.5)  # 렌더링 안정화를 위한 짧은 대기
        except Exception as e:
            if progress_callback:
                progress_callback(f"⚠️ 캔버스를 찾지 못했습니다: {e}")

        # 2. wrap_elem 스크린샷 저장
        wrap_elem = driver.find_element(By.CSS_SELECTOR, "div.api_cs_wrap")
        screenshot_path = f"{keyword}_chart.png"
        success = wrap_elem.screenshot(screenshot_path)
        if not success or not os.path.exists(screenshot_path):
            png_bytes = wrap_elem.screenshot_as_png
            Image.open(io.BytesIO(png_bytes)).save(screenshot_path)

        # 3. crop 좌표 계산 (invest_wrap, more_view 기준)
        try:
            invest_elem = driver.find_element(By.CSS_SELECTOR, "div.invest_wrap._button_scroller")
            rel_invest_bottom = (invest_elem.location['y'] - wrap_elem.location['y']) + invest_elem.size['height']
        except NoSuchElementException:
            try:
                more_view_elem = driver.find_element(By.CSS_SELECTOR, "div.more_view")
                rel_invest_bottom = more_view_elem.location['y'] - wrap_elem.location['y']
            except NoSuchElementException:
                rel_invest_bottom = wrap_elem.size['height']

        dpr = driver.execute_script("return window.devicePixelRatio")
        left, top = 0, 0
        right = int(wrap_elem.size['width'] * dpr)
        bottom = int(rel_invest_bottom * dpr)

        img = Image.open(screenshot_path)
        img = img.crop((left, top, right, bottom))
        img.save(screenshot_path)

        if progress_callback:
            progress_callback("✅ 차트 캡처 완료")

        # 4. "증권 정보 더보기" 클릭 및 새 창 전환
        more_view = chart_section.find_element(By.CSS_SELECTOR, "div.more_view a")
        before_handles = driver.window_handles
        driver.execute_script("arguments[0].click();", more_view)
        time.sleep(0.5)
        after_handles = driver.window_handles
        if len(after_handles) > len(before_handles):
            new_handle = list(set(after_handles) - set(before_handles))[0]
            driver.switch_to.window(new_handle)

        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".GraphMain_name__cEsOs"))
        )

        # 5. 데이터 추출
        stock_data["keyword"] = keyword
        stock_data["name"] = driver.find_element(By.CSS_SELECTOR, ".GraphMain_name__cEsOs").text
        stock_data["price"] = driver.find_element(By.CSS_SELECTOR, ".GraphMain_price__H72B2").text
        change_el = driver.find_element(By.CSS_SELECTOR, "div[class*='VGap_stockGap']")
        stock_data["change"] = change_el.text.replace("\n", " ")

        time_elements = driver.find_elements(By.CSS_SELECTOR, ".GraphMain_date__GglkR .GraphMain_time__38Tp2")
        if len(time_elements) >= 2:
            stock_data["korea_time"] = time_elements[0].text.replace("\n", " ")
            stock_data["us_time"] = time_elements[1].text.replace("\n", " ")

        # '종목정보 더보기' 클릭
        try:
            more_info_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "a.StockInfo_btnFold__XEUUS"))
            )
            driver.execute_script("arguments[0].click();", more_info_button)
            time.sleep(0.5)
        except:
            pass

        # 재무 정보
        financial_items = driver.find_elements(By.CSS_SELECTOR, "ul.StockInfo_list__V96U6 > li.StockInfo_item__puHWj")
        for item in financial_items:
            parts = item.text.split("\n")
            if len(parts) >= 2:
                stock_data[parts[0].strip()] = " ".join(parts[1:]).strip()

        # 기업 개요
        try:
            overview = driver.find_element(By.CSS_SELECTOR, "div.Overview_text__zT3AI")
            stock_data["기업 개요"] = overview.text.strip()
        except:
            pass

        if progress_callback:
            progress_callback("✅ 데이터 추출 완료")

        return screenshot_path, stock_data, True

    except Exception as e:
        print(f"❌ 오류: {e}")
        traceback.print_exc()
        return None, {}, False

    finally:
        if driver:
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
            return capture_naver_foreign_stock_chart(keyword, progress_callback=progress_callback)
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
def capture_and_generate_news(keyword: str, domain: str = "stock", progress_callback=None, debug=False):
    """
    키워드와 도메인에 따라 정보성 뉴스를 생성한다.
    :param keyword: 종목명/통화명/코인명 등
    :param domain: "stock", "fx", "coin" 등
    :param progress_callback: 진행상황 콜백 함수(옵션)
    :param debug: 디버그 출력 여부
    :return: LLM이 생성한 기사(제목, 본문, 해시태그)
    """
    from news.src.services.info_LLM import generate_info_news_from_text
    info_dict = {}
    is_stock = (domain == "stock")
    if domain == "stock":
        stock_code = get_stock_info_from_search(keyword)
        if not stock_code:
            # 해외주식/외국뉴스 처리: 이미지 캡처만 info_dict에 제공
            image_path, stock_data, success = capture_naver_foreign_stock_chart(keyword, progress_callback=progress_callback)
            if not image_path:
                if progress_callback:
                    progress_callback("해외주식 이미지 캡처에 실패했습니다.")
                return None
            if not stock_data:
                if progress_callback:
                    progress_callback("해외주식 데이터 크롤링에 실패했습니다.")
                return None
            info_dict = dict(stock_data)
            info_dict['키워드'] = keyword
            if debug:
                print("\n[LLM에 제공되는 정리된 정보 - 해외주식]")
                for k, v in info_dict.items():
                    print(f"{k}: {v}")
            if progress_callback:
                progress_callback("LLM 기사 생성 중...")
            news = generate_info_news_from_text(keyword, info_dict, domain)

            if news: # news 변수에 값이 있을 경우에만 저장
                save_news_to_file(keyword, domain, news)

            return news
        image_path, is_stock, chart_text, invest_info_text, chart_info, invest_info, summary_info_text = capture_wrap_company_area(stock_code, progress_callback=progress_callback, debug=debug)
        if not image_path:
            if progress_callback:
                progress_callback("이미지 캡처에 실패했습니다.")
            return None
        # chart_info와 invest_info를 합쳐 info_dict로 만들고 전체를 print로 출력
        info_dict = {**chart_info, **invest_info}
        # 기업개요도 info_dict에 추가
        if summary_info_text:
            info_dict['기업개요'] = summary_info_text
        # 사람이 읽기 좋은 형태로 info_dict 전체를 출력 (debug일 때만)
        if debug and '기업개요' in info_dict:
            print("\n[기업개요]")
            print(info_dict['기업개요'])
        if debug:
            print("\n[LLM에 제공되는 정리된 정보]")
            for k, v in info_dict.items():
                if k != '기업개요':
                    print(f"{k}: {v}")
    else:
        # 해외주식/외국뉴스 처리
        image_path, stock_data, success = capture_naver_foreign_stock_chart(keyword, progress_callback=progress_callback)
        if not image_path or not success:
            if progress_callback:
                progress_callback("해외주식 이미지 캡처에 실패했습니다.")
            return None
        info_dict['이미지'] = image_path
        info_dict['키워드'] = keyword
        if debug:
            print("\n[LLM에 제공되는 정리된 정보 - 해외주식]")
            for k, v in info_dict.items():
                print(f"{k}: {v}")
    if progress_callback:
        progress_callback("LLM 기사 생성 중...")
    news = generate_info_news_from_text(keyword, info_dict, domain)

    if news: # news 변수에 값이 있을 경우에만 저장
        save_news_to_file(keyword, domain, news)

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
    now_time = convert_get_today_kst_str()
    print("now_time 호출 결과:",  now_time)
    today_day = str(date_obj.day)
    yesterday = date_obj - timedelta(days=1)
    before_yesterday = date_obj - timedelta(days=2)
    yesterday_day = str(yesterday.day)
    before_yesterday_day = str(before_yesterday.day)
    stock_prompt = (

        "[Special Rules for Stock-Related News]\n"
        f"1. 제목 작성 시 규칙\n"
        f"   - 금액에는 천단위는 반드시 콤마(,)를 표기할 것 (예: 64,600원)\n"
        f"   - **반드시 날짜는 \"7월 8일\"과 같이 \"월 일\" 형식으로 기입할 것\n**"
        f"   - 가격과 등락률을 표시할때는 함께 표기할 것\n"
        f"   - 키워드 뒤에 반드시 콤마(,)를 표기하고 난 후 날짜를 표현한 후 내용을 이어 붙일것\n"
        f"   - '전일 대비'와 같은 비교 표현은 사용하지 않는다."
        f"   - 주가 정보 포함 시: 단, '장중' 이라는 단어는 날짜 뒤에 붙어서 나오거나 [등락률] 앞에 나올 것.\n"
        f"   - 시제는 기사 작성 시점을 반드시 기준일과 시점(예: 장마감, 장중 등)을 아래의 기준으로 구분한다.\n"
        f"   - **주가 정보는 간결하게 포함하며, 장이 마감되었을 경우에만 제목의 가장 마지막에 \"[변동 방향/상태] 마감\" 형식으로 추가할 것.**\n"
        f"2. 본문 작성 시 규칙\n"
        f"   - 첫줄에 날짜와 \"{now_time} 기준,\" 분까지 표기해서 표시할것, 그 이후는 [News Generation Process] 내용에 충실할 것\n "
        f"   - 날짜는 \"{today_day}일\", \"{yesterday_day}일\"처럼 **일(day)만** 표기 (월은 생략)\n"
        f"   - '전일' 이나 '전 거래일'이라는 표현하지 말 것, 대신 반드시 **\"지난 {yesterday_day}일\", \"지난 {before_yesterday_day}일\"**처럼 날짜를 명시할 것\n"
        f"   - 날짜가 포함된 시간 표현은 \"{today_kst} 오전 10시 56분\" → **\"{today_day}일 오전 10시 56분\"** 형식으로 변환\n"
        f"   - **절대로 '이날', '금일', '당일'과 같은 표현을 사용하지 말 것.** 대신 오늘 날짜인 \"{today_day}일\"로 반드시 바꿔서 명시**할 것.\n\n"
        f"3. 시제는 기사 작성 시점을 반드시 기준일과 시점(예: 장마감, 장중 등)을 아래의 기준으로 구분한다.\n"
        f"   - 장 시작 전: \"장 시작 전\"\n"
        f"   - 장중 (오전 9:00 ~ 오후 3:30): \"장중\"\n"
        f"   - 장 마감 후 (오후 3:30 이후): \"장 마감 후\"\n\n"
        f"4. 국내 주식의 경우, (KST, Asia/Seoul) 기준으로 종가 및 날짜 비교 시 매주 월요일에는 지난주 금요일 종가와 비교할 것\n"
        f"   - 예시:\n"
        f"   - (2025년 7월 14일이 월요일인 경우) 지난 11일 종가는 31,300원이었으며, 14일은 이에 비해 소폭 하락한 상태다.\n"
        f"   - (2025년 7월 15일이 화요일인 경우) 지난 14일 종가는 31,300원이었으며, 15일은 이에 비해 소폭 하락한 상태다.\n\n"
        f"5. 거래대금은 반드시 **억 단위, 천만 단위로 환산**하여 정확히 표기할 것\n"
        f"   - 예시: \"135,325백만\" → \"1,353억 2,500만 원\" / \"15,320백만\" → \"153억 2,000만 원\" / \"3,210백만\" → \"32억 1,000만 원\" / \"850백만\" → \"8억 5,000만 원\"\n\n"
        f"6. 출력 형식 적용 (최종 제공)\n"
        f"   - 기사 생성 후, 아래 출력 형식에 맞춰 제공\n"
        f"   - 최종 출력은 [제목], [해시태그], [본문]의 세 섹션으로 명확히 구분하여 작성할 것.\n\n"
        f"[Style]\n"
        f"- 반드시 장 시작/장중/장 마감 시점에 따라 서술 시제 변경\n"
        f"- 전일 대비 등락과 연속 흐름을 조건별로 구분해 자연스럽게 서술하도록 지시할 것.\n"
        f"- 기업과 주식 관련 정보는 구체적인 수치와 함께 명시할 것.\n"
        f"- 단순 데이터 나열을 금지하며, 원인과 결과를 엮어 [News Generation Process] 기반으로 구성할 것.\n"
        f"- **'관심, 주목, 기대, 풀이' 등 시장의 감정이나 기자의 주관이 담긴 표현을 절대 사용하지 않는다.\n**"
        f"- ** 마지막은 기업 개요 참고해서 ‘~을 주력으로 하는 기업이다’ 형식으로 엄격히 1줄 이하로 요약 설명으로 작성할 것.(단, 설립이야기는 제외할 것)\n**"
    )
    return stock_prompt

def safe_filename(s):
    # 파일명에 쓸 수 없는 문자 모두 _로 치환
    return re.sub(r'[\\/:*?"<>|,\s]', '_', s)