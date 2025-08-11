# AI 챗봇과의 상호작용 및 기사 생성을 담당합니다.
# 파일명: chatbot_app.py

import os
import re
import random
import google.generativeai as genai
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage

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
model = genai.GenerativeModel('models/gemini-2.5-flash-lite') # type: ignore 

class TravelChatbot:
    def __init__(self):
        # 챗봇 초기 설정
        pass

    # ✅ [수정] chat_history를 인자로 추가
    def recommend_travel_article(self, search_query: str, chat_history: list, places_json: str, weather_info: str) -> str:
        """
        사용자 입력(검색어), 대화 기록, 그리고 선택된 장소 데이터(JSON)를 바탕으로
        Gemini API를 통해 여행 기사를 생성합니다.
        """
        # PyQt 앱에서 이미 데이터를 가공해서 전달하므로, DB 조회 및 필터링 과정이 필요 없음.
        
        # 4. Gemini API 호출 및 응답 생성
        try:
            prompt_value = prompts.TRAVEL_ARTICLE_PROMPT.format_prompt(
                search_query=search_query,
                places_data_json=places_json,
                current_date=datetime.now().strftime("%Y년 %m월 %d일"),
                chat_history=chat_history,
                user_input=search_query,
                weather_info=weather_info
            )

            # API에 프롬프트 전송 (문자열로 변환)
            response = model.generate_content(prompt_value.to_string())
            return response.text
            
        except Exception as e:
            return f"죄송해요. 기사를 생성하는 중에 오류가 발생했어요. 다시 시도해주시면 감사하겠습니다! 오류: {e}"

# --- 메인 실행 ---
if __name__ == '__main__':
    chatbot = TravelChatbot()
    # ✅ [추가] 대화 기록을 저장할 리스트 생성
    chat_history = []

    while True:
        user_input = input("\n어떤 지역의 여행 정보를 원하시나요? (종료하려면 'q' 입력)\n> ")
        if user_input.lower() == 'q':
            print("👋 다음에 또 만나요!")
            break

        # DB 연결 및 데이터가 있는지 확인 (선택적)
        db_path = r"C:\hong_project\FromAI-crw\crw_data\naver_travel_places.db"
        conn, cursor = db_manager.connect_db(db_path)
        if not conn or not db_manager.create_places_table(cursor):
            print("데이터베이스 연결 또는 테이블 생성에 실패했습니다. 크롤링을 먼저 완료했는지 확인해주세요.")
            continue
        conn.close()

        print("\n[INFO] 잠시만 기다려주세요... 여행 기사를 작성하고 있어요...")
        
        # ✅ [수정] chatbot 객체에 대화 기록(chat_history) 전달
        article = chatbot.recommend_travel_article(user_input, chat_history)
        
        print("\n" + "="*50)
        print(article)
        print("="*50)

        # ✅ [추가] 다음 대화를 위해 현재 대화 내용을 기록
        chat_history.append(HumanMessage(content=user_input))
        chat_history.append(AIMessage(content=article))