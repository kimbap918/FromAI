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
    from . import check_LLM
except ImportError:
    import check_LLM

# ---------------------------
# 🔒 형식 고정(양식 보정) 유틸
# ---------------------------
import re

def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n].rstrip()

def ensure_output_sections(article_text: str, keyword: str, fallback_title: str) -> str:
    """
    [제목] [해시태그] [본문] 3섹션을 강제 보장.
    - 누락 섹션은 안전한 기본값으로 채움.
    - 제목은 3개(최대 35자 내외), 해시태그는 3~5개 보장.
    - 본문은 가능한 한 원문 기사(LLM 결과)에서 추출.
    """
    if not article_text:
        article_text = ""

    text = article_text.strip()
    has_title = "[제목]" in text
    has_tags  = "[해시태그]" in text
    has_body  = "[본문]" in text

    # 이미 완비된 경우도, 여분의 공백 정리만 하고 반환
    if has_title and has_tags and has_body:
        return text

    # 본문 후보 추출
    body_match = re.search(r"\[본문\]\s*(.*)\Z", text, flags=re.S)
    if body_match:
        body = body_match.group(1).strip()
    else:
        # [본문]이 없으면 통짜 텍스트를 본문으로 간주
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
    # 부족하면 일반 키워드 보충
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


def _ensure_env_loaded():
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


def _safe_keyword(name: str) -> str:
    name = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()
    return name.replace(" ", "_") or "log"

def _get_base_dir() -> Path:
    """
    exe 빌드 시: exe가 있는 위치
    개발/실행 시: 현재 실행 디렉토리(Working Directory)
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path.cwd()

def setup_logging(keyword: str) -> tuple[logging.Logger, str]:
    """
    뉴스 재구성 로깅을 실행 위치에 생성.
    예) ./기사 재생성/재생성20250821/키워드.txt
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

def log_and_print(logger, message: str, level: str = "info"):
    if level == "info":
        logger.info(message)
    elif level == "warning":
        logger.warning(message)
    elif level == "error":
        logger.error(message)
    elif level == "debug":
        logger.debug(message)


def extract_title_and_body(url, logger):
    log_and_print(logger, f"\n  📄 기사 추출 세부 과정:")
    log_and_print(logger, f"    - newspaper 라이브러리로 기사 다운로드 시도...")

    article = Article(url, language='ko')
    article.download()
    article.parse()
    title = article.title.strip()
    body = article.text.strip()

    log_and_print(logger, f"    - 다운로드된 제목: {title}")
    log_and_print(logger, f"    - 다운로드된 본문 길이: {len(body)}자")

    if len(body) < 50:
        log_and_print(logger, f"    ⚠️ 본문이 짧아 fallback으로 전환합니다.", "warning")
        log_and_print(logger, f"    - fallback: extract_naver_cp_article() 호출...")
        title, body = extract_naver_cp_article(url, logger)
        log_and_print(logger, f"    - fallback 결과 제목: {title}")
        log_and_print(logger, f"    - fallback 결과 본문 길이: {len(body)}자")
    else:
        log_and_print(logger, f"    ✅ 본문 길이 충분 - newspaper 결과 사용")

    return title, body


def extract_naver_cp_article(url, logger):
    log_and_print(logger, f"      🔄 네이버 CP 기사 fallback 처리:")
    log_and_print(logger, f"        - requests로 HTML 직접 다운로드...")

    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, 'html.parser')

    log_and_print(logger, f"        - HTML 다운로드 완료: {len(res.text)}자")

    title_tag = soup.select_one('h2.media_end_head_headline')
    title = title_tag.text.strip() if title_tag else "제목 없음"

    log_and_print(logger, f"        - 제목 태그 검색 결과: {'찾음' if title_tag else '찾지 못함'}")
    log_and_print(logger, f"        - 추출된 제목: {title}")

    body_area = soup.select_one('article#dic_area')
    body = body_area.get_text(separator="\n").strip() if body_area else "본문 없음"

    log_and_print(logger, f"        - 본문 영역 검색 결과: {'찾음' if body_area else '찾지 못함'}")
    log_and_print(logger, f"        - 추출된 본문 길이: {len(body)}자")

    return title, body


