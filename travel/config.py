# config.py - API 키 및 전역 설정 관리
# ===================================================================================
# 파일명     : config.py
# 작성자     : 하승주, 홍석원
# 최초작성일 : 2025-09-04
# 설명       : 환경변수(.env)에서 API 키들을 안전하게 로드하고
#              API 엔드포인트 URL 및 요청 설정 상수를 정의하는 전역 설정 모듈
# ===================================================================================
#
# 【주요 기능】
# - 환경변수(.env)에서 API 키들을 안전하게 로드
# - API 엔드포인트 URL 및 요청 설정 상수 정의
# - API 키 유효성 검증 및 연결 테스트 기능 제공
#
# 【관리하는 API】
# - KAKAO_API_KEY: 카카오 API (주소→좌표 변환)
# - KMA_API_KEY: 기상청 API (날씨 데이터)
# - GOOGLE_API_KEY: Google Gemini API (AI 기사 생성)
#
# 【설정 항목】
# - API 엔드포인트 URL들
# - 재시도 횟수 및 타임아웃 설정
# - 파일 인코딩 및 출력 형식 설정
#
# 【유틸리티 함수】
# - validate_api_keys(): 모든 API 키 설정 여부 확인
# - test_api_keys(): 실제 API 호출로 연결 상태 테스트
#
# 【보안】
# - API 키는 환경변수로만 관리
# - 소스코드에 하드코딩된 키 없음
# - .env 파일은 .gitignore에 포함되어야 함
#
# 【사용처】
# - weather_api.py: 날씨 관련 API 설정
# - chatbot_app.py: AI API 설정
# ===================================================================================

# 기존 API 키들
import os
from dotenv import load_dotenv

load_dotenv()

# API 키들 (환경 변수에서 로드)
KAKAO_API_KEY = os.getenv("KAKAO_API_KEY")
KMA_API_KEY = os.getenv("KMA_API_KEY")

# API URL 설정
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent"
KAKAO_COORD_URL = "https://dapi.kakao.com/v2/local/search/address.json"
KMA_WEATHER_URL = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"

# weather_api.py에서 사용하는 추가 URL들
KMA_CURRENT_URL = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"  # 초단기실황

# 재시도 설정
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30
RETRY_DELAY_MIN = 2
RETRY_DELAY_MAX = 5

# 파일 저장 설정
OUTPUT_ENCODING = 'utf-8'
OUTPUT_FILE_SUFFIX = '_weather_article.txt'

# API 키 검증 함수
def validate_api_keys():
    """API 키가 설정되었는지 확인"""
    missing_keys = []
    
    if not KAKAO_API_KEY or KAKAO_API_KEY == "YOUR_KAKAO_API_KEY_HERE":
        missing_keys.append("KAKAO_API_KEY")
    
    if not KMA_API_KEY or KMA_API_KEY == "YOUR_KMA_API_KEY_HERE":
        missing_keys.append("KMA_API_KEY")
    
    if missing_keys:
        print("⚠️ 다음 API 키들이 설정되지 않았습니다:")
        for key in missing_keys:
            print(f"   - {key}")
        print("\n🔧 config.py 파일에서 API 키를 설정해주세요.")
        print("📖 API 키 발급 방법:")
        print("   - 카카오 API: https://developers.kakao.com/")
        print("   - 기상청 API: https://www.data.go.kr/")
        return False
    
    print("✅ 모든 API 키가 정상적으로 설정되었습니다.")
    return True

def test_api_keys():
    """API 키 연결 테스트"""
    import requests
    
    print("🔍 API 키 연결 테스트 중...")
    
    # 카카오 API 테스트
    try:
        headers = {'Authorization': f'KakaoAK {KAKAO_API_KEY}'}
        params = {'query': '서울특별시 강남구'}
        response = requests.get(KAKAO_COORD_URL, headers=headers, params=params, timeout=5)
        
        if response.status_code == 200:
            print("✅ 카카오 API 연결 성공")
        else:
            print(f"❌ 카카오 API 오류: {response.status_code}")
            
    except Exception as e:
        print(f"❌ 카카오 API 연결 실패: {e}")
    
    # 기상청 API 테스트 (간단한 파라미터로)
    try:
        params = {
            'serviceKey': KMA_API_KEY,
            'pageNo': '1',
            'numOfRows': '1',
            'dataType': 'JSON',
            'base_date': '20250729',
            'base_time': '1400',
            'nx': '60',
            'ny': '127'
        }
        response = requests.get(KMA_WEATHER_URL, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('response', {}).get('header', {}).get('resultCode') == '00':
                print("✅ 기상청 API 연결 성공")
            else:
                result_msg = data.get('response', {}).get('header', {}).get('resultMsg', 'Unknown error')
                print(f"❌ 기상청 API 오류: {result_msg}")
        else:
            print(f"❌ 기상청 API HTTP 오류: {response.status_code}")
            
    except Exception as e:
        print(f"❌ 기상청 API 연결 실패: {e}")

if __name__ == "__main__":
    print("🔧 API 설정 확인")
    print("=" * 30)
    validate_api_keys()
    print()
    test_api_keys()