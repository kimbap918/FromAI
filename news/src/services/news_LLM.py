# news_LLM.py — JSON 검증 연동 + verdict 안정 처리 버전
import os
import sys
import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
from newspaper import Article
from dotenv import load_dotenv
from datetime import datetime
import logging
from pathlib import Path
from news.src.utils.common_utils import get_today_kst_str

try:
    from news.src.utils.article_utils import extract_article_content, MIN_BODY_LENGTH as AU_MIN
except Exception:
    extract_article_content = None
    AU_MIN = 300

try:
    from . import check_LLM
except ImportError:
    import check_LLM

# ---------------------------
# 🔒 형식 고정(양식 보정) 유틸
# ---------------------------
import re
import json  # ✅ 추가: JSON 보정을 위한 임포트

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 기능 : 문자열을 지정된 길이로 자르는 유틸리티 함수
# ------------------------------------------------------------------
def _truncate(s: str, n: int) -> str:
    """
    문자열 s를 최대 n자까지 자름
    :param s: 원본 문자열
    :param n: 최대 길이
    :return: 잘린 문자열
    """
    return s if len(s) <= n else s[:n].rstrip()

# ✅ 추가: 코드펜스 제거 & 안전 JSON 파싱 유틸
def _strip_code_fences(s: str) -> str:
    """ ``` 또는 ```json 로 감싼 텍스트의 펜스를 제거 """
    if not isinstance(s, str):
        return s
    s = s.strip()
    s = re.sub(r"^```(?:json)?\s*\n?", "", s, flags=re.I)
    s = re.sub(r"\n?```$", "", s, flags=re.I)
    return s.strip()

def _json_loads_maybe(s: str):
    """ 문자열 s를 JSON으로 파싱 시도. 실패 시 None """
    if not isinstance(s, str):
        return None
    try:
        return json.loads(_strip_code_fences(s))
    except Exception:
        return None

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-08-26
# 기능 : LLM 출력 결과에서 [제목], [해시태그], [본문] 3개 섹션을 보장
# ------------------------------------------------------------------
def ensure_output_sections(article_text: str, keyword: str, fallback_title: str) -> str:
    """
    LLM이 생성한 텍스트에 필수 섹션이 누락된 경우, 이를 보완하여 완전한 형식의 텍스트를 반환
    :param article_text: LLM이 생성한 원본 텍스트
    :param keyword: 기사 생성 시 사용된 키워드
    :param fallback_title: 제목 생성 실패 시 사용할 기본 제목
    :return: 형식이 보정된 기사 텍스트
    """
    if not article_text:
        article_text = ""

    text = article_text.strip()

    # ✅ 추가: JSON/코드펜스 응답을 감지해 섹션 재구성
    obj = _json_loads_maybe(text)
    if isinstance(obj, dict):
        titles, hashtags, body = [], [], ""

        # 제목 추출
        for k in ("titles", "title_list", "title"):
            v = obj.get(k)
            if isinstance(v, list):
                titles = [str(x).strip() for x in v if str(x).strip()]
                break
            if isinstance(v, str) and v.strip():
                titles = [v.strip()]
                break

        # 해시태그 추출
        for k in ("hashtags", "tags"):
            v = obj.get(k)
            if isinstance(v, list):
                hashtags = [("#" + str(x).strip().lstrip("#").replace(" ", "")) for x in v if str(x).strip()]
                break
            if isinstance(v, str) and v.strip():
                hashtags = [t if t.startswith("#") else "#" + t for t in v.strip().split()]

        # 본문 추출
        for k in ("body", "content", "article", "text"):
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                body = v.strip()
                break

        if titles or hashtags or body:
            base = _truncate(f"{keyword} {fallback_title}".strip(), 35) if fallback_title else _truncate(keyword, 35)
            t1 = titles[0] if len(titles) >= 1 else (base or "제목 제안 1")
            t2 = titles[1] if len(titles) >= 2 else (_truncate(f"{keyword} 핵심 정리", 35) if keyword else "제목 제안 2")
            t3 = titles[2] if len(titles) >= 3 else (_truncate(f"{keyword} 행보 업데이트", 35) if keyword else "제목 제안 3")

            tags = []
            if keyword:
                tags.append("#" + keyword.replace(" ", ""))
            for t in hashtags:
                if t not in tags:
                    tags.append(t)
            for extra in ["#뉴스", "#이슈", "#정보"]:
                if len(tags) >= 5:
                    break
                if extra not in tags:
                    tags.append(extra)
            if len(tags) < 3:
                tags = (tags + ["#뉴스", "#정보", "#업데이트"])[:3]
            tags = tags[:5]

            return "[제목]\n{}\n{}\n{}\n\n[해시태그]\n{}\n\n[본문]\n{}".format(
                _truncate(t1, 35), _truncate(t2, 35), _truncate(t3, 35),
                " ".join(tags),
                (body or "").strip()
            )

    has_title = "[제목]" in text
    has_tags  = "[해시태그]" in text
    has_body  = "[본문]" in text

    if has_title and has_tags and has_body:
        return text

    # 본문 후보 추출
    body_match = re.search(r"\[본문\]\s*(.*)\Z", text, flags=re.S)
    if body_match:
        body = body_match.group(1).strip()
    else:
        body = text

    # 해시태그 후보 추출
    found_tags = list(dict.fromkeys(re.findall(r"#\S+", text)))[:5]

    # 안전한 기본 제목 3개 구성
    base = _truncate(f"{keyword} {fallback_title}".strip(), 35) if fallback_title else _truncate(keyword, 35)
    title1 = base or "제목 제안 1"
    title2 = _truncate(f"{keyword} 핵심 정리", 35) if keyword else "제목 제안 2"
    title3 = _truncate(f"{keyword} 행보 업데이트", 35) if keyword else "제목 제안 3"

    # 해시태그 구성
    tags = []
    if keyword:
        tags.append("#" + keyword.replace(" ", ""))
    for t in found_tags:
        if t not in tags:
            tags.append(t)
    for extra in ["#뉴스", "#이슈", "#정보"]:
        if len(tags) >= 5:
            break
        if extra not in tags:
            tags.append(extra)
    if len(tags) < 3:
        tags = (tags + ["#뉴스", "#정보", "#업데이트"])[:3]
    tags = tags[:5]

    rebuilt = []
    rebuilt.append("[제목]")
    rebuilt.append(title1)
    rebuilt.append(title2)
    rebuilt.append(title3)
    rebuilt.append("")
    rebuilt.append("[해시태그]")
    rebuilt.append(" ".join(tags))
    rebuilt.append("")
    rebuilt.append("[본문]")
    rebuilt.append(body.strip())

    return "\n".join(rebuilt).strip()


# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-08-26
# 기능 : 다양한 실행 환경(.py, PyInstaller)에서 .env 파일 로드
# ------------------------------------------------------------------
def _ensure_env_loaded():
    """
    GOOGLE_API_KEY 환경 변수가 로드되었는지 확인하고, 로드되지 않았다면 여러 예상 경로에서 .env 파일을 찾아 로드
    """
    if os.getenv("GOOGLE_API_KEY"):
        return
    # 1) 기본 현재 경로 시도
    load_dotenv()
    if os.getenv("GOOGLE_API_KEY"):
        return
    # 2) 모듈 파일 경로 시도
    module_dir = os.path.dirname(__file__)
    load_dotenv(os.path.join(module_dir, ".env"))
    if os.getenv("GOOGLE_API_KEY"):
        return
    # 3) PyInstaller 실행파일 경로 시도
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        load_dotenv(os.path.join(exe_dir, ".env"))
        if os.getenv("GOOGLE_API_KEY"):
            return
    # 4) PyInstaller 임시 해제 경로(_MEIPASS) 시도
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        load_dotenv(os.path.join(meipass, ".env"))


_ensure_env_loaded()

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError(".env에서 GOOGLE_API_KEY를 불러오지 못했습니다.")
genai.configure(api_key=api_key)

