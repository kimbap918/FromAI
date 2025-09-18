import os
import sys
import json
import re
import time  
import google.generativeai as genai
from news.src.utils.common_utils import get_today_kst_str
from dotenv import load_dotenv
from datetime import datetime
from pathlib import Path
import logging

try:
    from news.src.utils.article_utils import extract_publish_datetime
except Exception:
    extract_publish_datetime = None
# ------------------------------------------------------------------
# 작성자 : 최준혁
# 기능 : 다양한 실행 환경(.py, PyInstaller)에서 .env 파일 로드
# ------------------------------------------------------------------
def _ensure_env_loaded():
    """
    GOOGLE_API_KEY 환경 변수가 로드되었는지 확인하고, 로드되지 않았다면 여러 예상 경로에서 .env 파일을 찾아 로드
    """
    if os.getenv("GOOGLE_API_KEY"):
        return
    
    if getattr(sys, "frozen", False):
        search_paths = [
            os.path.dirname(sys.executable),
            os.path.join(os.path.expanduser("~"), "Desktop"),
            os.path.join(os.getenv("APPDATA", ""), "NewsGenerator"),
            os.getcwd(),
        ]
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            search_paths.insert(0, meipass)
        for path in search_paths:
            if path and os.path.exists(path):
                env_path = os.path.join(path, ".env")
                if os.path.exists(env_path):
                    load_dotenv(env_path)
                    if os.getenv("GOOGLE_API_KEY"):
                        print(f"✅ .env 파일을 찾았습니다: {env_path}")
                        return
    else:
        load_dotenv()
        if os.getenv("GOOGLE_API_KEY"):
            return
        module_dir = os.path.dirname(__file__)
        load_dotenv(os.path.join(module_dir, ".env"))
        if os.getenv("GOOGLE_API_KEY"):
            return
        if getattr(sys, "frozen", False):
            exe_dir = os.path.dirname(sys.executable)
            load_dotenv(os.path.join(exe_dir, ".env"))
            if os.getenv("GOOGLE_API_KEY"):
                return
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
# 기능 : 사실관계 검증 과정을 기록할 로거(Logger) 설정
# ------------------------------------------------------------------
def setup_check_logging(keyword: str) -> tuple[logging.Logger, str]:
    """
    '기사 재생성' 폴더 내에 오늘 날짜의 폴더를 만들고, 키워드를 파일명으로 하는 로그 파일을 설정
    기존 news_LLM 로그 파일에 이어서 기록(mode="a")
    :param keyword: 로그 파일명으로 사용할 키워드
    :return: 설정된 로거 객체와 로그 파일 경로
    """
    current_date = datetime.now().strftime("%Y%m%d")
    base_dir = _get_base_dir()
    log_dir = base_dir / "기사 재생성" / f"재생성{current_date}"
    log_dir.mkdir(parents=True, exist_ok=True)

    safe_keyword = _safe_keyword(keyword)
    log_filepath = str(log_dir / f"{safe_keyword}.txt")

    logger_name = f"check_llm_{safe_keyword}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        fh = logging.FileHandler(log_filepath, encoding="utf-8", mode="a")
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
# 기능 : 사실관계 검증을 위한 시스템 프롬프트 생성
# ------------------------------------------------------------------
def generate_check_prompt(keyword: str = "", published_kst: str | None = None) -> str:
    today_kst = get_today_kst_str()
    keyword_info = f"- 키워드: {keyword}\n" if keyword else ""
    published_line = (
        f"- 원문 기사 작성일(사이트 추출): {published_kst}\n"
        if (published_kst and str(published_kst).strip())
        else "- 원문 기사 작성일(사이트 추출): 확인 불가\n"
    )

    prompt = f"""
        사용자가 입력한 두 개의 기사('생성된 기사'와 '원문 기사')를 비교하여 사실관계를 판단하라.
        사용자는 '=' 구분선을 사용하여 두 개의 기사를 구분하며, 첫 번째가 '생성된 기사', 두 번째가 '원문 기사'이다.

        [오늘(KST) 기준일]
        - 오늘 날짜(Asia/Seoul): {today_kst}
        - 원문 기사 작성일(사이트 추출): {published_line}

        [키워드]
        {keyword_info}

        [판정 원칙]
        - 내부적으로 이슈를 '경미'와 '중대'로 구분하되, JSON의 verdict는 다음을 따른다.
        * 경미 이슈만 있는 경우 → "OK" (재작성 유도 금지)
        * 중대 이슈가 1개 이상인 경우 → "ERROR" (필요 최소 수정 포함)
        - '경미'는 사실 왜곡이 없고, 의미·수치·날짜·인용·고유명사 정합성에 영향이 없는 편집/표현 차이를 말한다.
        - '중대'는 사실 왜곡·추가 사실 삽입·핵심 수치/날짜/고유명사/직함/인용 변경, 불확정을 단정으로 바꾸는 경우를 말한다.

        [비교 기준]
        - 완전히 동일하거나 의미가 동일 → "✅ 사실관계에 문제가 없습니다."
        - 표현 방식만 다르며 의미 동일 → "✅ 표현 방식이 다르지만, 사실관계는 일치합니다."
        - 일부 내용이 다르거나 빠졌으나 핵심 사실 유지(경미) → 상기 메시지 중 하나로 통과(OK).
        - 명확한 오류(중대)가 있는 경우 → "❌ 사실과 다른 정보가 포함되어 있습니다." + 어떤 부분이 틀렸는지 설명하고 ERROR.

        [경미 이슈(OK 처리) 예시]
        - 문장 순서 변경, 요약·압축·중복 제거(핵심 의미 보존 시)
        - 인용문의 따옴표 종류·문장부호 차이(단어·화자 동일 시)
        - 숫자 자리수 표기·퍼센트 반올림/내림 등 경미한 표기 차(정확한 수치가 변하지 않는 범위)
        - 본문 길이 260~880자 범위 내의 경미한 편차(가독성 목적의 생략/압축 포함)
        - 해시태그가 2~6개 범위의 경미한 편차(추정/허위 태그만 아니라면)
        - 동일 의미의 시제·상대시점 표현(‘지난/오는/이날/최근/이전’ 등) 및 날짜 노출 생략
        - 불필요한 수식어·가치 판단어 제거 또는 완화(사실 왜곡이 없을 때)

        [중대 이슈(ERROR 처리) 예시]
        - 원문에 없는 사실/수치/날짜/인물·직함·지명·제품 추가
        - 원문의 불확정(예정/추진/가능성)을 단정으로 변경
        - 핵심 수치·날짜·인물·직함·고유명사·인용문(단어/화자) 변경 또는 누락으로 의미가 바뀌는 경우
        - 사건의 시점을 잘못 바꿔 의미를 왜곡(과거↔현재↔미래 혼동)
        - 원문 핵심 주장·결론의 반전/왜곡

        [시제/날짜 허용 규칙(오류 아님)]
        1) '지난 O월/OO일/OOOO년', '오는 O월/OO일/OOOO년' 등 상대 시점 표현
        2) '이날', '오늘' 등 불필요한 시점 생략
        3) 방송·행사 등 복수 일자 중 **가장 최근** 기준 서술
        4) [오늘(KST) 기준일]과 비교해 과거/미래를 정확히 반영한 시제 조정
        5) 원문 발행일이 더 과거인 경우 과거 시제로 통일

        [예외 사항 - 사실 오류로 간주하지 말 것]
        - 날짜 표기 형식만 다른 경우(예: '2025-09-16' ↔ '9월 16일' ↔ '16일')
        - 서술 어미/문체 통일(이다/했다/한다)로의 변경
        - 링크·사진 캡션·SNS 임베드·저작권 고지 등 비핵심 메타요소의 추가/제거
        - 고유명사 표기 차이(띄어쓰기/하이픈/중점/대소문자/한영 변환)로 인한 **동일 주체** 표기 교체
        - 직함·기관 약칭 사용(예: '서울중앙지방법원' ↔ '서울중앙지법', '대표이사' ↔ '대표') — 의미 동일 시
        - 제품/서비스명 뒤 보조어(앱/플랫폼/서비스 등) 생략 또는 부가 — 주체 동일·혼동 없음
        - 단위·기호 표기만 다른 경우(예: ℃ ↔ 도, km ↔ 킬로미터, 원 ↔ KRW) — **수치값 불변**
        - 천 단위 구분기호·공백·억/만 환산 등 표기 차 — **값 동일**일 때
        - 제목의 요약·간결화·어순 조정 — 의미 동일 시
        - [제목]/[해시태그]에 사용자가 입력한 [키워드]의 포함/미포함 **만으로** 오류 판단 금지

        [점검 사항]
        1) 비교는 오로지 '원문 기사' 내용에 한정한다(외부 정보 금지).
        2) 인물 직함/회사명/제품/서비스/수치/날짜/지명/인용문은 원문과 일치해야 한다.
        3) 원문에 없는 정보가 추가되었는지 확인하고, 있었으면 '허위 정보'로 간주(중대).
        4) 불확정 표현을 단정으로 바꾸었는지 확인(중대).
        5) 간결해져도 핵심 의미가 보존되면 경미로 본다(OK).
        6) 길이·해시태그 개수는 **권고 기준**으로 보되, 과도한 일탈(예: 200자 미만, 1000자 초과, 해시태그 3개 이하/7개 이상)은 품질 저하로만 지적하라(가능하면 OK 유지).
        7) 제목/해시태그가 원문과 불일치하더라도 사실 왜곡이 아니면 경미로 간주한다. 단, 허위·추정 태그는 중대.
        8) 제목이나 해시태그가 원문과 불일치하거나 오류가 있는 경우에 단순 삭제하지 말고, 원문 기사 내용에 맞는 올바른 제목과 해시태그로 교체하여 반드시 기존에 생성된 개수를 유지
        - [제목] 섹션은 항상 3개 제목을 포함해야 한다.
        - [해시태그] 섹션은 항상 3~5개의 해시태그를 포함해야 한다.

        [응답 정책]
        - '중대'에 해당할 때만 verdict="ERROR"로 하고, 최소 수정만 반영한 corrected_article을 제공한다.
        - '경미'만 있으면 verdict="OK"로 통과시키며 corrected_article은 비워 둔다(또는 생략).
        - nonfactual_phrases에는 **중대 이슈만** 담는다(경미 이슈는 담지 않는다).

        [응답 형식]
        - 아래 JSON 하나만 정확히 출력하라(그 외 텍스트·설명·추가 JSON 금지)
        - corrected_article는 '사실이 아닌 부분만 최소 수정' 원칙으로 작성하라(불필요한 재서술 금지).
        - corrected_article는 반드시 하나의 문자열로 출력하라(객체/배열 금지), [제목]/[해시태그]/[본문] 섹션을 포함할 것.
        - verdict가 "OK"인 경우 corrected_article를 비워두거나 키 자체를 생략한다.

        [최종 출력: JSON 전용]
        {{
        "verdict": "OK" 또는 "ERROR",
        "nonfactual_phrases": [
            {{ "phrase": "문제 구절1", "reason": "이유 설명" }},
            {{ "phrase": "문제 구절2", "reason": "이유 설명" }}
        ],
        "corrected_article": "수정된 전체 기사 (ERROR일 때만, [제목]/[해시태그]/[본문] 포함)"
        }}
        """
    return prompt


