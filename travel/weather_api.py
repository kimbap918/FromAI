# weather_api.py - 기상청 API 기반 날씨 데이터 수집
# ===================================================================================
# 파일명     : weather_api.py
# 작성자     : 하승주, 홍석원
# 최초작성일 : 2025-09-04
# 설명       : 카카오 API로 주소→좌표 변환 및 기상청 API로 실시간 날씨 수집
#              초단기실황 + 단기예보 데이터 통합 처리로 전국 모든 지역 지원
# ===================================================================================
#
# 【주요 기능】
# - 카카오 API로 주소→좌표 변환
# - 기상청 API로 실시간 날씨 데이터 수집
# - 초단기실황 + 단기예보 데이터 통합 처리
# - 전국 모든 지역 지원 (하드코딩 매핑 제거)
#
# 【API 통합】
# 1. 카카오 API: 주소 검색 및 좌표 변환
# 2. 기상청 초단기실황: 현재 기온, 습도, 바람 (매시 40분 발표)
# 3. 기상청 단기예보: 강수확률, 최저/최고기온 (02,05,08,11,14,17,20,23시 발표)
#
# 【데이터 수집 전략】
# - 초단기실황 우선: 정확한 발표시각 계산하여 최신 데이터 확보
# - 단기예보 보완: 실황에 없는 예보 정보 추가
# - 실패 시 폴백: 여러 시간대 재시도 및 어제 예보 활용
#
# 【좌표 변환 로직】
# - LatLon → 기상청 격자좌표 (X,Y) 수학적 변환
# - Lambert Conformal Conic 투영법 사용
# - 정확한 격자 매핑으로 데이터 정확도 보장
#
# 【안정성 기능】
# - 재시도 로직: 각 API별 최대 3회 재시도
# - 타임아웃 설정: 연결/읽기 30초 (REQUEST_TIMEOUT)
# - 오류 분류: HTTP 오류, JSON 파싱 오류, API 결과 코드 오류 구분
#
# 【데이터 정규화】
# - 표준 OpenWeatherMap 호환 형식으로 출력
# - main.temp, weather.description 등 일관된 구조
# - 한국어 텍스트: 날씨 상태, 풍향 등
#
# 【오늘 기온 문제 해결】
# - 오전 6시 이전: 어제 예보의 오늘 최저기온 활용
# - 오후 3시 이전: 어제 예보의 오늘 최고기온 활용
# - 시간대별 적절한 데이터 소스 선택
#
# 【사용처】
# - weather_tab.py: 날씨 조회 기능
# - travel_logic.py: 여행 기사에 날씨 정보 포함
# ===================================================================================

import requests
import math
import time
from datetime import datetime, timedelta

import os
from dotenv import load_dotenv

# Custom print function to log to a file with UTF-8 encoding
def custom_print(*args, **kwargs):
    pass
    # Also print to original stdout for debugging in console
    # print(*args, **kwargs)

load_dotenv()

# API 키들 (환경 변수에서 로드)
KAKAO_API_KEY = os.getenv("KAKAO_API_KEY")
KMA_API_KEY = os.getenv("KMA_API_KEY")

# config.py에서 import - 오류 처리 추가
try:
    from config import KAKAO_COORD_URL, REQUEST_TIMEOUT
except ImportError:
    print("⚠️ config.py에서 import 실패. 기본값 사용")
    KAKAO_COORD_URL = "https://dapi.kakao.com/v2/local/search/address.json"
    REQUEST_TIMEOUT = 30

# data.py에서 import - 오류 처리 추가
try:
    from data import KOREA_REGIONS, SIMPLE_REGION_MAPPING
except ImportError:
    custom_print("⚠️ data.py에서 import 실패. 전국 지역 지원을 위해 카카오 API 사용")
    # 하드코딩된 매핑 제거 - 모든 지역을 카카오 API로 처리
    SIMPLE_REGION_MAPPING = {}
    KOREA_REGIONS = []

