# ------------------------------------------------------------------
# 작성자 : 최준혁
# 기능 : 공통 유틸 모듈
# ------------------------------------------------------------------
import os
import re
import subprocess
import platform
from datetime import datetime, timedelta
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
    now_kst = datetime.now(TZ)
    if now_kst.hour > 15 or (now_kst.hour == 15 and now_kst.minute >= 30):
        return f"{now_kst.day}일 KRX 장마감"
    am_pm = "오전" if now_kst.hour < 12 else "오후"
    hour_12 = now_kst.hour % 12
    if hour_12 == 0:
        hour_12 = 12
    return f"{now_kst.day}일 {am_pm} {hour_12}시 {now_kst.minute}분"

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-22
# 기능 : 파일명에 사용할 수 없는 문자를 _로 치환하는 함수
# ------------------------------------------------------------------
def safe_filename(s):
    # 파일명에 사용할 수 없는 문자 모두 _로 치환
    return re.sub(r'[\\/:*?"<>|,\s]', '_', s)

# ------------------------------------------------------------------
# 작성자 : 곽은규
# 작성일 : 2025-07-30
# 기능 : 뉴스를 파일로 저장하는 함수
# ------------------------------------------------------------------
def save_news_to_file(keyword: str, domain: str, news_content: str, save_dir: str = "생성된 기사", open_after_save: bool = True, custom_save_dir: Optional[str] = None):
    if not news_content or not news_content.strip():
        print("[WARNING] 저장할 뉴스 내용이 비어 있습니다. 파일 저장을 건너뜁니다.")
        return None
        
    if custom_save_dir:
        full_save_dir = custom_save_dir
    else:
        current_dir = os.getcwd()
        today_date_str = get_today_kst_date_str()
        base_save_dir = os.path.join(current_dir, save_dir)
        # 도메인별로 다른 폴더명을 사용하도록 수정
        folder_prefix = "토스" if domain == "toss" else "기사"
        full_save_dir = os.path.join(base_save_dir, f"{folder_prefix}{today_date_str}")
    os.makedirs(full_save_dir, exist_ok=True)
    safe_k = safe_filename(keyword)
    filename = f"{safe_k}_{domain}_news.txt"
    file_path = os.path.join(full_save_dir, filename)
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(news_content)
        try:
            current_os = platform.system()
            print(f"현재 운영체제: {current_os}")
            if open_after_save:
                if current_os == "Windows":
                    os.startfile(file_path)
                elif current_os == "Darwin":  # macOS
                    subprocess.run(["open", file_path])
                else:
                    print(f"지원하지 않는 운영체제입니다. 파일 자동 열기를 건너뜁니다: {file_path}")
        except Exception as open_err:
            print(f"저장된 파일 열기 중 오류 발생: {open_err}")
        return os.path.abspath(file_path)
    except Exception as e:
        print(f"뉴스 기사 저장 중 오류 발생: {e}")
        return None

# ------------------------------------------------------------------
# 작성자 : 곽은규
# 작성일 : 2025-07-30
# 기능 : 검색(KFinanceDataReader) 통해 종목 코드를 찾는 함수
# ------------------------------------------------------------------
def get_stock_info_from_search(keyword: str):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    import time

    clean_keyword = keyword.replace(' 주가','').strip()
    clean_keyword_2 = clean_keyword.replace('주가','').strip()
    found_code = finance(clean_keyword_2)
    if found_code:
        print(f"DEBUG: FinanceDataReader로 찾은 종목 코드: {found_code}")
        return found_code
    if keyword == "아이온큐":
        search_kyeword = keyword
    if '주가' not in keyword:
        search_keyword = f"{keyword} 주가"
    else:
        search_keyword = keyword
    if search_keyword.isdigit() and len(search_keyword) == 6:
        return search_keyword
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    driver = webdriver.Chrome(options=options)
    try:
        search_url = f"https://search.naver.com/search.naver?query={search_keyword}"
        driver.get(search_url)
        time.sleep(0.3)
        finance_links = driver.find_elements("css selector", "a[href*='finance.naver.com/item/main']")
        for link in finance_links:
            href = link.get_attribute('href')
            m = re.search(r"code=(\d{6})", href)
            if m:
                stock_code = m.group(1)
                return stock_code
        return None
    except Exception:
        return None
    finally:
        driver.quit()

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-22
# 기능 : 종목 코드를 통해 차트를 캡처하는 함수
# ------------------------------------------------------------------
def capture_stock_chart(keyword: str, progress_callback=None) -> str:
    if keyword.replace(' ', '') in ['구글', '구글주가']:
        keyword = '알파벳 주가'
    stock_code = get_stock_info_from_search(keyword)
    if stock_code:
        return capture_wrap_company_area(stock_code, progress_callback=progress_callback)
    else:
        from news.src.utils.foreign_utils import capture_naver_foreign_stock_chart
        return capture_naver_foreign_stock_chart(keyword, progress_callback=progress_callback)