# ------------------------------------------------------------------
# 작성자 : 최준혁
# 기능 : LLM 응답 텍스트에서 JSON 블록 추출
# ------------------------------------------------------------------
def _extract_json_block(text: str):
    """
    LLM 응답에서 하나 이상의 JSON 후보를 찾아 가장 적합한 객체(dict)를 반환.

    처리 순서:
    1) ```json ...``` 코드펜스 내 JSON 후보 수집(여러 개 가능)
    2) 일반 ``` ... ``` 코드펜스 내에서 { ... } 블록 수집
    3) 전체 텍스트에서 중괄호 균형으로 { ... } 블록 수집(정규식 한계 보완)
    4) 모든 후보에 대해 json.loads 시도 후, 핵심 키 포함 여부로 스코어링하여 최적 후보 선택

    :param text: LLM이 생성한 전체 텍스트
    :return: 최적으로 판단된 dict(JSON 객체), 실패 시 None
    """
    if not text:
        return None

    candidates: list[tuple[int, str]] = []  # (priority, payload)

    # 1) ```json 코드펜스 (가장 신뢰)
    for m in re.finditer(r"```json\s*(\{[\s\S]*?\})\s*```", text, flags=re.I):
        candidates.append((3, m.group(1)))

    # 2) 일반 코드펜스 내에서 { ... }만 추출
    for m in re.finditer(r"```\s*([\s\S]*?)\s*```", text):
        block = m.group(1)
        # 간단한 중괄호 균형 추출
        buf = []
        depth = 0
        start = -1
        for i, ch in enumerate(block):
            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start != -1:
                    buf.append(block[start:i+1])
                    start = -1
        for b in buf:
            candidates.append((2, b))

    # 3) 전체 텍스트에서 중괄호 균형 기반 스캔
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            if depth > 0:
                depth -= 1
                if depth == 0 and start != -1:
                    candidates.append((1, text[start:i+1]))
                    start = -1

    # 중복 제거(내용 기준)
    seen = set()
    uniq_candidates: list[tuple[int, str]] = []
    for prio, payload in candidates:
        key = payload.strip()
        if key not in seen:
            seen.add(key)
            uniq_candidates.append((prio, payload))

    # 파싱 및 스코어링
    best_obj = None
    best_score = -1
    for prio, payload in uniq_candidates:
        try:
            obj = json.loads(payload)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        # 핵심 키 가중치
        score = 0
        score += 3 if 'verdict' in obj else 0
        score += 2 if 'corrected_article' in obj else 0
        score += 1 if 'nonfactual_phrases' in obj else 0
        score += prio  # 코드펜스 등 신뢰도 반영
        if score > best_score:
            best_score = score
            best_obj = obj

    return best_obj

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 기능 : LLM이 생성한 다양한 형태의 판정(verdict)을 'OK' 또는 'ERROR'로 정규화
# ------------------------------------------------------------------
def _normalize_verdict(raw: str, json_obj: dict) -> str:
    """
    '✅', '일치' 등의 긍정 표현은 'OK'로, '❌', '오류' 등의 부정 표현은 'ERROR'로 변환
    :param raw: LLM이 생성한 원본 verdict 문자열
    :param json_obj: nonfactual_phrases 존재 여부 확인을 위한 JSON 객체
    :return: 'OK' 또는 'ERROR' 문자열
    """
    v = (raw or "").strip()
    vu = v.upper()
    if vu in ("OK", "ERROR"):
        return vu
    # 의미기반 휴리스틱
    if "✅" in v or ("일치" in v and "사실" in v):
        return "OK"
    if "❌" in v or "오류" in v or "틀렸" in v or "다릅" in v:
        return "ERROR"
    if "⚠️" in v or "주의" in v or "경고" in v:
        return "ERROR"
    nf = json_obj.get("nonfactual_phrases") or []
    return "ERROR" if nf else "OK"

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 기능 : 사실과 다른 구문(nonfactual_phrases) 목록을 표준 형식으로 정규화
# ------------------------------------------------------------------
def _normalize_nonfactual(nf) -> list[dict]:
    """
    다양한 형식의 오류 구문 목록을 {"phrase": ..., "reason": ...} 형태의 딕셔너리 리스트로 통일
    :param nf: LLM이 생성한 nonfactual_phrases
    :return: 정규화된 딕셔너리 리스트
    """
    items = []
    if isinstance(nf, list):
        for it in nf:
            if isinstance(it, dict):
                phrase = str(it.get("phrase") or it.get("문제 구절") or "").strip()
                reason = str(it.get("reason") or it.get("이유") or "").strip()
            else:
                phrase = str(it).strip()
                reason = ""
            if phrase:
                items.append({"phrase": phrase, "reason": reason})
    return items

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 기능 : 텍스트에 [제목], [해시태그], [본문] 섹션이 없으면 최소한의 기본 틀을 생성하여 보장
# ------------------------------------------------------------------
def _ensure_sections(text: str) -> str:
    """
    주어진 텍스트에 필수 섹션이 누락된 경우, 기본 제목과 해시태그를 추가하여 완전한 형식으로 반환
    :param text: 보정할 텍스트
    :return: 섹션이 보장된 텍스트
    """
    if not text:
        text = ""
    has_title = "[제목]" in text
    has_tags  = "[해시태그]" in text
    has_body  = "[본문]" in text
    if has_title and has_tags and has_body:
        return text.strip()
    # 본문 추정
    body = text
    m = re.search(r"\[본문\]\s*(.*)\Z", text, flags=re.S)
    if m:
        body = m.group(1).strip()
    # 기본 틀 생성
    rebuilt = []
    rebuilt.append("[제목]")
    rebuilt.append("수정 기사 1")
    rebuilt.append("수정 기사 2")
    rebuilt.append("수정 기사 3")
    rebuilt.append("")
    rebuilt.append("[해시태그]")
    # 해시태그 후보 추출
    candidates = list(dict.fromkeys(re.findall(r"#\S+", text)))[:5]
    if not candidates:
        candidates = ["#뉴스", "#정보", "#사실검증"]
    rebuilt.append(" ".join(candidates[:5]))
    rebuilt.append("")
    rebuilt.append("[본문]")
    rebuilt.append(body.strip())
    return "\n".join(rebuilt).strip()

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 기능 : 수정된 기사가 없을 때, 오류 구절을 원본에서 제거하여 최소한의 수정을 수행
# ------------------------------------------------------------------
def _auto_minimal_patch(generated_article: str, nonfactual_list: list[dict]) -> str:
    """
    LLM이 오류(ERROR)로 판정했으나 수정된 기사를 제공하지 않은 경우,
    감지된 오류 구문(nonfactual_phrases)을 생성된 기사에서 삭제하는 방식으로 자동 수정
    :param generated_article: LLM이 생성한 원본 기사
    :param nonfactual_list: 사실이 아닌 것으로 판별된 구문 리스트
    :return: 최소한으로 수정된 기사
    """
    if not generated_article:
        return ""
    patched = generated_article
    for item in nonfactual_list:
        phrase = item.get("phrase", "")
        if phrase:
            # 과격한 치환 방지: 정확히 일치하는 구절만 제거
            patched = patched.replace(phrase, "")
    return _ensure_sections(patched)


