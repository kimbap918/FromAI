# ------------------------------------------------------------------
# 작성자 : 최준혁
# 기능 : 공통 유틸 모듈
# ------------------------------------------------------------------
import os
import re
import subprocess
import platform
import holidays
from datetime import datetime, timedelta, date
from typing import Optional
from shutil import copyfile

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo('Asia/Seoul')
    def get_today_kst_str():
        return datetime.now(TZ).strftime('%Y%m%d %H:%M')
    def get_today_kst_date_str():
        return datetime.now(TZ).strftime('%Y%m%d')
except ImportError:
    import pytz
    TZ = pytz.timezone('Asia/Seoul')
    def get_today_kst_str():
        return datetime.now(TZ).strftime('%Y%m%d %H:%M')
    def get_today_kst_date_str():
        return datetime.now(TZ).strftime('%Y%m%d')

from PIL import Image
from news.src.utils.domestic_utils import finance
from news.src.utils.data_manager import data_manager

# ------------------------------------------------------------------
# 작성자 : 곽은규
# 작성일 : 2025-07-30
# 기능 : KST 시간을 한국 시간으로 변환하는 함수
# ------------------------------------------------------------------
def convert_get_today_kst_str() -> str:
    """
    현재 KST 시간을 증시 상황에 맞는 문자열로 변환.
    장마감 시간(15:30) 이후에는 '장마감'으로, 그 외에는 '오전/오후' 형식으로 표시.
    :return: 포맷팅된 시간 문자열 (예: "30일 KRX 장마감", "30일 오후 3시 10분")
    """
    now_kst = datetime.now(TZ) # 한국 시간대 기준 현재 시간
    # 오후 3시 30분 이후인지 확인하여 장마감 여부 결정
    if now_kst.hour > 15 or (now_kst.hour == 15 and now_kst.minute >= 30):
        return f"{now_kst.day}일 KRX 장마감"
    
    # 오전/오후 구분
    am_pm = "오전" if now_kst.hour < 12 else "오후"
    # 12시간 형식으로 시간 변환
    hour_12 = now_kst.hour % 12
    if hour_12 == 0: # 0시는 12시로 표시
        hour_12 = 12
        
    return f"{now_kst.day}일 {am_pm} {hour_12}시 {now_kst.minute}분"

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-22
# 기능 : 파일명에 사용할 수 없는 문자를 _로 치환하는 함수
# ------------------------------------------------------------------
def safe_filename(s):
    """
    문자열에서 파일명으로 사용할 수 없는 문자들을 '_'로 치환.
    :param s: 원본 문자열
    :return: 안전하게 변환된 파일명 문자열
    """
    # 정규표현식을 사용하여 파일명 금지 문자(\, /, :, *, ?, ", <, >, |, 공백)를 '_'로 변경
    return re.sub(r'[\\/:*?"<>|,\s]', '_', s)

