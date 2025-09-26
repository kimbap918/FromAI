# weather_ai_generator.py - AI 기반 날씨 기사 자동 생성
# ===================================================================================
# 파일명     : weather_ai_generator.py
# 작성자     : 하승주, 홍석원
# 최초작성일 : 2025-09-04
# 설명       : Google Gemini API를 활용한 날씨/기상특보 기사 자동 생성 모듈
#              실제 날씨 데이터와 기상특보 정보를 종합한 전문 기사 작성
# ===================================================================================
#
# 【주요 기능】
# - Google Gemini API를 활용한 날씨/기상특보 기사 자동 생성
# - 실제 날씨 데이터와 기상특보 정보를 종합한 전문 기사 작성
# - 순환형 특보 기사 생성으로 중복 방지
#
# 【핵심 클래스】
# WeatherArticleGenerator: 메인 기사 생성 클래스
#
# 【지원 기사 유형】
# 1. 일반 날씨 기사
#    - 현재 기온, 습도, 바람, 강수 정보
#    - 오늘/내일 최저/최고 기온
#    - 지역별 날씨 특성 분석
#
# 2. 기상특보 기사  
#    - 폭염, 호우, 대설 등 특보 정보
#    - 발효 시각, 영향 지역, 예상 강도
#    - 실제 현재 날씨와 연계한 현장감 있는 보도
#
# 【특보 순환 시스템】
# - 활성 특보 목록에서 처리되지 않은 특보 랜덤 선택
# - 동일 특보 중복 기사 방지
# - 모든 특보 처리 완료 시 자동 초기화
#
# 【기사 생성 과정】
# 1. 프롬프트 템플릿 (weather_article_prompts.py) 로드
# 2. 날씨/특보 데이터를 구조화된 텍스트로 포맷팅
# 3. Gemini API 호출하여 기사 생성
# 4. 응답 파싱: 제목1~3 + 본문 + 해시태그 분리
#
# 【출력 형식】
# - title: 대표 제목 (기존 호환용)
# - titles: 제목 1~3 배열
# - content: 기사 본문
# - hashtags: 해시태그 배열
# - type: 'weather' 또는 'warning'
#
# 【오류 처리】
# - API 호출 실패 시 폴백 프롬프트 사용
# - 응답 파싱 오류 시 안전한 기본값 반환
# - 재시도 로직 및 타임아웃 설정
#
# 【사용처】
# - weather_tab.py: 날씨/특보 기사 생성 버튼
# - weather_article_prompts.py와 긴밀한 연동
# ===================================================================================

import os
from dotenv import load_dotenv
import requests
import json
from datetime import datetime
import random

# 외부 프롬프트 모듈 import
try:
    from weather_article_prompts import GeminiWeatherPrompts as P
    PROMPTS_AVAILABLE = True
    print("프롬프트 모듈 로드 성공")

except ImportError as e:
    PROMPTS_AVAILABLE = False
    print(f"경고: 프롬프트 모듈 로드 실패: {e}")

load_dotenv()

class WeatherArticleGenerator:
    def __init__(self):
        self.gemini_api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        self.gemini_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
        self.active_warnings = []
        self.processed_warnings = []
        self.region_mapping = {
            "108": "서울", "109": "경기", "133": "대전", "143": "대구",
            "156": "광주", "159": "부산", "112": "인천", "152": "울산",
            "239": "세종", "105": "강원", "131": "충북", "129": "충남",
            "146": "전북", "165": "전남", "137": "경북", "155": "경남", "184": "제주"
        }

    def _format_weather_prompt(self, weather_data, location, current_date, current_time):
        # 프롬프트 템플릿 + 데이터 섹션 결합
        head = P.get_weather_article_prompt()
        tail = P.format_weather_data_for_prompt(
            weather_data=weather_data,
            region=location,
            current_date=current_date,
            current_time=current_time,
            weather_warning=None,
        )
        return head + "\n" + tail

    def _format_warning_prompt(self, region_name, warning_type, warning_level, warning_time, warning_content, weather_text):
        head = P.get_weather_warning_prompt()
        tail = P.format_warning_data_for_prompt(
            region=region_name,
            warning_type=warning_type,
            warning_level=warning_level,
            warning_time=warning_time,
            warning_content=warning_content,
            current_weather=weather_text,
        )
        return head + "\n" + tail


    def generate_weather_article(self, weather_data, region_name="해당 지역"):
        """일반 날씨 기사 생성 (외부 프롬프트 사용)"""
        try:
            if not PROMPTS_AVAILABLE:
                return self._fallback_weather_article(weather_data, region_name)
            
            current_date = datetime.now().strftime("%Y-%m-%d")
            current_time = datetime.now().strftime("%H:%M")
            
            formatted_prompt = self._format_weather_prompt(
                weather_data, region_name, current_date, current_time
            )
            
            full_prompt = formatted_prompt # WEATHER_ARTICLE_PROMPT already includes the full structure
            response = self._call_gemini_api(full_prompt)
            
            if response:
                parsed = self._parse_response(response)
                title = parsed.get("title") or f"{region_name} 오늘의 날씨"
                return {
                    'title': title,
                    'titles': parsed.get("titles") or [title],
                    'content': parsed.get("content", ""),
                    'hashtags': parsed.get("hashtags", []),
                    'type': 'weather'
                }
            else:
                return None
                
        except Exception as e:
            print(f"날씨 기사 생성 오류: {e}")
            return None

    def reset_warning_state(self):
        """특보 처리 상태를 초기화합니다."""
        print("기사 생성기 상태 초기화: 처리된 특보 목록을 비웁니다.")
        self.active_warnings = []
        self.processed_warnings = []

