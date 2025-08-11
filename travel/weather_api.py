#############################################################################################################################
#############################################################################################################################
#8월 11일 날씨 정확도 개선, 문제 해결
# weather_api.py
# 스마트한 기상청 API (문제 해결 버전)

import requests
import math
from datetime import datetime, timedelta

import os
from dotenv import load_dotenv

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
    print("⚠️ data.py에서 import 실패. 전국 지역 지원을 위해 카카오 API 사용")
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
                    print(f"   📋 검색 결과 {len(data['documents'])}개:")
                    
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
                    print(f"   📍 위도: {lat:.4f}, 경도: {lon:.4f}")
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
        print(f"\n🎯 === 최종 결과 ===")
        print(f"📊 총 항목 수: {len(final_weather)}")
        print(f"📋 수집된 항목:")
        for key, value in final_weather.items():
            if key != 'data_sources':
                print(f"   • {key}: {value}")
        
        if not final_weather or len(final_weather) <= 1:  # data_sources만 있는 경우
            raise Exception("모든 기상청 API에서 데이터를 가져올 수 없습니다.")
        
        return final_weather
    
    def try_current_weather(self, grid_x, grid_y, base_time):
        """초단기실황 데이터 (JSON 파싱 오류 해결)"""
        try:
            base_date = base_time.strftime('%Y%m%d')
            base_time_str = base_time.strftime('%H%M')
            
            print(f"   🔍 API 호출: {base_date} {base_time_str}")
            
            params = {
                'serviceKey': self.kma_api_key,
                'pageNo': '1',
                'numOfRows': '100',
                'dataType': 'JSON',
                'base_date': base_date,
                'base_time': base_time_str,
                'nx': str(grid_x),
                'ny': str(grid_y)
            }
            
            response = requests.get(self.kma_current_url, params=params, timeout=REQUEST_TIMEOUT)
            print(f"   📡 응답 코드: {response.status_code}")
            
            if response.status_code == 200:
                # 응답 내용 확인
                response_text = response.text.strip()
                if not response_text:
                    print("   ❌ 빈 응답")
                    return None
                
                # JSON 파싱 시도
                try:
                    data = response.json()
                except ValueError as json_error:
                    print(f"   ❌ JSON 파싱 오류: {json_error}")
                    print(f"   📄 응답 내용 (처음 200자): {response_text[:200]}")
                    return None
                
                # API 응답 구조 확인
                if 'response' not in data:
                    print(f"   ❌ 응답 구조 오류: response 키 없음")
                    return None
                
                header = data['response'].get('header', {})
                result_code = header.get('resultCode', '')
                result_msg = header.get('resultMsg', '')
                
                print(f"   📋 결과: {result_code} - {result_msg}")
                
                if result_code == '00':
                    # body 구조 확인
                    body = data['response'].get('body', {})
                    if not body:
                        print("   ⚠️ body 없음")
                        return None
                    
                    items = body.get('items', {})
                    if isinstance(items, list):
                        item_list = items
                    elif isinstance(items, dict):
                        item_list = items.get('item', [])
                    else:
                        print(f"   ⚠️ items 구조 오류: {type(items)}")
                        return None
                    
                    print(f"   📊 데이터 항목 수: {len(item_list) if item_list else 0}")
                    
                    if not item_list:
                        print("   ⚠️ 빈 데이터")
                        return None
                    
                    # 받은 원본 데이터 출력
                    for item in item_list:
                        category = item.get('category', 'Unknown')
                        value = item.get('obsrValue', 'N/A')
                        print(f"   📝 {category}: {value}")
                    
                    # 데이터 파싱
                    current_weather = {}
                    for item in item_list:
                        category = item.get('category')
                        value = item.get('obsrValue')
                        
                        if not category or not value:
                            continue
                        
                        if category == 'T1H':      # 기온
                            try:
                                current_weather['temperature'] = float(value)
                            except ValueError:
                                pass
                        elif category == 'REH':    # 습도
                            try:
                                current_weather['humidity'] = float(value)
                            except ValueError:
                                pass
                        elif category == 'PTY':    # 강수형태
                            current_weather['precipitation_type'] = self.get_precipitation_text(value)
                        elif category == 'RN1':    # 1시간 강수량
                            current_weather['hourly_precipitation'] = self.parse_precipitation_amount(value)
                        elif category == 'WSD':    # 풍속
                            try:
                                current_weather['wind_speed'] = float(value)
                            except ValueError:
                                pass
                        elif category == 'VEC':    # 풍향
                            try:
                                wind_deg = float(value)
                                current_weather['wind_direction'] = wind_deg
                                current_weather['wind_direction_text'] = self.get_wind_direction_text(wind_deg)
                            except ValueError:
                                pass
                    
                    print(f"   ✅ 파싱 완료: {current_weather}")
                    return current_weather if current_weather else None
                else:
                    print(f"   ❌ API 오류: {result_code} - {result_msg}")
                    return None
            else:
                print(f"   ❌ HTTP 오류: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"   💥 예외: {str(e)}")
            return None
    
    def try_forecast_weather(self, grid_x, grid_y):
        """단기예보 데이터 (정확한 발표시각 계산)"""
        try:
            now = datetime.now()
            
            # 단기예보 발표 시각: 02, 05, 08, 11, 14, 17, 20, 23시 (10분 후 데이터 제공)
            forecast_times = [2, 5, 8, 11, 14, 17, 20, 23]
            current_hour = now.hour
            current_minute = now.minute
            
            base_time = None
            base_date = now.strftime('%Y%m%d')
            
            # 현재 시각 기준으로 가장 최근 발표시각 찾기
            for time in reversed(forecast_times):
                if current_hour > time or (current_hour == time and current_minute >= 10):
                    base_time = f"{time:02d}00"
                    break
            
            if base_time is None:
                # 오늘 발표된 것이 없으면 어제 마지막 발표 사용
                yesterday = now - timedelta(days=1)
                base_date = yesterday.strftime('%Y%m%d')
                base_time = "2300"
            
            print(f"   🔍 API 호출: {base_date} {base_time}")
            
            params = {
                'serviceKey': self.kma_api_key,
                'pageNo': '1',
                'numOfRows': '1000',
                'dataType': 'JSON',
                'base_date': base_date,
                'base_time': base_time,
                'nx': str(grid_x),
                'ny': str(grid_y)
            }
            
            response = requests.get(self.kma_forecast_url, params=params, timeout=REQUEST_TIMEOUT)
            print(f"   📡 응답 코드: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                if 'response' not in data:
                    print(f"   ❌ 응답 구조 오류")
                    return None
                
                result_code = data['response']['header']['resultCode']
                result_msg = data['response']['header'].get('resultMsg', '')
                
                print(f"   📋 결과: {result_code} - {result_msg}")
                
                if result_code == '00':
                    body = data['response'].get('body', {})
                    if not body:
                        return None
                    
                    items = body.get('items', {})
                    if isinstance(items, list):
                        item_list = items
                    elif isinstance(items, dict):
                        item_list = items.get('item', [])
                    else:
                        return None
                    
                    print(f"   📊 데이터 항목 수: {len(item_list) if item_list else 0}")
                    
                    if not item_list:
                        return None
                    
                    # 오늘/내일 날짜
                    today = now.strftime('%Y%m%d')
                    tomorrow = (now + timedelta(days=1)).strftime('%Y%m%d')
                    current_hour_str = f"{now.hour:02d}00"
                    
                    forecast_data = {}
                    found_items = []
                    
                    for item in item_list:
                        category = item.get('category')
                        value = item.get('fcstValue')
                        fcst_date = item.get('fcstDate')
                        fcst_time = item.get('fcstTime')
                        
                        if not all([category, value, fcst_date, fcst_time]):
                            continue
                        
                        # 현재 시간 이후 첫 데이터 또는 가장 가까운 시간
                        if fcst_date == today and fcst_time >= current_hour_str:
                            if category == 'POP' and 'rain_probability' not in forecast_data:
                                try:
                                    forecast_data['rain_probability'] = int(value)
                                    found_items.append(f"POP={value}%")
                                except ValueError:
                                    pass
                            elif category == 'PCP' and 'precipitation_amount' not in forecast_data:
                                forecast_data['precipitation_amount'] = self.parse_precipitation_amount(value)
                                found_items.append(f"PCP={value}")
                            elif category == 'SKY' and 'sky_condition' not in forecast_data:
                                forecast_data['sky_condition'] = self.get_sky_text(value)
                                found_items.append(f"SKY={self.get_sky_text(value)}")
                        
                        # 오늘 최저/최고 기온 (06시 TMN, 15시 TMX)
                        if fcst_date == today:
                            if category == 'TMN' and fcst_time == '0600' and value not in ['-999', '-', ''] and 'min_temp_today' not in forecast_data:
                                try:
                                    forecast_data['min_temp_today'] = float(value)
                                    found_items.append(f"today TMN={value}°C")
                                except ValueError:
                                    pass
                            elif category == 'TMX' and fcst_time == '1500' and value not in ['-999', '-', ''] and 'max_temp_today' not in forecast_data:
                                try:
                                    forecast_data['max_temp_today'] = float(value)
                                    found_items.append(f"today TMX={value}°C")
                                except ValueError:
                                    pass
                        
                        # 내일 최저/최고 기온 (06시 TMN, 15시 TMX)
                        elif fcst_date == tomorrow:
                            if category == 'TMN' and fcst_time == '0600' and value not in ['-999', '-', ''] and 'min_temp_tomorrow' not in forecast_data:
                                try:
                                    forecast_data['min_temp_tomorrow'] = float(value)
                                    found_items.append(f"tomorrow TMN={value}°C")
                                except ValueError:
                                    pass
                            elif category == 'TMX' and fcst_time == '1500' and value not in ['-999', '-', ''] and 'max_temp_tomorrow' not in forecast_data:
                                try:
                                    forecast_data['max_temp_tomorrow'] = float(value)
                                    found_items.append(f"tomorrow TMX={value}°C")
                                except ValueError:
                                    pass
                    
                    print(f"   ✅ 찾은 항목: {found_items}")
                    print(f"   📊 최종 데이터: {forecast_data}")
                    
                    return forecast_data if forecast_data else None
                else:
                    print(f"   ❌ API 오류: {result_code} - {result_msg}")
                    return None
            else:
                print(f"   ❌ HTTP 오류: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"   💥 예외: {str(e)}")
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
            formatted_data = {
                'main': {
                    'temp': temperature,
                    'feels_like': temperature,
                    'humidity': weather_data.get('humidity', 60),
                    'temp_min': weather_data.get('min_temp_today'),
                    'temp_max': weather_data.get('max_temp_today')
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
                    'today_min': weather_data.get('min_temp_today'),
                    'today_max': weather_data.get('max_temp_today'),
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
            
            weather_text = f"""
📍 {matched_region} 상세 날씨 정보

🌡️ 기온:
- 현재: {main['temp']}°C
- 최저: {main.get('temp_min', '--')}°C (오늘)
- 최고: {main.get('temp_max', '--')}°C (오늘)
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
                weather_text += f"""

🔮 내일 예보:
- 최저: {forecast.get('tomorrow_min', '--')}°C
- 최고: {forecast.get('tomorrow_max', '--')}°C"""

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
    print("🌤️ 수정된 날씨 API 테스트 (문제 해결 버전)")
    print("=" * 50)
    
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
            print(f"\n📍 {test_city} 테스트:")
            print("-" * 30)
            
            try:
                weather_data = weather_api.get_weather_data(test_city)
                weather_text = weather_api.format_weather_info(weather_data, test_city)
                print(weather_text)
            except Exception as city_error:
                print(f"❌ {test_city} 오류: {city_error}")
            
            print("\n" + "=" * 50)
        
    except Exception as e:
        print(f"❌ 전체 오류: {e}")                                                                                                            
        import traceback
        traceback.print_exc()