# ------------------------------------------------------------------
# 작성자 : 곽은규
# 작성일 : 2025-08-12
# 기능 : 기사 헤드 라인 템플릿 만드는 함수
# ------------------------------------------------------------------
def create_pamphlet(keyword: str, is_foreign: bool) -> str:
    """
    국내/해외 및 장중/장마감 여부에 따라 다른 헤드라인 템플릿을 생성합니다.
    is_foreign: 해외 주식이면 True, 국내 주식이면 False
    """
    now_kst_dt = datetime.now(TZ)
    weekday = now_kst_dt.weekday()

    # ▼▼▼ 1. 해외 주식일 경우의 로직 ▼▼▼
    if is_foreign:
        # 'date_str'에 사용할 한국 날짜 변수
        korea_display_date = now_kst_dt
        
        # 날짜 계산 로직 (주말 처리 포함)
        if weekday == 5:  # 토요일
            yesterday = now_kst_dt - timedelta(days=1) # 금요일
        elif weekday == 6:  # 일요일
            yesterday = now_kst_dt - timedelta(days=2) # 금요일
            korea_display_date = now_kst_dt - timedelta(days=1) 
        elif weekday == 0:  # 월요일
            yesterday = now_kst_dt - timedelta(days=3) # 금요일
            korea_display_date = now_kst_dt - timedelta(days=2) 
        else: # 화요일 ~ 금요일
            yesterday = now_kst_dt - timedelta(days=1)
        
        # '23일(미국 동부 기준 22일)' 형태의 문자열 생성
        # now_kst_dt.day 대신 korea_display_date.day 사용
        date_str = f"{korea_display_date.day}일(미국 동부 기준 {yesterday.day}일) 기준"
        
        return f"{date_str}, 네이버페이 증권에 따르면"

    # ▼▼▼ 2. 국내 주식일 경우의 로직 ▼▼▼
    else:
        # 주말(토, 일)일 경우, 금요일 기준으로 장마감 처리
        if weekday == 5: # 토요일
            friday_dt = now_kst_dt - timedelta(days=1)
            time_status_str = f"{friday_dt.day}일 KRX 장마감"
        elif weekday == 6: # 일요일
            friday_dt = now_kst_dt - timedelta(days=2)
            time_status_str = f"{friday_dt.day}일 KRX 장마감"
        else: # 평일
            time_status_str = convert_get_today_kst_str()

        if "장마감" in time_status_str:
            # 장마감일 경우
            day_part = time_status_str.split(' ')[0]
            return f"{day_part} KRX 마감 기준, 네이버페이 증권에 따르면"
        else:
            # 장중일 경우
            return f"{time_status_str} 기준, 네이버페이 증권에 따르면"

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-25
# 기능 : 차트를 캡처하고 LLM을 통해 뉴스를 생성하는 함수
# ------------------------------------------------------------------
def capture_and_generate_news(keyword: str, domain: str = "stock", progress_callback=None, is_running_callback=None, step_callback=None, debug=False, open_after_save=True, custom_save_dir: Optional[str] = None):
    from news.src.services.info_LLM import generate_info_news_from_text
    from news.src.utils.foreign_utils import capture_naver_foreign_stock_chart
    from news.src.utils.domestic_utils import capture_wrap_company_area

    total_steps = 3 # 1: 정보 조회, 2: 이미지 캡처, 3: 기사 생성
    current_step = 0

    def report_step():
        nonlocal current_step
        current_step += 1
        if step_callback:
            step_callback(current_step, total_steps)
    info_dict = {}
    is_stock = (domain == "stock")

    def save_news_and_image(news, image_path=None):
        today_str = get_today_kst_date_str()

        # ✅ 저장 경로 설정
        if custom_save_dir:
            full_dir = custom_save_dir
        else:
            base_dir = os.path.join(os.getcwd(), "생성된 기사")
            sub_dir = f"기사{today_str}"
            full_dir = os.path.join(base_dir, sub_dir)
        os.makedirs(full_dir, exist_ok=True)

        # 기사 저장
        safe_k = safe_filename(keyword)
        news_path = os.path.join(full_dir, f"{safe_k}_{domain}_news.txt")
        with open(news_path, "w", encoding="utf-8") as f:
            f.write(news)
        if open_after_save:
            try:
                if platform.system() == "Windows":
                    os.startfile(news_path)
                elif platform.system() == "Darwin":
                    subprocess.run(["open", news_path])
            except Exception as e:
                print(f"[WARNING] 메모장 열기 실패: {e}")


        # Toss 탭에서는 이미지 저장 로직 제거 (이미지가 없는 경우가 있으므로 안전하게 처리)
        if domain == "toss" and image_path and os.path.exists(image_path):
            print(f"[INFO] Toss 탭: 이미지 저장 생략 - {image_path}")
            pass  # Toss 탭에서는 이미지 저장을 하지 않음

    if domain in ["stock", "toss"]:  # "toss"와 "stock" 도메인 처리
        stock_code = get_stock_info_from_search(keyword)
        report_step() # 1. 정보 조회 완료

        if not stock_code:
            # 🔹 해외 주식 처리
            if progress_callback:
                progress_callback(f"{keyword} 해외주식 정보 조회 중...")
            image_path, stock_data, success = capture_naver_foreign_stock_chart(keyword, progress_callback=progress_callback, custom_save_dir=custom_save_dir)
            report_step() # 2. 이미지 캡처 완료
            if not image_path or not stock_data:
                if progress_callback:
                    progress_callback("해외주식 데이터 수집 실패")
                return None
            
            info_dict = stock_data
            if progress_callback:
                progress_callback("LLM 기사 생성 중...")
            news = generate_info_news_from_text(keyword, info_dict, domain)
            report_step() # 3. 기사 생성 완료
            if news:
                # 1. 팜플렛 문구를 별도로 생성합니다. (해외 주식으로 설정)
                pamphlet_text = create_pamphlet(keyword, is_foreign=True)

                # 2. LLM 결과물에서 '[본문]' 또는 '본문' 마커를 찾아 후처리합니다.
                if re.search(r'(\[본문\]|본문)', news):
                    # 교체될 텍스트: '[본문]' 다음 줄에 팜플렛이 오고, 그 뒤에 한 칸 띄고 본문이 시작됩니다.
                    replacement_text = f"[본문]\n{pamphlet_text} "
                    # re.sub를 사용하여 '[본문]' 또는 '본문'과 그 뒤의 공백을 찾아 한 번만 교체합니다.
                    final_output = re.sub(r'(\[본문\]|본문)\s+', replacement_text, news, count=1)
                else:
                    # '본문' 마커가 없는 비상시에는, 맨 앞에 붙입니다.
                    final_output = pamphlet_text + '\n\n' + news
                
                # 3. 최종 완성본을 저장합니다.
                save_news_and_image(final_output, image_path)
            return news

        # 🔹 국내 주식 처리 (Toss 탭 제외)
        if domain == "toss":
            # Toss 탭의 경우, 이미지 경로는 None으로 설정하고 차트 정보만 가져옴
            if progress_callback:
                progress_callback(f"{keyword} Toss 종목 정보 조회 중...")
            
            # Toss 탭에서는 Toss 기사 폴더에 차트와 기사를 각각 1개씩만 저장
            if progress_callback:
                progress_callback(f"{keyword} Toss 종목 정보 조회 중...")
                
            # Toss 기사 폴더 경로 설정
            if custom_save_dir:
                toss_save_dir = custom_save_dir
            else:
                today_str = get_today_kst_date_str()
                toss_save_dir = os.path.join(os.getcwd(), "Toss기사", f"기사{today_str}")
                
            # 차트 정보 가져오기 (Toss 기사 폴더에 저장)
            image_path, is_stock, chart_text, invest_info_text, chart_info, invest_info, summary_info_text = capture_wrap_company_area(
                stock_code, 
                progress_callback=progress_callback, 
                debug=debug,
                custom_save_dir=toss_save_dir,
                is_running_callback=is_running_callback
            )
        else:
            # 일반 주식의 경우 기존 로직 유지
            if progress_callback:
                progress_callback(f"{keyword} 국내주식 정보 조회 중...")
            image_path, is_stock, chart_text, invest_info_text, chart_info, invest_info, summary_info_text = capture_wrap_company_area(
                stock_code, 
                progress_callback=progress_callback, 
                debug=debug, 
                custom_save_dir=custom_save_dir,
                is_running_callback=is_running_callback
            )
        report_step() # 2. 이미지 캡처 완료
        if not image_path:
            if progress_callback:
                progress_callback("국내주식 이미지 캡처 실패")
            return None
        info_dict = {**chart_info, **invest_info}
        
        # 신규상장 관련 정보 추가하기
        is_newly_listed_stock = data_manager.is_newly_listed(keyword)
        info_dict["신규상장여부"] = is_newly_listed_stock

        # if summary_info_text:
        #     info_dict["기업개요"] = summary_info_text
        if debug:
            print("[DEBUG] 국내 주식 정보:\n", info_dict)
        if progress_callback:
            progress_callback("LLM 기사 생성 중...")
        news = generate_info_news_from_text(keyword, info_dict, domain)
        report_step() # 3. 기사 생성 완료
        if news:
            # 1. 팜플렛 문구를 별도로 생성합니다. (해외 주식으로 설정)
            pamphlet_text = create_pamphlet(keyword, is_foreign= False)

            # 2. LLM 결과물에서 '[본문]' 또는 '본문' 마커를 찾아 후처리합니다.
            if re.search(r'(\[본문\]|본문)', news):
                # 교체될 텍스트: '[본문]' 다음 줄에 팜플렛이 오고, 그 뒤에 한 칸 띄고 본문이 시작됩니다.
                replacement_text = f"[본문]\n{pamphlet_text} "
                # re.sub를 사용하여 '[본문]' 또는 '본문'과 그 뒤의 공백을 찾아 한 번만 교체합니다.
                final_output = re.sub(r'(\[본문\]|본문)\s+', replacement_text, news, count=1)
            else:
                # '본문' 마커가 없는 비상시에는, 맨 앞에 붙입니다.
                final_output = pamphlet_text + '\n\n' + news
            
            # 3. 최종 완성본을 저장합니다.
            save_news_and_image(final_output, image_path)
        return news

    else:
        report_step() # 1. 정보 조회 완료 (기타 도메인은 조회 단계가 없으므로 바로 호출)
        # 🔹 기타 도메인 (coin, fx 등)
        image_path, stock_data, success = capture_naver_foreign_stock_chart(keyword, progress_callback=progress_callback, custom_save_dir=custom_save_dir)
        report_step() # 2. 이미지 캡처 완료
        if not image_path or not success:
            if progress_callback:
                progress_callback("이미지 캡처 실패")
            return None
        info_dict = {"이미지": image_path, "키워드": keyword}
        if debug:
            print("[DEBUG] 기타 도메인 정보:\n", info_dict)
        if progress_callback:
            progress_callback("LLM 기사 생성 중...")
        news = generate_info_news_from_text(keyword, info_dict, domain)
        if news:
            # 1. 팜플렛 문구를 별도로 생성합니다. (해외 주식으로 설정)
            pamphlet_text = create_pamphlet(keyword, is_foreign=True)

            # 2. LLM 결과물에서 '[본문]' 또는 '본문' 마커를 찾아 후처리합니다.
            if re.search(r'(\[본문\]|본문)', news):
                # 교체될 텍스트: '[본문]' 다음 줄에 팜플렛이 오고, 그 뒤에 한 칸 띄고 본문이 시작됩니다.
                replacement_text = f"[본문]\n{pamphlet_text} "
                # re.sub를 사용하여 '[본문]' 또는 '본문'과 그 뒤의 공백을 찾아 한 번만 교체합니다.
                final_output = re.sub(r'(\[본문\]|본문)\s+', replacement_text, news, count=1)
            else:
                # '본문' 마커가 없는 비상시에는, 맨 앞에 붙입니다.
                final_output = pamphlet_text + '\n\n' + news
            
            # 3. 최종 완성본을 저장합니다.
            save_news_and_image(final_output, image_path)
        return news

