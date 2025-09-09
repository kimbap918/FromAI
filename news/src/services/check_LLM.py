import os
import sys
import json
import re
import time  # ✅ (1) RTT 측정용 추가
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
        사용자는 콤마(,)를 사용하여 두 개의 기사를 구분하며, 첫 번째가 '생성된 기사', 두 번째가 '원문 기사'이다.

        [오늘(KST) 기준일]
        - 오늘 날짜(Asia/Seoul): {today_kst}
        - 원문 기사 작성일(사이트 추출): {published_line}
     
        [키워드]
        {keyword_info}

        [비교 기준]
        - 완전히 동일한 경우 → "✅ 사실관계에 문제가 없습니다."
        - 표현 방식이 다르지만 의미가 동일한 경우 → "✅ 표현 방식이 다르지만, 사실관계는 일치합니다."
        - 일부 내용이 다르거나 빠진 경우 → "⚠️ 일부 내용이 원문과 다릅니다."
        - 명확한 오류가 있는 경우 → "❌ 사실과 다른 정보가 포함되어 있습니다." + 어떤 부분이 틀렸는지 설명

        [점검 사항]
        1. '생성된 기사'는 반드시 오로지 '원문 기사'의 내용 기반으로만 비교하라. 외부 정보를 사용하지 말라. '원문 기사'의 정보가 사실이라는 전제로 '생성된 기사'를 비교하라.
        2. '생성된 기사'의 내용이 '원문 기사'의 특정 인물의 직책이나 특정 회사의 기술, 사업, 제품, 서비스 혹은 사건의 경우 일어난 일 등의 정보와 일치하지 않는 경우 '원문 기사'의 정보와 일치하는 내용으로 수정하라.
        3. '원문 기사'에 없는 정보를 '생성된 기사'가 넣었는지 반드시 확인하라. 사실관계가 확인되지 않은 내용을 임의로 추가했을 경우 '허위 정보'로 간주하고 수정하라.
        4. '원문 기사'에서 '예정', '추진 중', '가능성 있음' 등의 불확정 표현이 사용된 경우, '생성된 기사'가 이를 단정적으로 표현했는지 확인하라.
        5. 기업이나 인물 등의 명예 훼손, 오해 유발, 정정보도 요청 가능성 있는 민감한 표현이 포함되어 있다면 반드시 지적하라.
        6. 문장이 간결해졌더라도, 핵심 의미가 왜곡되거나 빠진 부분이 없는지 확인하라.
        7. 완성된 기사의 본문 길이가 300자 이하, 800자 이상으로 작성되지 않도록 유의하라.
        8. 제목이나 해시태그가 원문과 불일치하거나 오류가 있는 경우에 단순 삭제하지 말고, 원문 기사 내용에 맞는 올바른 제목과 해시태그로 교체하여 반드시 기존에 생성된 개수를 유지한다.
        - [제목] 섹션은 항상 3개 제목을 포함해야 한다.
        - [해시태그] 섹션은 항상 3~5개의 해시태그를 포함해야 한다.

        [예외 사항 - 다음 경우는 사실 오류로 간주하지 말 것]
        1. '지난 O월' '지난 OOOO년' '지난 OO일', '오는 O월' '오는 OOOO년' '오는 OO일' 등의 상대적 시간 표현 사용
        2. '이날', '오늘' 등의 불필요한 시점 표현 생략
        3. 방송일이 1주일 이상 지난 경우 '최근 방송된', '이전 방송에서' 등으로 표현한 경우
        4. 여러 방송일이 있는 경우 가장 최근 방송일을 기준으로 한 시점 조정
        5. 원문과 재생성 기사 내용을 비교했을때 재생성 기사가 [오늘(KST) 기준일]과 비교해 과거/미래 시점으로 정확히 표현한 경우
        6. 원문 기사의 원문 기사 작성일(사이트 추출)이 재생성 기사 작성 시점인 [오늘(KST) 기준일]보다 과거인 경우, 재생성 기사 본문이 과거 시제로 정확히 표현한 경우
        7. [제목], [해시태그]에 사용자가 입력한 [키워드]가 포함된 경우

        ✅ 원문에 있지만 사용자가 기사에서 생략해도 문제 삼지 않는다.
        ✅ 위의 시제 관련 예외 사항에 해당하는 경우는 사실 오류로 간주하지 않는다.
        ❌ 사용자가 원문에 없는 내용을 추가하거나 왜곡해 넣은 경우, 반드시 구체적으로 지적하고 그 이유를 명시하라.
        - 각 지적 사항은 'phrase'(문제 구절)와 'reason'(이유)을 포함한 객체로 작성
        - 예시: {{ "phrase": "문제 구절", "reason": "구체적인 이유" }}

        [응답 형식]
        - 아래 JSON만 정확히 출력하라(그 외 텍스트 금지)
        - corrected_article는 '사실이 아닌 부분만 최소 수정' 원칙으로 작성하라(불필요한 재서술 금지).
        - corrected_article는 반드시 하나의 문자열로 출력하라(객체/배열 금지), [제목]/[해시태그]/[본문] 섹션을 포함할 것.

        [최종 출력: JSON 전용]
        {{
        "verdict": "OK" 또는 "ERROR",
        "nonfactual_phrases": [
            {{ "phrase": "문제 구절1", "reason": "이유 설명" }},
            {{ "phrase": "문제 구절2", "reason": "이유 설명" }}
        ],
        "corrected_article": "수정된 전체 기사 (문제가 있을 때만, [제목]/[해시태그]/[본문] 포함)"
        }}
        """
    return prompt

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 기능 : LLM 응답 텍스트에서 JSON 블록 추출
# ------------------------------------------------------------------
def _extract_json_block(text: str):
    """
    마크다운 코드 펜스(```json) 또는 중괄호({})로 감싸인 JSON 문자열을 찾아 파싱
    :param text: LLM이 생성한 전체 텍스트
    :return: 파싱된 JSON 객체, 실패 시 None
    """
    fence = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text)
    if fence:
        try:
            return json.loads(fence.group(1))
        except Exception:
            pass
    braces = re.findall(r"(\{[\s\S]*\})", text)
    for blk in braces[::-1]:
        try:
            return json.loads(blk)
        except Exception:
            continue
    return None

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
        user_request = f"생성된 기사: {generated_article}, \n\n원문 기사: {original_article}"
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
