import os
import sys
import json
import re
import google.generativeai as genai
from dotenv import load_dotenv
from datetime import datetime
import logging

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


def setup_check_logging(keyword: str) -> tuple:
    """
    check_LLM용 로그 폴더와 파일을 설정하고 로거를 반환합니다.
    키워드별 텍스트 파일에 추가로 기록합니다.
    """
    # 현재 날짜로 폴더명 생성
    current_date = datetime.now().strftime("%Y%m%d")
    
    # exe 빌드 시와 개발 시를 구분하여 경로 설정
    if getattr(sys, 'frozen', False):
        # exe 빌드 시: 실행 파일이 있는 디렉토리
        base_dir = os.path.dirname(sys.executable)
    else:
        # 개발 시: 현재 스크립트 위치에서 상위로 이동하여 FromAI1.1.3 2 찾기
        current_dir = os.path.dirname(os.path.dirname(__file__))  # news/src/services -> news/
        base_dir = current_dir
        
        # FromAI1.1.3 2 폴더를 찾을 때까지 상위 디렉토리로 이동
        while base_dir and not os.path.exists(os.path.join(base_dir, "FromAI1.1.3 2")):
            parent_dir = os.path.dirname(base_dir)
            if parent_dir == base_dir:  # 루트 디렉토리에 도달
                break
            base_dir = parent_dir
        
        # FromAI1.1.3 2 폴더가 없으면 현재 디렉토리 사용
        if not os.path.exists(os.path.join(base_dir, "FromAI1.1.3 2")):
            base_dir = current_dir
    
    # 폴더 경로 생성
    if getattr(sys, 'frozen', False):
        # exe 빌드 시: 실행 파일 루트에 직접 생성
        log_dir = os.path.join(base_dir, "기사 재생성", f"재생성{current_date}")
    else:
        # 개발 시: FromAI1.1.3 2 폴더 아래에 생성
        log_dir = os.path.join(base_dir, "FromAI1.1.3 2", "기사 재생성", f"재생성{current_date}")
    
    # 폴더 생성
    os.makedirs(log_dir, exist_ok=True)
    
    # 키워드로 파일명 생성 (특수문자 제거)
    safe_keyword = "".join(c for c in keyword if c.isalnum() or c in (' ', '-', '_')).strip()
    safe_keyword = safe_keyword.replace(' ', '_')
    
    # 로그 파일명 생성 - 키워드별 파일에 추가 기록
    log_filename = f"{safe_keyword}.txt"
    log_filepath = os.path.join(log_dir, log_filename)
    
    # 로거 설정
    logger = logging.getLogger(f"check_llm_{keyword}_{datetime.now().strftime('%H%M%S')}")
    logger.setLevel(logging.INFO)
    
    # 파일 핸들러 설정 (텍스트 파일에 추가 기록)
    file_handler = logging.FileHandler(log_filepath, encoding='utf-8', mode='a')  # 'a' 모드로 추가 기록
    file_handler.setLevel(logging.INFO)
    
    # 콘솔 핸들러 설정
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 포맷터 설정 (콘솔용과 파일용을 다르게)
    console_formatter = logging.Formatter('%(message)s')  # 콘솔에는 메시지만
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')  # 파일에는 시간 포함
    
    file_handler.setFormatter(file_formatter)
    console_handler.setFormatter(console_formatter)
    
    # 핸들러 추가
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger, log_filepath


def log_and_print(logger, message: str, level: str = "info"):
    """
    로그와 콘솔에 동시에 메시지를 출력합니다.
    """
    if level == "info":
        logger.info(message)
    elif level == "warning":
        logger.warning(message)
    elif level == "error":
        logger.error(message)
    elif level == "debug":
        logger.debug(message)


