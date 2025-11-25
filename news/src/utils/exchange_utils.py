# ------------------------------------------------------------------
# 작성자 : 최준혁
# 기능 : 네이버 금융 환율 정보 검색 및 차트 캡처 유틸리티 모듈
# ------------------------------------------------------------------
import os
import time
import io
from datetime import datetime
from PIL import Image
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from news.src.utils.driver_utils import initialize_driver
from news.src.utils.clipboard_utils import copy_image_to_clipboard

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 기능 : 환율 검색어 생성
# ------------------------------------------------------------------
def make_exchange_keyword(keyword: str) -> str:
    """
    환율 정보 검색을 위한 검색어 생성
    :param keyword: 변환할 원본 키워드 (예: '달러')
    :return: '환율'이 접미사로 붙은 검색어 (예: '달러환율')
    """
    keyword = keyword.strip()
    if keyword.endswith("환율"):
        return keyword
    return f"{keyword}환율"

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 기능 : 환율 차트 캡처
# ------------------------------------------------------------------
def capture_exchange_chart(keyword: str, progress_callback=None) -> str:
    """
    네이버 검색에서 환율 차트를 찾아 캡처 및 저장
    :param keyword: 검색할 환율 키워드 (예: '달러', '유로')
    :param progress_callback: 진행 상태를 전달할 콜백 함수
    :return: 캡처된 이미지 파일의 전체 경로
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
        time.sleep(0.5)
        
        if progress_callback:
            progress_callback("차트 영역 찾는 중...")
            
        # 차트 영역 찾기 시도
        selectors = [
            ("div.exchange_top.up", "div.invest_wrap"),
            ("div.exchange_top", "div.invest_wrap"),
            ("[class*='exchange']", "[class*='invest']")
        ]
        
        top = bottom = None
        for top_selector, bottom_selector in selectors:
            try:
                top = driver.find_element(By.CSS_SELECTOR, top_selector)
                bottom = driver.find_element(By.CSS_SELECTOR, bottom_selector)
                if top and bottom:
                    break
            except:
                continue
                
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
        
        with Image.open(io.BytesIO(screenshot)).convert("RGB") as image:
            top_coord = max(0, start_y)
            bottom_coord = min(image.height, end_y - 20)
            left_offset = 395
            crop_width = 670
            
            if progress_callback:
                progress_callback("차트 이미지 잘라내기...")
                
            cropped = image.crop((left_offset, top_coord, left_offset + crop_width, bottom_coord))
            currency = top.text.split('\n')[0].strip().replace(' ', '') or "환율"
            today = datetime.now().strftime('%Y%m%d')
            folder = os.path.join(os.getcwd(), "환율차트", f"환율{today}")
            os.makedirs(folder, exist_ok=True)
            output_path = os.path.join(folder, f"{currency}_환율차트.png")
            cropped.save(output_path, format="PNG")
            
        if progress_callback:
            progress_callback("이미지를 클립보드에 복사 중...")
            
        copy_image_to_clipboard(output_path)
        return output_path
        
    finally:
        driver.quit()

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-10-13
# 기능 : FX용 시간 상태 문자열 (09:00 장 시작, 익일 03:30 장 마감 규칙 설명용)
# ------------------------------------------------------------------
def fx_time_status_str(now_dt=None) -> str:
    try:
        from zoneinfo import ZoneInfo
        TZ = ZoneInfo('Asia/Seoul')
    except Exception:
        try:
            import pytz
            TZ = pytz.timezone('Asia/Seoul')
        except Exception:
            TZ = None
    from datetime import datetime as _dt
    from datetime import timedelta as _td
    if now_dt is None:
        now_dt = _dt.now(TZ) if TZ else _dt.now()
    # 03:30~09:00 : 전일 장마감 간주
    if (now_dt.hour < 9):
        y = now_dt - _td(days=1)
        return f"{y.day}일 장마감"
    # 09:00~익일 03:30 : 장중 현재시각 표기
    am_pm = "오전" if now_dt.hour < 12 else "오후"
    h12 = now_dt.hour % 12
    if h12 == 0:
        h12 = 12
    return f"{now_dt.day}일 {am_pm} {h12}시 {now_dt.minute}분"

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-10-13
# 기능 : FX 기사 본문 선두 템플릿 생성
# 설명 : "D일 오전/오후 H시 M분 기준, 네이버페이 증권에 따르면" 또는 "D일 장마감 기준, ..."
# ------------------------------------------------------------------
def create_fx_template(now_kst_dt=None) -> str:
    try:
        # fx_time_status_str는 KST 기준을 내부에서 처리
        time_status = fx_time_status_str(now_kst_dt)
    except Exception:
        from datetime import datetime as _dt
        time_status = f"{_dt.now().day}일"
    return f"{time_status} 기준, 네이버페이 증권에 따르면"

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-10-13
# 기능 : 환율 차트 캡처 + 상단 텍스트 파싱하여 수치 데이터 동시 반환
# 반환: (output_path, data_dict)
# ------------------------------------------------------------------
def capture_exchange_chart_with_data(keyword: str, progress_callback=None):
    if progress_callback:
        progress_callback("네이버 검색 페이지 접속 중...")
    key = make_exchange_keyword(keyword)
    driver = initialize_driver()
    try:
        url = f"https://search.naver.com/search.naver?query={key}"
        driver.get(url)
        if progress_callback:
            progress_callback("페이지 로딩 대기 중...")
        WebDriverWait(driver, 3).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        time.sleep(0.5)

        if progress_callback:
            progress_callback("차트 영역 찾는 중...")
        selectors = [
            ("div.exchange_top.up", "div.invest_wrap"),
            ("div.exchange_top", "div.invest_wrap"),
            ("[class*='exchange']", "[class*='invest']"),
        ]
        top = bottom = None
        for top_selector, bottom_selector in selectors:
            try:
                top = driver.find_element(By.CSS_SELECTOR, top_selector)
                bottom = driver.find_element(By.CSS_SELECTOR, bottom_selector)
                if top and bottom:
                    break
            except:
                continue
        if not top or not bottom:
            if progress_callback:
                progress_callback("❌ 환율 차트 영역을 찾을 수 없습니다.")
            raise Exception(f"환율 차트 요소를 찾을 수 없습니다. 검색어: {key}")

        # 상단 텍스트 파싱
        top_text = top.text.strip()
        data = _parse_exchange_top_text(top_text)

        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", top)
        time.sleep(0.3)
        zoom = driver.execute_script("return window.devicePixelRatio || 1;")
        start_y = int(top.location['y'] * zoom)
        end_y = int((bottom.location['y'] + bottom.size['height']) * zoom)
        if progress_callback:
            progress_callback("화면 전체 스크린샷 캡처 중...")
        screenshot = driver.get_screenshot_as_png()
        with Image.open(io.BytesIO(screenshot)).convert("RGB") as image:
            top_coord = max(0, start_y)
            bottom_coord = min(image.height, end_y - 20)
            left_offset = 395
            crop_width = 670
            if progress_callback:
                progress_callback("차트 이미지 잘라내기...")
            cropped = image.crop((left_offset, top_coord, left_offset + crop_width, bottom_coord))
            currency = top.text.split('\n')[0].strip().replace(' ', '') or "환율"
            today = datetime.now().strftime('%Y%m%d')
            folder = os.path.join(os.getcwd(), "환율차트", f"환율{today}")
            os.makedirs(folder, exist_ok=True)
            output_path = os.path.join(folder, f"{currency}_환율차트.png")
            cropped.save(output_path, format="PNG")
        if progress_callback:
            progress_callback("이미지를 클립보드에 복사 중...")
        copy_image_to_clipboard(output_path)
        return output_path, data
    finally:
        driver.quit()

def _parse_exchange_top_text(text: str) -> dict:
    """상단 텍스트에서 통화/현재가/등락률/등락금액을 휴리스틱으로 추출"""
    import re
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    head = lines[0] if lines else ""
    # 숫자(천단위 콤마, 소수), 퍼센트 탐색
    num_pattern = re.compile(r"\d{1,3}(?:,\d{3})*(?:\.\d+)?")
    pct_pattern = re.compile(r"[-+]?\d+(?:\.\d+)?\s*%")
    cur = None
    chg = None
    pct = None
    # 우선 전체 텍스트에서 패턴 검색
    nums = num_pattern.findall(text)
    # JPY(엔) 표기 보정: 네이버 상단에 'JPY 100' 또는 '100엔당'처럼 단위 숫자 100이
    # 가격 앞에 먼저 등장하는 경우가 있어 첫 숫자가 100으로 잘못 캡처되는 문제를 방지한다.
    try:
        if ("엔" in head) or ("JPY" in head) or ("엔" in text) or ("JPY" in text):
            if nums and nums[0].replace(",", "") in ("100", "100.0"):
                nums = nums[1:]
    except Exception:
        pass
    pcts = pct_pattern.findall(text)
    if nums:
        cur = nums[0]
        if len(nums) > 1:
            chg = nums[1]
    if pcts:
        pct = pcts[0].replace(" ", "")
    return {
        "통화": head,
        "현재가": cur,
        "등락": chg,
        "등락률": pct,
    }

# ------------------------------------------------------------------
# 작성자 : 최준혁 
# 작성일 : 2025-10-13
# 기능 : 환율(FX) 뉴스를 위한 프롬프트 생성 함수
# ------------------------------------------------------------------
def build_fx_prompt(today_kst: str, include_aggregate_tag: bool = False) -> str:
    """
    환율 뉴스 생성을 위한 LLM 프롬프트. 통화 간 비교, 지표 해석, 금지어/형식 규칙을 지시한다.
    :param today_kst: 한국시간 문자열 (예: '20251013 15:30')
    :param include_aggregate_tag: 종합 기사일 때 제목에 [종합 환율] 강제 여부
    :return: LLM 시스템 프롬프트에 추가할 문자열
    """
    title_rule_line = (
        "   - 제목에는 반드시 [종합 환율] 'O월 O일' 날짜를 포함할 것. (예: [종합 환율] 10월 13일 주요국 환율 강세 엔화 홀로 약세)\n"
        if include_aggregate_tag
        else
        "   - 제목에는 반드시 'O월 O일' 날짜를 포함할 것. (예: 10월 13일 주요국 환율 강세 엔화 홀로 약세)\n"
    )
    fx_prompt = (
        "[Special Rules for FX-Related News]\n"
        f"오늘 날짜 : {today_kst}\n\n"
        "1. 전역 규칙\n"
        "   - 기사 문체는 일관된 단정형(~이다)으로 유지하고 추측/전망 금지.\n"
        "   - 통화별 관찰 사실(수준·변동폭·범위·상대 위치)을 기반으로 서술하고, 통화 간 비교를 통해 의미를 도출할것.\n"
        "   - 모든 환율은 원화를 기준으로 한 대원화 환율(원/달러, 유로/원, 엔/원 등)로 서술한다.\n"
        "   - 환율 하락은 해당 통화 가치 하락·원화 가치 상승, 환율 상승은 해당 통화 가치 상승·원화 가치 하락을 의미함을 일관되게 유지할 것.\n"
        "   - 주어를 명확히 쓴다. 예) '달러/원 환율이 하락했다', '달러화가 원화 대비 약세를 보였다'처럼 무엇이 기준이고 무엇이 변했는지 드러내고,\n"
        "     '주요국 환율은 원화 대비 가치 하락'처럼 애매한 표현은 사용하지 않는다.\n"
        "   - 이미지와 텍스트를 분석해 상대적으로 내용을 풍부하게 작성할것.(400자 이상 800자 이하)\n"
        "   - 메타 서술 금지: 이미지/차트/사진/분석/모델/AI 등 도구나 분석 행위 자체를 언급하지 않는다.\n"
        "   - 데이터 나열을 피하고 원인-결과·관계 중심으로 문장을 구성.\n\n"
        "   - 장 시작: 오늘 날짜 기준 오전 9시 KST, 장 마감: 다음 날 새벽 3시 30분 KST.\n"
        "   - 09:00 ~ 익일 03:30 KST 구간은 장중, 03:31 ~ 08:59 KST 구간은 '장마감' 기준으로 본다.\n"
        "   - 장중에는 제목과 본문에 '장중'을 포함하고, 장마감에는 '장마감'을 포함할 것.\n\n"
        "2. 제목 규칙\n"
        + title_rule_line +
        "   - 키워드 뒤 콤마 사용 가능. 핵심 수치·핵심 결과를 간결히 요약.\n"
        "   - 특수문자 금지 규칙 준수(괄호/…/!/? 등 금지).\n"
        "   - 제목에 숫자 작성 시 천 단위에 콤마(,) 반드시 작성.\n"
        "   - 제목에서는 가능하면 '원/달러 환율 하락', '원화 강세', '달러화 약세'처럼 환율 방향과 강·약세 관계가 한눈에 드러나게 쓴다.\n\n"
        "3. 본문 규칙\n"
        '   - 본문 시작부에는 시스템이 자동 삽입하는 템플릿(\"… 기준, 네이버페이 증권에 따르면\")만 날짜/시간을 포함하고, 그 외 본문에서는 날짜/시간을 사용하지 않는다.\n'
        "   - 통화별 관찰 포인트를 제시하되 최종 본문은 하나의 통합 기사로 작성.\n"
        "   - 수준/범위/상대 위치 등 수치 기반 근거로 기술하고, 형용적 평가 대신 객관 서술로 제시.\n"
        "   - 통화별 기본 서술 구조는 '원/달러 환율은 X원으로 전일보다 Y원(Z%) 하락했다' 형식을 따른다.\n"
        "   - 등락 서술 시에는 반드시 '어제 대비 얼마, 몇 퍼센트 상승/하락'을 우선 제시하고,\n"
        "     그 다음 문장에서 보조적으로 '원화 강세/약세, 달러 강세/약세' 표현을 사용할 수 있다.\n"
        "   - '강세/약세'를 쓸 때는 반드시 어떤 통화가 무엇(원화)을 기준으로 강세/약세인지 명시한다.\n"
        "   - 이미지/차트 분석 언급, 모델/AI 언급을 포함한 메타 표현을 사용하지 않는다.\n"
        "   - N/A 또는 불명확한 경우 해당 서술은 생략.\n"
    )

    return fx_prompt

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-10-13
# 기능 : 여러 통화의 환율 차트를 일괄 캡처
# ------------------------------------------------------------------
def capture_multiple_exchange_charts(keywords: list[str], progress_callback=None):
    """
    주어진 통화 키워드 목록에 대해 환율 차트를 순차 캡처합니다.
    :param keywords: 통화명 리스트 (예: ['달러','엔','유로', ...])
    :param progress_callback: 진행 상태 콜백
    :return: {통화키워드: 이미지경로} 딕셔너리 (실패 항목은 누락)
    """
    images = {}
    datas = {}
    total = len(keywords)
    for idx, kw in enumerate(keywords, start=1):
        try:
            if progress_callback:
                progress_callback(f"[{idx}/{total}] '{kw}' 환율 차트 캡처 시작")
            path, data = capture_exchange_chart_with_data(kw, progress_callback=progress_callback)
            if path:
                images[kw] = path
                if data:
                    datas[kw] = data
                if progress_callback:
                    progress_callback(f"[{idx}/{total}] '{kw}' 캡처 완료: {path}")
            else:
                if progress_callback:
                    progress_callback(f"[{idx}/{total}] '{kw}' 캡처 실패")
        except Exception as e:
            if progress_callback:
                progress_callback(f"[{idx}/{total}] '{kw}' 오류: {e}")
            continue
    if progress_callback:
        progress_callback("모든 환율 차트 캡처 작업이 완료되었습니다.")
    return images, datas