import google.generativeai as genai
import os
import sys
from PIL import Image
from dotenv import load_dotenv
# 절대경로 import로 수정
from news.src.utils.capture_utils import get_today_kst_str, build_stock_prompt

# .env 파일 경로를 빌드/개발 환경 모두에서 안전하게 지정
if hasattr(sys, '_MEIPASS'):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(os.path.abspath(__file__))

dotenv_path = os.path.join(base_path, '.env')
if not os.path.exists(dotenv_path):
    dotenv_path = os.path.join(os.getcwd(), '.env')

load_dotenv(dotenv_path)
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

BASE_SYSTEM_PROMPT = (
    """
    [System Message]
    사용자가 키워드, 텍스트 정보, 그리고 관련 이미지를 제공합니다.
    당신은 제공된 모든 정보를 종합적으로 분석하여 독자가 이해하기 쉬운 기사 문체로 작성하는 데이터 기반 정보 전달 전문 기자입니다.
    날씨, 주식, 환율, 복권 등 다양한 주제의 데이터를 이미지로 받아 해석하여 독자가 이해하기 쉽고 객관적인 정보를 전달하는 기사를 작성합니다.
    해당 메세지를 읽고 나서 아래의 [News Generation Process (Step-by-Step Execution)], [Special Rules for...]를 순서대로 읽은 후 [Output Format]에 따라 출력합니다.

    [News Generation Process (Step-by-Step Execution)]
    1. 제공된 정보 인식 및 유효성 검증
    - 사용자가 입력한 키워드, 텍스트 데이터, 이미지를 수집합니다.
    - 제공된 데이터가 충분하지 않거나 유효하지 않다면, 해당 정보는 기사에 포함하지 않거나 '정보 부족'으로 처리합니다. 없는 정보를 임의로 생성하거나 추측하지 않습니다.

    2. 텍스트 정보 분석
    - 제공된 텍스트 데이터의 핵심 내용을 파악하고, 포함된 수치나 날짜 정보를 정확하게 분석합니다.
    - 날짜 정보가 포함된 경우, 기사 작성 시점을 고려하여 시제를 적절히 반영합니다.

    3. 이미지 분석 (이미지 제공 시)
    - 제공된 이미지에서 시각적 정보를 분석합니다. (예: 차트의 추세, 주요 패턴, 시각적으로 명확한 수치 등)
    - 이미지에서 추출된 시각적 정보와 텍스트로 제공된 수치 정보가 상충할 경우, 텍스트로 명시된 수치 정보를 우선적으로 활용하여 기사를 작성합니다.

    4. 본문 작성 (종합 분석 기반)
    - 텍스트 정보와 이미지 분석 결과를 종합하여 객관적인 정보를 전달하는 기사 형식으로 작성합니다.
    - 문장의 연결을 자연스럽게 하며 뉴스 문체 (~이다, ~했다 체 사용)를 일관되게 사용합니다.
    - 핵심 요약으로 시작: 기사 첫 문단에 현재 시점의 가장 중요한 정보(핵심 현상, 주요 수치 등)를 요약하여 제시합니다.
    - 서사적 설명: 데이터를 단순히 나열하지 않고, 논리적인 순서나 시간의 흐름에 따라 자연스러운 이야기로 풀어 설명합니다.
    - 객관성 유지: 제공된 데이터에만 기반하여 사실을 전달하며, 과장되거나 편향된 내용은 배제합니다. 불확실한 정보에 대한 추측성 표현('~일 것으로 보인다', '~으로 예상된다')은 사용하지 않습니다. (이 부분은 주식 특화 프롬프트에서 조절)
    - 가독성 원칙 준수: 전문 용어를 사용할 경우, 독자의 이해를 돕기 위해 필요한 경우 간결한 부연 설명을 덧붙입니다.
    - 입력된 키워드를 3~5회 자연스럽게 포함합니다.
    - 볼드체, 기울임체 등 서식은 사용하지 않습니다.
    - Markdown 문법은 사용하지 않습니다.

    5. 제목 작성 방식
    - 생성된 본문을 기반으로 추천 제목 3개 제공
    - 입력된 키워드를 최대한 제목 앞쪽에 배치
    - 완전한 문장형이 아닌 핵심 키워드 중심으로 구성
    - 궁금증을 유발할 수 있도록 작성하되, 특수문자 없이 표현
    - 말줄임표 "⋯", 마침표(.) 사용 금지, 특수문자 (?, !, " 등) 사용 금지

    6. 출력 형식 적용 (최종 제공)
    기사 생성 후, 아래 출력 형식에 맞춰 제공

    [Output Format]
    - 제목 (3개 제공, 각 제목 당 최대 35자 내외)
    - 본문 (최소 300자 이상, 최대 1000자 이하)
    - 해시태그 (5개 내외, 기사의 핵심 키워드만 포함)
"""
)


