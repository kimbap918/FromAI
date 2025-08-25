import os
import sys
import json
import re
import google.generativeai as genai
from news.src.utils.common_utils import get_today_kst_str
from dotenv import load_dotenv
from datetime import datetime
from pathlib import Path
import logging

def _ensure_env_loaded():
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

def setup_check_logging(keyword: str) -> tuple[logging.Logger, str]:
    """
    check_LLM 로깅을 실행 위치에 생성.
    예) ./기사 재생성/재생성YYYYMMDD/키워드.txt
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

def log_and_print(logger, message: str, level: str = "info"):
    if level == "info":
        logger.info(message)
    elif level == "warning":
        logger.warning(message)
    elif level == "error":
        logger.error(message)
    elif level == "debug":
        logger.debug(message)


def generate_check_prompt() -> str:
    today_kst = get_today_kst_str()

    # f-string 내 JSON 예시의 중괄호는 모두 {{ }} 로 이스케이프 처리
    prompt = (
        f"""사용자가 입력한 두 개의 기사(사용자가 작성한 기사와 원문 기사)를 비교하여 사실관계를 판단하라.
            사용자는 콤마(,)를 사용하여 두 개의 기사를 구분하며, 첫 번째가 사용자가 작성한 기사, 두 번째가 원문 기사이다.
            
            [오늘(KST) 기준일]
            - 오늘 날짜(Asia/Seoul): {today_kst}

            [비교 기준]
            - 완전히 동일한 경우 → "✅ 사실관계에 문제가 없습니다."
            - 표현 방식이 다르지만 의미가 동일한 경우 → "✅ 표현 방식이 다르지만, 사실관계는 일치합니다."
            - 일부 내용이 다르거나 빠진 경우 → "⚠️ 일부 내용이 원문과 다릅니다."
            - 명확한 오류가 있는 경우 → "❌ 사실과 다른 정보가 포함되어 있습니다." + 어떤 부분이 틀렸는지 설명

            [점검 사항]
            1. 원문에 없는 정보를 사용자가 기사에 넣었는지 반드시 확인하라. 사실관계가 확인되지 않은 내용을 임의로 추가했을 경우 '허위 정보'로 간주하라.
            2. 원문 기사에서 '예정', '추진 중', '가능성 있음' 등의 불확정 표현이 사용된 경우, 사용자가 이를 단정적으로 표현했는지 확인하라.
            3. 기업이나 인물 등의 명예 훼손, 오해 유발, 정정보도 요청 가능성 있는 민감한 표현이 포함되어 있다면 반드시 지적하라.
            4. 문장이 간결해졌더라도, 핵심 의미가 왜곡되거나 빠진 부분이 없는지 확인하라.
            
            [시제 관련 예외 사항 - 다음 경우는 사실 오류로 간주하지 말 것]
            1. '지난 O월' '지난 OOOO년' '지난 OO일', '오는 O월' '오는 OOOO년' '오는 OO일' 등의 상대적 시간 표현 사용
            2. '이날', '오늘' 등의 불필요한 시점 표현 생략
            3. 방송일이 1주일 이상 지난 경우 '최근 방송된', '이전 방송에서' 등으로 표현한 경우
            4. 여러 방송일이 있는 경우 가장 최근 방송일을 기준으로 한 시점 조정
            5. 원문과 재생성 기사 내용을 비교했을때 재생성 기사가 [오늘(KST) 기준일]과 비교해 과거/미래 시점으로 정확히 표현한 경우
            
            ✅ 원문에 있지만 사용자가 기사에서 생략해도 문제 삼지 않는다.
            ✅ 위의 시제 관련 예외 사항에 해당하는 경우는 사실 오류로 간주하지 않는다.
            ❌ 사용자가 원문에 없는 내용을 추가하거나 왜곡해 넣은 경우, 반드시 구체적으로 지적하라.

            [응답 형식]
            - 아래 JSON만 정확히 출력하라(그 외 텍스트 금지)
            - corrected_article는 '사실이 아닌 부분만 최소 수정' 원칙으로 작성하라(불필요한 재서술 금지).
            - corrected_article는 반드시 하나의 문자열로 출력하라(객체/배열 금지), [제목]/[해시태그]/[본문] 섹션을 포함할 것.


            [최종 출력: JSON 전용]
            {{
              "verdict": "OK" 또는 "ERROR",
              "nonfactual_phrases": ["문제 구절1", "문제 구절2"],
              "corrected_article": "수정된 전체 기사 (문제가 있을 때만, [제목]/[해시태그]/[본문] 포함)"
            }}"""
    )
    return prompt


def _extract_json_block(text: str):
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


def check_article_facts(generated_article: str, original_article: str, keyword: str = "check_LLM") -> dict:
    logger, log_filepath = setup_check_logging(keyword)

    log_and_print(logger, "\n" + "="*80)
    log_and_print(logger, "🔍 CHECK_LLM - 기사 사실관계 검증 시작")
    log_and_print(logger, "="*80)
    log_and_print(logger, f"\n📥 입력 데이터:")
    log_and_print(logger, f"  - 생성된 기사 길이: {len(generated_article)}자")
    log_and_print(logger, f"  - 원문 기사 길이: {len(original_article)}자")
    log_and_print(logger, f"  - 로그 파일: {log_filepath}")

    try:
        log_and_print(logger, f"\n🤖 AI 모델 호출:")
        system_prompt = generate_check_prompt()
        user_request = f"사용자 기사: {generated_article}, \n\n원문 기사: {original_article}"
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
        response = model.generate_content(contents)
        full_text = response.text.strip()

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
            elif not isinstance(corrected, str):
                corrected = str(corrected)

            json_obj["corrected_article"] = corrected

            result = {
                "explanation": full_text,
                "json": json_obj,
                "error": None
            }

        log_and_print(logger, f"\n📋 최종 반환 결과:")
        log_and_print(logger, f"  - explanation 길이: {len(result['explanation'])}자")
        log_and_print(logger, f"  - json 존재: {result['json'] is not None}")
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

    result = check_article_facts(generated, original, keyword)
    if result["error"]:
        print("❌ 오류:", result["error"])
    else:
        print("\n=== 설명 ===\n", result["explanation"])
        print("\n=== JSON ===\n", json.dumps(result["json"], ensure_ascii=False, indent=2))