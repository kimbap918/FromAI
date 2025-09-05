# news_LLM.py — 속도·로깅 보강 + Fast-Pass/Trimmed Compare 연동
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
from time import perf_counter
from google.generativeai.types import GenerationConfig


try:
    from news.src.utils.article_utils import extract_article_content, MIN_BODY_LENGTH as AU_MIN, extract_publish_datetime
except Exception:
    extract_article_content = None
    extract_publish_datetime = None
    AU_MIN = 300

try:
    from . import check_LLM
except ImportError:
    import check_LLM

import re
import json

# ======================================================
# 출력 섹션 보정 (LLM 출력이 JSON/코드펜스여도 안전)
# ======================================================
def _truncate(s: str, n: int) -> str:
    """문자열을 최대 n자까지 자르고 깔끔하게 반환."""
    return s if len(s) <= n else s[:n].rstrip()

def _strip_code_fences(s: str) -> str:
    """``` 또는 ```json 코드펜스를 제거해 순수 텍스트로 변환."""
    if not isinstance(s, str):
        return s
    s = s.strip()
    s = re.sub(r"^```(?:json)?\s*\n?", "", s, flags=re.I)
    s = re.sub(r"\n?```$", "", s, flags=re.I)
    return s.strip()

def _json_loads_maybe(s: str):
    """문자열이 JSON이면 파싱해서 dict/리스트 반환, 아니면 None."""
    if not isinstance(s, str):
        return None
    try:
        return json.loads(_strip_code_fences(s))
    except Exception:
        return None

def ensure_output_sections(article_text: str, keyword: str, fallback_title: str) -> str:
    """LLM 출력이 섹션 형식을 지키지 않아도 [제목]/[해시태그]/[본문] 형태로 복구."""
    if not article_text:
        article_text = ""
    text = article_text.strip()

    # JSON 형태 응답일 때도 복구
    obj = _json_loads_maybe(text)
    if isinstance(obj, dict):
        titles, hashtags, body = [], [], ""
        for k in ("titles", "title_list", "title"):
            v = obj.get(k)
            if isinstance(v, list):
                titles = [str(x).strip() for x in v if str(x).strip()]
                break
            if isinstance(v, str) and v.strip():
                titles = [v.strip()]
                break
        for k in ("hashtags", "tags"):
            v = obj.get(k)
            if isinstance(v, list):
                hashtags = [("#" + str(x).strip().lstrip("#").replace(" ", "")) for x in v if str(x).strip()]
                break
            if isinstance(v, str) and v.strip():
                hashtags = [t if t.startswith("#") else "#" + t for t in v.strip().split()]
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
                if len(tags) >= 5: break
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

    body_match = re.search(r"\[본문\]\s*(.*)\Z", text, flags=re.S)
    body = body_match.group(1).strip() if body_match else text
    found_tags = list(dict.fromkeys(re.findall(r"#\S+", text)))[:5]
    base = _truncate(f"{keyword} {fallback_title}".strip(), 35) if fallback_title else _truncate(keyword, 35)
    title1 = base or "제목 제안 1"
    title2 = _truncate(f"{keyword} 핵심 정리", 35) if keyword else "제목 제안 2"
    title3 = _truncate(f"{keyword} 행보 업데이트", 35) if keyword else "제목 제안 3"
    tags = []
    if keyword:
        tags.append("#" + keyword.replace(" ", ""))
    for t in found_tags:
        if t not in tags:
            tags.append(t)
    for extra in ["#뉴스", "#이슈", "#정보"]:
        if len(tags) >= 5: break
        if extra not in tags:
            tags.append(extra)
    if len(tags) < 3:
        tags = (tags + ["#뉴스", "#정보", "#업데이트"])[:3]
    tags = tags[:5]
    rebuilt = []
    rebuilt.append("[제목]"); rebuilt.append(title1); rebuilt.append(title2); rebuilt.append(title3)
    rebuilt.append(""); rebuilt.append("[해시태그]"); rebuilt.append(" ".join(tags))
    rebuilt.append(""); rebuilt.append("[본문]"); rebuilt.append(body.strip())
    return "\n".join(rebuilt).strip()