def generate_system_prompt(keyword: str, today_kst: str) -> str:
    # 기존 포맷 유지 + 출력 형식 고정 요구 (강화)
    prompt = (
        f"""[System message]
        - 키워드, 기사 제목,  본문 순으로 사용자가 입력한다.
        - **최종 출력은 [제목], [해시태그], [본문]의 세 섹션으로 명확히 구분하여 반드시 작성할 것.** 

        [Role]
        - 당신은 제공된 기사 제목과 본문을 바탕으로 사실을 유지하며 재구성하는 전문 기자이자 에디터이다.
        - 최우선 목표는 사실 왜곡 없이 가독성과 논리 전개를 개선하고, 오늘(KST) 기준으로 시제를 일관되게 맞추는 것이다.
        - 본문 작성 전 1) [시제 변환 규칙], 2) [News Generation Process], 3) [출력 형식]을 반드시 확인하고 준수한다.
        - 추측/전망성 표현은 사용하지 않는다. 문체는 일관된 기사 문체(~이다/~했다)로 작성하며 Markdown 문법은 사용하지 않는다.

        [오늘(KST) 기준일]
        - 오늘 날짜(Asia/Seoul): {today_kst}

        [시제 변환 규칙]
        - 원문에 포함된 날짜/시간 표현과 오늘(KST) 기준일을 비교하여 시제를 일관되게 조정한다.
        - 이미 발생한 사실은 과거 시제(…했다/…이었다), 진행 중인 사실은 현재 시제(…한다), 예정된 사실은 미래 지향 서술(…할 예정이다/…로 예정돼 있다)로 기술한다.
        - 추측성 표현(…할 것으로 보인다, …전망이다)은 사용하지 않는다.
        - 날짜를 노출할 필요가 없으면 직접적인 날짜 표기는 피하고, '당시', '이후', '이전', '같은 날'과 같은 상대적 시간 표현을 사용한다.

        [News Generation Process (Step-by-Step Execution)]
        1. 제목 생성
        - 제공된 기사 제목을 인용하고, 본문의 핵심 내용을 반영하여 **3개의 창의적이고 다양한 제목**을 생성한다.
        - 키워드는 가능한 한 앞쪽에 자연스럽게 포함하되, 강제로 앞에 배치하지 않는다.
        - 제목 유형은 다음과 같이 다양성을 확보한다:
        * 1번 제목: 핵심 사실을 간결하게 전달하는 전통적 뉴스 제목
        * 2번 제목: 독자의 관심을 끌 수 있는 창의적인 제목
        * 3번 제목: 기사 내용의 핵심 가치나 영향력을 강조하는 제목
        - 25~40자 내외로 간결하고 강렬한 인상을 주도록 작성한다.
        - 문장 부호는 최소화하고, 필요한 경우에만 쉼표(,)를 사용한다.
        - 궁금증을 유발하는 표현 금지 (예: '?', '왜', '어떻게', '무엇이' 등 사용 금지)
        - 사용 금지 기호: 마침표(.), 콜론(:), 마크다운 기호(*, #, &), Markdown 문법
        - 사용 가능 기호: 쉼표(,), 따옴표(' '), 쌍따옴표(" ") 
        - 부정적인 표현을 긍정적인 방향으로 조정한다.

        2. 본문 생성: 입력된 기사 본문을 바탕으로 간결한 기사를 작성한다.
        - **400~700자 내외로 완성** (절대 700자 초과 금지, 원문이 짧으면 불필요한 내용 추가 금지)
        - 핵심 내용만 간결하게 전달 (중복 제거, 장황한 설명 생략)
        - 원문의 주요 사실은 모두 포함하되, 표현 방식은 완전히 변경
        - 문장은 짧고 명확하게 (한 문장당 15~20자 내외 권장)
        - 인용문은 원문 그대로 유지 (단어 하나도 변경 금지)
        - 비격식체 사용 (예: "~이다", "~했다", "~한다")
        - 맞춤법 정확히 준수, 부적절한 표현 사용 금지
        - '...', '~~', '!!' 등 불필요한 기호 사용 금지

        3. 제목 및 본문 검토 
        -  제목과 본문에서 **금지된 기호(…, *, , #, &) 사용 여부 확인 및 수정
        - 제공된 정보 외 추측·허구·외부 자료 추가 여부 검토 후 수정

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
        (여기에 생성한 본문 내용)"""
    )
    return prompt


