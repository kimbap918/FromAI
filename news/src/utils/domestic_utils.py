# ------------------------------------------------------------------
# 작성자 : 최준혁
# 기능 : 국내 주식 관련 유틸 모듈
# ------------------------------------------------------------------
import os
import time
import io
import re
from datetime import datetime
from PIL import Image
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from news.src.utils.driver_utils import initialize_driver
import FinanceDataReader as fdr
import pandas as pd
from bs4 import BeautifulSoup
try:
    import pyperclip
    HAS_PYPERCLIP = True
except ImportError:
    HAS_PYPERCLIP = False


# ------------------------------------------------------------------
# 작성자 : 곽은규
# 작성일 : 2025-07-22
# 기능 : 주식 종목 코드 받아오기 위한 연결 라이브러리
# ------------------------------------------------------------------
def finance(stock_name):
    df_krx = fdr.StockListing('KRX')
    matching_stocks = df_krx[df_krx['Name'].str.fullmatch(stock_name, case=False)]
    if not matching_stocks.empty:
        return matching_stocks.iloc[0]['Code']
    return None


# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-22
# 기능 : 주식 차트 텍스트 파싱
# ------------------------------------------------------------------
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
# 작성자 : 최준혁
# 작성일 : 2025-07-22
# 기능 : 주식 투자정보 텍스트 파싱
# ------------------------------------------------------------------
def parse_invest_info_text(invest_info_text, debug=False):
    info = {}
    if not invest_info_text or not isinstance(invest_info_text, str):
        if debug:
            print("[WARNING] 유효하지 않은 투자정보 텍스트가 입력되었습니다.")
        return info
    lines = invest_info_text.split('\n')
    for line in lines:
        if not isinstance(line, str) or not line.strip():
            continue
        line = line.strip()
        if line.startswith('시가총액순위'):
            parts = re.split(r'[\s\t]+', line, maxsplit=1)
            if len(parts) > 1 and parts[1].strip():
                info['시가총액순위'] = parts[1].strip()
            continue
        if line.startswith('상장주식수'):
            parts = re.split(r'[\s\t]+', line, maxsplit=1)
            if len(parts) > 1 and parts[1].strip():
                info['상장주식수'] = parts[1].strip()
            continue
    per_match = re.search(r'^(PER(?:lEPS)?(?:\([^\)]*\))?)\s*[\n:|l|\|\s]*([\d\.,]+)\s*배', invest_info_text, re.MULTILINE)
    if per_match:
        info['PER'] = f"{per_match.group(2).replace(',', '')}배"
    elif re.search(r'^PER[^\n]*N/A', invest_info_text, re.MULTILINE):
        info['PER'] = 'N/A'
    else:
        if debug:
            print("[INFO] PER 정보를 찾을 수 없습니다.")
    lines = invest_info_text.splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith('배당수익률'):
            for j in range(i+1, min(i+3, len(lines))):
                m = re.search(r'([\d\.]+)%', lines[j])
                if m:
                    info['배당수익률'] = f"{m.group(1)}%"
                    found = True
                    break
            if not found:
                for j in range(i+1, min(i+3, len(lines))):
                    if 'N/A' in lines[j]:
                        info['배당수익률'] = 'N/A'
                        found = True
                        break
            break
    if not found and debug:
        print("[INFO] 배당수익률 정보를 찾을 수 없습니다.")
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
        if key not in info:
            m = re.search(pat, invest_info_text)
            if m and m.group(1):
                info[key] = m.group(1).strip()
    if debug:
        print(f"[DEBUG] invest_info 파싱 결과(보강): {info}")
    return info

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 기능 : 네이버 금융 종목 상세 페이지에서 wrap_company 영역을 캡처하고 저장하는 함수(주식 차트)
# ------------------------------------------------------------------
def capture_wrap_company_area(stock_code: str, progress_callback=None, debug=False, is_running_callback=None, custom_save_dir: str = None):
    def log(msg):
        with open("capture_log.txt", "a", encoding="utf-8") as f:
            f.write(f"[capture_wrap_company_area] {msg}\n")
    
    # 취소 체크를 위한 최적화된 함수
    def check_cancellation():
        if is_running_callback and not is_running_callback():
            if progress_callback:
                progress_callback("\n사용자에 의해 취소되었습니다.")
            return True
        return False

    summary_info_text = ""
    driver = None
    chart_text = ""
    invest_info_text = ""
    chart_info = {}
    invest_info = {}
    
    try:
        # 초기 취소 체크
        if check_cancellation():
            return "", False, "", "", {}, {}, ""
            
        driver = initialize_driver()
        
        # 드라이버 초기화 후 취소 체크
        if check_cancellation():
            driver.quit()
            return "", False, "", "", {}, {}, ""
        url = f"https://finance.naver.com/item/main.naver?code={stock_code}"
        driver.get(url)
        
        if is_running_callback and not is_running_callback():
            if progress_callback:
                progress_callback("사용자에 의해 취소되었습니다.")
            driver.quit()
            return "", False, "", "", {}, {}, ""
            
        if progress_callback:
            progress_callback("페이지 로딩 대기 중...")
            
        # Reduce timeout and add more frequent cancellation checks
        try:
            WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.wrap_company"))
            )
            
            # Add a small delay but check for cancellation during wait
            for _ in range(3):
                if is_running_callback and not is_running_callback():
                    if progress_callback:
                        progress_callback("사용자에 의해 취소되었습니다.")
                    driver.quit()
                    return "", False, "", "", {}, {}, ""
                time.sleep(0.1)
        except Exception as e:
            if progress_callback:
                progress_callback(f"페이지 로딩 중 오류: {str(e)}")
            driver.quit()
            return "", False, "", "", {}, {}, ""
        
        if is_running_callback and not is_running_callback():
            if progress_callback:
                progress_callback("사용자에 의해 취소되었습니다.")
            driver.quit()
            return "", False, "", "", {}, {}, ""
            
        if progress_callback:
            progress_callback("차트 영역 찾는 중...")
            
        try:
            company_name_element = driver.find_element(By.CSS_SELECTOR, "div.wrap_company h2 a")
            company_name = company_name_element.text.strip()
            if not company_name:
                company_name = "Unknown"
        except Exception:
            company_name = "Unknown"
            
        clean_company_name = company_name.replace(" ", "").replace("/", "_").replace("\\", "_")
        
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
        location = el.location
        left = int(location['x'])
        top_coord = int(location['y'])
        log(f"Element position - x: {left}, y: {top_coord}, width: {width}, height: {height}")
        try:
            chart_area_el = driver.find_element(By.CSS_SELECTOR, "div#chart_area")
            chart_text = chart_area_el.text.strip()
            if debug:
                print(f"[DEBUG] chart_text 원본: {chart_text}")
            from news.src.utils.common_utils import capture_stock_chart 
            chart_info = parse_chart_text(chart_text)
        except Exception as e:
            chart_text = ""
            chart_info = {}
            log(f"chart_area 텍스트 추출 실패: {e}")
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
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div#summary_info"))
            )
            summary_info_el = driver.find_element(By.CSS_SELECTOR, "div#summary_info")
            html = summary_info_el.get_attribute('innerHTML')
            soup = BeautifulSoup(html, 'html.parser')
            p_tags = soup.find_all('p')
            summary_info_text = "\n".join([p.get_text(strip=True) for p in p_tags if p.get_text(strip=True)])
            if debug:
                print(f"[DEBUG] summary_info_text: {summary_info_text}")
        except Exception as e:
            summary_info_text = ""
            if debug:
                print(f"[WARNING] summary_info(BeautifulSoup) 추출 실패: {e}")

        try:
            date_els = driver.find_elements(By.CSS_SELECTOR, "em.date")
            for el in date_els:
                date_text = el.text.strip()
                if date_text:
                    chart_info["기준일"] = date_text
                    break
        except Exception as e:
            pass

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

        if is_running_callback and not is_running_callback():
            if progress_callback:
                progress_callback("사용자에 의해 취소되었습니다.")
            driver.quit()
            return "", False, "", "", {}, {}, ""
            
        if progress_callback:
            progress_callback("화면 전체 스크린샷 캡처 중...")
        try:
            screenshot = driver.get_screenshot_as_png()
            image = Image.open(io.BytesIO(screenshot))
            cropped = image.crop((left, top_coord, left + width, top_coord + height))
            log(f"Cropped image size: {cropped.size}")
            # 저장 경로 설정 (기사와 동일한 폴더에 저장)
            if custom_save_dir:
                folder = custom_save_dir
            else:
                today = datetime.now().strftime('%Y%m%d')
                current_dir = os.getcwd()
                # 기사가 저장되는 기본 폴더 구조를 따름
                folder = os.path.join(current_dir, "생성된 기사", f"기사{today}")
            os.makedirs(folder, exist_ok=True)
            filename = f"{stock_code}_{clean_company_name}.png"
            output_path = os.path.join(folder, filename)
            from news.src.utils.common_utils import safe_filename 
            cropped.save(output_path)
            log(f"이미지 저장 완료: {output_path}, 파일 존재 여부: {os.path.exists(output_path)}")
            del screenshot
            del image
            del cropped
        except Exception as e:
            log(f"스크린샷 처리 중 오류 발생: {str(e)}")
            return "", False, chart_text, invest_info_text, chart_info, invest_info, summary_info_text

        if not os.path.exists(output_path):
            log(f"이미지 저장 실패: {output_path}")
            return "", False, chart_text, invest_info_text, chart_info, invest_info, summary_info_text

        # 클립보드 복사 기능 비활성화
        if progress_callback:
            progress_callback("✅ 차트 캡처 완료")
        log("클립보드 복사 기능이 비활성화되었습니다.")

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