# ------------------------------------------------------------------
# 작성자 : 최준혁
# 기능 : 생성된 기사와 원문 기사를 비교하여 사실관계를 검증하는 메인 로직
# ------------------------------------------------------------------
def check_article_facts(
    generated_article: str,
    original_article: str,
    keyword: str = "check_LLM",
    source_url: str | None = None,        # ✅ (2) 작성일시 주입을 위한 파라미터 추가
    published_kst: str | None = None      # ✅ (2) 외부에서 직접 전달 가능
) -> dict:
    """
    두 기사를 LLM에 전달하여 사실관계 오류를 확인하고, 오류가 있을 경우 수정된 기사를 포함한 JSON을 반환
    :param generated_article: news_LLM이 생성한 기사
    :param original_article: 원본 기사 본문
    :param keyword: 로깅 및 프롬프트에 사용될 키워드
    :param source_url: 원문 기사 URL(있다면 발행일 재추출 시도)
    :param published_kst: 'YYYY-MM-DD HH:MM' 등 가독형 KST 문자열(우선 주입)
    :return: 검증 결과를 담은 딕셔너리 ('explanation', 'json', 'error' 포함)
    """
    logger, log_filepath = setup_check_logging(keyword)

    log_and_print(logger, "\n" + "="*80)
    log_and_print(logger, "🔍 CHECK_LLM - 기사 사실관계 검증 시작")
    log_and_print(logger, "="*80)
    log_and_print(logger, f"\n📥 입력 데이터:")
    log_and_print(logger, f"  - 생성된 기사 길이: {len(generated_article)}자")
    log_and_print(logger, f"  - 원문 기사 길이: {len(original_article)}자")
    log_and_print(logger, f"  - 로그 파일: {log_filepath}")
    if source_url:
        log_and_print(logger, f"  - source_url: {source_url}")

    # ✅ (2) 작성일시 주입: 우선순위 published_kst 인자 → URL 추출 → 미확인
    published_kst_str = (published_kst or "").strip() or None
    if not published_kst_str and source_url and extract_publish_datetime:
        try:
            dt_raw = extract_publish_datetime(source_url)  # 예: '20250901 08:39' 또는 None
            if dt_raw:
                m = re.match(r"^(\d{4})(\d{2})(\d{2})\s+(\d{2}:\d{2})$", dt_raw)
                published_kst_str = (
                    f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}" if m else dt_raw
                )
                log_and_print(logger, f"  - 원문 기사 작성일(KST): {published_kst_str}")
        except Exception as e:
            log_and_print(logger, f"  - 작성일 추출 실패: {e}", "warning")

    try:
        log_and_print(logger, f"\n🤖 AI 모델 호출:")
        # ✅ (2) 프롬프트에 작성일시 주입
        system_prompt = generate_check_prompt(keyword=keyword, published_kst=published_kst_str)
        user_request = (
            f"생성된 기사: {generated_article}\n" 
            f"=\n" 
            f"원문 기사: {original_article}"
        )
        log_and_print(logger, f"  - 모델: gemini-2.5-flash")
        log_and_print(logger, f"  - 시스템 프롬프트 길이: {len(system_prompt)}자")
        log_and_print(logger, f"  - 사용자 요청 길이: {len(user_request)}자")

        log_and_print(logger, f"\n📋 전체 시스템 프롬프트:")
        log_and_print(logger, f"{'='*80}")
        log_and_print(logger, system_prompt)
        log_and_print(logger, f"{'='*80}")

        log_and_print(logger, f"\n📋 전체 사용자 요청:")
        log_and_print(logger, f"{'='*80}")
        log_and_print(logger, user_request)
        log_and_print(logger, f"{'='*80}")

        contents = [
            {'role': 'user', 'parts': [{'text': system_prompt}]},
            {'role': 'model', 'parts': [{'text': '이해했습니다. 비교 후 JSON도 함께 제공하겠습니다.'}]},
            {'role': 'user', 'parts': [{'text': user_request}]}
        ]

        log_and_print(logger, f"\n⏳ AI 응답 대기 중...")
        t0 = time.perf_counter()                     # ✅ (1) 시작
        response = model.generate_content(contents)
        rtt = time.perf_counter() - t0               # ✅ (1) 경과

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

        full_text = (response.text or "").strip()
        log_and_print(logger, f"  - RTT: {rtt*1000:.0f}ms")  # ✅ (1) 밀리초로 기록

        log_and_print(logger, f"\n📤 AI 응답 결과:")
        log_and_print(logger, f"  - 응답 길이: {len(full_text)}자")

        log_and_print(logger, f"\n📋 전체 AI 응답:")
        log_and_print(logger, f"{'='*80}")
        log_and_print(logger, full_text)
        log_and_print(logger, f"{'='*80}")

        log_and_print(logger, f"\n🔍 JSON 파싱 시도:")
        json_obj = _extract_json_block(full_text)

        if not json_obj or "verdict" not in json_obj:
            log_and_print(logger, f"  ❌ JSON 파싱 실패", "warning")
            result = {
                "explanation": full_text,
                "json": None,
                "error": "JSON 파싱 실패"
            }
        else:
            log_and_print(logger, f"  ✅ JSON 파싱 성공")

            # --------- 보정 1: nonfactual 목록 정상화
            nf = _normalize_nonfactual(json_obj.get("nonfactual_phrases"))
            json_obj["nonfactual_phrases"] = nf

            # --------- 보정 2: verdict 정규화(OK/ERROR) 
            json_obj["verdict"] = _normalize_verdict(json_obj.get("verdict", ""), json_obj)

            # --------- 보정 3: corrected_article 타입/섹션 보장 
            corrected = (json_obj.get("corrected_article", "") or "")
            if isinstance(corrected, dict):
                corrected = "\n".join([
                    "[제목]",
                    str(corrected.get("title", "")).strip(),
                    "",
                    "[해시태그]",
                    str(corrected.get("hashtags", "")).strip(),
                    "",
                    "[본문]",
                    str(corrected.get("본문", "")).strip(),
                ])
            elif isinstance(corrected, list):
                # 잘못된 리스트 형태로 올 때는 문자열로 병합
                corrected = "\n".join(str(x) for x in corrected)
            else:
                corrected = str(corrected)

            # 오류인데 교정문이 비어 있으면 자동 최소 보정 생성
            if json_obj["verdict"] == "ERROR" and not corrected.strip():
                corrected = _auto_minimal_patch(generated_article, nf)

            # 섹션 강제 보장
            corrected = _ensure_sections(corrected) if corrected else corrected
            json_obj["corrected_article"] = corrected

            result = {
                "explanation": full_text,
                "json": json_obj,
                "error": None
            }

        log_and_print(logger, f"\n📋 최종 반환 결과:")
        log_and_print(logger, f"  - explanation 길이: {len(result['explanation'])}자")
        log_and_print(logger, f"  - json 존재: {result['json'] is not None}")
        
        # Display nonfactual phrases with reasons if they exist
        if result['json'] and 'nonfactual_phrases' in result['json']:
            nonfactual = result['json']['nonfactual_phrases']
            if nonfactual:
                log_and_print(logger, "\n⚠️ 발견된 사실 오류 구문:")
                for i, item in enumerate(nonfactual, 1):
                    if isinstance(item, dict):
                        log_and_print(logger, f"  {i}. {item.get('phrase', '')}")
                        log_and_print(logger, f"     → 이유: {item.get('reason', '사유가 제공되지 않았습니다')}")
                    else:
                        log_and_print(logger, f"  {i}. {item}")
                        log_and_print(logger, f"     → 이유: 상세한 이유가 제공되지 않았습니다")
        
        log_and_print(logger, f"  - error: {result['error']}")

        log_and_print(logger, f"\n💾 최종 결과를 로그 파일에 저장 완료")
        log_and_print(logger, f"  - 로그 파일 경로: {log_filepath}")

        log_and_print(logger, "\n" + "="*80)
        log_and_print(logger, "🔍 CHECK_LLM - 기사 사실관계 검증 완료")
        log_and_print(logger, "="*80)

        return result

    except Exception as e:
        log_and_print(logger, f"\n❌ 예외 발생: {str(e)}", "error")
        log_and_print(logger, "\n" + "="*80, "error")
        log_and_print(logger, "🔍 CHECK_LLM - 기사 사실관계 검증 실패", "error")
        log_and_print(logger, "="*80, "error")

        return {
            "explanation": "",
            "json": None,
            "error": str(e)
        }


if __name__ == "__main__":
    print("🔍 기사 사실관계 검증 및 최소수정 프로그램")
    keyword = input("키워드를 입력하세요 (로그 파일명용): ").strip()
    generated = input("생성된 기사(제목/해시태그/본문 포함)를 붙여넣으세요: ").strip()
    original = input("원문 기사를 붙여넣으세요: ").strip()

    # 참고: 필요 시 여기에서 source_url, published_kst를 추가 입력받아 전달할 수 있습니다.
    result = check_article_facts(generated, original, keyword)
    if result["error"]:
        print("❌ 오류:", result["error"])
    else:
        print("\n=== 설명 ===\n", result["explanation"])
        print("\n=== JSON ===\n", json.dumps(result["json"], ensure_ascii=False, indent=2))
