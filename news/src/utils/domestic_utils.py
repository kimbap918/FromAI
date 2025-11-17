# ------------------------------------------------------------------
# 작성자 : 최준혁
# 기능 : 국내 주식 관련 유틸 모듈
# ------------------------------------------------------------------
import os
import time
import io
import re
from datetime import datetime, timedelta
from PIL import Image
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from news.src.utils.driver_utils import initialize_driver
import FinanceDataReader as fdr
import pandas as pd
from bs4 import BeautifulSoup
import requests
import ast
try:
    import pyperclip
    HAS_PYPERCLIP = True
except ImportError:
    HAS_PYPERCLIP = False


# ------------------------------------------------------------------
# 작성자 : 최준혁 
# 작성일 : 2025-11-17
# 기능 : 네이버 분봉 데이터 조회 헬퍼
# ------------------------------------------------------------------
def _fetch_naver_minute_df(stock_code: str, count: int = 400, debug: bool = False) -> pd.DataFrame:
    """
    네이버 finance 비공식 API(siseJson.naver)를 사용해 분 단위 가격 데이터를 조회.
    - count: 최근 몇 개 분 데이터를 가져올지 (400이면 약 6~7시간 분량)
    - 반환: DatetimeIndex를 가진 DataFrame (컬럼: Open, High, Low, Close, Volume, 외국인소진율)
    """
    try:
        url = (
            "https://api.finance.naver.com/siseJson.naver?"
            f"symbol={stock_code}&requestType=0&count={count}&timeframe=minute"
        )
        print("=================url 데이터 확인====================", url)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0 Safari/537.36",
            "Referer": "https://finance.naver.com/",
        }
        res = requests.get(url, headers=headers, timeout=10)
        text = res.text.strip()
        if not text:
            if debug:
                print(f"[DEBUG] 네이버 분봉 응답이 비어 있음 - code={stock_code}")
            return pd.DataFrame()

        # 일부 응답은 'null' 토큰을 포함하므로 파싱 전 치환
        safe_text = text.replace('null', 'None')
        try:
            data = ast.literal_eval(safe_text)
        except Exception as e:
            if debug:
                print(f"[DEBUG] literal_eval 실패, 원문 길이={len(text)} 에러={e}")
            return pd.DataFrame()
        if not data or len(data) <= 1:
            if debug:
                print(f"[DEBUG] 네이버 분봉 데이터 부족 - code={stock_code}")
            return pd.DataFrame()

        df = pd.DataFrame(
            data[1:], 
            columns=["Date", "Open", "High", "Low", "Close", "Volume", "외국인소진율"]
        )

        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"]).set_index("Date").sort_index()
        return df

    except Exception as e:
        if debug:
            print(f"[DEBUG] 네이버 분봉 데이터 조회 실패 - code={stock_code}, error={e}")
        return pd.DataFrame()


