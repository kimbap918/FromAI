# chatbot_app.py - AI 챗봇 기반 여행 기사 생성
# ===================================================================================
# 파일명     : chatbot_app.py
# 작성자     : 하승주, 홍석원
# 최초작성일 : 2025-09-04
# 설명       : Google Gemini API를 활용한 여행 기사 자동 생성 모듈
#              사용자 검색어, 장소 데이터, 날씨 정보를 종합하여 자연스러운 기사 작성
# ===================================================================================
#
# 【주요 기능】
# - Google Gemini 2.5 Flash 모델을 활용한 여행 기사 자동 생성
# - 사용자 검색어, 장소 데이터, 날씨 정보를 종합하여 자연스러운 기사 작성
# - 대화 히스토리 관리로 연속적인 대화 지원
# - 제목 형식 자동 교정 기능 (_fix_titles)
# - 텍스트 정규화 (전각공백/NBSP 변환, 과도한 공백 정리)
#
# 【작동 방식】
# 1. 환경변수에서 Google API 키 로드
# 2. 사용자 입력(검색어)과 선택된 장소 데이터를 JSON으로 받음
# 3. 선택적으로 날씨 정보 포함 가능
# 4. prompts.py의 문자열 템플릿(TRAVEL_ARTICLE_PROMPT)을 기반으로 프롬프트 구성
# 5. Gemini API 호출하여 기사 생성
# 6. 텍스트 정규화 및 제목 형식 교정 적용
# 7. 생성된 기사를 텍스트로 반환
#
# 【입력 데이터】
# - search_query: 사용자 검색어 (예: "부산 해운대")
# - places_json: 선택된 장소들의 JSON 데이터 (문자열 형태)
# - weather_info: 날씨 정보 텍스트 (선택적)
# - chat_history: 이전 대화 기록 (List[Dict], {"role":"user"/"ai", "content":...})
#
# 【출력 형식】
# - 제목 3개 + 본문 + 해시태그 형태의 완성된 여행 기사
# - 객관적이고 정보성 있는 뉴스 스타일 문체
# - 제목은 "{search_query} 가볼 만한 곳, [부제]" 형식으로 자동 교정
#
# 【핵심 클래스 및 함수】
# - TravelChatbot: 메인 챗봇 클래스
#   - recommend_travel_article(): 여행 기사 생성 메인 함수
# - _build_prompt(): prompts.py 템플릿에 데이터 삽입
# - _fix_titles(): 제목 형식 자동 교정
# - _normalize_spaces(): 텍스트 정규화 (공백 처리)
# - _history_to_block(): 대화 기록을 문자열 블록으로 변환
#
# 【의존성】
# - prompts.py: 기사 생성용 프롬프트 템플릿
# - db_manager.py: 데이터베이스 연결 관리 (CLI 테스트용)
# - Google Generative AI: Gemini 2.5 Flash 모델 사용
# - python-dotenv: 환경변수 관리
#
# 【CLI 테스트】
# - 메인 실행 시 대화형 테스트 모드 제공
# - 데이터베이스 연결 체크 포함
# - 대화 히스토리 누적 관리
# ===================================================================================

import os
from datetime import datetime
from typing import List, Dict

import google.generativeai as genai
from dotenv import load_dotenv


# DB 및 프롬프트 관리 모듈 임포트
import db_manager
import prompts

# .env 파일에서 환경 변수 로드
load_dotenv()

# --- Gemini API 키 설정 ---
API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    raise ValueError("GOOGLE_API_KEY 환경 변수가 설정되지 않았습니다. .env 파일을 확인하세요.")
genai.configure(api_key=API_KEY) # type: ignore 
model = genai.GenerativeModel('models/gemini-2.5-flash') # type: ignore 



# =========================
# 유틸
# =========================
def _history_to_block(chat_history: List[Dict[str, str]]) -> str:
    """
    대화 기록(chat_history)을 문자열 블록으로 변환.
    ex)
    [{"role":"user","content":"서울 여행 기사"}, {"role":"ai","content":"..."}]
    -> 
    사용자: 서울 여행 기사
    AI: ...
    """
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
    """전각 공백/nbsp 치환 및 과도한 공백 정리"""
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
    """
    prompts.py에 정의된 TRAVEL_ARTICLE_PROMPT 문자열에
    실제 데이터(search_query, places_json, weather_info 등)를 삽입해서
    최종 프롬프트 텍스트를 생성.
    """
    current_date = datetime.now().strftime("%Y년 %m월 %d일")
    return prompts.TRAVEL_ARTICLE_PROMPT.format(
        search_query=search_query,
        places_data_json=places_json,
        current_date=current_date,
        weather_info=weather_info or "",
        chat_history_block=_history_to_block(chat_history),
    )

