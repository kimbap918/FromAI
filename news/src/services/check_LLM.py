import os
import sys
import google.generativeai as genai
from dotenv import load_dotenv

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


def generate_check_prompt() -> str:
    prompt = (
        """사용자가 입력한 두 개의 기사(사용자가 작성한 기사와 원문 기사)를 비교하여 사실관계를 판단하라.
            사용자는 콤마(,)를 사용하여 두 개의 기사를 구분하며, 첫 번째가 사용자가 작성한 기사, 두 번째가 원문 기사이다.
            비교 기준:
            - 완전히 동일한 경우 → "✅ 사실관계에 문제가 없습니다."
            - 표현 방식이 다르지만 의미가 동일한 경우 → "✅ 표현 방식이 다르지만, 사실관계는 일치합니다."
            - 일부 내용이 다르거나 빠진 경우 → "⚠️ 일부 내용이 원문과 다릅니다." + 차이점 간략 요약
            - 명확한 오류가 있는 경우 → "❌ 사실과 다른 정보가 포함되어 있습니다." + 어떤 부분이 틀렸는지 설명

            또한 다음 항목들도 반드시 점검하라:
            1. 원문에 없는 정보를 사용자가 기사에 넣었는지 반드시 확인하라. 사실관계가 확인되지 않은 내용을 임의로 추가했을 경우 '허위 정보'로 간주하라.
            2. 원문 기사에서 '예정', '추진 중', '가능성 있음' 등의 불확정 표현이 사용된 경우, 사용자가 이를 단정적으로 표현했는지 확인하라. → 이 경우도 허위 정보로 판단하라.
            3. 기업이나 인물 등의 명예 훼손, 오해 유발, 정정보도 요청 가능성 있는 민감한 표현이 포함되어 있다면 반드시 지적하라.
            4. 문장이 간결해졌더라도, 핵심 의미가 왜곡되거나 빠진 부분이 없는지 확인하라.

            ✅ 원문에 있지만 사용자가 기사에서 생략해도 문제 삼지 않는다.
            ❌ 하지만 사용자가 원문에 없는 내용을 추가하거나 왜곡해 넣은 경우, 반드시 구체적으로 지적하라.

            응답은 간결하고 명확하게 작성하되, 문제 되는 표현은 구체적으로 인용하여 설명하라."""
    )
    return prompt

# 원문 + 생성된 본문 + 틀린 부분을



def check_article_facts(generated_article: str, original_article: str) -> dict:
    """
    생성된 기사와 원문 기사를 비교하여 사실관계를 검증합니다.
    
    Args:
        generated_article (str): 사용자가 작성한 기사
        original_article (str): 원문 기사
        
    Returns:
        dict: 검증 결과를 담은 딕셔너리
    """
    try:
        system_prompt = generate_check_prompt()
        user_request = f"사용자 기사: {generated_article}\n\n원문 기사: {original_article}"

        contents = [
            {'role': 'user', 'parts': [{'text': system_prompt}]},
            {'role': 'model', 'parts': [{'text': '이해했습니다. 두 기사를 비교하여 사실관계를 검증하겠습니다.'}]},
            {'role': 'user', 'parts': [{'text': user_request}]}
        ]

        response = model.generate_content(contents)
        check_result = response.text.strip()

        return {
            "generated_article": generated_article,
            "original_article": original_article,
            "check_result": check_result,
            "error": None
        }
    except Exception as e:
        return {
            "generated_article": generated_article,
            "original_article": original_article,
            "check_result": "",
            "error": str(e)
        }


if __name__ == "__main__":
    print("🔍 기사 사실관계 검증 프로그램")
    print("생성된 기사와 원문 기사를 비교하여 사실관계를 검증합니다.")
    
    generated = input("생성된 기사를 입력하세요: ").strip()
    original = input("원문 기사를 입력하세요: ").strip()

    result = check_article_facts(generated, original)

    if result["error"]:
        print("❌ 오류 발생:", result["error"])
    else:
        print("\n✅ 검증 완료:")
        print("\n📝 검증 결과:\n")
        print(result["check_result"]) 