# ------------------------------------------------------------------
# 작성자 : 곽은규
# 작성일 : 2025-07-30
# 기능 : 뉴스를 파일로 저장하는 함수
# ------------------------------------------------------------------
def save_news_to_file(keyword: str, domain: str, news_content: str, save_dir: str = "생성된 기사", open_after_save: bool = True, custom_save_dir: Optional[str] = None):
    """
    생성된 뉴스 기사 내용을 텍스트 파일로 저장하고, 저장 후 파일을 자동으로 연다.
    :param keyword: 뉴스 키워드 (파일 이름에 사용)
    :param domain: 뉴스 도메인 ('toss' 또는 그 외, 폴더 이름에 사용)
    :param news_content: 저장할 기사 본문
    :param save_dir: 기본 저장 디렉토리 이름
    :param open_after_save: 저장 후 파일을 열지 여부
    :param custom_save_dir: 사용자가 지정한 저장 경로 (이 값이 있으면 다른 경로는 무시)
    :return: 저장된 파일의 절대 경로, 실패 시 None
    """
    # 저장할 내용이 비어있는지 확인
    if not news_content or not news_content.strip():
        print("[WARNING] 저장할 뉴스 내용이 비어 있습니다. 파일 저장을 건너뜁니다.")
        return None
        
    # 저장 경로 설정: 사용자 지정 경로가 있으면 사용, 없으면 기본 경로 생성
    if custom_save_dir:
        full_save_dir = custom_save_dir
    else:
        current_dir = os.getcwd()
        today_date_str = get_today_kst_date_str()
        base_save_dir = os.path.join(current_dir, save_dir)
        # 'toss' 도메인이면 '토스' 폴더, 아니면 '기사' 폴더 사용
        folder_prefix = "토스" if domain == "toss" else "기사"
        full_save_dir = os.path.join(base_save_dir, f"{folder_prefix}{today_date_str}")
        
    os.makedirs(full_save_dir, exist_ok=True) # 폴더가 없으면 생성
    
    safe_k = safe_filename(keyword) # 키워드를 파일명에 적합하게 변경
    filename = f"{safe_k}_{domain}_news.txt"
    file_path = os.path.join(full_save_dir, filename)
    
    try:
        # 파일을 UTF-8 인코딩으로 저장
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(news_content)
            
        # 파일 자동 열기 기능
        try:
            current_os = platform.system() # 현재 운영체제 확인
            print(f"현재 운영체제: {current_os}")
            if open_after_save:
                if current_os == "Windows":
                    os.startfile(file_path)
                elif current_os == "Darwin":  # macOS
                    subprocess.run(["open", file_path])
                else: # 그 외 OS는 지원하지 않음
                    print(f"지원하지 않는 운영체제입니다. 파일 자동 열기를 건너뜁니다: {file_path}")
        except Exception as open_err:
            print(f"저장된 파일 열기 중 오류 발생: {open_err}")
        return os.path.abspath(file_path) # 성공 시 절대 경로 반환
    except Exception as e:
        print(f"뉴스 기사 저장 중 오류 발생: {e}")
        return None # 실패 시 None 반환