# ------------------------------------------------------------------
# 작성자 : 곽은규
# 작성일 : 2025-07-09
# 기능 : 주식 정보를 위한 프롬프트를 생성하는 함수
# ------------------------------------------------------------------
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

    weekday = date_obj.weekday()
    is_weekend = weekday in [5, 6]

    # 주말일 경우 날짜를 금요일로 조정
    if is_weekend:
        # weekday가 5(토)이면 1일 빼고, 6(일)이면 2일 뺀다. (weekday - 4)
        effective_date_obj = date_obj - timedelta(days=weekday - 4)
        now_time = f"{effective_date_obj.day}일 KRX 장마감"
    else:
        effective_date_obj = date_obj
        now_time = convert_get_today_kst_str()

    print("now_time 호출 결과:", now_time)

    # 모든 날짜 계산을 effective_date_obj 기준으로 수행
    if effective_date_obj.weekday() == 0:  # 월요일은 0
        yesterday = effective_date_obj - timedelta(days=3)
    else:
        yesterday = effective_date_obj - timedelta(days=1)
    before_yesterday = yesterday - timedelta(days=1)
    
    today_day_str = str(effective_date_obj.day)
    print(f"today_day_str: {today_day_str}")

    if effective_date_obj.month != yesterday.month:
        yesterday_str = f"지난달 {yesterday.day}"
    else:
        yesterday_str = f"지난 {yesterday.day}"
    print(f"yesterday_str: {yesterday_str}")
    if yesterday.month != before_yesterday.month:
        before_yesterday_str = f"지난달 {before_yesterday.day}"
    else:
        before_yesterday_str = f"지난 {before_yesterday.day}"
    print(f"before_yesterday_str: {before_yesterday_str}") 

    # 'O월 O일' 형식으로 날짜를 변환하는 내부 함수
    def format_month_day(dt):
        if platform.system() == "Windows":
            return dt.strftime("%#m월 %#d일")
        else:
            return dt.strftime("%-m월 %-d일")
    
    today_month_day_format = format_month_day(effective_date_obj)

    if "장마감" in now_time:
        title_time_format = f"\"{today_month_day_format}\" "
    else:
        title_time_format = f"\"{today_month_day_format} 장중\""
        
    today_month_day = format_month_day(effective_date_obj)
    print(f"월과 일: {today_month_day_format}")
    print(title_time_format)
        

    # 원하는 형식의 최종 문자열을 생성
    # 주말 해외주식 날짜 표기를 위한 로직
    if weekday in [5, 6, 0]: # 토요일, 일요일, 월요일
    # 금요일 날짜 계산
        friday = date_obj - timedelta(days= (weekday - 4) % 7)
        
        # 한국 날짜(금요일), 미국 날짜(금요일)
        output_current_day = f"{friday.day}일(미국 동부 기준 {friday.day}일)"
        
        # 이전 날짜(목요일) 계산
        yesterday = friday - timedelta(days=1)
        output_previous_day = f"{yesterday.day}일(미국 동부 기준 {yesterday.day}일)"
    
    else: # 화요일부터 금요일
        # 한국 날짜는 오늘(화요일)의 날짜, 미국 날짜는 어제의 날짜
        yesterday = date_obj - timedelta(days=1)
        output_current_day = f"{date_obj.day}일(미국 동부 기준 {yesterday.day}일)"
        
        # 이전 날짜는 그저께 날짜
        before_yesterday = yesterday - timedelta(days=1)
        output_previous_day = f"{yesterday.day}일(미국 동부 기준 {before_yesterday.day}일)"

    print(f"output_current_day: {output_current_day}")
    print(f"output_previous_day: {output_previous_day}")

    stock_prompt = (
        "[Special Rules for Stock-Related News]\n"
        f"1. 제목 작성 시 규칙\n"
        f"   - **순서는 1)키워드 2)\"{title_time_format}\" 3)내용 순으로 생성하고, 키워드 뒤에는 반드시 콤마(,)를 표기할 것.**\n"
        f"   - 금액에는 천단위는 반드시 콤마(,)를 표기할 것 (예: 64,600원)\n"
        f"   - **국내 주식일 경우에만, 반드시 날짜는 \"{title_time_format}\"과 같은 형식으로만 기입할 것.\n**"
        f"   - 해외 주식일 경우에만, 제목을 작성할 때 날짜를 포함하지 말고 생성 할 것.\n"
        f"   - 해외 주식을 판별하는 방법은 [주식 정보]안에 us_time을 제공이 되면 해외주식 규칙을 적용할 것\n"
        f"   - 해외 주식일 경우, [주식 정보] 안에 us_time을 참고해서 장중/장마감 구분하기.\n"
        f"   - 가격과 등락률(%)을 반드시 함께 표기하고, 다양한 서술 방식을 사용하여 제목을 풍부하고 다채롭게 표현할 것.\n"
        f"   - 제목을 작성 할 때 '전일 대비, 지난, 대비'와 같은 비교 표현은 사용하지 않는다.\n"
        f"   - **주가 정보는 간결하게 포함하며, 장이 마감되었을 경우에만 제목의 가장 마지막에 \"<변동 방향/상태> 마감\" 형식으로 마무리 할 것.**\n\n"
        f"2. 본문 작성 시 절대 규칙\n"
        f"   - **본문 작성 원칙: 시스템이 자동 추가하는 날짜/시간/출처/기준점 정보와 반드시 중복되지 않게할 것.**\n"
        f"   - **작성 범위: 종목명으로 시작하여 [주식 정보] 데이터 기반으로 가격 변동 분석을 충분한 분량으로 서술할 것.**\n"
        f"   - **장중/장마감 구분은 [키워드 정보(user message)] 내의 [주식 정보] 안에 기준일을 참고하여 구분할 것.**\n"
        f"   - 주식의 최종 가격과 변동률을 한 문장으로 명확히 서술할 것.\n"
        f"   - **[본문] 내용을 작성할 때 시간 관련 표현과 데이터 기준점 설명을 모두 배제하고 순수한 주가 수치와 변동률만 서술할 것.**\n"
        f"   - [키워드 정보(user message)] 내의 [주식 정보]안에 신규상장 값이 Ture이면, 신규상장이란 지난 종가를 공모가로 바꾸고 내용도 신규상장에 맞게 작성할 것."
        f"   - '전일', '전날', '전 거래일', '지난 거래일' 같은 표현은 '지난 종가'로 표현할것.\n\n"
        f"3. 해외 주식의 경우, 날짜와 추가 본문 작성 규칙\n"
        f"     - 해외 주식의 경우 '시간 외 거래'가 있는 경우 본문에 정규장 내용 이후 시간 외 거래 내용을 포함할 것.\n"
        f"     - **장중/장마감 구분은 [키워드 정보(user message)] 내의 [해외주식 정보] 안에 us_time을 참고하여 구분할 것.**\n"
        f"     - 예시: 실시간 -> 장 중 장마감 -> 장 마감\n\n"
        f"4. 거래대금은 반드시 **억 단위, 천만 단위로 환산**하여 정확히 표기할 것\n"
        f"   - 예시: \"135,325백만\" → \"1,353억 2,500만 원\" / \"15,320백만\" → \"153억 2,000만 원\" / \"3,210백만\" → \"32억 1,000만 원\" / \"850백만\" → \"8억 5,000만 원\"\n\n"

        f"[Style]\n"
        f"- 반드시 장 시작/장중/장 마감 시점에 따라 서술 시제 변경\n"
        f"- 등락과 연속 흐름을 조건별로 구분해 자연스럽게 서술하도록 지시할 것.\n"
        f"- 기업과 주식 관련 정보는 구체적인 수치와 함께 명시할 것.\n"
        f"- 단순 데이터 나열을 금지하며, 원인과 결과를 엮어 [News Generation Process] 기반으로 구성할 것.\n"
        f"- **'투자자들, 관심, 주목, 기대, 풀이, 분석' 이라는 단어와 분석내용,감정,주관이 담긴 표현을 엄격히 사용하지 않는다.\n**"
        f"- **'이날, 전일, 전 거래일, 전날' 이라는 단어와 표현은 엄격히 절대 사용하지 말 것.\n\n**"
    )
    return stock_prompt
    