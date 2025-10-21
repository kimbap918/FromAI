# chatbot_app.py - AI 챗봇 기반 여행 기사 생성
# ===================================================================================
# 파일명     : chatbot_app.py
# 작성자     : 하승주, 홍석원
# 최초작성일 : 2025-09-04
# 설명       : Google Gemini API를 활용한 여행 기사 자동 생성 모듈
#              사용자 검색어, 장소 데이터, 날씨 정보를 종합하여 자연스러운 기사 작성
# ===================================================================================

import os
import sys
from datetime import datetime
from typing import List, Dict

import google.generativeai as genai
from dotenv import load_dotenv # Re-added

import db_manager
import prompts

def resource_path(relative_path): # Re-added
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# .env 파일에서 환경 변수 로드 (표준 라이브러리 사용)
load_dotenv(dotenv_path=resource_path('.env')) # Re-added

# --- Gemini API 키 설정 ---
API_KEY = os.getenv("GOOGLE_API_KEY") # Re-added
if not API_KEY:
    raise ValueError("GOOGLE_API_KEY 환경 변수가 설정되지 않았습니다. .env 파일을 확인하세요.")
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('models/gemini-2.5-flash')

# =========================
# 유틸
# =========================
def _history_to_block(chat_history: List[Dict[str, str]]) -> str:
    if not chat_history:
        return "(이전 대화 없음)"
    lines = []
    for m in chat_history:
        role = m.get("role", "")
        content = m.get("content", "")
        role_ko = "사용자" if role == "user" else "AI"
        lines.append(f"{role_ko}: {content}")
    return "\n".join(lines)

def _normalize_spaces(text: str) -> str:
    if not text:
        return text
    text = text.replace("\u3000", " ").replace("\u00A0", " ")
    while "  " in text:
        text = text.replace("  ", " ")
    return text

def _build_prompt(
    search_query: str,
    chat_history: List[Dict[str, str]],
    places_json: str,
    weather_info: str,
) -> str:
    current_date = datetime.now().strftime("%Y년 %m월 %d일")
    return prompts.TRAVEL_ARTICLE_PROMPT.format(
        search_query=search_query,
        places_data_json=places_json,
        current_date=current_date,
        weather_info=weather_info or "",
        chat_history_block=_history_to_block(chat_history),
    )

# def _fix_titles(text: str, search_query: str) -> str:
#     lines = text.splitlines()
#     title_count = 0
#     for i, line in enumerate(lines):
#         s = line.strip()
#         if not (s.startswith("제목") or (len(s) > 1 and s[0].isdigit() and s[1] in '.)')) or len(s) > 150:
#             continue

#         title_count += 1
#         num = f"제목{title_count}"

#         body = s
#         if ":" in body: body = body.split(":", 1)[-1]
#         elif ")" in body: body = body.split(")", 1)[-1]
#         elif "." in body: body = body.split(".", 1)[-1]
#         body = body.strip()

#         sub = body.split(",", 1)[-1].strip() if "," in body else (body or "현장감 있는 동선")
        
#         if f"{search_query} 가볼 만한 곳," in body and body.strip().startswith(f"{search_query} 가볼 만한 곳,"):
#             lines[i] = f"{num}: {body}"
#         else:
#             lines[i] = f"{num}: {search_query} 가볼 만한 곳, {sub}"
            
#     return "\n".join(lines)

def _fix_titles(text: str, search_query: str) -> str:

    if not text:
        return text

    lines = text.splitlines()
    title_idx = 0

    def extract_body(s: str) -> str:
        s = s.strip()
        # '제목', '제목1', '1)', '1.' 같은 패턴 처리
        if ":" in s:
            parts = s.split(":", 1)
            # 왼쪽이 라벨 느낌이면 오른쪽만 본문으로
            left = parts[0].strip()
            right = parts[1].strip()
            if left.startswith("제목") or (left[:1].isdigit() and (left[1:2] in [")", "."])):
                return right
        # 숫자 라벨 패턴
        if len(s) >= 2 and s[0].isdigit() and s[1] in ").":
            return s[2:].strip()
        # '제목N' 패턴
        if s.startswith("제목"):
            # '제목' 다음에 숫자나 문자가 와도 콜론이 없으면 '제목'을 라벨로 간주하고 본문만 추출 시도
            # 다만 콜론이 없고 '제목'만 있으면 본문 없음으로 처리
            stripped = s[2:].strip("0123456789). ").strip()
            return stripped if stripped else ""
        return s

    def normalize_spaces(s: str) -> str:
        s = s.replace("\u3000", " ").replace("\u00A0", " ")
        while "  " in s:
            s = s.replace("  ", " ")
        return s.strip()

    for i, line in enumerate(lines):
        s = line.strip()
        # 제목 후보 라인 판별
        is_title_candidate = (
            s.startswith("제목") or
            (len(s) > 1 and s[0].isdigit() and s[1] in '.)')
        )
        if not is_title_candidate:
            continue

        body = extract_body(s)
        body = normalize_spaces(body)

        if not body:
            # 본문이 비면 제목으로 취급하지 않음
            continue

        title_idx += 1
        # ✅ 자연 제목 유지: 접두사/형식 강제 X, 라벨만 통일
        lines[i] = f"제목{title_idx}: {body}"

    return "\n".join(lines)


class TravelChatbot:
    def __init__(self) -> None:
        pass

    def recommend_travel_article(
        self,
        search_query: str,
        chat_history: List[Dict[str, str]],
        places_json: str,
        weather_info: str,
    ) -> str:
        try:
            prompt_text = _build_prompt(
                search_query=search_query,
                chat_history=chat_history,
                places_json=places_json,
                weather_info=weather_info,
            )
            response = model.generate_content(prompt_text)
            text = getattr(response, "text", "") or ""
            text = _normalize_spaces(text)
            text = _fix_titles(text, search_query)
            return text
        except Exception as e:
            return f"죄송해요. 기사를 생성하는 중에 오류가 발생했어요. 다시 시도해주시면 감사하겠습니다! 오류: {e}"

if __name__ == "__main__":
    chatbot = TravelChatbot()
    chat_history: List[Dict[str, str]] = []

    while True:
        user_input = input("\n어떤 지역의 여행 정보를 원하시나요? (종료하려면 'q' 입력)\n> ")
        if user_input.lower() == "q":
            print("👋 다음에 또 만나요!")
            break

        db_path = r"C:\Users\TDI\Desktop\0909_여행&날씨 기사생성기\crw_data\naver_travel_places.db"
        conn, cursor = db_manager.connect_db(db_path)
        if not conn or not db_manager.create_places_table(cursor):
            print("데이터베이스 연결 또는 테이블 생성에 실패했습니다. 크롤링을 먼저 완료했는지 확인해주세요.")
            continue
        conn.close()

        print("\n[INFO] 잠시만 기다려주세요... 여행 기사를 작성하고 있어요...")

        places_json = "{}"
        weather_info = ""

        article = chatbot.recommend_travel_article(
            search_query=user_input,
            chat_history=chat_history,
            places_json=places_json,
            weather_info=weather_info,
        )

        print("\n" + "=" * 50)
        print(article)
        print("=" * 50)

        chat_history.append({"role": "user", "content": user_input})
        chat_history.append({"role": "ai", "content": article})