# ------------------------------------------------------------------
# 작성자 : 최준혁 
# 작성일 : 2025-11-17
# 기능 : 이전 거래일 OHLC 정보 조회 (FinanceDataReader)
# ------------------------------------------------------------------
def get_prev_trading_day_ohlc(stock_code: str, lookback_days: int = 15, debug: bool = False) -> dict:
    """
    FinanceDataReader를 이용해 최근 N일간의 일별 시세를 조회하고,
    직전 거래일(마지막 행 바로 전)의 OHLC/거래량 정보를 반환.
    """
    try:
        today = datetime.today().date()
        start = today - timedelta(days=lookback_days * 2)

        df = fdr.DataReader(stock_code, start.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
        if df is None or df.empty:
            if debug:
                print(f"[DEBUG] 이전 거래일 OHLC 조회 실패 - 빈 데이터, code={stock_code}")
            return {}

        if len(df) >= 2:
            row = df.iloc[-2]
            date_idx = df.index[-2]
        else:
            row = df.iloc[-1]
            date_idx = df.index[-1]

        date_str = date_idx.strftime("%Y-%m-%d")

        def fmt(v):
            try:
                return f"{int(v):,}"
            except Exception:
                return None

        result = {
            "날짜": date_str,
            "시가": fmt(row.get("Open")),
            "고가": fmt(row.get("High")),
            "저가": fmt(row.get("Low")),
            "종가": fmt(row.get("Close")),
        }

        if "Volume" in row:
            vol = fmt(row.get("Volume"))
            if vol is not None:
                result["거래량"] = vol

        result = {k: v for k, v in result.items() if v is not None}
        return result

    except Exception as e:
        if debug:
            print(f"[DEBUG] 이전 거래일 OHLC 조회 중 예외 - code={stock_code}, error={e}")
        return {}


# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-11-17
# 기능 : 금일 분봉을 1시간 단위로 집계하여 시간대별 시세 생성
# ------------------------------------------------------------------
def get_intraday_hourly_data(stock_code: str, now_dt: datetime, debug: bool = False) -> dict:
    """
    네이버 분봉 데이터를 사용해 금일(now_dt 기준 날짜)의 1시간 단위 OHLC/거래량을 집계.
    - now_dt: Asia/Seoul 시간대를 가진 datetime
    - 반환 예: {"09:00": {"시가": "...", ...}, ...}
    """
    try:
        df = _fetch_naver_minute_df(stock_code, count=1200, debug=debug)
        if df.empty:
            if debug:
                print(f"[DEBUG] 시간대별시세 - 분봉 데이터 없음, code={stock_code}")
            return {}

        naive_now = now_dt.replace(tzinfo=None)
        target_date = naive_now.date()

        df_today = df[df.index.date == target_date]
        # 진행 중인 현재 시간대 제외: 현재 시각의 정각 미만까지만 사용
        current_hour_start = naive_now.replace(minute=0, second=0, microsecond=0)
        df_today = df_today[df_today.index < current_hour_start]
        if debug:
            try:
                print(f"[DEBUG] 시간대별시세 - 전체분봉 범위: {df.index.min()} ~ {df.index.max()} ({len(df)}건)")
                if not df_today.empty:
                    print(f"[DEBUG] 시간대별시세 - 금일분봉 범위: {df_today.index.min()} ~ {df_today.index.max()} ({len(df_today)}건), 기준시각: {current_hour_start}")
                else:
                    print(f"[DEBUG] 시간대별시세 - 금일분봉 없음 (target_date={target_date}), 기준시각: {current_hour_start}")
            except Exception:
                pass

        # 09:00 이전(예: 08:30) 분봉은 제외
        pre_cnt = len(df_today)
        df_today = df_today[df_today.index.hour >= 9]
        if debug and pre_cnt != len(df_today):
            try:
                print(f"[DEBUG] 시간대별시세 - 09시 이전 분봉 제외: {pre_cnt - len(df_today)}건 제거")
            except Exception:
                pass

        # 일부 분봉 응답은 O/H/L가 null이고 Close만 제공됨 → Close 기준으로 OHLC 산출
        hourly_price = df_today["Close"].resample("1h").agg(["first", "max", "min", "last"])  # 가격 집계
        hourly_vol = df_today["Volume"].resample("1h").sum()  # 거래량 집계
        hourly = pd.concat([hourly_price, hourly_vol], axis=1)
        hourly.columns = ["Open", "High", "Low", "Close", "Volume"]
        hourly = hourly.dropna(subset=["Open", "High", "Low", "Close"])  # 가격 필수

        if hourly.empty:
            if debug:
                print(f"[DEBUG] 시간대별시세 - 1시간 집계 결과 없음 (df_today={len(df_today)}건, Close기반 집계)")
            return {}

        result = {}
        for idx, row in hourly.iterrows():
            label = idx.strftime("%H:%M")
            try:
                result[label] = {
                    "시간대시작가": f"{int(row['Open']):,}",
                    "시간대최고가": f"{int(row['High']):,}",
                    "시간대최저가": f"{int(row['Low']):,}",
                    "시간대마지막가": f"{int(row['Close']):,}",
                    "시간대거래량": f"{int(row['Volume']):,}",
                }
            except Exception:
                if debug:
                    print(f"[DEBUG] 시간대별시세 - 포맷 실패, index={idx}, row={row}")
                continue

        # 장마감(>= 15:30) 이후 조회 시, 마지막 시간 라벨을 15:30으로 표기
        try:
            market_closed = (naive_now.hour > 15) or (naive_now.hour == 15 and naive_now.minute >= 30)
            if market_closed and "15:00" in result:
                result["15:30"] = result.pop("15:00")
        except Exception:
            pass

        return result

    except Exception as e:
        if debug:
            print(f"[DEBUG] 시간대별시세 집계 실패 - code={stock_code}, error={e}")
        return {}
# ------------------------------------------------------------------
# 작성자 : 곽은규
# 작성일 : 2025-07-22
# 기능 : 주식 종목 코드 받아오기 위한 연결 라이브러리
# ------------------------------------------------------------------
def finance(stock_name):
    """
    FinanceDataReader 라이브러리를 사용하여 주식 이름으로 종목 코드를 조회.
    :param stock_name: 조회할 주식의 이름 (e.g., "삼성전자")
    :return: 6자리 종목 코드 문자열. 찾지 못하면 None.
    """
    df_krx = fdr.StockListing('KRX') # 한국거래소(KRX) 전체 종목 목록을 불러옴
    # 입력된 주식 이름과 대소문자 구분 없이 완전히 일치하는 종목을 찾음
    matching_stocks = df_krx[df_krx['Name'].str.fullmatch(stock_name, case=False)]
    if not matching_stocks.empty:
        # 일치하는 종목이 있으면 첫 번째 종목의 'Code'를 반환
        return matching_stocks.iloc[0]['Code']
    return None

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-08-30
# 기능 : 투자주의/거래정지 종목 확인
# ------------------------------------------------------------------
def check_investment_restricted(stock_code, progress_callback=None, keyword=None):
    """
    종목 코드를 이용해 해당 주식이 거래정지 상태인지 확인.
    최근 거래 데이터의 시가, 고가, 저가가 모두 0이면 거래정지로 판단.
    :param stock_code: 확인할 6자리 종목 코드
    :param progress_callback: 진행 상태를 알리는 콜백 함수
    :param keyword: 콜백 메시지에 사용할 종목 이름
    :return: 거래정지 종목이면 True, 아니면 False
    """
    print(f"[DEBUG] 거래금지 체크 시작 - stock_code: {stock_code}, keyword: {keyword}")
    
    try:
        # FinanceDataReader를 통해 최근 10일간의 거래 데이터를 조회
        end_date = datetime.now().date()
        start_date = end_date - pd.Timedelta(days=10)
        df = fdr.DataReader(stock_code, start=start_date, end=end_date)
        
        # 데이터프레임이 비어있지 않은지 확인
        if df is not None and not df.empty:
            latest_data = df.iloc[-1] # 가장 최근 거래일 데이터
            open_price = latest_data.get('Open', 0)
            high_price = latest_data.get('High', 0)
            low_price = latest_data.get('Low', 0)
            
            # 시가, 고가, 저가가 모두 0이면 거래정지로 간주
            if open_price <= 0 and high_price <= 0 and low_price <= 0:
                if progress_callback and keyword:
                    progress_callback(f"[{keyword}]는 거래금지종목입니다.")
                return True
        else:
            # 조회된 데이터가 없으면 거래정지 또는 상장 폐지로 간주
            if progress_callback and keyword:
                progress_callback(f"[{keyword}]는 거래금지종목입니다.")
            return True
        
        return False
        
    except Exception as e:
        # 오류 발생 시 정상 종목으로 간주하고 통과
        pass
# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-22
# 기능 : 주식 차트 텍스트 파싱
# ------------------------------------------------------------------
def parse_chart_text(chart_text):
    """
    네이버 금융 차트 영역에서 스크레이핑한 텍스트를 파싱하여 주요 정보를 추출.
    :param chart_text: 스크레이핑한 원본 텍스트 문자열
    :return: 주요 정보가 담긴 딕셔너리
    """
    info = {}
    # 정규표현식 패턴을 사용하여 각 정보를 추출
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
            cleaned_value = re.sub(r'\s', '', m.group(1)) # 공백 제거
            # 거래대금의 경우 단위 '백만'을 붙여줌
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
    """
    네이버 금융 투자정보 영역에서 스크레이핑한 텍스트를 파싱하여 세부 정보를 추출.
    :param invest_info_text: 스크레이핑한 원본 텍스트 문자열
    :param debug: 디버깅 메시지 출력 여부
    :return: 투자 정보가 담긴 딕셔너리
    """
    info = {}
    if not invest_info_text or not isinstance(invest_info_text, str):
        if debug: print("[WARNING] 유효하지 않은 투자정보 텍스트가 입력되었습니다.")
        return info

    # '시가총액순위', '상장주식수'는 줄 단위로 파싱
    lines = invest_info_text.split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith('시가총액순위'):
            parts = re.split(r'[\s\t]+', line, maxsplit=1)
            if len(parts) > 1: info['시가총액순위'] = parts[1].strip()
            continue
        if line.startswith('상장주식수'):
            parts = re.split(r'[\s\t]+', line, maxsplit=1)
            if len(parts) > 1: info['상장주식수'] = parts[1].strip()
            continue
            
    # PER 정보 추출 (다양한 형식 처리)
    per_match = re.search(r'^(PER(?:lEPS)?(?:\([^\)]*\))?)\s*[\n:|l|\|\s]*([\d\.,]+)\s*배', invest_info_text, re.MULTILINE)
    if per_match:
        info['PER'] = f"{per_match.group(2).replace(',', '')}배"
    elif re.search(r'^PER[^\n]*N/A', invest_info_text, re.MULTILINE):
        info['PER'] = 'N/A'
        
    # 배당수익률 정보 추출 (여러 줄에 걸쳐 있을 수 있음)
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith('배당수익률'):
            # '배당수익률' 텍스트 다음 몇 줄 내에서 '%' 기호를 포함한 숫자 탐색
            for j in range(i+1, min(i+3, len(lines))):
                m = re.search(r'([\d\.]+)%', lines[j])
                if m:
                    info['배당수익률'] = f"{m.group(1)}%"
                    found = True
                    break
            if not found and 'N/A' in lines[i+1]:
                info['배당수익률'] = 'N/A'
            break
            
    # 나머지 정보들을 정규표현식으로 추출
    patterns = [
        ("시가총액", r"시가총액[\s|:|l|\|]*([\d,조억\s]+원)"),
        ("액면가", r"액면가[\s|:|l|\|\d]*([\d,]+원)"),
        ("외국인한도주식수", r"외국인한도주식수\(A\)[\s|:|l|\|]*([\d,]+)"),
        ("외국인보유주식수", r"외국인보유주식수\(B\)[\s|:|l|\|]*([\d,]+)"),
        ("외국인소진율", r"외국인소진율\(B/A\)[\s|:|l|\|]*([\d\.]+%)"),
        ("PBR", r"PBR[\s|:|l|\|\(\)\d\.]*([\d\.]+)배"),
        ("BPS", r"BPS[\s|:|l|\|\(\)\d\.]*([\d,]+)원"),
        ("동일업종 PER", r"동일업종 PER[\s|:|l|\|]*([\d\.]+)배"),
        ("동일업종 등락률", r"동일업종 등락률[\s|:|l|\|]*([\-\+\d\.]+%)"),
    ]
    for key, pat in patterns:
        if key not in info: # 이미 추출된 정보는 건너뜀
            m = re.search(pat, invest_info_text)
            if m and m.group(1):
                info[key] = m.group(1).strip()
    if debug: print(f"[DEBUG] invest_info 파싱 결과(보강): {info}")
    return info

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 기능 : 네이버 금융 종목 상세 페이지에서 wrap_company 영역을 캡처하고 저장하는 함수(주식 차트)
# ------------------------------------------------------------------
def capture_wrap_company_area(stock_code: str, progress_callback=None, debug=False, is_running_callback=None, custom_save_dir: str = None):
    """
    Selenium을 사용하여 네이버 금융 페이지의 주식 정보 영역을 캡처하고, 관련 텍스트 데이터를 추출.
    :param stock_code: 캡처할 6자리 종목 코드
    :param progress_callback: UI에 진행 상태를 전달하는 콜백 함수
    :param debug: 디버깅 로그 출력 여부
    :param is_running_callback: 작업 취소 여부를 확인하는 콜백 함수
    :param custom_save_dir: 이미지를 저장할 특정 경로
    :return: (이미지 경로, 성공 여부, 차트 텍스트, 투자정보 텍스트, 차트 정보 딕셔너리, 투자 정보 딕셔너리, 기업개요 텍스트) 튜플
    """
    # 로그 기록을 위한 내부 함수
    def log(msg):
        with open("capture_log.txt", "a", encoding="utf-8") as f:
            f.write(f"[capture_wrap_company_area] {msg}\n")
    
    # 작업 취소 여부를 확인하는 내부 함수
    def check_cancellation():
        if is_running_callback and not is_running_callback():
            if progress_callback: progress_callback("\n사용자에 의해 취소되었습니다.")
            return True
        return False

    # 반환할 변수들 초기화
    driver = None
    chart_text, invest_info_text, summary_info_text = "", "", ""
    chart_info, invest_info = {}, {}
    
    try:
        if check_cancellation(): return "", False, "", "", {}, {}, ""
            
        driver = initialize_driver() # Selenium 웹 드라이버 초기화
        
        if check_cancellation(): 
            driver.quit()
            return "", False, "", "", {}, {}, ""
            
        url = f"https://finance.naver.com/item/main.naver?code={stock_code}"
        driver.get(url)
        
        if progress_callback: progress_callback("페이지 로딩 대기 중...")
            
        # 'wrap_company' 요소가 나타날 때까지 최대 3초 대기
        WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.wrap_company")))
            
        # 취소 체크를 위한 짧은 대기
        for _ in range(3):
            if check_cancellation():
                driver.quit()
                return "", False, "", "", {}, {}, ""
            time.sleep(0.1)
        
        if progress_callback: progress_callback("차트 영역 찾는 중...")
            
        # 회사 이름 추출
        try:
            company_name = driver.find_element(By.CSS_SELECTOR, "div.wrap_company h2 a").text.strip()
        except Exception:
            company_name = "Unknown"
        clean_company_name = re.sub(r'[\\/:*?"<>|]', '_', company_name) # 파일명으로 사용 가능하게 정제
        
        # 'KRX' 탭이 있는지 확인하고 있으면 클릭 (캡처 영역 크기 조절을 위함)
        if driver.find_elements(By.CSS_SELECTOR, "a.top_tab_link"):
            width, height = 965, 505
            elements = driver.find_elements(By.CSS_SELECTOR, "a.top_tab_link")
            for el in elements:
                if "KRX" in el.text.upper():
                    el.click()
                    time.sleep(0.3)
                    break
        else:
            width, height = 965, 465

        # 캡처할 요소(div.wrap_company)를 찾고 화면 중앙으로 스크롤
        el = driver.find_element(By.CSS_SELECTOR, "div.wrap_company")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'})", el)
        time.sleep(0.3)
        location = el.location
        
        # 1. 차트 정보 텍스트 추출 및 파싱
        try:
            chart_text = driver.find_element(By.CSS_SELECTOR, "div#chart_area").text.strip()
            chart_info = parse_chart_text(chart_text)
        except Exception as e:
            log(f"chart_area 텍스트 추출 실패: {e}")

        # 2. 투자 정보 텍스트 추출 및 파싱
        try:
            invest_info_text = driver.find_element(By.CSS_SELECTOR, "div.aside_invest_info").text.strip()
            invest_info = parse_invest_info_text(invest_info_text, debug=debug)
        except Exception as e:
            log(f"aside_invest_info 텍스트 추출 실패: {e}")

        # 3. 기업 개요 텍스트 추출 (BeautifulSoup 사용)
        try:
            summary_info_el = driver.find_element(By.CSS_SELECTOR, "div#summary_info")
            html = summary_info_el.get_attribute('innerHTML')
            soup = BeautifulSoup(html, 'html.parser')
            p_tags = soup.find_all('p')
            summary_info_text = "\n".join([p.get_text(strip=True) for p in p_tags if p.get_text(strip=True)])
        except Exception as e:
            if debug: print(f"[WARNING] summary_info(BeautifulSoup) 추출 실패: {e}")

        # 4. 기준일 정보 추출
        try:
            date_text = driver.find_element(By.CSS_SELECTOR, "em.date").text.strip()
            match = re.search(r'\(.*\)', date_text) # 괄호 안의 내용 (e.g., KRX 장중) 추출
            chart_info["기준일"] = match.group(0) if match else date_text
        except Exception as e:
            pass

        # 5. 현재가 정보 보강 (텍스트 파싱이 실패할 경우를 대비)
        try:
            price_str = ""
            ems = driver.find_elements(By.CSS_SELECTOR, "div.rate_info p.no_today em")
            for em in ems:
                # 'blind' 클래스를 가진 span 태그는 불필요한 텍스트이므로 제외하고 합침
                price_str += "".join([span.text.strip() for span in em.find_elements(By.TAG_NAME, "span") if "blind" not in span.get_attribute("class")])
            if price_str and price_str != '0':
                chart_info["현재가"] = price_str
        except Exception as e:
            if debug: print(f"[DEBUG] 현재가(보강) 추출 실패: {e}")

        if check_cancellation():
            driver.quit()
            return "", False, "", "", {}, {}, ""
            
        if progress_callback: progress_callback("화면 전체 스크린샷 캡처 중...")
        try:
            # 화면 전체를 스크린샷하고, 필요한 부분만 잘라내기
            screenshot = driver.get_screenshot_as_png()
            image = Image.open(io.BytesIO(screenshot))
            left, top_coord = int(location['x']), int(location['y'])
            cropped = image.crop((left, top_coord, left + width, top_coord + height))
            
            # 저장 경로 설정
            if custom_save_dir:
                folder = custom_save_dir
            else:
                today = datetime.now().strftime('%Y%m%d')
                folder = os.path.join(os.getcwd(), "생성된 기사", f"기사{today}")
            os.makedirs(folder, exist_ok=True)
            
            # 이미지 파일 저장
            filename = f"{clean_company_name}_chart.png"
            output_path = os.path.join(folder, filename)
            cropped.save(output_path)
            log(f"이미지 저장 완료: {output_path}")

        except Exception as e:
            log(f"스크린샷 처리 중 오류 발생: {str(e)}")
            return "", False, chart_text, invest_info_text, chart_info, invest_info, summary_info_text

        if progress_callback: progress_callback("✅ 차트 캡처 완료")
        
        # 성공적으로 완료 시 모든 결과 반환
        return output_path, True, chart_text, invest_info_text, chart_info, invest_info, summary_info_text

    except Exception as e:
        log(f"오류 발생: {e}")
        return None, False, chart_text, invest_info_text, chart_info, invest_info, summary_info_text
    finally:
        # 드라이버가 실행 중이면 항상 종료
        if driver:
            try:
                driver.quit()
            except Exception as e:
                log(f"드라이버 종료 실패: {e}")