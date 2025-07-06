import os
import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
from newspaper import Article
from dotenv import load_dotenv

load_dotenv()
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
    return f"""
            [시스템 메세지]
            단계별로 기사를 작성하고, **출력규칙에 맞게 제목과 본문만 출력하세요.**
            ※ 전체 기사 제목과 본문 다음 표현은 절대 사용하지 않는다: 볼드체(**), 말줄임표(...), 마침표(.), 쌍따옴표(" "), 콜론(:), 마크다운 기호(*, #, &), 감탄문, 질문형 문장, 기자 메일 주소 및 기자명 표기

            1. 본문 생성: 입력된 기사 본문 내용만 사용하여 새로운 기사 본문을 작성한다.
            - 500~1500자 내외로 작성 (단, 제공된 기사가 짧으면 불필요한 내용을 추가하지 않는다.)
            - 기사의 흐름과 논점을 유지하되, 문장이 어색하거나 단절될 경우 문맥에 맞게 재구성할 수 있다. 이때 의미를 왜곡하거나 내용을 과장·추가해서는 안 된다.
            - 특히 첫 번째 문장은 원문과 구분되는 새로운 요약형 문장으로 작성하되, 제공된 기사에서 명시된 사실 중 핵심 인물·조치·배경 정보를 포함한 요약 문장으로 구성한다. (단, 기사 외 정보를 추가하거나 의미를 추측·왜곡하지 않는다.)
            - 주요 흐름과 논란의 쟁점을 왜곡하지 않는다.
            - **인용문은 단어 하나도 변경하지 않는다.**
            - 인용문을 제외한 모든 문장에서 **격식체 종결어미(습니다, 합니다, 입니다 등)**를 **반드시 평서형(했다, 한다, 이다 등)**으로 작성한다.
            - 격식체 표현이 남아 있지 않도록 주의하고, 맞춤법에 맞게 자연스럽게 바꾸어야 하며, 출력 전 반드시 검수한다.
            - 다음은 자주 사용되는 예시이며, 문맥에 따라 적용해야 한다:
                - "입니다" →  "이다" 또는 "다" 
                - "했습니다" → "했다"
                - "합니다" → "한다"
                - "없습니다" → "없다"
                - "되었다" 및 "되었습니다"→ "됐다"
            - 모든 문장은 국립국어원 맞춤법 기준을 준수해야 하며, 띄어쓰기나 어색한 표현이 없도록 주의한다.
            - **볼드체(굵은 글씨,**) 사용 금지.**  
            - 본문은 반드시 세 문장마다 줄바꿈한다. (**입력 내용이 짧아도 이 규칙은 동일하게 적용하며, 줄바꿈은 시각적 구분을 위한 것이다.**)

            2. 제목 생성
            - 작성된 본문을 바탕으로 제목을 창의적으로 작성한다.
            - 제공된 기사 제목의 핵심 내용을 참고하되, 본문에서 드러난 핵심 주제를 우선 반영한다.
            - 입력된 키워드를 최대한 앞쪽에 배치하고, 관련성이 적어도 자연스럽게 포함되도록 작성한다.
            - 제공된 제목을 그대로 사용하는 것은 금지한다.
            - 궁금증을 유발하는 표현 금지 (예: '?', '왜', '어떻게', '무엇이' 등 사용 금지)
            - 부정적인 표현을 긍정적인 방향으로 조정한다.

            3. 제목 및 본문 검토 
            - 맞춤법 및 띄어쓰기 준수 여부를 확인하고, 문장이 자연스럽도록 수정
            - 제목과 본문에서 금지된 표현(볼드체(**, 굵은글씨), 말줄임표(...), 마침표(.), 쌍따옴표(" "), 콜론(:), 마크다운 기호(*, #, &), 감탄문, 질문형 문장, 기자 메일 주소 및 기자명 표기) 사용 여부 확인 및 수정
            - 제공된 정보 외 추측·허구·외부 자료 추가 여부 검토 후 수정
            - **인용문 외에서 격식체 종결어미 사용여부 확인 후,  평서형 종결어미로 변경한다.**  (예: "입니다" → "이다" or "다", "했습니다" → "했다", "합니다" → "한다", "되었다" 및 "되었습니다"→ "됐다")

            4. 출력규칙
            - 제목과 본문을 출력하세요.  
            - 생성된 텍스트 외 다른 문장은 출력하지 않는다  
            - 첫 줄: 제목  
            - 두 번째 줄부터: 본문
            - 저희는 첫 줄을 제목으로 인식하고, 두 번째 줄부터 본문으로 인식합니다.
"""


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

        return {
            "url": url,
            "keyword": keyword,
            "title": title,
            "original_body": body,
            "generated_article": article_text,
            "error": None
        }
    except Exception as e:
        return {
            "url": url,
            "keyword": keyword,
            "title": "",
            "original_body": "",
            "generated_article": "",
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
