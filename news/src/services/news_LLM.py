import os
import sys
import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
from newspaper import Article
from dotenv import load_dotenv
try:
    from . import check_LLM
except ImportError:
    import check_LLM

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


def extract_title_and_body(url):
    article = Article(url, language='ko')
    article.download()
    article.parse()
    title = article.title.strip()
    body = article.text.strip()
    if len(body) < 50:
        print("📌 본문이 짧아 fallback으로 전환합니다.")
        title, body = extract_naver_cp_article(url)
    return title, body

def extract_naver_cp_article(url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, 'html.parser')
    title_tag = soup.select_one('h2.media_end_head_headline')
    title = title_tag.text.strip() if title_tag else "제목 없음"
    body_area = soup.select_one('article#dic_area')
    body = body_area.get_text(separator="\n").strip() if body_area else "본문 없음"
    return title, body

def generate_system_prompt(keyword: str) -> str:
    prompt = (
    """[시스템 메세지]
        키워드, 기사 제목,  본문 순으로 사용자가 입력한다.
        단계별로 기사를 작성하고, **출력 형식에 맞게 출력한다.**

        1. 제목 생성
        - 제공된 기사 제목을 인용하고, 생성된 본문을 반영하여 **추천 제목 3개**를 생성한다.
        - 입력된 키워드를 최대한 앞쪽에 배치하고, 관련성이 적어도 자연스럽게 포함되도록 작성한다.
        - 궁금증을 유발하는 표현 금지 (예: '?', '왜', '어떻게', '무엇이' 등 사용 금지)
        - 사용 금지 기호: 마침표(.), 쌍따옴표(" "), 말줄임표(...), 콜론(:), 마크다운 기호(*, #, &)
        - 부정적인 표현을 긍정적인 방향으로 조정한다.

        2. 본문 생성: 입력된 기사 본문 내용만 사용하여 새로운 기사 본문을 작성한다.
        - 500~1000자 내외로 작성 (단, 제공된 기사가 짧으면 불필요한 내용을 추가하지 않는다.)
        - 기사의 흐름과 논점을 유지하고, 의미를 변형하지 않는다.
        - 주요 흐름과 논란의 쟁점을 왜곡하지 않는다.
        - **인용문은 단어 하나도 변경하지 않는다.**
        - 격식체 종결어미 금지 (예: "입니다" → "이다", "했습니다" → "했다", "합니다" → "한다")
        - 맞춤법을 준수하고, 부적절한 표현 수정한다.
        -  제목과 본문에서 **'...' 사용 금지.**  
        - **볼드체(굵은 글씨) 사용 금지.**  

        3. 제목 및 본문 검토 
        -  제목과 본문에서 **금지된 기호(…, *, , #, &) 사용 여부 확인 및 수정
        - 제공된 정보 외 추측·허구·외부 자료 추가 여부 검토 후 수정

        4. 키워드 생성
        - 생성된 본문을 기반으로 5개 내외의 핵심 키워드를 추출한다.

        5. 출력형식에 맞게 출력한다.  
        [출력 형식]  
        - 생성된 제목 3개  
        - 생성된 본문
        - 해시태그 5개 내외"""
    )
    return prompt



def generate_article(state: dict) -> dict:
    url = state.get("url")
    keyword = state.get("keyword")

    try:
        title, body = extract_title_and_body(url)
        system_prompt = generate_system_prompt(keyword)
        user_request = f"키워드: {keyword}\n제목: {title}\n본문: {body}"

        contents = [
            {'role': 'user', 'parts': [{'text': system_prompt}]},
            {'role': 'model', 'parts': [{'text': '이해했습니다. 규칙을 따르겠습니다.'}]},
            {'role': 'user', 'parts': [{'text': user_request}]}
        ]


        response = model.generate_content(contents)
        article_text = response.text.strip()

        # 사실관계 검증 수행
        fact_check_result = check_LLM.check_article_facts(article_text, body)

        return {
            "url": url,
            "keyword": keyword,
            "title": title,
            "original_body": body,
            "generated_article": article_text,
            "fact_check_result": fact_check_result["check_result"] if fact_check_result["error"] is None else f"검증 오류: {fact_check_result['error']}",
            "error": None
        }
    except Exception as e:
        return {
            "url": url,
            "keyword": keyword,
            "title": "",
            "original_body": "",
            "generated_article": "",
            "fact_check_result": "",
            "error": str(e)
        }

if __name__ == "__main__":
    print("🔗 기사 URL과 키워드를 입력하면 Gemini가 재작성한 기사로 변환해줍니다.")
    url = input("기사 URL을 입력하세요: ").strip()
    keyword = input("핵심 키워드를 입력하세요: ").strip()

    result = generate_article({"url": url, "keyword": keyword})

    if result["error"]:
        print("❌ 오류 발생:", result["error"])
    else:
        print("\n✅ 기사 재작성 완료:")
        print("\n📌 원제목:", result["title"])
        print("\n📝 재작성 기사:\n")
        print(result["generated_article"])
        print("\n🔍 사실관계 검증 결과:\n")
        print(result["fact_check_result"])