# weather_ai_generator.py의 기존 generate_warning_article 메서드 수정

    def generate_warning_article(self, new_warning_data, region_name=None):
        """
        기상특보 기사를 실제 날씨 데이터와 함께 랜덤으로 순환하며 생성합니다.
        """
        try:
            if not PROMPTS_AVAILABLE:
                return self._fallback_warning_article(new_warning_data, region_name or "전국 일부 지역")

            # 활성 특보 목록이 비어있으면 새 데이터로 채움
            if not self.active_warnings:
                self.active_warnings = new_warning_data

            available_warnings = [w for w in self.active_warnings if not self._is_warning_processed(w)]

            if not available_warnings and self.active_warnings:
                print("모든 특보를 다루었으므로, 처리 목록을 초기화합니다.")
                self.processed_warnings = []
                available_warnings = self.active_warnings

            if not available_warnings:
                print("활성화된 특보가 없거나 모든 특보가 처리되어 기사를 생성하지 않습니다.")
                return {
                    'title': f"[{region_name or '전국'}] 현재 발효 중인 기상특보 없음",
                    'titles': [f"[{region_name or '전국'}] 현재 발효 중인 기상특보 없음"],
                    'content': "현재 해당 지역에 발효 중인 기상특보가 없거나 모든 특보에 대한 기사 생성을 완료했습니다.",
                    'type': 'warning'
                }

            current_warning = random.choice(available_warnings)
            self.processed_warnings.append(current_warning)
            
            warning_title = current_warning.get('title', '알 수 없는 특보')
            specific_region_name = current_warning.get('region', '전국 일부')
            
            # ★ 해당 지역의 실제 날씨 데이터 수집
            weather_data = None
            weather_text = "기상 상황 변화"
            
            try:
                # WeatherAPI를 동적으로 import하여 사용
                from weather_api import WeatherAPI
                weather_api = WeatherAPI()
                print(f"{specific_region_name} 날씨 데이터 수집 중...")
                weather_data = weather_api.get_weather_data(specific_region_name)
                
                # 날씨 데이터를 텍스트로 포맷팅
                if weather_data:
                    weather_lines = [f"[{specific_region_name} 현재 기상 상황]"]
                    
                    if 'main' in weather_data:
                        main = weather_data['main']
                        if 'temp' in main:
                            weather_lines.append(f"현재기온: {main['temp']}°C")
                        if 'temp_min' in main and main['temp_min'] is not None:
                            weather_lines.append(f"최저기온: {main['temp_min']}°C")
                        if 'temp_max' in main and main['temp_max'] is not None:
                            weather_lines.append(f"최고기온: {main['temp_max']}°C")
                        if 'humidity' in main:
                            weather_lines.append(f"습도: {main['humidity']}% ")
                    
                    if 'weather' in weather_data and weather_data['weather']:
                        weather = weather_data['weather'][0]
                        if 'description' in weather:
                            weather_lines.append(f"날씨상태: {weather['description']}")
                    
                    if 'precipitation' in weather_data:
                        precip = weather_data['precipitation']
                        if 'probability' in precip and precip['probability']:
                            weather_lines.append(f"강수확률: {precip['probability']}% ")
                    
                    if 'wind' in weather_data:
                        wind = weather_data['wind']
                        if 'speed' in wind and wind['speed']:
                            weather_lines.append(f"풍속: {wind['speed']}m/s")
                    
                    weather_text = '\n'.join(weather_lines)
                    print(f"날씨 데이터 수집 완료: {specific_region_name}")
                
            except Exception as weather_error:
                print(f"경고: 날씨 데이터 수집 실패 ({specific_region_name}): {weather_error}")
                weather_text = "기상 상황 변화"
            
            # 특보 발표시각 파싱
            warning_time_raw = current_warning.get('tmFc', '')
            if warning_time_raw and len(warning_time_raw) >= 12:
                try:
                    year = warning_time_raw[:4]
                    month = warning_time_raw[4:6]
                    day = warning_time_raw[6:8]
                    hour = warning_time_raw[8:10]
                    minute = warning_time_raw[10:12]
                    warning_time = f"{year}-{month}-{day} {hour}:{minute}"
                    print(f"특보 발표시각 파싱: {warning_time_raw} → {warning_time}")
                except Exception as e:
                    print(f"경고: 시간 파싱 오류: {e}, 원본 사용: {warning_time_raw}")
                    warning_time = warning_time_raw
            else:
                warning_time = datetime.now().strftime("%Y-%m-%d %H:%M")
                print(f"경고: tmFc 데이터 없음, 현재 시각 사용: {warning_time}")
            
            print(f"다음 특보 기사를 (날씨 포함하여) 생성합니다: {warning_title} ({specific_region_name})")

            # 프롬프트 생성
            
            warning_type = "기상특보"
            if '폭염' in warning_title:
                warning_type = '폭염주의보' if '주의보' in warning_title else '폭염경보'
            elif '호우' in warning_title:
                warning_type = '호우주의보' if '주의보' in warning_title else '호우경보'
            elif '대설' in warning_title:
                warning_type = '대설주의보' if '주의보' in warning_title else '대설경보'
            
            warning_level = "경보" if "경보" in warning_title else "주의보"
            warning_content = f"{warning_title} ({specific_region_name})"

            formatted_prompt = self._format_warning_prompt(
                specific_region_name, warning_type, warning_level, warning_time, 
                warning_content, weather_text
            )
            
            full_prompt = formatted_prompt # WEATHER_WARNING_PROMPT already includes the full structure
            response = self._call_gemini_api(full_prompt)
            
            if response:
                parsed = self._parse_response(response)
                title = parsed.get("title")
                if title and not title.startswith('[기상특보]'):
                    title = f"[기상특보] {title}"
                if not title:
                    title = f"[기상특보] {specific_region_name} {warning_type} 발효"
                
                return {
                    'title': title,
                    'titles': parsed.get("titles") or [title],
                    'content': parsed.get("content", ""),
                    'hashtags': parsed.get("hashtags", []),
                    'type': 'warning'
                }
            else:
                return None
                
        except Exception as e:
            print(f"기상특보 기사 생성 오류: {e}")
            return None

    def _is_warning_processed(self, warning):
        """주어진 특보가 이미 처리되었는지 확인 (title과 region 기준)"""
        w_id = (warning.get('title', ''), warning.get('region', ''))
        return any(w_id == (p.get('title', ''), p.get('region', '')) for p in self.processed_warnings)

    def _is_warning_list_equal(self, list1, list2):
        """두 특보 목록이 동일한지 비교 (사용되지 않지만 호환성을 위해 남겨둠)"""
        if len(list1) != len(list2):
            return False
        
        ids1 = sorted([(w.get('title', ''), w.get('region', '')) for w in list1])
        ids2 = sorted([(w.get('title', ''), w.get('region', '')) for w in list2])
        
        return ids1 == ids2

    def _parse_response(self, response):
        """AI 응답에서 제목, 본문, 해시태그를 각각 분리하여 반환"""
        try:
            import re
            text = (response or "").strip()
            lines = [line.strip() for line in text.splitlines() if line.strip()]

            if not lines:
                return {"title": "", "titles": [], "content": "", "hashtags": []}

            # 해시태그 분리
            hashtag_lines = [line for line in lines if line.startswith('#')]
            non_hashtag_lines = [line for line in lines if not line.startswith('#')]

            # 제목 분리 (AI가 생성한 제목은 보통 3줄 이하)
            titles = []
            # 본문은 보통 100자를 훌쩍 넘기므로, 그 이전의 짧은 줄들을 제목으로 간주
            for i, line in enumerate(non_hashtag_lines):
                if len(line) < 100 and i < 3: # 제목 길이 제한을 100으로 늘리고, 최대 3줄까지 탐색
                    titles.append(line)
                else:
                    break
            
            # 본문 분리 (제목으로 식별된 줄들을 제외)
            body_lines = non_hashtag_lines[len(titles):]
            body = '\n'.join(body_lines)

            # 해시태그 파싱
            hashtags = []
            if hashtag_lines:
                full_hashtag_str = ' '.join(hashtag_lines)
                hashtags = [tag.strip() for tag in full_hashtag_str.split('#') if tag.strip()]

            # 제목에서 "제목1:" 등 접두사 제거
            cleaned_titles = [re.sub(r'^\s*제목\d:\s*', '', t).strip() for t in titles]

            return {
                "title": cleaned_titles[0] if cleaned_titles else "제목 없음",
                "titles": cleaned_titles,
                "content": body, # content에는 오직 본문만 포함
                "hashtags": hashtags,
            }

        except Exception as e:
            print(f"응답 파싱 오류: {e}")
            return {
                "title": "제목 파싱 오류",
                "titles": [],
                "content": response or "(기사 생성에 실패했습니다)",
                "hashtags": [],
            }

    def _call_gemini_api(self, prompt, retries=2):
        """Gemini API 호출 (안정화 버전)"""
        if not self.gemini_api_key:
            print("❌ API 키가 없습니다.")
            return None

        url = f"{self.gemini_url}?key={self.gemini_api_key}"
        headers = {"Content-Type": "application/json"}
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.5, "topK": 40, "topP": 0.95, "maxOutputTokens": 4096,
            },
        }

        for attempt in range(retries + 1):
            try:
                print(f"Gemini API 호출 중... (시도 {attempt+1})")
                response = requests.post(url, headers=headers, json=data, timeout=30)
                result = response.json()

                if response.status_code == 200 and "candidates" in result:
                    candidate = result["candidates"][0]
                    content = candidate.get("content", {})
                    parts = content.get("parts", [])
                    if parts and "text" in parts[0]:
                        print("✅ 기사 생성 완료")
                        return parts[0]["text"].strip()
                    else:
                        print(f"⚠️ parts 없음 → 응답: {result}")
                        return None
                else:
                    print(f"❌ API 오류 {response.status_code}: {result}")
                    return None

            except Exception as e:
                print(f"예외 발생: {e}")

        # 모든 시도가 실패했을 때
        return None


    def _parse_response(self, response_text: str):
        """AI 응답 텍스트에서 제목, 본문, 해시태그를 분리"""
        try:
            if not response_text or not isinstance(response_text, str):
                return {"title": "", "titles": [], "content": "", "hashtags": []}

            import re
            lines = [line.strip() for line in response_text.splitlines() if line.strip()]

            # 해시태그 분리
            hashtag_lines = [line for line in lines if line.startswith('#')]
            non_hashtag_lines = [line for line in lines if not line.startswith('#')]

            # 제목 추출 (앞부분의 짧은 줄)
            titles = []
            for i, line in enumerate(non_hashtag_lines):
                if len(line) < 100 and i < 3:  # 제목 후보
                    titles.append(line)
                else:
                    break

            # 본문 = 나머지
            body_lines = non_hashtag_lines[len(titles):]
            body = "\n".join(body_lines)

            # 해시태그 파싱
            hashtags = []
            if hashtag_lines:
                full_hashtag_str = " ".join(hashtag_lines)
                hashtags = [tag.strip() for tag in full_hashtag_str.split("#") if tag.strip()]

            # "제목1:" 같은 접두사 제거
            cleaned_titles = [re.sub(r"^\s*제목\d:\s*", "", t).strip() for t in titles]

            return {
                "title": cleaned_titles[0] if cleaned_titles else "제목 없음",
                "titles": cleaned_titles,
                "content": body,
                "hashtags": hashtags,
            }

        except Exception as e:
            print(f"응답 파싱 오류: {e}")
            return {
                "title": "제목 파싱 오류",
                "titles": [],
                "content": response_text or "(기사 생성 실패)",
                "hashtags": [],
            }