# ------------------------------------------------------------------
# 작성자 : 곽은규
# 작성일 : 2025-07-30
# 기능 : 검색(KFinanceDataReader) 통해 종목 코드를 찾는 함수
# ------------------------------------------------------------------
def get_stock_info_from_search(keyword: str):
    """
    키워드를 이용해 종목 코드를 찾는다. FinanceDataReader를 먼저 시도하고,
    실패하면 Naver 검색을 통해 찾는다.
    :param keyword: 종목명 또는 검색어 (예: "삼성전자", "삼성전자 주가")
    :return: 6자리 종목 코드, 찾지 못하면 None
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    import time

    # 키워드에서 ' 주가' 또는 '주가' 문자열 제거
    clean_keyword = keyword.replace(' 주가','').strip()
    clean_keyword_2 = clean_keyword.replace('주가','').strip()
    
    # 1. FinanceDataReader 라이브러리로 종목 코드 검색 시도
    found_code = finance(clean_keyword_2)
    if found_code:
        print(f"DEBUG: FinanceDataReader로 찾은 종목 코드: {found_code}")
        return found_code
        
    # 키워드에 '주가'가 없으면 추가하여 검색 정확도 향상
    if '주가' not in keyword:
        search_keyword = f"{keyword} 주가"
    else:
        search_keyword = keyword
        
    # 키워드가 6자리 숫자면 종목 코드로 간주하고 바로 반환
    if search_keyword.isdigit() and len(search_keyword) == 6:
        return search_keyword
        
    # 2. Selenium을 이용한 Naver 검색 (FinanceDataReader 실패 시)
    options = Options()
    options.add_argument("--headless") # 브라우저 창을 띄우지 않음
    options.add_argument("--no-sandbox") #サンドボックスモードを無効にする
    driver = webdriver.Chrome(options=options)
    try:
        search_url = f"https://search.naver.com/search.naver?query={search_keyword}"
        driver.get(search_url)
        time.sleep(0.3) # 페이지 로딩 대기
        
        # 네이버 금융 페이지로 연결되는 링크 탐색
        finance_links = driver.find_elements("css selector", "a[href*='finance.naver.com/item/main']")
        for link in finance_links:
            href = link.get_attribute('href')
            # 링크 URL에서 'code=' 뒤의 6자리 숫자(종목 코드) 추출
            m = re.search(r"code=(\d{6})", href)
            if m:
                stock_code = m.group(1)
                return stock_code
        return None # 찾지 못하면 None 반환
    except Exception:
        return None
    finally:
        driver.quit() # 드라이버 종료

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-22
# 기능 : 종목 코드를 통해 차트를 캡처하는 함수
# ------------------------------------------------------------------
def capture_stock_chart(keyword: str, progress_callback=None) -> str:
    """
    키워드로 국내/해외 주식을 판별하여 적절한 차트 캡처 함수를 호출.
    :param keyword: 주식 이름 (예: "삼성전자", "애플")
    :param progress_callback: 진행 상태를 알리는 콜백 함수
    :return: 캡처된 이미지 파일의 경로
    """
    # '구글' 검색 시 '알파벳'으로 키워드 변경
    if keyword.replace(' ', '') in ['구글', '구글주가']:
        keyword = '알파벳 주가'
        
    stock_code = get_stock_info_from_search(keyword)
    if stock_code: # 종목 코드가 있으면 국내 주식으로 간주
        return capture_wrap_company_area(stock_code, progress_callback=progress_callback)
    else: # 없으면 해외 주식으로 간주하고 다른 함수 호출
        from news.src.utils.foreign_utils import capture_naver_foreign_stock_chart
        return capture_naver_foreign_stock_chart(keyword, progress_callback=progress_callback)

# ------------------------------------------------------------------
# 작성자 : 곽은규
# 작성일 : 2025-08-12
# 기능 : 기사 헤드 라인 템플릿 생성 함수
# ------------------------------------------------------------------
def create_pamphlet(keyword: str, is_foreign: bool, now_kst_dt: datetime = None) -> str:
    """
    국내/해외 및 장중/장마감 여부에 따라 다른 헤드라인 템플릿을 생성합니다.
    오늘이 공휴일(또는 주말)인 경우, 템플릿은 '직전 거래일' 기준으로 날짜를 출력합니다.
    :param keyword: 뉴스 키워드
    :param is_foreign: 해외 주식이면 True, 국내 주식이면 False
    :param now_kst_dt: 테스트용 현재 시각 (기본값은 datetime.now(TZ))
    """
    if now_kst_dt is None:
        now_kst_dt = datetime.now(TZ)

    weekday = now_kst_dt.weekday()  # 월요일=0, 일요일=6
    today_kst_date = now_kst_dt.date()

    # 한국/미국 휴일 객체
    kr_h = holidays.KR(years=[today_kst_date.year - 1, today_kst_date.year, today_kst_date.year + 1])
    us_h = holidays.US(years=[today_kst_date.year - 1, today_kst_date.year, today_kst_date.year + 1])

    # 직전 거래일 계산 함수
    def _prev_trading_day(d: date, holi) -> date:
        cur = d
        if cur.weekday() >= 5 or cur in holi:
            pass
        else:
            cur = cur - timedelta(days=1)
        while cur.weekday() >= 5 or cur in holi:
            cur = cur - timedelta(days=1)
        return cur

    # 마지막 거래일 계산 함수 (신규 추가)
    def _get_last_trading_day(d: date, holi) -> date:
        cur = d
        while cur.weekday() >= 5 or cur in holi:
            cur = cur - timedelta(days=1)
        return cur

    is_kr_holiday_or_weekend = (today_kst_date.weekday() >= 5) or (today_kst_date in kr_h)

    # ▼▼▼ 해외 주식 ▼▼▼
    if is_foreign:
        # 미국 증시는 한국 시간 기준으로 하루 전날 마감됩니다.
        us_date_ref = (now_kst_dt - timedelta(days=1)).date()
        last_us_trading_day = _get_last_trading_day(us_date_ref, us_h)

        # 한국 표시 날짜는 미국 마지막 거래일 + 1일 입니다.
        last_kr_trading_day = last_us_trading_day + timedelta(days=1)
        
        date_str = f"{last_kr_trading_day.day}일(미국 동부 기준 {last_us_trading_day.day}일) 기준"
        return f"{date_str}, 네이버페이 증권에 따르면"

    # ▼▼▼ 국내 주식 ▼▼▼
    
    else:
        if is_kr_holiday_or_weekend:
            # 주말 또는 공휴일이면 마지막 거래일 기준으로 '장마감'을 표시
            last_kr_biz = _get_last_trading_day(today_kst_date, kr_h)
            time_status_str = f"{last_kr_biz.day}일 KRX 장마감"
            print(f"[DEBUG] 국내주식: 주말/공휴일 분기 → {time_status_str}")
        else:
            # 평일 영업일이면 현재 시간에 따라 상태 표시
            time_status_str = convert_get_today_kst_str()
            print(f"[DEBUG] 국내주식: 평일 영업일 분기 → {time_status_str}")

        if "장마감" in time_status_str:
            day_part = time_status_str.split(' ')[0]
            print(f"[DEBUG] 국내주식 최종 → 마감 기준일: {day_part}")
            return f"{day_part} KRX 마감 기준, 네이버페이 증권에 따르면"
        else:
            print(f"[DEBUG] 국내주식 최종 → 장중 기준:", time_status_str)
            return f"{time_status_str} 기준, 네이버페이 증권에 따르면"
# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-25
# 기능 : 차트를 캡처하고 LLM을 통해 뉴스를 생성하는 함수
# ------------------------------------------------------------------
def capture_and_generate_news(keyword: str, domain: str = "stock", progress_callback=None, is_running_callback=None, step_callback=None, debug=False, open_after_save=True, custom_save_dir: Optional[str] = None):
    """
    주식 정보 조회, 차트 이미지 캡처, LLM을 통한 기사 생성을 총괄하는 메인 함수.
    :param keyword: 검색할 종목명
    :param domain: 분야 ('stock', 'toss', 'coin' 등)
    :param progress_callback: UI에 진행 상태를 전달하는 콜백
    :param is_running_callback: 현재 실행 상태를 전달하는 콜백
    :param step_callback: 단계별 진행 상태를 전달하는 콜백
    :param debug: 디버그 정보 출력 여부
    :param open_after_save: 저장 후 파일 자동 열기 여부
    :param custom_save_dir: 사용자 지정 저장 경로
    :return: 생성된 뉴스 기사 텍스트, 실패 시 None
    """
    from news.src.services.info_LLM import generate_info_news_from_text
    from news.src.utils.foreign_utils import capture_naver_foreign_stock_chart
    from news.src.utils.domestic_utils import capture_wrap_company_area

    total_steps = 3 # 전체 프로세스 단계 수: 1.정보조회, 2.이미지캡처, 3.기사생성
    current_step = 0

    # 단계 진행을 보고하는 내부 함수
    def report_step():
        nonlocal current_step
        current_step += 1
        if step_callback:
            step_callback(current_step, total_steps)
            
    info_dict = {} # LLM에 전달할 정보를 담을 딕셔너리
    is_stock = (domain == "stock")

    # 기사와 이미지를 저장하는 내부 함수
    def save_news_and_image(news, image_path=None):
        today_str = get_today_kst_date_str()

        # 저장 경로 설정
        if custom_save_dir:
            full_dir = custom_save_dir
        else:
            base_dir = os.path.join(os.getcwd(), "생성된 기사")
            sub_dir = f"기사{today_str}"
            full_dir = os.path.join(base_dir, sub_dir)
        os.makedirs(full_dir, exist_ok=True)

        # 기사 텍스트 파일 저장
        safe_k = safe_filename(keyword)
        news_path = os.path.join(full_dir, f"{safe_k}_{domain}_news.txt")
        with open(news_path, "w", encoding="utf-8") as f:
            f.write(news)
            
        # 저장 후 파일 열기
        if open_after_save:
            try:
                if platform.system() == "Windows":
                    os.startfile(news_path)
                elif platform.system() == "Darwin":
                    subprocess.run(["open", news_path])
            except Exception as e:
                print(f"[WARNING] 메모장 열기 실패: {e}")

        # 'toss' 탭에서는 이미지 저장 안함
        if domain == "toss" and image_path and os.path.exists(image_path):
            print(f"[INFO] Toss 탭: 이미지 저장 생략 - {image_path}")
            pass

    # 도메인이 'stock' 또는 'toss'인 경우
    if domain in ["stock", "toss"]:
        stock_code = get_stock_info_from_search(keyword)
        report_step() # 1. 정보 조회 완료

        if not stock_code:
            # 🔹 해외 주식 처리
            if progress_callback: progress_callback(f"{keyword} 해외주식 정보 조회 중...")
            image_path, stock_data, success = capture_naver_foreign_stock_chart(keyword, progress_callback=progress_callback, custom_save_dir=custom_save_dir)
            report_step() # 2. 이미지 캡처 완료
            
            if not image_path or not stock_data:
                if progress_callback: progress_callback("해외주식 데이터 수집 실패")
                return None
            
            info_dict = stock_data
            if progress_callback: progress_callback("LLM 기사 생성 중...")
            news = generate_info_news_from_text(keyword, info_dict, domain) # LLM 기사 생성
            report_step() # 3. 기사 생성 완료
            
            if news:
                # 1. 팜플렛(기사 서두) 문구 생성 (해외 주식용)
                pamphlet_text = create_pamphlet(keyword, is_foreign=True)

                # 2. LLM 결과물에서 '[본문]' 마커를 찾아 팜플렛 삽입
                if re.search(r'(\[본문\]|본문)', news):
                    replacement_text = f"[본문]\n{pamphlet_text} "
                    final_output = re.sub(r'(\[본문\]|본문)\s+', replacement_text, news, count=1)
                else: # 마커가 없으면 맨 앞에 추가
                    final_output = pamphlet_text + '\n\n' + news
                
                # 3. 최종 결과물 저장
                save_news_and_image(final_output, image_path)
            return news

        # 🔹 국내 주식 처리
        if domain == "toss":
            # 'toss' 탭의 경우 특정 폴더에 차트 정보 저장
            if progress_callback: progress_callback(f"{keyword} Toss 종목 정보 조회 중...")
            if custom_save_dir:
                toss_save_dir = custom_save_dir
            else:
                today_str = get_today_kst_date_str()
                toss_save_dir = os.path.join(os.getcwd(), "Toss기사", f"기사{today_str}")
            image_path, is_stock, chart_text, invest_info_text, chart_info, invest_info, summary_info_text = capture_wrap_company_area(
                stock_code, progress_callback=progress_callback, debug=debug,
                custom_save_dir=toss_save_dir, is_running_callback=is_running_callback
            )
        else: # 일반 'stock' 탭의 경우
            if progress_callback: progress_callback(f"{keyword} 국내주식 정보 조회 중...")
            image_path, is_stock, chart_text, invest_info_text, chart_info, invest_info, summary_info_text = capture_wrap_company_area(
                stock_code, progress_callback=progress_callback, debug=debug, 
                custom_save_dir=custom_save_dir, is_running_callback=is_running_callback
            )
        report_step() # 2. 이미지 캡처 완료
        
        if not image_path:
            if progress_callback: progress_callback("국내주식 이미지 캡처 실패")
            return None
            
        info_dict = {**chart_info, **invest_info} # 차트와 투자자 정보를 합쳐 LLM에 전달
        
        # 신규상장 종목 여부 정보 추가
        is_newly_listed_stock = data_manager.is_newly_listed(keyword)
        info_dict["신규상장여부"] = is_newly_listed_stock

        if debug: print("[DEBUG] 국내 주식 정보:\n", info_dict)
        if progress_callback: progress_callback("LLM 기사 생성 중...")
        news = generate_info_news_from_text(keyword, info_dict, domain) # LLM 기사 생성
        report_step() # 3. 기사 생성 완료
        
        if news:
            # 1. 팜플렛 문구 생성 (국내 주식용)
            pamphlet_text = create_pamphlet(keyword, is_foreign= False)
            # 2. LLM 결과물 후처리 및 저장
            if re.search(r'(\[본문\]|본문)', news):
                replacement_text = f"[본문]\n{pamphlet_text} "
                final_output = re.sub(r'(\[본문\]|본문)\s+', replacement_text, news, count=1)
            else:
                final_output = pamphlet_text + '\n\n' + news
            save_news_and_image(final_output, image_path)
        return news

    else:
        # 🔹 기타 도메인 (코인, 환율 등) 처리
        report_step() # 1. 정보 조회 완료 (별도 조회 단계 없음)
        image_path, stock_data, success = capture_naver_foreign_stock_chart(keyword, progress_callback=progress_callback, custom_save_dir=custom_save_dir)
        report_step() # 2. 이미지 캡처 완료
        
        if not image_path or not success:
            if progress_callback: progress_callback("이미지 캡처 실패")
            return None
            
        info_dict = {"이미지": image_path, "키워드": keyword}
        if debug: print("[DEBUG] 기타 도메인 정보:\n", info_dict)
        if progress_callback: progress_callback("LLM 기사 생성 중...")
        news = generate_info_news_from_text(keyword, info_dict, domain) # LLM 기사 생성
        
        if news:
            # 해외 주식과 동일한 로직으로 팜플렛 생성 및 후처리
            pamphlet_text = create_pamphlet(keyword, is_foreign=True)
            if re.search(r'(\[본문\]|본문)', news):
                replacement_text = f"[본문]\n{pamphlet_text} "
                final_output = re.sub(r'(\[본문\]|본문)\s+', replacement_text, news, count=1)
            else:
                final_output = pamphlet_text + '\n\n' + news
            save_news_and_image(final_output, image_path)
        return news

# ------------------------------------------------------------------
# 작성자 : 곽은규
# 작성일 : 2025-07-09
# 기능 : 주식 정보를 위한 프롬프트를 생성하는 함수
# ------------------------------------------------------------------
def build_stock_prompt(today_kst):
    """
    주식 뉴스 생성을 위한 동적 LLM 프롬프트를 생성.
    날짜, 요일, 장 상태(장중/장마감)에 따라 내용이 달라진다.
    :param today_kst: 'YYYYMMDD' 형식의 한국 날짜 문자열
    :return: LLM에 전달할 프롬프트 문자열
    """
    date_obj = None
    # 다양한 날짜 형식('YYYY년 M월 D일', 'YYYYMMDD' 등) 파싱 시도
    for fmt in ["%Y년 %m월 %d일", "%Y%m%d", "%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%Y %m %d"]:
        try:
            date_obj = datetime.strptime(today_kst.split()[0], fmt)
            break
        except Exception:
            continue
    if not date_obj: # 파싱 실패 시 현재 날짜 사용
        date_obj = datetime.now()

    weekday = date_obj.weekday()
    is_weekend = weekday in [5, 6] # 토요일(5), 일요일(6)

    # 주말일 경우, 모든 기준 날짜를 금요일로 조정
    if is_weekend:
        effective_date_obj = date_obj - timedelta(days=weekday - 4)
        now_time = f"{effective_date_obj.day}일 KRX 장마감"
    else: # 평일일 경우
        effective_date_obj = date_obj
        now_time = convert_get_today_kst_str()

    print("now_time 호출 결과:", now_time)

    # 어제 날짜 계산 (월요일이면 금요일로)
    if effective_date_obj.weekday() == 0:
        yesterday = effective_date_obj - timedelta(days=3)
    else:
        yesterday = effective_date_obj - timedelta(days=1)
    
    # 날짜를 'O월 O일' 형식으로 변환하는 내부 함수 (OS 호환성 고려)
    def format_month_day(dt):
        if platform.system() == "Windows":
            return dt.strftime("%#m월 %#d일") # Windows: '7월 1일'
        else:
            return dt.strftime("%-m월 %-d일") # macOS/Linux: '7월 1일'
    
    # 기사 제목에 들어갈 날짜/시간 형식 설정
    if "장마감" in now_time:
        title_time_format = f"\"{format_month_day(effective_date_obj)}\" "
    else:
        title_time_format = f"\"{format_month_day(effective_date_obj)} 장중\""
        
    # 최종 프롬프트 템플릿
    stock_prompt = (
    "[Special Rules for Stock-Related News]\n"
        f"1. 제목 작성 시 규칙\n"
        f"   - **순서는 1)키워드 2)\"{title_time_format}\" 3)내용 순으로 생성하고 키워드 뒤에는 반드시 콤마(,)를 표기할 것.**\n"
        f"   - 금액에는 천단위는 반드시 콤마(,)를 표기할 것 (예: 64,600원)\n"
        f"   - **국내 주식 제목에는 \"{title_time_format}\" 정보를 반드시 포함할 것.\n"
        f"   - 가격과 등락률(%)을 반드시 함께 표기하고, 다양한 서술 방식을 사용하여 제목을 풍부하고 다채롭게 표현할 것.\n"
        f"   - 제목을 작성 할 때 '전일 대비, 지난, 대비'와 같은 비교 표현은 사용하지 않는다.\n"
        f"   - [주식 정보]의 신규상장 값이 True이면, '신규상장' 관련 표현을 주가 정보와 함께 제목의 핵심 내용으로 서술할 것.\n"
        f"   - **주가 정보는 간결하게 포함하며, 장이 마감되었을 경우에만 제목의 가장 마지막에 \"<변동 방향/상태> 마감\" 형식으로 마무리 할 것.**\n\n"
        
        f"2. 본문 작성 시 절대 규칙\n"
        f"   - **본문 작성 원칙: 시스템이 자동 추가하는 날짜/시간/출처/기준점 정보와 중복되지 않게 서술할 것.**\n"
        f"   - **작성 범위: 종목명으로 시작하여 [주식 정보] 데이터를 기반으로 가격 변동 분석을 서술할 것.**\n"
        f"   - **[주식 정보]는 시계열 데이터가 아니므로 ‘출발·상승·하락·마감’ 등 시간 순서의 흐름을 서술하지 말고, 단일 시점의 가격 범위와 특징만 기술하여 현재가로 마무리 할 것.**\n"
        f"   - **모든 [주식 정보]를 활용하되, 단순 나열하지 말고 기사의 흐름 속에서 논리적 연결고리를 만들어 제시할 것.**\n"
        f"   - **장중/장마감 구분은 [주식 정보] 안에 기준일을 참고해서 구분하되, 본문에 날짜는 언급하지 말 것.**\n"
        f"   - **누락된 데이터(N/A 등)는 자연스럽게 생략하는 대신 [주식정보] 데이터 간의 관계성을 추론없이 도출해낼 것.**\n"
        f"   - **[주식 정보]내 신규상장 값이 Ture이면, 신규상장이란 지난 종가를 공모가로 바꾸고 내용도 신규상장에 맞게 작성할 것.**\n"
        f"   - **'전일', '전날', '전 거래일', '지난 거래일' 같은 표현은 '지난 종가'로 표현할것.**\n\n"

        f"3. [해외주식 정보]가 있을 경우, 날짜와 추가 제목,본문 작성 규칙\n"
        f"   - [해외주식 정보]가 있을 경우 '시간 외 거래'가 있는 경우 본문에 정규장 내용 이후 시간 외 거래 내용을 포함할 것.\n"
        f"   - **[해외주식 정보]가 있을 경우, 제목에는 날짜를 포함하지 말 것.**\n"
        f"   - **장중/장마감 구분은 [해외주식 정보] 안에 us_time을 참고하여 구분할 것.**\n"
        f"   - 예시: 실시간 -> 장 중, 장마감 -> 장 마감\n\n"
        
        f"4. 거래대금은 반드시 **억 단위, 천만 단위로 환산**하여 정확히 표기할 것\n"
        f"   - 예시: \"135,325백만\" → \"1,353억 2,500만 원\" / \"15,320백만\" → \"153억 2,000만 원\" / \"3,210백만\" → \"32억 1,000만 원\" / \"850백만\" → \"8억 5,000만 원\"\n\n"
        
        f"[Style]\n"
        f"   - 반드시 장 시작/장중/장 마감 시점에 따라 서술 시제 변경\n"
        f"   - 단순 데이터 나열을 금지하며, 원인과 결과를 엮어 [News Generation Process] 기반으로 구성할 것.\n"
        f"   - **'투자자들, 관심, 주목, 기대, 풀이, 분석' 이라는 단어와 분석내용,감정,주관이 담긴 표현을 엄격히 사용하지 않는다.\n**"
        f"   - **'이날, 전일, 전 거래일, 전날, 오늘' 이라는 단어와 표현은 엄격히 절대 사용하지 말 것.\n\n**"
    )
    return stock_prompt