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
def save_news_to_file(keyword: str, domain: str, news_content: str, save_dir: str = "생성된 기사", open_after_save: bool = True):
    if not news_content or not news_content.strip():
        print("[WARNING] 저장할 뉴스 내용이 비어 있습니다. 파일 저장을 건너뜁니다.")
        return None
        
    current_dir = os.getcwd()
    today_date_str = get_today_kst_date_str()
    base_save_dir = os.path.join(current_dir, save_dir)
    full_save_dir = os.path.join(base_save_dir, f"기사{today_date_str}")
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
# 작성자 : 최준혁
# 작성일 : 2025-07-25
# 기능 : 차트를 캡처하고 LLM을 통해 뉴스를 생성하는 함수
# ------------------------------------------------------------------
def capture_and_generate_news(keyword: str, domain: str = "stock", progress_callback=None, debug=False, open_after_save=True, custom_save_dir: Optional[str] = None):
    from news.src.services.info_LLM import generate_info_news_from_text
    from news.src.utils.foreign_utils import capture_naver_foreign_stock_chart
    from news.src.utils.domestic_utils import capture_wrap_company_area
    info_dict = {}
    is_stock = (domain == "stock")

    def save_news_and_image(news, image_path=None):
        today_str = get_today_kst_date_str()

        # ✅ 저장 경로 설정
        if custom_save_dir:
            base_dir = custom_save_dir
            sub_dir = f"토스{today_str}"
        else:
            base_dir = os.path.join(os.getcwd(), "생성된 기사")
            sub_dir = f"기사{today_str}"

        full_dir = os.path.join(base_dir, sub_dir)
        os.makedirs(full_dir, exist_ok=True)

        # 기사 저장
        safe_k = safe_filename(keyword)
        news_path = os.path.join(full_dir, f"{safe_k}_{domain}_news.txt")
        if not os.path.exists(news_path):
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
        else:
            print(f"[INFO] 뉴스 파일 중복되어 저장 생략: {news_path}")

        # 이미지 저장
        if image_path and os.path.exists(image_path):
            if custom_save_dir:
                try:
                    image_save_path = os.path.join(full_dir, f"{safe_k}_chart.png")
                    copyfile(image_path, image_save_path)
                    print(f"[INFO] 차트 이미지 저장 완료: {image_save_path}")

                    # 루트 경로에 저장된 이미지라면 삭제
                    if os.path.dirname(image_path) == os.getcwd():
                        os.remove(image_path)
                        print(f"[INFO] 루트 이미지 삭제 완료: {image_path}")
                except Exception as e:
                    print(f"[ERROR] 이미지 저장 실패: {e}")

    if domain in ["stock", "toss"]:  # "toss" 도메인도 국내주식과 동일하게 처리
        stock_code = get_stock_info_from_search(keyword)

        if not stock_code:
            # 🔹 해외 주식 처리
            image_path, stock_data, success = capture_naver_foreign_stock_chart(keyword, progress_callback=progress_callback)
            if not image_path or not stock_data:
                if progress_callback:
                    progress_callback("해외주식 데이터 수집 실패")
                return None
            info_dict = dict(stock_data)
            info_dict["키워드"] = keyword
            if debug:
                print("[DEBUG] 해외주식 정보:\n", info_dict)
            if progress_callback:
                progress_callback("LLM 기사 생성 중...")
            news = generate_info_news_from_text(keyword, info_dict, domain)
            if news:
                save_news_and_image(news, image_path)
            return news

        # 🔹 국내 주식 처리
        image_path, is_stock, chart_text, invest_info_text, chart_info, invest_info, summary_info_text = capture_wrap_company_area(
            stock_code, progress_callback=progress_callback, debug=debug
        )
        if not image_path:
            if progress_callback:
                progress_callback("국내주식 이미지 캡처 실패")
            return None
        info_dict = {**chart_info, **invest_info}
        if summary_info_text:
            info_dict["기업개요"] = summary_info_text
        if debug:
            print("[DEBUG] 국내 주식 정보:\n", info_dict)
        if progress_callback:
            progress_callback("LLM 기사 생성 중...")
        news = generate_info_news_from_text(keyword, info_dict, domain)
        if news:
            save_news_and_image(news, image_path)
        return news

    else:
        # 🔹 기타 도메인 (coin, fx 등)
        image_path, stock_data, success = capture_naver_foreign_stock_chart(keyword, progress_callback=progress_callback)
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
            save_news_and_image(news, image_path)
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
    now_time = convert_get_today_kst_str()
    print("now_time 호출 결과:", now_time)
    if date_obj.weekday() == 0:  # 월요일은 0
        yesterday = date_obj - timedelta(days=3)
    else:
        yesterday = date_obj - timedelta(days=1)
    before_yesterday = yesterday - timedelta(days=1)
    today_day_str = str(date_obj.day)
    print(f"today_day_str: {today_day_str}")
    if date_obj.month != yesterday.month:
        yesterday_str = f"지난달 {yesterday.day}"
    else:
        yesterday_str = f"지난 {yesterday.day}"
    print(f"yesterday_str: {yesterday_str}")
    if yesterday.month != before_yesterday.month:
        before_yesterday_str = f"지난달 {before_yesterday.day}"
    else:
        before_yesterday_str = f"지난 {before_yesterday.day}"
    print(f"before_yesterday_str: {before_yesterday_str}")  
    stock_prompt = (
        "[Special Rules for Stock-Related News]\n"
        f"1. 제목 작성 시 규칙\n"
        f"   - 금액에는 천단위는 반드시 콤마(,)를 표기할 것 (예: 64,600원)\n"
        f"   - **반드시 날짜는 \"O월 O일\"과 같이 \"월 일\" 형식으로 기입할 것\n**"
        f"   - 가격과 등락률을 표시할때는 함께 표기할 것\n"
        f"   - 키워드 뒤에 반드시 콤마(,)를 표기하고 난 후 날짜를 표현한 후 내용을 이어 붙일 것\n"
        f"   - '전일 대비'와 같은 비교 표현은 사용하지 않는다."
        f"   - 주가 정보 포함 시: 단, '장중' 이라는 단어는 날짜 뒤에 붙어서 나오거나 [등락률] 앞에 나올 것.\n"
        f"   - 시제는 기사 작성 시점을 반드시 기준일과 시점(예: 장마감, 장중 등)을 아래의 기준으로 구분한다.\n"
        f"   - **주가 정보는 간결하게 포함하며, 장이 마감되었을 경우에만 제목의 가장 마지막에 \"[변동 방향/상태] 마감\" 형식으로 추가할 것.**\n"
        f"2. 본문 작성 시 규칙\n"
        f"   - 첫줄에 날짜와 \"{now_time} 기준, 네이버페이 증권에 따르면\" 분까지 표기해서 표시할 것, 그 이후는 [News Generation Process] 내용에 충실할 것\n "
        f"   - 날짜는 반드시 **\"{today_day_str}일\", \"{yesterday.day}일\"처럼 일(day)만** 표기 (월은 생략)\n"
        f"   - '전일'이나 '전 거래일'이라는 표현하지 말 것, 대신 반드시 **\"{yesterday_str}일\", \"{before_yesterday_str}일\"**처럼 날짜를 명시할 것\n"
        f"   - 날짜가 포함된 시간 표현은 \"{today_kst} 오전 10시 56분\" → **\"{today_day_str}일 오전 10시 56분\"** 형식으로 변환\n"
        f"   - **절대로 '이날', '금일', '당일'과 같은 표현을 사용하지 말 것.** 대신 오늘 날짜인 \"{today_day_str}일\"로 반드시 바꿔서 명시할 것.\n\n"
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