def _is_fact_ok(check_result: dict) -> bool:
    if not check_result or "json" not in check_result or not check_result["json"]:
        return False
    return check_result["json"].get("verdict") == "OK"


def generate_article(state: dict) -> dict:
    url = state.get("url")
    keyword = state.get("keyword")

    logger, log_filepath = setup_logging(keyword)

    log_and_print(logger, "\n" + "="*80)
    log_and_print(logger, "📰 NEWS_LLM - 기사 재구성 시작")
    log_and_print(logger, "="*80)
    log_and_print(logger, f"\n📥 입력 데이터:")
    log_and_print(logger, f"  - URL: {url}")
    log_and_print(logger, f"  - 키워드: {keyword}")
    log_and_print(logger, f"  - 로그 파일: {log_filepath}")

    try:
        log_and_print(logger, f"\n🔗 기사 추출 단계:")
        log_and_print(logger, f"  - URL에서 기사 다운로드 및 파싱 중...")
        title, body = extract_title_and_body(url, logger)
        log_and_print(logger, f"  ✅ 기사 추출 완료")
        log_and_print(logger, f"  - 제목: {title}")
        log_and_print(logger, f"  - 본문 길이: {len(body)}자")

        log_and_print(logger, f"\n📋 전체 원본 기사:")
        log_and_print(logger, f"{'='*80}")
        log_and_print(logger, f"제목: {title}")
        log_and_print(logger, f"{'='*40}")
        log_and_print(logger, body)
        log_and_print(logger, f"{'='*80}")

        log_and_print(logger, f"\n🤖 AI 프롬프트 생성:")
        today_kst = get_today_kst_str()
        system_prompt = generate_system_prompt(keyword, today_kst)
        user_request = f"키워드: {keyword}\n제목: {title}\n본문: {body}"
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
            {'role': 'model', 'parts': [{'text': '이해했습니다. 규칙을 따르겠습니다.'}]},
            {'role': 'user', 'parts': [{'text': user_request}]}
        ]

        log_and_print(logger, f"\n⏳ Gemini AI 호출 중...")
        log_and_print(logger, f"  - 모델: gemini-2.5-flash")
        log_and_print(logger, f"  - 요청 내용 길이: {len(str(contents))}자")

        response = model.generate_content(contents)
        article_text = response.text.strip()

        log_and_print(logger, f"\n📤 AI 응답 결과:")
        log_and_print(logger, f"  - 응답 길이: {len(article_text)}자")

        log_and_print(logger, f"\n📋 전체 AI 응답:")
        log_and_print(logger, f"{'='*80}")
        log_and_print(logger, article_text)
        log_and_print(logger, f"{'='*80}")

        # ---------------------------
        # 🔒 형식 고정 처리 (LLM 응답 직후)
        # ---------------------------
        article_text = ensure_output_sections(article_text, keyword, title)

        log_and_print(logger, f"\n📊 기사 길이 비교:")
        log_and_print(logger, f"  - 원본 기사: {len(body)}자")
        log_and_print(logger, f"  - 재구성된 기사: {len(article_text)}자")
        log_and_print(logger, f"  - 길이 변화: {len(article_text) - len(body)}자")

        log_and_print(logger, f"\n🔍 사실관계 검증 단계:")
        log_and_print(logger, f"  - check_LLM.check_article_facts() 호출...")
        fact_check_result = check_LLM.check_article_facts(article_text, body, keyword)
        log_and_print(logger, f"  ✅ 사실관계 검증 완료")

        # --- 핵심 분기 ---
        log_and_print(logger, f"\n🎯 결과 분기 결정:")
        if _is_fact_ok(fact_check_result):
            log_and_print(logger, f"  ✅ 사실관계 문제 없음 - 재구성된 기사 사용")
            display_text = article_text
            display_kind = "article"
        else:
            log_and_print(logger, f"  ⚠️ 사실관계 문제 발견 - 수정된 기사 확인 중...")
            corrected_article = ""
            if fact_check_result and fact_check_result.get("json"):
                corrected_article = fact_check_result["json"].get("corrected_article", "") or ""
            if corrected_article:
                # ---------------------------
                # 🔒 형식 고정 처리 (교정 기사에도 적용)
                # ---------------------------
                corrected_article = ensure_output_sections(corrected_article, keyword, title)
                log_and_print(logger, f"  ✅ 수정된 기사 사용")
                display_text = corrected_article
                display_kind = "corrected_article"
            else:
                log_and_print(logger, f"  ⚠️ 수정된 기사 없음 - 재구성된 기사 사용")
                display_text = article_text
                display_kind = "article"

        log_and_print(logger, f"\n📋 최종 결과:")
        log_and_print(logger, f"  - display_kind: {display_kind}")
        log_and_print(logger, f"  - display_text 길이: {len(display_text)}자")

        log_and_print(logger, f"\n📋 전체 최종 결과:")
        log_and_print(logger, f"{'='*80}")
        log_and_print(logger, display_text)
        log_and_print(logger, f"{'='*80}")

        if fact_check_result and "explanation" in fact_check_result:
            log_and_print(logger, f"\n📋 전체 사실관계 검증 결과:")
            log_and_print(logger, f"{'='*80}")
            log_and_print(logger, fact_check_result["explanation"])
            log_and_print(logger, f"{'='*80}")
            if fact_check_result.get("json"):
                log_and_print(logger, f"\n📋 JSON 검증 결과:")
                log_and_print(logger, f"{'='*80}")
                import json
                log_and_print(logger, json.dumps(fact_check_result["json"], ensure_ascii=False, indent=2))
                log_and_print(logger, f"{'='*80}")

        result = {
            "url": url,
            "keyword": keyword,
            "title": title,
            "original_body": body,
            "generated_article": article_text,
            "fact_check_result": fact_check_result,
            "corrected_article": corrected_article if 'corrected_article' in locals() else "",
            "display_text": display_text,
            "display_kind": display_kind,
            "error": None
        }

        log_and_print(logger, f"\n💾 최종 결과를 로그 파일에 저장 완료")
        log_and_print(logger, f"  - 로그 파일 경로: {log_filepath}")

        log_and_print(logger, "\n" + "="*80)
        log_and_print(logger, "📰 NEWS_LLM - 기사 재구성 완료")
        log_and_print(logger, "="*80)

        return result

    except Exception as e:
        log_and_print(logger, f"\n❌ 예외 발생: {str(e)}", "error")
        log_and_print(logger, "\n" + "="*80, "error")
        log_and_print(logger, "📰 NEWS_LLM - 기사 재구성 실패", "error")
        log_and_print(logger, "="*80, "error")

        return {
            "url": url,
            "keyword": keyword,
            "title": "",
            "original_body": "",
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
        print(f"   폴더 구조: FromAI1.1.3 2/기사 재생성/재생성{datetime.now().strftime('%Y%m%d')}/")
        print(f"   파일명: {keyword}.txt")
        print(f"   FromAI1.1.3 2 폴더 바로 아래에 '기사 재생성' 폴더가 생성되었습니다.")