def build_system_prompt(keyword, today_kst, is_stock=False):
    prompt = BASE_SYSTEM_PROMPT.format(keyword=keyword, today_kst=today_kst)
    if is_stock:
        stock_prompt = build_stock_prompt(today_kst)
        prompt += "\n" + stock_prompt
        print(prompt)
    return prompt



def generate_info_news(keyword: str, image_path: str, is_stock: bool):
    """
    주식 관련 이미지를 LLM(Gemini Vision)에 입력하여 기사 생성.
    :param stock_name: 주식명 또는 키워드
    :param image_path: 캡처 이미지 경로
    :return: LLM이 생성한 기사(제목, 본문, 해시태그)
    """
    today_kst = get_today_kst_str()
    system_prompt = build_system_prompt(keyword, today_kst, is_stock=is_stock)

    user_message = f"아래 이미지는 '{keyword}' 관련 이미지 입니다. 이미지의 내용을 면밀히 분석해 기사 형식으로 작성하세요."


    model = genai.GenerativeModel(
        model_name='gemini-2.5-flash',
        system_instruction=system_prompt
    )

    try:
        img = Image.open(image_path)
        response = model.generate_content([
            user_message,
            img
        ])
        return response.text
    except Exception as e:
        print(f"Gemini Vision API 호출 중 오류 발생: {e}")
        return None


def generate_info_news_from_text(keyword: str, info_dict: dict, domain: str = "generic"):
    """
    도메인(주식, 환율, 코인 등)에 상관없이 정보성 뉴스 생성 (info_dict는 도메인별로 정제된 데이터)
    """
    today_kst = get_today_kst_str()
    system_prompt = build_system_prompt(keyword, today_kst, is_stock=(domain=="stock"))

    # 도메인별 프롬프트/정보 포맷 분기
    if domain == "stock":
        info_str = "\n".join([f"{k}: {v}" for k, v in info_dict.items()])
        user_message = (
            f"아래는 '{keyword}'의 주식 시세 및 재무정보입니다. "
            f"이 데이터는 모두 '{keyword}'(회사)의 실제 시세 및 재무정보입니다. "
            f"이 데이터를 바탕으로 기사 형식으로 분석해 주세요.\n"
            f"[주식 정보]\n{info_str}"
        )
    elif domain == "fx":
        info_str = "\n".join([f"{k}: {v}" for k, v in info_dict.items()])
        user_message = (
            f"아래는 '{keyword}'의 환율 정보입니다. "
            f"이 데이터는 모두 '{keyword}'(통화)의 실제 환율 정보입니다. "
            f"이 데이터를 바탕으로 기사 형식으로 분석해 주세요.\n"
            f"[환율 정보]\n{info_str}"
        )
    elif domain == "coin":
        info_str = "\n".join([f"{k}: {v}" for k, v in info_dict.items()])
        user_message = (
            f"아래는 '{keyword}'의 암호화폐(코인) 정보입니다. "
            f"이 데이터는 모두 '{keyword}'(코인)의 실제 시세 및 정보입니다. "
            f"이 데이터를 바탕으로 기사 형식으로 분석해 주세요.\n"
            f"[코인 정보]\n{info_str}"
        )
    else:
        info_str = "\n".join([f"{k}: {v}" for k, v in info_dict.items()])
        user_message = (
            f"아래는 '{keyword}'의 정보입니다. "
            f"이 데이터를 바탕으로 기사 형식으로 분석해 주세요.\n"
            f"[정보]\n{info_str}"
        )

    print("\n[키워드 정보(user message)]\n" + user_message + "\n")

    model = genai.GenerativeModel(
        model_name='gemini-2.5-flash',
        system_instruction=system_prompt
    )

    response = model.generate_content(user_message)
    print("[LLM 응답 결과]\n" + response.text + "\n")
    return response.text