# ======================================================
# 환경/설정
# ======================================================
def _ensure_env_loaded():
    """다양한 배포 환경에서 .env를 찾고 GOOGLE_API_KEY를 로드."""
    if os.getenv("GOOGLE_API_KEY"): return
    load_dotenv()
    if os.getenv("GOOGLE_API_KEY"): return
    module_dir = os.path.dirname(__file__)
    load_dotenv(os.path.join(module_dir, ".env"))
    if os.getenv("GOOGLE_API_KEY"): return
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        load_dotenv(os.path.join(exe_dir, ".env"))
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        load_dotenv(os.path.join(meipass, ".env"))

_ensure_env_loaded()

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError(".env에서 GOOGLE_API_KEY를 불러오지 못했습니다.")
genai.configure(api_key=api_key)

# ⚠️ 모델 인스턴스는 generate_article 안에서 system_instruction과 함께 생성 (수정사항 ②)
# model = genai.GenerativeModel("gemini-2.5-flash")

FAST_MODE = os.getenv("FAST_MODE", "0") == "1"
LOG_LEVEL = os.getenv("NEWS_LOG_LEVEL", "INFO").upper()

def _safe_keyword(name: str) -> str:
    """파일명 안전화를 위해 키워드에서 특수문자를 제거하고 공백은 언더스코어로 변경."""
    name = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()
    return name.replace(" ", "_") or "log"