class WeatherAPI:
    def __init__(self):
        self.kakao_api_key = KAKAO_API_KEY
        self.kma_api_key = KMA_API_KEY
        self.kakao_url = KAKAO_COORD_URL
        # 기상청 API URLs
        self.kma_current_url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"  # 초단기실황
        self.kma_forecast_url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"  # 단기예보
        
    def find_region(self, user_input):
        """사용자 입력을 그대로 카카오 API로 전달 (전국 모든 지역 지원)"""
        user_input = user_input.strip()
        
        # 간단한 전처리만 수행
        if not user_input:
            raise Exception("지역명을 입력해주세요.")
        
        print(f"🔍 지역 검색: '{user_input}' (카카오 API 직접 검색)")
        return user_input
        
    def get_coordinates_from_address(self, address):
        """카카오 API로 주소에서 좌표 변환 (전국 모든 지역 지원)"""
        headers = {
            'Authorization': f'KakaoAK {self.kakao_api_key}'
        }
        params = {
            'query': address,
            'size': 5  # 여러 후보 검색
        }
        
        try:
            response = requests.get(self.kakao_url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                data = response.json()
                if data['documents']:
                    print(f"   📋 '{address}' 검색 결과 {len(data['documents'])}개:")
                    
                    # 모든 검색 결과 출력
                    for i, doc in enumerate(data['documents']):
                        addr_name = doc['address_name']
                        addr_type = doc.get('address_type', 'UNKNOWN')
                        print(f"      {i+1}. {addr_name} (타입: {addr_type})")
                    
                    # 가장 적합한 결과 선택
                    best_coord = self.select_best_coordinate(data['documents'], address)
                    
                    lat = float(best_coord['y'])
                    lon = float(best_coord['x'])
                    full_address = best_coord['address_name']
                    
                    print(f"✅ 좌표 변환 성공: {full_address}")
                    custom_print(f"   📍 위도: {lat:.4f}, 경도: {lon:.4f}")
                    return lat, lon, full_address
                else:
                    raise Exception(f"'{address}' 지역을 찾을 수 없습니다. 정확한 지역명을 입력해주세요.")
            else:
                raise Exception(f"카카오 API 오류: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            raise Exception(f"카카오 API 연결 오류: {e}")
    
    def select_best_coordinate(self, documents, search_query):
        """검색 결과에서 가장 적합한 좌표 선택"""
        if len(documents) == 1:
            return documents[0]
        
        # 우선순위 1: REGION 타입 (행정구역)
        region_docs = [doc for doc in documents if doc.get('address_type') == 'REGION']
        if region_docs:
            print(f"   🎯 행정구역 타입 선택: {region_docs[0]['address_name']}")
            return region_docs[0]
        
        # 우선순위 2: 검색어와 가장 유사한 이름
        best_match = None
        max_similarity = 0
        
        for doc in documents:
            addr_name = doc['address_name']
            # 간단한 유사도 계산 (검색어가 주소에 포함되는지)
            if search_query in addr_name:
                similarity = len(search_query) / len(addr_name)
                if similarity > max_similarity:
                    max_similarity = similarity
                    best_match = doc
        
        if best_match:
            print(f"   🎯 유사도 매칭 선택: {best_match['address_name']}")
            return best_match
        
        # 우선순위 3: 첫 번째 결과
        print(f"   🎯 첫 번째 결과 선택: {documents[0]['address_name']}")
        return documents[0]
    
    def convert_to_grid(self, lat, lon):
        """위경도를 기상청 격자좌표로 변환"""
        # 기상청 격자 변환 공식
        RE = 6371.00877
        GRID = 5.0
        SLAT1 = 30.0
        SLAT2 = 60.0
        OLON = 126.0
        OLAT = 38.0
        XO = 43
        YO = 136
        
        DEGRAD = math.pi / 180.0
        
        re = RE / GRID
        slat1 = SLAT1 * DEGRAD
        slat2 = SLAT2 * DEGRAD
        olon = OLON * DEGRAD
        olat = OLAT * DEGRAD
        
        sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
        sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
        sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
        sf = math.pow(sf, sn) * math.cos(slat1) / sn
        ro = math.tan(math.pi * 0.25 + olat * 0.5)
        ro = re * sf / math.pow(ro, sn)
        
        ra = math.tan(math.pi * 0.25 + lat * DEGRAD * 0.5)
        ra = re * sf / math.pow(ra, sn)
        theta = lon * DEGRAD - olon
        if theta > math.pi:
            theta -= 2.0 * math.pi
        if theta < -math.pi:
            theta += 2.0 * math.pi
        theta *= sn
        
        x = int(ra * math.sin(theta) + XO + 0.5)
        y = int(ro - ra * math.cos(theta) + YO + 0.5)
        
        return x, y
    
    def get_proper_base_time(self, target_time=None):
        """초단기실황용 정확한 발표시각 계산"""
        if target_time is None:
            target_time = datetime.now()
        
        # 초단기실황은 매시 40분에 발표되고, 10분마다 업데이트
        # 실제로는 45분 이후에 데이터가 안정적으로 제공됨
        current_minute = target_time.minute
        
        if current_minute >= 45:
            # 현재 시간의 40분 데이터 사용
            base_time = target_time.replace(minute=40, second=0, microsecond=0)
        else:
            # 이전 시간의 40분 데이터 사용
            base_time = target_time.replace(minute=40, second=0, microsecond=0) - timedelta(hours=1)
        
        return base_time
    
    def get_weather_with_fallback(self, grid_x, grid_y):
        """향상된 날씨 정보 수집 (초단기실황 문제 해결)"""
        now = datetime.now()
        final_weather = {}
        
        print("🔍 === 날씨 데이터 수집 시작 ===")
        
        # 1단계: 초단기실황 시도 (발표시각 정확히 계산)
        print("\n1️⃣ 초단기실황 시도 중...")
        current_success = False
        
        # 정확한 발표시각들로 시도
        base_times_to_try = [
            self.get_proper_base_time(now),
            self.get_proper_base_time(now - timedelta(hours=1)),
            self.get_proper_base_time(now - timedelta(hours=2)),
        ]
        
        for base_time in base_times_to_try:
            current_data = self.try_current_weather(grid_x, grid_y, base_time)
            if current_data:
                print(f"✅ 초단기실황 성공! 시각: {base_time.strftime('%H:%M')}, 항목: {list(current_data.keys())}")
                final_weather.update(current_data)
                final_weather['data_sources'] = ['초단기실황']
                current_success = True
                break
            else:
                print(f"   ❌ {base_time.strftime('%H:%M')} 실패")
        
        if not current_success:
            print("❌ 초단기실황: 모든 시도 실패")
        
        # 2단계: 단기예보 시도 (강수확률, 최저/최고기온 등)
        print("\n2️⃣ 단기예보 시도 중...")
        forecast_data = self.try_forecast_weather(grid_x, grid_y)
        if forecast_data:
            print(f"✅ 단기예보 성공! 항목: {list(forecast_data.keys())}")
            added_count = 0
            for key, value in forecast_data.items():
                if key not in final_weather:
                    final_weather[key] = value
                    added_count += 1
                    print(f"   📝 추가: {key} = {value}")
                else:
                    print(f"   ⏭️ 중복 스킵: {key}")
            if 'data_sources' in final_weather:
                final_weather['data_sources'].append('단기예보')
            else:
                final_weather['data_sources'] = ['단기예보']
            print(f"📊 단기예보에서 {added_count}개 항목 추가")
        else:
            print("❌ 단기예보: 데이터 없음")
        
        # 최종 결과
        custom_print(f"\n🎯 === 최종 결과 ===")
        print(f"📊 총 항목 수: {len(final_weather)}")
        print(f"📋 수집된 항목:")
        for key, value in final_weather.items():
            if key != 'data_sources':
                print(f"   • {key}: {value}")
        
        if not final_weather or len(final_weather) <= 1:  # data_sources만 있는 경우
            raise Exception("모든 기상청 API에서 데이터를 가져올 수 없습니다.")
        
        return final_weather
    
    def try_current_weather(self, grid_x, grid_y, base_time):
        """초단기실황 데이터 (재시도 로직 추가)"""
        max_retries = 3
        retry_delay = 1 # 초

        for attempt in range(max_retries):
            try:
                base_date = base_time.strftime('%Y%m%d')
                base_time_str = base_time.strftime('%H%M')
                
                print(f"   🔍 API 호출 (시도 {attempt + 1}/{max_retries}): {base_date} {base_time_str}")
                
                params = {
                    'serviceKey': self.kma_api_key, 'pageNo': '1', 'numOfRows': '100',
                    'dataType': 'JSON', 'base_date': base_date, 'base_time': base_time_str,
                    'nx': str(grid_x), 'ny': str(grid_y)
                }
                
                response = requests.get(self.kma_current_url, params=params, timeout=REQUEST_TIMEOUT)
                print(f"   📡 응답 코드: {response.status_code}")

                if response.status_code != 200:
                    print(f"   ❌ HTTP 오류: {response.status_code}")
                    time.sleep(retry_delay)
                    continue

                response_text = response.text.strip()
                if not response_text:
                    print("   ❌ 빈 응답")
                    time.sleep(retry_delay)
                    continue

                try:
                    data = response.json()
                except ValueError as json_error:
                    print(f"   ❌ JSON 파싱 오류: {json_error}")
                    print(f"   📄 응답 내용 (처음 200자): {response_text[:200]}")
                    time.sleep(retry_delay)
                    continue

                if 'response' not in data or 'header' not in data['response']:
                    print(f"   ❌ 응답 구조 오류: response 키 없음")
                    time.sleep(retry_delay)
                    continue
                
                header = data['response']['header']
                result_code = header.get('resultCode', '')
                result_msg = header.get('resultMsg', '')
                print(f"   📋 결과: {result_code} - {result_msg}")
                
                if result_code == '00':
                    body = data['response'].get('body', {})
                    if not body: return None

                    items = body.get('items', {})
                    item_list = items.get('item', []) if isinstance(items, dict) else items
                    if not item_list: return None

                    current_weather = {}
                    for item in item_list:
                        category, value = item.get('category'), item.get('obsrValue')
                        if not category or not value: continue
                        
                        try:
                            if category == 'T1H': current_weather['temperature'] = float(value)
                            elif category == 'REH': current_weather['humidity'] = float(value)
                            elif category == 'PTY': current_weather['precipitation_type'] = self.get_precipitation_text(value)
                            elif category == 'RN1': current_weather['hourly_precipitation'] = self.parse_precipitation_amount(value)
                            elif category == 'WSD': current_weather['wind_speed'] = float(value)
                            elif category == 'VEC': 
                                wind_deg = float(value)
                                current_weather['wind_direction'] = wind_deg
                                current_weather['wind_direction_text'] = self.get_wind_direction_text(wind_deg)
                        except (ValueError, TypeError):
                            pass
                    
                    return current_weather if current_weather else None
                else:
                    print(f"   ❌ API 오류: {result_code} - {result_msg}")
                    time.sleep(retry_delay)

            except requests.exceptions.RequestException as req_err:
                print(f"   💥 요청 예외 (시도 {attempt + 1}): {req_err}")
                time.sleep(retry_delay)

            except Exception as e:
                print(f"   💥 일반 예외 (시도 {attempt + 1}): {e}")
                time.sleep(retry_delay)

        # print(f"   ❌ 모든 재시도({max_retries}번) 실패.") # 이 메시지는 get_weather_with_fallback에서 처리
        return None
    
    def try_forecast_weather(self, grid_x, grid_y):
        """단기예보 데이터 (재시도 로직 추가)"""
        max_retries = 3
        retry_delay = 1  # 초

        for attempt in range(max_retries):
            try:
                now = datetime.now()
                
                # 단기예보 발표 시각: 02, 05, 08, 11, 14, 17, 20, 23시 (10분 후 데이터 제공)
                forecast_times = [2, 5, 8, 11, 14, 17, 20, 23]
                current_hour = now.hour
                current_minute = now.minute
                
                base_time = None
                base_date = now.strftime('%Y%m%d')
                
                for time_val in reversed(forecast_times):
                    if current_hour > time_val or (current_hour == time_val and current_minute >= 10):
                        base_time = f"{time_val:02d}00"
                        break
                
                if base_time is None:
                    yesterday = now - timedelta(days=1)
                    base_date = yesterday.strftime('%Y%m%d')
                    base_time = "2300"
                
                print(f"   🔍 API 호출 (시도 {attempt + 1}/{max_retries}): {base_date} {base_time}")
                
                params = {
                    'serviceKey': self.kma_api_key, 'pageNo': '1', 'numOfRows': '1000',
                    'dataType': 'JSON', 'base_date': base_date, 'base_time': base_time,
                    'nx': str(grid_x), 'ny': str(grid_y)
                }
                
                response = requests.get(self.kma_forecast_url, params=params, timeout=REQUEST_TIMEOUT)
                print(f"   📡 응답 코드: {response.status_code}")

                if response.status_code != 200:
                    print(f"   ❌ HTTP 오류: {response.status_code}")
                    time.sleep(retry_delay)
                    continue

                # JSON 파싱 시도
                try:
                    data = response.json()
                except ValueError as json_error:
                    print(f"   ❌ JSON 파싱 오류: {json_error}")
                    print(f"   📄 응답 내용 (처음 200자): {response.text.strip()[:200]}")
                    time.sleep(retry_delay)
                    continue

                if 'response' not in data or 'header' not in data['response']:
                    print(f"   ❌ 응답 구조 오류")
                    time.sleep(retry_delay)
                    continue
                
                result_code = data['response']['header']['resultCode']
                result_msg = data['response']['header'].get('resultMsg', '')
                print(f"   📋 결과: {result_code} - {result_msg}")
                
                if result_code == '00':
                    body = data['response'].get('body', {})
                    if not body: return None
                    
                    items = body.get('items', {})
                    item_list = items.get('item', []) if isinstance(items, dict) else items
                    if not item_list: return None

                    today = now.strftime('%Y%m%d')
                    tomorrow = (now + timedelta(days=1)).strftime('%Y%m%d')
                    current_hour_str = f"{now.hour:02d}00"
                    
                    forecast_data = {}
                    found_items = []
                    
                    can_get_today_min = now.hour >= 6
                    can_get_today_max = now.hour >= 15
                    
                    today_tmn_found = any(i.get('category') == 'TMN' and i.get('fcstDate') == today and i.get('fcstTime') == '0600' for i in item_list)
                    today_tmx_found = any(i.get('category') == 'TMX' and i.get('fcstDate') == today and i.get('fcstTime') == '1500' for i in item_list)

                    missing_today_temps = []
                    if not today_tmn_found and can_get_today_min: 
                        missing_today_temps.append("TMN")
                    if not today_tmx_found:  # can_get_today_max 조건 제거
                        missing_today_temps.append("TMX")

                    if missing_today_temps:
                        print(f"🔍 missing_today_temps: {missing_today_temps}")
                        yesterday_forecast = self.get_yesterday_forecast_for_today(grid_x, grid_y)
                        print(f"🔍 yesterday_forecast: {yesterday_forecast}")
                        if yesterday_forecast:
                            if "TMN" in missing_today_temps and 'yesterday_min_for_today' in yesterday_forecast:
                                forecast_data['min_temp_today'] = yesterday_forecast['yesterday_min_for_today']
                                found_items.append(f"today TMN={forecast_data['min_temp_today']}°C (어제예보)")
                                print(f"✅ TMN 추가됨: {forecast_data['min_temp_today']}")
                            if "TMX" in missing_today_temps and 'yesterday_max_for_today' in yesterday_forecast:
                                forecast_data['max_temp_today'] = yesterday_forecast['yesterday_max_for_today']
                                found_items.append(f"today TMX={forecast_data['max_temp_today']}°C (어제예보)")
                                print(f"✅ TMX 추가됨: {forecast_data['max_temp_today']}")

                    for item in item_list:
                        category, value, fcst_date, fcst_time = item.get('category'), item.get('fcstValue'), item.get('fcstDate'), item.get('fcstTime')
                        if not all([category, value, fcst_date, fcst_time]): continue

                        if fcst_date == today and fcst_time >= current_hour_str:
                            if category == 'POP' and 'rain_probability' not in forecast_data:
                                forecast_data['rain_probability'] = int(value)
                            elif category == 'PCP' and 'precipitation_amount' not in forecast_data:
                                forecast_data['precipitation_amount'] = self.parse_precipitation_amount(value)
                            elif category == 'SKY' and 'sky_condition' not in forecast_data:
                                forecast_data['sky_condition'] = self.get_sky_text(value)

                        if fcst_date == today and category == 'TMN' and fcst_time == '0600' and 'min_temp_today' not in forecast_data and can_get_today_min:
                            if value not in ['-999', '-', '']: forecast_data['min_temp_today'] = float(value)
                        
                        if fcst_date == today and category == 'TMX' and fcst_time == '1500' and can_get_today_max:
                            if value not in ['-999', '-', '']: forecast_data['max_temp_today'] = float(value)

                        if fcst_date == tomorrow and category == 'TMN' and fcst_time == '0600' and 'min_temp_tomorrow' not in forecast_data:
                            if value not in ['-999', '-', '']: forecast_data['min_temp_tomorrow'] = float(value)
                        
                        if fcst_date == tomorrow and category == 'TMX' and fcst_time == '1500' and 'max_temp_tomorrow' not in forecast_data:
                            if value not in ['-999', '-', '']: forecast_data['max_temp_tomorrow'] = float(value)
                    
                    # 단기예보 파싱이 끝난 후, 간단하게 처리
                    if 'max_temp_today' not in forecast_data or forecast_data.get('max_temp_today') is None:
                        # 오늘 최고기온이 없으면 어제 예보 사용
                        yesterday_forecast = self.get_yesterday_forecast_for_today(grid_x, grid_y)
                        if yesterday_forecast and 'yesterday_max_for_today' in yesterday_forecast:
                            forecast_data['max_temp_today'] = yesterday_forecast['yesterday_max_for_today']
                            found_items.append(f"today TMX={forecast_data['max_temp_today']}°C (어제예보)")
                            print(f"✅ 최고기온 후처리로 추가됨: {forecast_data['max_temp_today']}")
                    
                    return forecast_data if forecast_data else None

                else: # API 에러 코드 '00'이 아닌 경우
                    print(f"   ❌ API 오류: {result_code} - {result_msg}")
                    time.sleep(retry_delay)
            
            except requests.exceptions.RequestException as req_err:
                print(f"   💥 요청 예외 (시도 {attempt + 1}): {req_err}")
                time.sleep(retry_delay)
            
            except Exception as e:
                print(f"   💥 일반 예외 (시도 {attempt + 1}): {e}")
                time.sleep(retry_delay)

        print(f"   ❌ 모든 재시도({max_retries}번) 실패.")
        return None
    
    def get_yesterday_forecast_for_today(self, grid_x, grid_y):
        """어제 예보한 오늘 기온 데이터 가져오기 (재시도 로직 추가)"""
        max_retries = 3
        retry_delay = 1

        for attempt in range(max_retries):
            try:
                now = datetime.now()
                yesterday = now - timedelta(days=1)
                today = now.strftime('%Y%m%d')
                
                print(f"      🔍 어제 예보 확인 (시도 {attempt + 1}/{max_retries}): {yesterday.strftime('%Y%m%d')} 23시")
                
                params = {
                    'serviceKey': self.kma_api_key, 'pageNo': '1', 'numOfRows': '1000',
                    'dataType': 'JSON', 'base_date': yesterday.strftime('%Y%m%d'),
                    'base_time': '2300', 'nx': str(grid_x), 'ny': str(grid_y)
                }
                
                response = requests.get(self.kma_forecast_url, params=params, timeout=REQUEST_TIMEOUT)

                if response.status_code != 200:
                    print(f"      ❌ HTTP 오류: {response.status_code}")
                    time.sleep(retry_delay)
                    continue

                data = response.json()
                if data.get('response', {}).get('header', {}).get('resultCode') == '00':
                    items = data.get('response', {}).get('body', {}).get('items', {})
                    item_list = items.get('item', []) if isinstance(items, dict) else items
                    
                    yesterday_data = {}
                    for item in item_list:
                        category, value, fcst_date = item.get('category'), item.get('fcstValue'), item.get('fcstDate')
                        if fcst_date == today and value not in ['-999', '-', '']:
                            try:
                                if category == 'TMN':
                                    yesterday_data['yesterday_min_for_today'] = float(value)
                                elif category == 'TMX':
                                    yesterday_data['yesterday_max_for_today'] = float(value)
                            except (ValueError, TypeError):
                                pass
                    
                    if yesterday_data:
                        print(f"      ✅ 어제 예보에서 {list(yesterday_data.keys())} 찾음")
                    return yesterday_data if yesterday_data else None
                else:
                    print(f"      ❌ 어제 예보 API 오류")
                    time.sleep(retry_delay)

            except (requests.exceptions.RequestException, ValueError) as e:
                print(f"      ❌ 어제 예보 확인 실패 (시도 {attempt + 1}): {e}")
                time.sleep(retry_delay)

        print(f"      ❌ 어제 예보 확인 최종 실패.")
        return None
    
    def parse_precipitation_amount(self, value):
        """강수량 파싱"""
        if not value or value in ['강수없음', '0', '0.0', '-']:
            return 0.0
        try:
            value_str = str(value)
            if '미만' in value_str:
                return 0.5
            elif '~' in value_str:
                parts = value_str.replace('mm', '').split('~')
                if len(parts) == 2:
                    return (float(parts[0]) + float(parts[1])) / 2
            else:
                return float(value_str.replace('mm', ''))
        except:
            return 0.0
    
    def get_precipitation_text(self, pty_code):
        """강수형태 텍스트 변환"""
        pty_dict = {
            '0': '없음', '1': '비', '2': '비/눈', '3': '눈',
            '4': '소나기', '5': '빗방울', '6': '빗방울/눈날림', '7': '눈날림'
        }
        return pty_dict.get(str(pty_code), '없음')
    
    def get_sky_text(self, sky_code):
        """하늘상태 텍스트 변환"""
        sky_dict = {'1': '맑음', '3': '구름많음', '4': '흐림'}
        return sky_dict.get(str(sky_code), '맑음')
    
    def get_wind_direction_text(self, degree):
        """풍향 텍스트 변환"""
        if degree < 0:
            degree += 360
        directions = ['북', '북북동', '북동', '동북동', '동', '동남동', '남동', '남남동',
                     '남', '남남서', '남서', '서남서', '서', '서북서', '북서', '북북서']
        idx = int((degree + 11.25) / 22.5) % 16
        return directions[idx]
    
    def get_weather_data(self, city_name):
        """통합 날씨 정보 가져오기 (구 단위 정확도 개선)"""
        try:
            print(f"🔍 '{city_name}' 검색 중...")
            full_region = self.find_region(city_name)
            
            print(f"🗺️ 좌표 변환 중...")
            lat, lon, full_address = self.get_coordinates_from_address(full_region)
            
            print("🔄 격자 변환 중...")
            grid_x, grid_y = self.convert_to_grid(lat, lon)
            print(f"✅ 격자: X={grid_x}, Y={grid_y}")
            
            print("🌡️ 날씨 데이터 수집 중...")
            weather_data = self.get_weather_with_fallback(grid_x, grid_y)
            
            # 표준 형식으로 변환
            temperature = weather_data.get('temperature', 20.0)
            
            # 오늘 최저/최고 기온 매핑 - 수정된 부분
            today_min = (weather_data.get('min_temp_today') or 
                        weather_data.get('yesterday_min_for_today'))
            today_max = (weather_data.get('max_temp_today') or 
                        weather_data.get('yesterday_max_for_today'))
            
            # 디버깅 출력 추가
            print(f"🔍 기온 매핑 확인:")
            print(f"   - weather_data에서 min_temp_today: {weather_data.get('min_temp_today')}")
            print(f"   - weather_data에서 max_temp_today: {weather_data.get('max_temp_today')}")
            print(f"   - weather_data에서 yesterday_min_for_today: {weather_data.get('yesterday_min_for_today')}")
            print(f"   - weather_data에서 yesterday_max_for_today: {weather_data.get('yesterday_max_for_today')}")
            print(f"   - 최종 today_min: {today_min}")
            print(f"   - 최종 today_max: {today_max}")
            
            formatted_data = {
                'main': {
                    'temp': temperature,
                    'feels_like': temperature,
                    'humidity': weather_data.get('humidity', 60),
                    'temp_min': today_min,  # min_temp_today를 temp_min에 매핑
                    'temp_max': today_max   # max_temp_today를 temp_max에 매핑
                },
                'weather': [{
                    'description': self.get_weather_description(weather_data),
                    'main': weather_data.get('sky_condition', '맑음')
                }],
                'wind': {
                    'speed': weather_data.get('wind_speed'),
                    'deg': weather_data.get('wind_direction'),
                    'direction': weather_data.get('wind_direction_text')
                },
                'precipitation': {
                    'type': weather_data.get('precipitation_type', '없음'),
                    'probability': weather_data.get('rain_probability'),
                    'amount': weather_data.get('precipitation_amount', 0)
                },
                'forecast': {
                    'today_min': today_min,
                    'today_max': today_max,
                    'tomorrow_min': weather_data.get('min_temp_tomorrow'),
                    'tomorrow_max': weather_data.get('max_temp_tomorrow')
                },
                'name': full_address,
                'region_info': {
                    'user_input': city_name,
                    'matched_region': full_region,
                    'full_address': full_address
                },
                'data_source': f"기상청 ({', '.join(weather_data.get('data_sources', []))})",
                'raw_data': weather_data  # 디버깅용
            }
            
            # 최종 확인 출력
            print(f"✅ 최종 매핑 확인:")
            print(f"   - formatted_data['main']['temp_min']: {formatted_data['main']['temp_min']}")
            print(f"   - formatted_data['main']['temp_max']: {formatted_data['main']['temp_max']}")
            
            return formatted_data
            
        except Exception as e:
            raise Exception(f"날씨 정보 수집 실패: {str(e)}")
    
    def get_weather_description(self, weather_data):
        """종합 날씨 설명"""
        parts = []
        
        if weather_data.get('sky_condition'):
            parts.append(weather_data['sky_condition'])
        
        precipitation = weather_data.get('precipitation_type', '없음')
        if precipitation != '없음':
            parts.append(precipitation)
        
        if weather_data.get('rain_probability') and weather_data['rain_probability'] > 0:
            parts.append(f"강수확률 {weather_data['rain_probability']}%")
        
        return ', '.join(parts) if parts else '맑음'
    
    def format_weather_info(self, weather_data, city_name):
        """향상된 날씨 정보 텍스트"""
        try:
            main = weather_data['main']
            weather = weather_data['weather'][0]
            wind = weather_data.get('wind', {})
            precip = weather_data.get('precipitation', {})
            forecast = weather_data.get('forecast', {})
            raw_data = weather_data.get('raw_data', {})
            
            region_info = weather_data.get('region_info', {})
            matched_region = region_info.get('matched_region', city_name)
            
            # 기온 표시 개선 - None 처리
            current_temp = main['temp']
            min_temp = main.get('temp_min')
            max_temp = main.get('temp_max')
            
            # 최저/최고 기온 텍스트 처리
            min_temp_text = f"{min_temp}°C" if min_temp is not None else "정보없음"
            max_temp_text = f"{max_temp}°C" if max_temp is not None else "정보없음"
            
            weather_text = f"""
📍 {matched_region} 상세 날씨 정보

🌡️ 기온:
- 현재: {current_temp}°C
- 최저: {min_temp_text} (오늘)
- 최고: {max_temp_text} (오늘)
- 습도: {main['humidity']}%

🌤️ 날씨:
- 상태: {weather['description']}
- 하늘: {weather.get('main', '--')}

💧 강수:
- 형태: {precip.get('type', '없음')}
- 확률: {precip.get('probability', '--')}%
- 강수량: {precip.get('amount', 0)}mm

🌬️ 바람:
- 풍속: {wind.get('speed', '--')}m/s
- 풍향: {wind.get('direction', '--')} ({wind.get('deg', '--')}°)"""

            if forecast.get('tomorrow_min') or forecast.get('tomorrow_max'):
                tomorrow_min = forecast.get('tomorrow_min')
                tomorrow_max = forecast.get('tomorrow_max')
                tomorrow_min_text = f"{tomorrow_min}°C" if tomorrow_min is not None else "--"
                tomorrow_max_text = f"{tomorrow_max}°C" if tomorrow_max is not None else "--"
                
                weather_text += f"""

🔮 내일 예보:
- 최저: {tomorrow_min_text}
- 최고: {tomorrow_max_text}"""

            weather_text += f"""

📊 데이터: {weather_data.get('data_source', '기상청')}
🕐 조회: {datetime.now().strftime('%m월 %d일 %H시 %M분')}

🔍 디버깅 정보:
수집된 원본 데이터: {len(raw_data)}개 항목
{', '.join([k for k in raw_data.keys() if k != 'data_sources']) if raw_data else '없음'}
            """
            
            return weather_text.strip()
            
        except Exception as e:
            return f"날씨 정보 표시 오류: {str(e)}"

# 테스트 실행
if __name__ == "__main__":
    print("🌤️ 수정된 날씨 API 테스트 (오늘 기온 문제 완전 해결)")
    print("=" * 60)
    
    try:
        weather_api = WeatherAPI()
        
        # 여러 지역 테스트 (전국 다양한 지역)
        test_cities = [
            "서울", "마포구", "부산 해운대구", "제주시", 
            "부여군", "강릉시", "속초시", "전주시",
            "광주 서구", "대전 유성구", "울산 남구",
            "경주시", "안동시", "여수시", "춘천시"
        ]
        
        for test_city in test_cities:
            custom_print(f"\n📍 {test_city} 테스트:")
            print("-" * 40)
            
            try:
                weather_data = weather_api.get_weather_data(test_city)
                weather_text = weather_api.format_weather_info(weather_data, test_city)
                print(weather_text)
            except Exception as city_error:
                print(f"❌ {test_city} 오류: {city_error}")
            
            custom_print("\n" + "=" * 60)
        
    except Exception as e:
        print(f"❌ 전체 오류: {e}")
        import traceback
        traceback.print_exc()