model = genai.GenerativeModel("gemini-2.5-flash")

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 기능 : 파일명으로 사용하기 안전한 문자열로 키워드를 변환
# ------------------------------------------------------------------
def _safe_keyword(name: str) -> str:
    """
    문자열에서 알파벳, 숫자, 공백, 하이픈, 언더스코어만 남기고 공백을 언더스코어로 변경
    :param name: 원본 문자열
    :return: 파일명으로 사용 가능한 문자열
    """
    name = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()
    return name.replace(" ", "_") or "log"

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 기능 : 프로그램의 기본 실행 디렉토리 경로 획득
# ------------------------------------------------------------------
def _get_base_dir() -> Path:
    """
    개발 환경과 PyInstaller 빌드 환경을 구분하여 로그 파일 등을 저장할 기본 경로를 반환
    :return: 기본 디렉토리의 Path 객체
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path.cwd()


# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-08-25
# 기능 : 기사 재구성 과정을 기록할 로거(Logger) 설정
# ------------------------------------------------------------------
def setup_logging(keyword: str) -> tuple[logging.Logger, str]:
    """
    실행 위치에 '기사 재생성/재생성YYYYMMDD' 폴더를 만들고, 키워드를 파일명으로 하는 로그 파일을 생성 및 설정
    :param keyword: 로그 파일명으로 사용할 키워드
    :return: 설정된 로거 객체와 로그 파일 경로
    """

    current_date = datetime.now().strftime("%Y%m%d")
    base_dir = _get_base_dir()
    log_dir = base_dir / "기사 재생성" / f"재생성{current_date}"
    log_dir.mkdir(parents=True, exist_ok=True)

    safe_keyword = _safe_keyword(keyword)
    log_filepath = str(log_dir / f"{safe_keyword}.txt")

    logger_name = f"news_llm_{safe_keyword}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)

    # 중복 핸들러 방지
    if not logger.handlers:
        fh = logging.FileHandler(log_filepath, encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter("%(message)s"))

        logger.addHandler(fh)
        logger.addHandler(ch)

    return logger, log_filepath

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 기능 : 메시지를 로거와 콘솔에 동시 출력
# ------------------------------------------------------------------
def log_and_print(logger, message: str, level: str = "info"):
    """
    주어진 메시지를 지정된 로그 레벨로 파일과 콘솔에 기록
    :param logger: 사용할 로거 객체
    :param message: 기록할 메시지
    :param level: 로그 레벨 ('info', 'warning', 'error', 'debug')
    """
    if level == "info":
        logger.info(message)
    elif level == "warning":
        logger.warning(message)
    elif level == "error":
        logger.error(message)
    elif level == "debug":
        logger.debug(message)

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-08-25
# 기능 : newspaper 라이브러리를 이용한 기사 제목 및 본문 추출
# ------------------------------------------------------------------
def extract_title_and_body(url, logger=None):
    """
    주어진 URL에서 기사 제목과 본문을 추출, 추출된 본문이 짧을 경우 fallback 함수(extract_naver_cp_article) 호출
    :param url: 기사 URL
    :param logger: 로깅을 위한 로거 객체 (선택 사항)
    :return: 추출된 제목과 본문 튜플
    """
    if logger:
        log_and_print(logger, f"\n  📄 기사 추출 세부 과정:")
        log_and_print(logger, f"    - newspaper 라이브러리로 기사 다운로드 시도...")

    article = Article(url, language='ko')
    article.download()
    article.parse()
    title = (article.title or "").strip()
    body = (article.text or "").strip()

    if logger:
        log_and_print(logger, f"    - 다운로드된 제목: {title}")
        log_and_print(logger, f"    - 다운로드된 본문 길이: {len(body)}자")

    if len(body) < 50:
        if logger:
            log_and_print(logger, f"    ⚠️ 본문이 짧아 fallback으로 전환합니다.", "warning")
            log_and_print(logger, f"    - fallback: extract_naver_cp_article() 호출...")
        title, body = extract_naver_cp_article(url, logger)
        if logger:
            log_and_print(logger, f"    - fallback 결과 제목: {title}")
            log_and_print(logger, f"    - fallback 결과 본문 길이: {len(body)}자")
    else:
        if logger:
            log_and_print(logger, f"    ✅ 본문 길이 충분 - newspaper 결과 사용")

    return title, body


# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-08-25
# 기능 : 네이버 CP 기사 형식에 특화된 간이 HTML 파서
# ------------------------------------------------------------------
def extract_naver_cp_article(url, logger=None):
    """
    requests와 BeautifulSoup을 사용하여 네이버 뉴스 페이지에서 제목과 본문을 직접 추출 (fallback용)
    :param url: 네이버 뉴스 기사 URL
    :param logger: 로깅을 위한 로거 객체 (선택 사항)
    :return: 추출된 제목과 본문 튜플
    """
    if logger:
        log_and_print(logger, f"      🔄 네이버 CP 기사 fallback 처리:")
        log_and_print(logger, f"        - requests로 HTML 직접 다운로드...")

    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, 'html.parser')

    if logger:
        log_and_print(logger, f"        - HTML 다운로드 완료: {len(res.text)}자")

    title_tag = soup.select_one('h2.media_end_head_headline')
    title = title_tag.text.strip() if title_tag else "제목 없음"

    if logger:
        log_and_print(logger, f"        - 제목 태그 검색 결과: {'찾음' if title_tag else '찾지 못함'}")
        log_and_print(logger, f"        - 추출된 제목: {title}")

    body_area = soup.select_one('article#dic_area')
    body = body_area.get_text(separator="\n").strip() if body_area else "본문 없음"

    if logger:
        log_and_print(logger, f"        - 본문 영역 검색 결과: {'찾음' if body_area else '찾지 못함'}")
        log_and_print(logger, f"        - 추출된 본문 길이: {len(body)}자")

    return title, body


# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-08-11
# 기능 : 기사 생성을 위한 시스템 프롬프트 생성
# ------------------------------------------------------------------
def generate_system_prompt(keyword: str, today_kst: str) -> str:
    """
    Gemini 모델에 전달할 시스템 프롬프트를 생성. 역할, 목표, 규칙, 출력 형식 등을 정의
    :param keyword: 기사 생성에 사용할 키워드
    :param today_kst: 오늘 날짜(KST) 문자열
    :return: 완성된 시스템 프롬프트 문자열
    """
    prompt = (
        f"""
        [System message]
        - 키워드, 기사 제목,  본문 순으로 사용자가 입력한다.
        - **최종 출력은 [제목], [해시태그], [본문]의 세 섹션으로 명확히 구분하여 반드시 작성할 것.** [Role]
        - 당신은 제공된 기사 제목과 본문을 바탕으로 사실을 유지하며 재구성하는 전문 기자이자 에디터이다.
        - 최우선 목표는 사실 왜곡 없이 가독성과 논리 전개를 개선하고, 오늘(KST) 기준으로 시제를 일관되게 맞추는 것이다.
        - 본문 작성 전 1) [오늘(KST) 기준일] 2) [시제 변환 규칙], 3) [News Generation Process], 4) [출력 형식]을 반드시 확인하고 준수한다.
        - 추측/전망성 표현은 사용하지 않는다. 문체는 일관된 기사 문체(~이다/~했다)로 작성하며 Markdown 문법은 사용하지 않는다.

        [오늘(KST) 기준일]
        - 오늘 날짜(Asia/Seoul): {today_kst}

        [시제 변환 규칙]
        - 원문에 포함된 날짜/시간 표현과 [오늘(KST) 기준일]을 비교하여 시제를 일관되게 조정한다.
        - 날짜가 이미 지난 시점 혹은 이미 발생한 사실은 과거 시제(…했다/…이었다), 진행 중인 사실은 현재 시제(…한다), 예정된 사실은 미래 지향 서술(…할 예정이다/…로 예정돼 있다)로 기술한다.
        - 추측성 표현(…할 것으로 보인다, …전망이다)은 사용하지 않는다.
        - 날짜를 노출할 필요가 없으면 직접적인 날짜 표기는 피하고, '당시', '이후', '이전', '같은 날'과 같은 상대적 시간 표현을 사용한다.
        - 인용문 내의 날짜를 제외하고 날짜가 주어지는 경우 시제를 아래 규칙과 같이 변경한다.
        - [오늘(KST) 기준일]을 기준으로 동일 일의 경우 "O일"로 표기한다. "O월 O일", "오늘 OO일", "오늘(OO일)" 등의 표현 금지.
        - [오늘(KST) 기준일]을 기준으로 동일 월의 과거인 경우 "O월 O일, O일 -> 지난 O일", 동일 월의 미래인 경우 "O월 O일, O일 -> 오는 O일"로 표기한다.
        - [오늘(KST) 기준일]을 기준으로 직전 월인 과거인 경우(예: [오늘(KST) 기준일]이 2025년 9월 1일인 경우, 2025년 8월 20일 -> 지난달 20일) "O월 O일, O일 -> 지난달 O일"로 표기한다.
        - [오늘(KST) 기준일]을 기준으로 년도가 주어진 과거인 경우 "OOOO년 O월 O일, "OOOO년" -> 지난 OOOO년, "지난 OOOO년 O월 O일"으로 표기한다.
        - [오늘(KST) 기준일]을 기준으로 년도가 주어진 미래인 경우 "OOOO년 O월 O일, "OOOO년" -> 오는 OOOO년, "오는 OOOO년 O월 O일"으로 표기한다.

        [News Generation Process]
        1. 제목 생성 
        - 우선순위: **1. 입력된 키워드를 포함하고, 2. 제공된 기사 제목을 인용하고, 3. 본문의 핵심 내용을 반영하여 3개의 창의적이고 다양한 제목을 생성한다.**
        - **키워드는 최대한 앞쪽에 배치하고, 관련성이 적어도 자연스럽게 포함하도록 작성한다.**.
        - 제목 유형은 다음과 같이 다양성을 확보한다:
        * 1번 제목: 핵심 사실을 간결하게 전달하는 전통적 뉴스 제목
        * 2번 제목: 독자의 관심을 끌 수 있는 창의적인 제목
        * 3번 제목: 기사 내용의 핵심 가치나 영향력을 강조하는 제목
        - 25~40자 내외로 간결하고 강렬한 인상을 주도록 작성한다.
        - 문장 부호는 최소화하고, 필요한 경우에만 쉼표(,)를 사용한다.
        - 궁금증을 유발하는 표현 금지 (예: '?', '왜', '어떻게', '무엇이' 등 사용 금지)
        - 사용 금지 기호: 마침표(.), 콜론(:), 마크다운 기호(*, #, &), Markdown 문법
        - 사용 가능 기호: 쉼표(,), 따옴표(' '), 쌍따옴표(" ") 

        2. 본문 생성: 입력된 기사 본문을 바탕으로 핵심 내용을 담은 간결한 기사를 작성한다.
        -  **문장을 단순히 줄이는 것을 넘어, 원문의 여러 문장에 흩어져 있는 관련 정보를 하나의 문장으로 통합하고 압축하여 전체적인 글의 밀도를 높일 것. 단, 인용문은 원문 그대로 유지한다.**
        -  **이 과정에서 원문의 핵심 사실관계(인용문, 발언 대상, 발언 내용, 표현, 날짜, 제공된 주요 정보)가 누락되지 않도록 각별히 유의할 것. 목표는 사실을 유지한 정보의 손실 없는 압축이다.**
        - **공백 포함 300~700자 내외로 완성** (절대 800자 초과 금지, 원문이 짧으면 불필요한 내용 추가 금지)
        - 출력 직전에 스스로 글자수를 세고, 800자를 넘으면 문장을 줄여 800자 이내로 조정한다.
        - 핵심 내용만 간결하게 전달 (중복 제거, 장황한 설명 생략)
        - **원문의 주요 사실은 모두 포함하되, 표현 방식은 완전히 변경**
        - 문장은 짧고 명확하게 (한 문장당 15~20자 내외 권장)
        - **인용문은 원문 그대로 유지 (단어 하나도 변경 금지)**
        - 비격식체를 (예: "~이다", "~했다", "~한다")를 일관되게 사용, **서술식("~습니다", "~입니다")표현은 절대 사용하지 않는다.**
        - 맞춤법 정확히 준수
        - '...', '~~', '!!' 등 불필요한 기호 사용 금지

        3. 제목 및 본문 검토 
        - 제목과 본문에서 **금지된 기호(…, *, #, &) 사용 여부 확인 및 수정
        - 입력된 기사 본문에서 제공된 정보 외 추측·허구·외부 자료 추가 여부 검토 후 수정


        4. 키워드 생성
        - 생성된 본문을 기반으로 5개 내외의 핵심 키워드를 추출한다.

        5. 출력형식에 맞게 출력한다.  

        [출력 형식]  

        - 제목 (3개 제공, 각 제목 당 최대 35자 내외)
        - 해시태그 (5개 내외)
        - 본문 내용
        -**아래 예시 형식을 반드시, 그리고 정확히 준수할것** [제목]
        (여기에 생성한 제목 1)
        (여기에 생성한 제목 2)
        (여기에 생성한 제목 3)

        [해시태그]
        #(해시태그1) #(해시태그2) #(해시태그3) ...

        [본문]
        (공백 포함 300~800자 내외의 본문 내용)"""
    )
    return prompt

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 기능 : 사실관계 검증 결과(verdict)가 'OK'인지 판별
# ------------------------------------------------------------------
def _is_fact_ok_text(verdict: str) -> bool:
    """
    check_LLM 모듈의 JSON 응답에서 'verdict' 필드 값을 확인하여 사실관계에 문제가 없는지(OK) 여부를 반환
    :param verdict: 검증 결과 문자열 ('OK', 'ERROR' 등)
    :return: 'OK'일 경우 True, 아닐 경우 False
    """
    return (verdict or "").strip().upper() == "OK"


# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-08-25
# 기능 : URL과 키워드를 입력받아 기사를 재구성하는 메인 로직
# ------------------------------------------------------------------
def generate_article(state: dict) -> dict:
    """
    기사 추출, LLM을 통한 재구성, 사실관계 검증의 전체 파이프라인을 실행
    :param state: 'url', 'keyword', 'title', 'body' 등을 포함하는 딕셔너리
    :return: 처리 결과를 담은 딕셔너리. 최종적으로 표시될 텍스트와 상태 정보를 포함.
    """
    url = state.get("url")
    keyword = state.get("keyword")

    # 로거 준비
    logger, log_filepath = setup_logging(keyword or "로그")

    # 외부에서 전달된 제목/본문(예: news_tab_test에서 추출) 우선 사용
    title = (state.get("title") or "").strip()
    body = (state.get("body") or "").strip()

    try:
        log_and_print(logger, "\n" + "="*80)
        log_and_print(logger, "📰 NEWS_LLM - 기사 재구성 시작")
        log_and_print(logger, "="*80)
        log_and_print(logger, f"\n📥 입력 데이터:")
        log_and_print(logger, f"  - URL: {url}")
        log_and_print(logger, f"  - 키워드: {keyword}")
        log_and_print(logger, f"  - 로그 파일: {log_filepath}")

        # 1) state에 충분한 본문이 없으면, article_utils로 견고 추출 시도
        if (not title or not body) or (len(body) < AU_MIN):
            log_and_print(logger, "\n🔗 기사 추출 단계: 외부 추출 미흡 → article_utils 시도")
            if extract_article_content is not None:
                try:
                    t2, b2 = extract_article_content(url, progress_callback=None)
                    if len(b2 or "") >= AU_MIN:
                        title, body = t2, b2
                        log_and_print(logger, f"  ✅ article_utils 성공: 본문 {len(body)}자")
                except Exception as e:
                    log_and_print(logger, f"  ⚠️ article_utils 실패: {e}", "warning")

        # 2) 그래도 부족하면, 내부 간이 추출기 사용
        if not title or not body:
            log_and_print(logger, "  🔁 내부 추출기로 폴백")
            t3, b3 = extract_title_and_body(url, logger)
            if len((b3 or "")) > len(body or ""):
                title, body = t3, b3

        if not body:
            raise ValueError("본문 추출 실패: 본문이 비어 있습니다.")

        # 프롬프트 준비
        today_kst = get_today_kst_str()
        system_prompt = generate_system_prompt(keyword or "", today_kst)
        user_request = f"키워드: {keyword}\n제목: {title}\n본문: {body}"

        # 로그: 원문 요약
        log_and_print(logger, f"\n📋 전체 원본 기사:")
        log_and_print(logger, f"{'='*80}")
        log_and_print(logger, f"제목: {title}")
        log_and_print(logger, f"{'='*40}")
        log_and_print(logger, body if len(body) <= 2000 else (body[:2000] + "\n...[생략]"))
        log_and_print(logger, f"{'='*80}")

        contents = [
            {'role': 'user', 'parts': [{'text': system_prompt}]},
            {'role': 'model', 'parts': [{'text': '이해했습니다. 규칙을 따르겠습니다.'}]},
            {'role': 'user', 'parts': [{'text': user_request}]}
        ]

        log_and_print(logger, f"\n⏳ Gemini AI 호출 중... 모델: gemini-2.5-flash")

        response = model.generate_content(contents)
        article_text = (getattr(response, "text", "") or "").strip()

        log_and_print(logger, f"\n📤 AI 응답 길이: {len(article_text)}자")

        # 🔒 LLM 응답 형식 보정
        article_text = ensure_output_sections(article_text, keyword or "", title)

        log_and_print(logger, f"\n📊 기사 길이 비교: 원본 {len(body)}자 → 재구성 {len(article_text)}자")

        # 사실관계 검증 (check_LLM는 (generated, original, [keyword]) 3인자 시그니처 허용)
        log_and_print(logger, f"\n🔍 사실관계 검증 단계: check_LLM.check_article_facts 호출")
        check_res = check_LLM.check_article_facts(article_text, body, (keyword or "check_LLM"))

        verdict = ""
        corrected_article = ""
        explanation = ""

        if isinstance(check_res, dict):
            json_obj = check_res.get("json")
            explanation = check_res.get("explanation", "")
            if json_obj:
                # ✅ 보강: 문자열/코드펜스 JSON도 안전 파싱
                if isinstance(json_obj, str):
                    parsed = _json_loads_maybe(json_obj)
                    if isinstance(parsed, dict):
                        verdict_val = parsed.get("verdict", "")
                        corrected_article_val = parsed.get("corrected_article", "")
                    else:
                        verdict_val = ""
                        corrected_article_val = ""
                else:
                    verdict_val = json_obj.get("verdict", "")
                    corrected_article_val = json_obj.get("corrected_article", "")
                verdict = str(verdict_val or "").strip().upper()
                corrected_article = str(corrected_article_val or "").strip()

        # 결과 분기
        if _is_fact_ok_text(verdict):
            display_text = article_text
            display_kind = "article"
            log_and_print(logger, "  ✅ 사실관계 이상 없음 → 기사 채택")
        else:
            if verdict == "ERROR" and corrected_article:
                # 교정 기사가 도착한 경우, 교정본을 바로 채택
                display_text = corrected_article
                display_kind = "article"
                log_and_print(logger, "  ✏️ 오류 발견 + 교정본 제공 → 교정 기사 채택")
            else:
                # 교정본이 없으면 경고 및 설명 출력
                warn = "[사실검증]\n검증 경고 또는 파싱 실패\n\n" + (explanation or "검증에 실패했습니다.")
                display_text = warn
                display_kind = "fact_check"
                log_and_print(logger, "  ⚠️ 사실관계 이슈 또는 검증 실패 → fact_check 표출")

        result = {
            "url": url,
            "keyword": keyword,
            "title": title,
            "original_body": body,
            "generated_article": article_text,
            "fact_check_result": verdict or "UNKNOWN",
            "corrected_article": corrected_article,
            "display_text": display_text,
            "display_kind": display_kind,
            "error": None
        }

        log_and_print(logger, f"\n📋 display_kind: {display_kind}")
        log_and_print(logger, "\n" + "="*80)
        log_and_print(logger, "📰 NEWS_LLM - 기사 재구성 완료")
        log_and_print(logger, "="*80)
        
        # 생성된 파일 자동으로 열기 (Windows에서만 동작) – 현재는 로그 파일만 자동 오픈
        if os.name == 'nt' and 'log_filepath' in locals() and os.path.exists(log_filepath):
            try:
                os.startfile(log_filepath)
                log_and_print(logger, f"\n📂 생성된 파일을 엽니다: {log_filepath}")
            except Exception as e:
                log_and_print(logger, f"\n⚠️ 파일을 여는 중 오류가 발생했습니다: {e}", "warning")

        return result

    except Exception as e:
        # 안전 처리: logger가 없을 가능성도 대비
        try:
            log_and_print(logger, f"\n❌ 예외 발생: {str(e)}", "error")
            log_and_print(logger, "\n" + "="*80, "error")
            log_and_print(logger, "📰 NEWS_LLM - 기사 재구성 실패", "error")
            log_and_print(logger, "="*80, "error")
        except Exception:
            pass

        return {
            "url": state.get("url"),
            "keyword": state.get("keyword"),
            "title": state.get("title") or "",
            "original_body": state.get("body") or "",
            "generated_article": "",
            "fact_check_result": "",
            "display_text": f"오류: {str(e)}",
            "display_kind": "error",
            "error": str(e)
        }


if __name__ == "__main__":
    print("🔗 기사 URL과 키워드를 입력하면 Gemini가 재작성한 기사로 변환해줍니다.")
    url = input("기사 URL을 입력하세요: ").strip()
    keyword = input("핵심 키워드를 입력하세요: ").strip()

    print(f"\n📝 키워드: {keyword}")
    print(f"🔗 URL: {url}")
    print("="*50)
    print("처리 과정이 시작됩니다. 모든 과정은 로그 파일에 저장됩니다.")
    print("="*50)

    result = generate_article({"url": url, "keyword": keyword})

    if result["error"]:
        print("❌ 오류 발생:", result["error"])
    else:
        print("\n✅ 결과:\n")
        print(result["display_text"])
        print(f"\n📁 로그 파일이 저장되었습니다.")
        print(f"   파일명: {keyword}.txt")
