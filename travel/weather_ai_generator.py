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
        self.gemini_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent"
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
                    'hashtags': [],
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
        """모델 응답에서 제목1~3, 본문, 해시태그를 안전하게 분리"""
        try:
            import re
            text = (response or "").strip()

            # 제목들 (정확한 라벨 우선)
            t1 = re.search(r'^\s*제목1:\s*(.+)$', text, re.M)
            t2 = re.search(r'^\s*제목2:\s*(.+)$', text, re.M)
            t3 = re.search(r'^\s*제목3:\s*(.+)$', text, re.M)
            titles = [t1.group(1).strip() if t1 else None,
                      t2.group(1).strip() if t2 else None,
                      t3.group(1).strip() if t3 else None]

            # 해시태그(문서 끝 #으로 시작하는 단 한 줄)
            h = re.search(r'(?:\r?\n)(#[^\r\n]+)\s*$', text)
            hashtags_line = h.group(1).strip() if h else ""
            hashtags = [tag for tag in (hashtags_line.split() if hashtags_line else []) if tag.startswith('#')]

            # 본문 = 전체에서 제목 라인 제거 후, 해시태그 라인 이전까지만
            body = text
            for pat in (r'^\s*제목1:.*$', r'^\s*제목2:.*$', r'^\s*제목3:.*$'):
                body = re.sub(pat, '', body, flags=re.M)
            if h:
                body = body[:h.start()].rstrip()

            # 폴백: 라벨이 없고 첫 줄이 짧으면 그걸 제목1로
            if not any(titles):
                lines = [ln for ln in body.splitlines() if ln.strip()]
                if lines and 0 < len(lines[0].strip()) <= 60:
                    titles[0] = lines[0].strip()
                    body = '\n'.join(lines[1:]).lstrip()

            primary_title = titles[0] or "제목 없음"
            return {
                "title": primary_title,          # 기존 호환 필드
                "titles": [t for t in titles if t],
                "content": body.strip(),
                "hashtags": hashtags
            }

        except Exception as e:
            print(f"응답 파싱 오류: {e}")
            # 완전 폴백: 기존 동작에 가깝게
            return {
                "title": "제목 파싱 오류",
                "titles": ["제목 파싱 오류"],
                "content": response or "",
                "hashtags": []
            }

    def _call_gemini_api(self, prompt):
        """Gemini API 호출"""
        try:
            if not self.gemini_api_key:
                raise Exception("GOOGLE_API_KEY 또는 GEMINI_API_KEY가 설정되지 않았습니다.")
            
            headers = {'Content-Type': 'application/json'}
            data = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.7, "topK": 40, "topP": 0.95, "maxOutputTokens": 2048,
                }
            }
            url = f"{self.gemini_url}?key={self.gemini_api_key}"
            print("Gemini API 호출 중...")
            response = requests.post(url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if 'candidates' in result and result['candidates']:
                    content = result['candidates'][0]['content']['parts'][0]['text']
                    print("기사 생성 완료")
                    return content.strip()
                else:
                    print(f"경고: API 응답에 유효한 'candidates'가 없습니다. 응답: {result}")
                    return f"기사 생성 실패: API가 유효한 응답을 반환하지 않았습니다. (응답: {result})"
            else:
                error_msg = f"API 호출 실패: {response.status_code}"
                try:
                    error_detail = response.json()
                    error_msg += f" - {error_detail}"
                except:
                    error_msg += f" - {response.text}"
                raise Exception(error_msg)
                
        except Exception as e:
            print(f"Gemini API 오류: {e}")
            return None

    # --- Fallback and Formatting Methods ---

    def _fallback_weather_article(self, weather_data, region_name):
        """프롬프트 모듈이 없을 때 사용하는 기본 날씨 기사"""
        try:
            weather_text = self._format_weather_data(weather_data, region_name)
            
            simple_prompt = f'''다음 날씨 정보로 간단한 날씨 기사를 작성해주세요:

{weather_text}

형식:
제목1: ...
제목2: ...
제목3: ...

[본문]

#해시태그1 #해시태그2 #해시태그3 #해시태그4 #해시태그5 #해시태그6 #해시태그7 #해시태그8
'''
            response = self._call_gemini_api(simple_prompt)
            if response:
                parsed = self._parse_response(response)
                title = parsed.get("title") or f"{region_name} 날씨"
                return {
                    'title': title,
                    'titles': parsed.get("titles") or [title],
                    'content': parsed.get("content", ""),
                    'hashtags': parsed.get("hashtags", []),
                    'type': 'weather'
                }
            return None
            
        except Exception as e:
            print(f"폴백 날씨 기사 생성 오류: {e}")
            return None

    def _fallback_warning_article(self, warning_data, region_name):
        """프롬프트 모듈이 없을 때 사용하는 기본 특보 기사"""
        try:
            warning_text = self._format_warning_data(warning_data, region_name)
            
            simple_prompt = f'''다음 기상특보 정보로 간단한 특보 기사를 작성해주세요:

{warning_text}

형식:
제목1: [기상특보] ...
제목2: [기상특보] ...
제목3: [기상특보] ...

[본문]

#기상특보 #특보종류 #지역명 #기상청 #날씨경보 #특보전망 #기상현상 #날씨특보
'''
            response = self._call_gemini_api(simple_prompt)
            if response:
                parsed = self._parse_response(response)
                title = parsed.get("title")
                if title and not title.startswith('[기상특보]'):
                    title = f"[기상특보] {title}"
                return {
                    'title': title or f"[기상특보] {region_name} 기상특보",
                    'titles': parsed.get("titles") or [title or f"[기상특보] {region_name} 기상특보"],
                    'content': parsed.get("content", ""),
                    'hashtags': parsed.get("hashtags", []),
                    'type': 'warning'
                }
            return None
            
        except Exception as e:
            print(f"폴백 특보 기사 생성 오류: {e}")
            return None

    def _format_weather_data(self, weather_data, region_name):
        """날씨 데이터를 간단한 텍스트로 변환"""
        try:
            text_lines = [f"지역: {region_name}"]
            
            if 'main' in weather_data:
                main = weather_data['main']
                if 'temp' in main:
                    text_lines.append(f"현재기온: {main['temp']}°C")
                if 'temp_min' in main and main['temp_min']:
                    text_lines.append(f"최저기온: {main['temp_min']}°C")
                if 'temp_max' in main and main['temp_max']:
                    text_lines.append(f"최고기온: {main['temp_max']}°C")
                if 'humidity' in main:
                    text_lines.append(f"습도: {main['humidity']}% ")
            
            if 'weather' in weather_data and weather_data['weather']:
                weather = weather_data['weather'][0]
                if 'description' in weather:
                    text_lines.append(f"날씨상태: {weather['description']}")
            
            if 'precipitation' in weather_data:
                precip = weather_data['precipitation']
                if 'probability' in precip and precip['probability']:
                    text_lines.append(f"강수확률: {precip['probability']}% ")
            
            return '\n'.join(text_lines)
            
        except Exception as e:
            return f"날씨 정보: {str(weather_data)}"

    def _format_warning_data(self, warning_data, region_name):
        """특보 데이터를 간단한 텍스트로 변환"""
        try:
            text_lines = [f"지역: {region_name}"]
            
            if isinstance(warning_data, list) and warning_data:
                text_lines.append(f"특보 건수: {len(warning_data)}건")
                for i, warning in enumerate(warning_data[:3], 1):
                    if 'title' in warning:
                        text_lines.append(f"특보{i}: {warning['title']}")
            
            return '\n'.join(text_lines)
            
        except Exception as e:
            return f"특보 정보: {str(warning_data)}"