def _fix_titles(text: str, search_query: str) -> str:
    """
    모델이 잘못된 제목을 출력할 경우 강제로 교정.
    - 반드시 "{search_query} 가볼 만한 곳, ..." 형식으로 제목을 수정
    - '추천 여행지 가볼 만한 곳, ...' 같은 잘못된 prefix를 보정
    """
    lines = text.splitlines()
    title_count = 0
    for i, line in enumerate(lines):
        s = line.strip()
        # '제목'으로 시작하거나, '숫자)'/'숫자.'로 시작하는 줄을 제목 후보로 간주
        # 단, 길이가 너무 길면 본문으로 판단하여 제외
        if not (s.startswith("제목") or (len(s) > 1 and s[0].isdigit() and s[1] in '.)')) or len(s) > 150:
            continue

        title_count += 1
        
        # 제목 형식 통일을 위해 '제목N:' 접두사 준비
        num = f"제목{title_count}"

        # 기존 내용에서 실제 내용(body) 추출
        body = s
        if ":" in body: body = body.split(":", 1)[-1]
        elif ")" in body: body = body.split(")", 1)[-1]
        elif "." in body: body = body.split(".", 1)[-1]
        body = body.strip()

        # 부제(sub) 추출
        sub = body.split(",", 1)[-1].strip() if "," in body else (body or "현장감 있는 동선")
        
        # 이미 올바른 포맷이면 형식만 통일해서 유지
        if f"{search_query} 가볼 만한 곳," in body and body.strip().startswith(f"{search_query} 가볼 만한 곳,"):
            lines[i] = f"{num}: {body}"
        else:
            # 잘못된 제목 교정
            lines[i] = f"{num}: {search_query} 가볼 만한 곳, {sub}"
            
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
        """
        사용자 입력(검색어), 대화 기록, 선택된 장소 데이터(JSON)를 바탕으로
        Gemini API를 통해 여행 기사를 생성한다.
        """
        try:
            prompt_text = _build_prompt(
                search_query=search_query,
                chat_history=chat_history,
                places_json=places_json,
                weather_info=weather_info,
            )
            response = model.generate_content(prompt_text)  # type: ignore
            text = getattr(response, "text", "") or ""
            text = _normalize_spaces(text)
            text = _fix_titles(text, search_query)  # ← 제목 보정
            return text
        except Exception as e:
            return f"죄송해요. 기사를 생성하는 중에 오류가 발생했어요. 다시 시도해주시면 감사하겠습니다! 오류: {e}"

# =========================
# 메인 실행 (CLI 테스트용)
# =========================
if __name__ == "__main__":
    chatbot = TravelChatbot()
    chat_history: List[Dict[str, str]] = []

    while True:
        user_input = input("\n어떤 지역의 여행 정보를 원하시나요? (종료하려면 'q' 입력)\n> ")
        if user_input.lower() == "q":
            print("👋 다음에 또 만나요!")
            break

        # DB 연결 체크 (선택)
        db_path = r"C:\Users\TDI\Desktop\0909_여행&날씨 기사생성기\crw_data\naver_travel_places.db"
        conn, cursor = db_manager.connect_db(db_path)
        if not conn or not db_manager.create_places_table(cursor):
            print("데이터베이스 연결 또는 테이블 생성에 실패했습니다. 크롤링을 먼저 완료했는지 확인해주세요.")
            continue
        conn.close()

        print("\n[INFO] 잠시만 기다려주세요... 여행 기사를 작성하고 있어요...")

        # 실제 앱에서는 선택된 장소 JSON/날씨 텍스트를 전달하세요.
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

        # 히스토리 dict로 저장
        chat_history.append({"role": "user", "content": user_input})
        chat_history.append({"role": "ai", "content": article})