def generate_check_prompt() -> str:
    prompt = (
        """사용자가 입력한 두 개의 기사(사용자가 작성한 기사와 원문 기사)를 비교하여 사실관계를 판단하라.
            사용자는 콤마(,)를 사용하여 두 개의 기사를 구분하며, 첫 번째가 사용자가 작성한 기사, 두 번째가 원문 기사이다.
            비교 기준:
            - 완전히 동일한 경우 → "✅ 사실관계에 문제가 없습니다."
            - 표현 방식이 다르지만 의미가 동일한 경우 → "✅ 표현 방식이 다르지만, 사실관계는 일치합니다."
            - 일부 내용이 다르거나 빠진 경우 → "⚠️ 일부 내용이 원문과 다릅니다."
            - 명확한 오류가 있는 경우 → "❌ 사실과 다른 정보가 포함되어 있습니다." + 어떤 부분이 틀렸는지 설명

            또한 다음 항목들도 반드시 점검하라:
            1. 원문에 없는 정보를 사용자가 기사에 넣었는지 반드시 확인하라. 사실관계가 확인되지 않은 내용을 임의로 추가했을 경우 '허위 정보'로 간주하라.
            2. 원문 기사에서 '예정', '추진 중', '가능성 있음' 등의 불확정 표현이 사용된 경우, 사용자가 이를 단정적으로 표현했는지 확인하라. → 이 경우도 허위 정보로 판단하라.
            3. 기업이나 인물 등의 명예 훼손, 오해 유발, 정정보도 요청 가능성 있는 민감한 표현이 포함되어 있다면 반드시 지적하라.
            4. 문장이 간결해졌더라도, 핵심 의미가 왜곡되거나 빠진 부분이 없는지 확인하라.

            ✅ 원문에 있지만 사용자가 기사에서 생략해도 문제 삼지 않는다.
            ❌ 하지만 사용자가 원문에 없는 내용을 추가하거나 왜곡해 넣은 경우, 반드시 구체적으로 지적하라.

            응답은 간결하고 명확하게 작성하되, 문제 되는 표현은 구체적으로 인용하여 설명하라.
            JSON 외의 추가 요약(간략 요약, 개요 등)은 포함하지 마라.
            
            마지막에 아래 JSON 형식만 정확히 제공하라(그 외 텍스트 금지):
            {
              "verdict": "OK" 또는 "ERROR",
              "nonfactual_phrases": ["문제 구절1", "문제 구절2"],
              "corrected_article": "수정된 전체 기사 (문제가 있을 때만)"
            }"""
    )
    return prompt


def _extract_json_block(text: str):
    # ```json ... ``` 또는 가장 큰 {} 블록을 파싱
    # 1) 코드펜스 우선
    fence = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text)
    if fence:
        try:
            return json.loads(fence.group(1))
        except Exception:
            pass
    # 2) 최대 중괄호 블록 파싱(보수적으로)
    braces = re.findall(r"(\{[\s\S]*\})", text)
    for blk in braces[::-1]:
        try:
            return json.loads(blk)
        except Exception:
            continue
    return None


def check_article_facts(generated_article: str, original_article: str, keyword: str = "check_LLM") -> dict:
    """
    생성된 기사와 원문 기사를 비교하여 사실관계를 검증하고,
    문제가 있으면 '사실 아닌 부분만' 수정한 corrected_article을 JSON으로 반환.
    """
    # 로거 설정
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
        
        # 전체 프롬프트 내용을 로그에 저장
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
        
        
        # 전체 AI 응답 내용을 로그에 저장
        log_and_print(logger, f"\n📋 전체 AI 응답:")
        log_and_print(logger, f"{'='*80}")
        log_and_print(logger, full_text)
        log_and_print(logger, f"{'='*80}")
        
        log_and_print(logger, f"\n🔍 JSON 파싱 시도:")
        json_obj = _extract_json_block(full_text)
        
        if json_obj:
            log_and_print(logger, f"  ✅ JSON 파싱 성공")
            log_and_print(logger, f"  - verdict: {json_obj.get('verdict', 'N/A')}")
            log_and_print(logger, f"  - nonfactual_phrases 개수: {len(json_obj.get('nonfactual_phrases', []))}")
            log_and_print(logger, f"  - corrected_article 길이: {len(json_obj.get('corrected_article', ''))}자")
        else:
            log_and_print(logger, f"  ❌ JSON 파싱 실패")

        # 안전장치
        if not json_obj or "verdict" not in json_obj:
            log_and_print(logger, f"\n⚠️ JSON 검증 실패 - 기본값 반환", "warning")
            result = {
                "explanation": full_text,
                "json": None,
                "error": "JSON 파싱 실패"
            }
        else:
            log_and_print(logger, f"\n✅ 검증 완료 - 정상 결과 반환")
            result = {
                "explanation": full_text,
                "json": json_obj,
                "error": None
            }
        
        log_and_print(logger, f"\n📋 최종 반환 결과:")
        log_and_print(logger, f"  - explanation 길이: {len(result['explanation'])}자")
        log_and_print(logger, f"  - json 존재: {result['json'] is not None}")
        log_and_print(logger, f"  - error: {result['error']}")
        
        # 최종 결과를 로그 파일에 저장
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