def _get_base_dir() -> Path:
    """PyInstaller 실행 파일/일반 실행 구분하여 기준 디렉토리 결정."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path.cwd()

def setup_logging(keyword: str) -> tuple[logging.Logger, str]:
    """키워드 기반 파일 로그 + 콘솔 로그 설정을 생성하고 반환."""
    current_date = datetime.now().strftime("%Y%m%d")
    base_dir = _get_base_dir()
    log_dir = base_dir / "기사 재생성" / f"재생성{current_date}"
    log_dir.mkdir(parents=True, exist_ok=True)

    safe_keyword = _safe_keyword(keyword)
    # Use distinct suffix to avoid collision with finalized article files
    log_filepath = str(log_dir / f"{safe_keyword}_log.txt")

    logger_name = f"news_llm_{safe_keyword}"
    logger = logging.getLogger(logger_name)

    level_map = {"DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARNING": logging.WARNING, "ERROR": logging.ERROR}
    logger.setLevel(level_map.get(LOG_LEVEL, logging.INFO))

    if not logger.handlers:
        fh = logging.FileHandler(log_filepath, encoding="utf-8")
        fh.setLevel(level_map.get(LOG_LEVEL, logging.INFO))
        fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

        ch = logging.StreamHandler()
        ch.setLevel(level_map.get(LOG_LEVEL, logging.INFO))
        ch.setFormatter(logging.Formatter("%(message)s"))

        logger.addHandler(fh)
        logger.addHandler(ch)

    return logger, log_filepath

def log_and_print(logger, message: str, level: str = "info"):
    """logger와 콘솔에 동시에 메시지를 출력."""
    if level == "info":
        logger.info(message)
    elif level == "warning":
        logger.warning(message)
    elif level == "error":
        logger.error(message)
    elif level == "debug":
        logger.debug(message)

# ======================================================
# 기사 추출기
# ======================================================
def extract_title_and_body(url, logger=None):
    """
    newspaper3k로 1차 파싱을 시도하고, 본문이 짧으면 네이버 CP 전용 파서로 폴백.
    네트워크/파싱 예외는 내부에서 처리하여 하위 단계가 계속 진행되도록 보강. (수정사항 ④)
    """
    if logger:
        log_and_print(logger, f"\n  📄 기사 추출 세부 과정:")
        log_and_print(logger, f"    - newspaper 라이브러리로 기사 다운로드 시도...")

    title, body = "", ""

    # 1) newspaper 시도
    try:
        article = Article(url, language='ko')
        article.download()
        article.parse()
        title = (article.title or "").strip()
        body = (article.text or "").strip()
        if logger:
            log_and_print(logger, f"    - 다운로드된 제목: {title}")
            log_and_print(logger, f"    - 다운로드된 본문 길이: {len(body)}자")
    except Exception as e:
        if logger:
            log_and_print(logger, f"    ⚠️ newspaper 처리 실패: {e}", "warning")

    # 2) 본문 길이 미달 → 폴백
    if len(body) < 50:
        if logger:
            log_and_print(logger, f"    ⚠️ 본문이 짧아 fallback으로 전환합니다.", "warning")
            log_and_print(logger, f"    - fallback: extract_naver_cp_article() 호출...")
        try:
            t2, b2 = extract_naver_cp_article(url, logger)
            title = t2 or title or "제목 없음"
            body = b2 or body or ""
            if logger:
                log_and_print(logger, f"    - fallback 결과 제목: {title}")
                log_and_print(logger, f"    - fallback 결과 본문 길이: {len(body)}자")
        except Exception as e:
            if logger:
                log_and_print(logger, f"    ⚠️ fallback 중 예외: {e}", "warning")
    else:
        if logger:
            log_and_print(logger, f"    ✅ 본문 길이 충분 - newspaper 결과 사용")

    return title, body

def extract_naver_cp_article(url, logger=None):
    """
    네이버 뉴스(CP) 구조에 맞춘 간단 파서.
    (5번 항목의 HTTP 상태/예외 확장은 이번 요청에서 제외)
    """
    if logger:
        log_and_print(logger, f"      🔄 네이버 CP 기사 fallback 처리:")
        log_and_print(logger, f"        - requests로 HTML 직접 다운로드...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(url, headers=headers, timeout=7)
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

# ======================================================
# 프롬프트 (변경 금지)
# ======================================================
def generate_system_prompt(keyword: str, today_kst: str, published_kst: str | None = None) -> str:
    """시제 규칙/출력 형식을 포함한 시스템 프롬프트 생성 (내용 변경 금지)."""
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
        - 원문 기사 작성일(사이트 추출): {published_kst or '파악 불가'}

        [시제 변환 규칙]
        - 원문에 포함된 날짜/시간 표현, 원문 기사 작성일과 [오늘(KST) 기준일]을 비교하여 시제 및 날짜 표현을 현재 기사를 작성하는 시점에 맞게 일관되게 조정한다.
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
        - **이 과정에서 원문의 핵심 사실관계(인용문, 발언 대상, 발언 내용, 표현, 날짜, 제공된 주요 수치 등의 핵심 정보)가 누락되지 않도록 각별히 유의할 것. 목표는 사실을 유지한 정보의 손실 없는 압축이다.**
        - **공백 포함 300~900자 내외로 완성** (절대 1000자 초과 금지, 원문이 짧으면 불필요한 내용 추가 금지)
        - 출력 직전에 스스로 글자수를 세고, 900자를 넘으면 문장을 줄여 900자 이내로 조정한다.
        - 핵심 내용을 간결하게 전달 (중복 제거, 장황한 설명 생략)
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
        -**아래 예시 형식을 반드시, 그리고 정확히 준수할것** 
        [제목]
        (여기에 생성한 제목 1)
        (여기에 생성한 제목 2)
        (여기에 생성한 제목 3)

        [해시태그]
        #(해시태그1) #(해시태그2) #(해시태그3) ...

        [본문]
        (공백 포함 300~800자 내외의 본문 내용)"""
    )
    return prompt


def _is_fact_ok_text(verdict: str) -> bool:
    """사실검증 결과 텍스트가 OK인지 판별."""
    return (verdict or "").strip().upper() == "OK"

# Fast-Pass에 필요한 패턴
_NUM_PAT = re.compile(r"(?:\d{4}\.\d{1,2}\.\d{1,2}|\d{4}-\d{1,2}-\d{1,2}|\d{1,2}월\s?\d{1,2}일|\d{4}년|\d{1,3}(?:,\d{3})+|\d+%|\d+명|\d+건|\d+개|\d+원|\d+억|\d+조|\d+회|\d+일|\d+시간|\d+분|\d+초|\d+세|\d+위|\d+점)")
_QUOTE_PAT = re.compile(r"[“”\"']([^“”\"']{2,200})[“”\"']")

def _extract_numbers(text: str) -> set[str]:
    """문서에서 숫자/단위 패턴을 찾아 집합으로 반환."""
    return set(m.group(0) for m in _NUM_PAT.finditer(text or ""))

def _extract_quotes(text: str) -> set[str]:
    """문서에서 인용문(따옴표 내부)을 추출해 집합으로 반환."""
    return set(m.group(1).strip() for m in _QUOTE_PAT.finditer(text or ""))

def _fast_pass_consistency(generated: str, original: str) -> bool:
    """
    Fast-Pass: 생성문이 원문 숫자/인용문을 '초과'로 포함하지 않으면 통과.
    - 생성문에 있는 숫자/인용이 원문 집합의 부분집합이면 True.
    """
    if not generated or not original:
        return False
    gen_nums = _extract_numbers(generated)
    org_nums = _extract_numbers(original)
    if gen_nums and not gen_nums.issubset(org_nums):
        return False
    gen_quotes = _extract_quotes(generated)
    org_quotes = _extract_quotes(original)
    if gen_quotes and not gen_quotes.issubset(org_quotes):
        return False
    return True

def _safe_response_text(resp) -> str:
    """
    Gemini 응답에서 안전하게 텍스트를 꺼낸다. (수정사항 ③)
    - 후보 없음/차단 등으로 .text가 비거나 예외가 날 수 있어 방지.
    """
    try:
        if not getattr(resp, "candidates", None):
            return ""
        # 안전성 차단 여부 (간단 진단용)
        safety = getattr(resp.candidates[0], "safety_ratings", None)
        if safety:
            blocked = any(getattr(r, "blocked", False) for r in safety)
            if blocked:
                return ""
        return getattr(resp, "text", "") or ""
    except Exception:
        return ""

# ======================================================
# 메인
# ======================================================
def generate_article(state: dict) -> dict:
    """
    URL/키워드를 받아:
      1) 기사 추출
      2) 발행일 추출(선행) 및 시스템 프롬프트 구성
      3) Gemini로 기사 재구성
      4) Fast-Pass 또는 check_LLM로 사실검증
      5) 결과/로깅 반환
    """
    url = state.get("url")
    keyword = state.get("keyword")

    t_total_start = perf_counter()  # ⏱ 총 소요시간 측정 시작
    logger, log_filepath = setup_logging(keyword or "로그")

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

        # 1) 기사 추출
        t_extract_start = perf_counter()
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
        if not title or not body:
            log_and_print(logger, "  🔁 내부 추출기로 폴백")
            t3, b3 = extract_title_and_body(url, logger)
            if len((b3 or "")) > len(body or ""):
                title, body = t3, b3
        if not body:
            raise ValueError("본문 추출 실패: 본문이 비어 있습니다.")
        t_extract = perf_counter() - t_extract_start
        log_and_print(logger, f"⏱ 기사 추출 단계 소요: {t_extract:.2f}s")

        # 1.5) 🆕 발행일 추출 —— 생성 전에 수행 (수정사항 ①)
        today_kst = get_today_kst_str()
        published_kst = None
        if extract_publish_datetime is not None:
            try:
                published_kst = extract_publish_datetime(url)
                if published_kst:
                    log_and_print(logger, f"🗓️ 발행일 추출 성공: {published_kst}")
                else:
                    log_and_print(logger, "🗓️ 발행일 추출 실패 또는 미제공")
            except Exception as e:
                log_and_print(logger, f"🗓️ 발행일 추출 중 오류: {e}", "warning")

        # 2) 시스템 프롬프트 생성 + 모델 구성 (system_instruction 사용 / 수정사항 ②)
        system_prompt = generate_system_prompt(keyword or "", today_kst, published_kst)
        user_request = f"키워드: {keyword}\n제목: {title}\n본문: {body}"

        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=system_prompt
            # generation_config=GenerationConfig(
            #     max_output_tokens=
            # )
        )

        # 3) 생성 호출
        t_gen_start = perf_counter()
        log_and_print(logger, f"\n⏳ Gemini AI 호출 중... 모델: gemini-2.5-flash")
        # user 입력만 전달

        response = model.generate_content(user_request)

        # 토큰 계산
        usage = getattr(response, "usage_metadata", None)
        if usage:
            p = getattr(usage, "prompt_token_count", 0)
            c = getattr(usage, "candidates_token_count", 0)
            t = getattr(usage, "total_token_count", 0)
            th = getattr(usage, "thoughts_token_count", 0)  # ✅ 사고 토큰
            tu = getattr(usage, "tool_use_prompt_token_count", 0)
            cc = getattr(usage, "cached_content_token_count", 0)
            resid = t - (p + c + th + tu)  # 남는다면 API/버전별 집계 차이
            log_and_print(logger,
                f"🧾 토큰 상세 | 입력={p}, 출력={c}, 생각={th}, 툴프롬프트={tu}, 캐시={cc}, 합계={t}, 잔차={resid}")
        else:
            log_and_print(logger, "🧾 usage_metadata 없음", "warning")

        t_gen = perf_counter() - t_gen_start
        log_and_print(logger, f"⏱ 기사 생성 소요: {t_gen:.2f}s")

        # 응답 안전 추출 (수정사항 ③)
        article_text = _safe_response_text(response).strip()
        if not article_text:
            log_and_print(logger, "⚠️ LLM 응답이 비어 있음(차단/빈 후보 가능성).", "warning")

        # 섹션 강제 보정
        article_text = ensure_output_sections(article_text, keyword or "", title)
        log_and_print(logger, f"\n📊 기사 길이 비교: 원본 {len(body)}자 → 재구성 {len(article_text)}자")

        # 4) 사실검증(Fast-Pass 우선)
        if FAST_MODE and _fast_pass_consistency(article_text, body):
            # (수정사항 ⑧) Fast-Pass 내부 진단 로그 강화
            log_and_print(
                logger,
                f"⚡ FAST-PASS 통과 → nums={_extract_numbers(article_text)} quotes={_extract_quotes(article_text)}"
            )
            verdict = "OK"
            corrected_article = ""
            display_text = article_text
            display_kind = "article"
        else:
            t_fc_start = perf_counter()
            log_and_print(logger, f"\n🔍 사실관계 검증 단계: check_LLM.check_article_facts 호출")
            check_res = check_LLM.check_article_facts(
                article_text,
                body,
                (keyword or "check_LLM"),
                source_url=url,                  # 원문 링크 전달 (로깅/추적용)
                published_kst=published_kst,     # 시제 참고용
            )
            t_factcheck = perf_counter() - t_fc_start
            log_and_print(logger, f"⏱ 사실검증 소요: {t_factcheck:.2f}s")

            verdict = ""
            corrected_article = ""
            explanation = ""
            if isinstance(check_res, dict):
                json_obj = check_res.get("json")
                explanation = check_res.get("explanation", "")
                if json_obj:
                    if isinstance(json_obj, str):
                        try:
                            parsed = json.loads(json_obj)
                        except Exception:
                            parsed = None
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

            if _is_fact_ok_text(verdict):
                display_text = article_text
                display_kind = "article"
                log_and_print(logger, "  ✅ 사실관계 이상 없음 → 기사 채택")
            else:
                if verdict == "ERROR" and corrected_article:
                    display_text = corrected_article
                    display_kind = "article"
                    log_and_print(logger, "  ✏️ 오류 발견 + 교정본 제공 → 교정 기사 채택")
                else:
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
            "corrected_article": corrected_article if not FAST_MODE else "",
            "display_text": display_text,
            "display_kind": display_kind,
            "error": None
        }

        log_and_print(logger, f"\n📋 display_kind: {display_kind}")
        t_total = perf_counter() - t_total_start
        log_and_print(logger, f"⏱ 총 처리 시간: {t_total:.2f}s")
        log_and_print(logger, "\n" + "="*80)
        log_and_print(logger, "📰 NEWS_LLM - 기사 재구성 완료")
        log_and_print(logger, "="*80)

        # Windows에서 로그 파일 자동 오픈은 사용하지 않음 (기사 파일과 혼동 방지)
        # if os.name == 'nt' and 'log_filepath' in locals() and os.path.exists(log_filepath):
        #     try:
        #         os.startfile(log_filepath)
        #         log_and_print(logger, f"\n📂 생성된 파일을 엽니다: {log_filepath}")
        #     except Exception as e:
        #         log_and_print(logger, f"\n⚠️ 파일을 여는 중 오류가 발생했습니다: {e}", "warning")

        return result

    except Exception as e:
        try:
            log_and_print(logger, f"\n❌ 예외 발생: {str(e)}", "error")
            t_total = perf_counter() - t_total_start
            log_and_print(logger, f"⏱ 총 처리 시간(예외 발생): {t_total:.2f}s", "error")
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
