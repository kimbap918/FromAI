# weather_warning.py - 기상특보 API 연동 및 데이터 파싱
# ===================================================================================
# 파일명     : weather_warning.py
# 작성자     : 하승주, 홍석원
# 최초작성일 : 2025-09-04
# 설명       : 기상청 기상특보 API (getPwnStatus) 전용 클래스 및
#              전국 특보 데이터 파싱과 복잡한 특보 문자열의 구조화된 데이터 변환
# ===================================================================================
#
# 【주요 기능】
# - 기상청 기상특보 API (getPwnStatus) 전용 클래스
# - 전국 특보 데이터 파싱 및 지역별 분해
# - 복잡한 특보 문자열의 구조화된 데이터 변환
#
# 【핵심 파싱 로직】
# 1. 전국 조회 응답의 t6 필드 파싱
#    - "o 폭염경보 : 충청남도(공주, 아산), 전라남도 \r\n o 폭염주의보 : 서울특별시"
#    - 개별 특보와 지역으로 분해
#
# 2. 지역 문자열 처리
#    - "충청남도(공주, 아산)" → ["충청남도(공주, 아산)"]
#    - 괄호 내 쉼표와 지역 구분 쉼표 구별
#
# 3. 구조화된 출력
#    - [{title: "폭염경보", region: "충청남도(공주, 아산)"}, ...]
#
# 【API 연동】
# - WeatherWarningAPI 클래스: 기상청 API 래퍼
# - 재시도 로직: 5회 재시도, 백오프 전략
# - 타임아웃 설정: 연결/읽기 시간 제한
# - XML 응답 파싱: ElementTree 기반
#
# 【데이터 변환】
# - 원본: 전국 단위 통합 특보 (1개 레코드)
# - 변환: 지역별/종류별 개별 특보 (N개 레코드)
# - 메타데이터 보존: 발표시각(tmFc), 발효시각(tmEf) 유지
#
# 【출력 포맷팅】
# - format_warning_info(): UI 표시용 텍스트 생성
# - 특보별 지역, 발표시각 정리
# - 이모지 활용한 직관적 표시
#
# 【지역 코드 지원】
# - 전국 조회: stn_ids=None
# - 지역별 조회: 17개 시도 코드 제공
# - 필요 시 특정 지역만 선택 조회 가능
#
# 【오류 처리】
# - API 응답 코드 검증
# - XML 파싱 오류 방지
# - 빈 데이터 및 해제 특보 필터링
#
# 【사용처】
# - weather_tab.py: 기상특보 탭 데이터 소스
# - weather_ai_generator.py: 특보 기사 생성 데이터
# ===================================================================================

import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Optional

import requests
from requests.adapters import HTTPAdapter, Retry
from dotenv import load_dotenv

API_URL = "http://apis.data.go.kr/1360000/WthrWrnInfoService/getPwnStatus"

# ==============================================================================
# 파싱 유틸리티 함수 (핵심 로직)
# ==============================================================================

def _parse_regions(region_str: str) -> List[str]:
    """'충청남도(공주, 아산), 전라남도, ...' 같은 문자열을 개별 지역 리스트로 분해"""
    # 괄호 안의 쉼표를 임시 문자로 대체하여, 지역 구분을 위한 쉼표와 혼동되지 않게 함
    # 예: '충청남도(공주, 아산)' -> '충청남도(공주; 아산)'
    in_parens = re.findall(r'\((.*?)\)', region_str)
    for content in in_parens:
        region_str = region_str.replace(content, content.replace(',', ';'))

    # 쉼표로 지역들을 분리
    regions = [r.strip() for r in region_str.split(',') if r.strip()]

    # 임시 문자를 다시 쉼표로 복원
    return [r.replace(';', ',') for r in regions]

def _parse_t6_string(t6_text: str) -> List[Dict[str, str]]:
    """
    API 응답의 t6 필드(긴 텍스트)를 구조화된 딕셔너리 리스트로 파싱합니다.
    예: [{'title': '폭염경보', 'region': '충청남도(공주, 아산)'}, ...]
    """
    if not t6_text:
        return []

    parsed_warnings = []
    # "o 폭염경보 : [지역들] \r\n o 폭염주의보 : [지역들]" 형식의 문자열을 분리
    warning_blocks = t6_text.strip().split('\r\n')

    for block in warning_blocks:
        block = block.strip()
        if not block.startswith('o '):
            continue

        # "o [특보명] : [지역들]" 형식에서 특보명과 지역들을 추출
        match = re.match(r'o\s*(?P<title>\S+)\s*:\s*(?P<regions>.+)', block)
        if not match:
            continue

        data = match.groupdict()
        warning_title = data.get('title', '기상특보')
        regions_text = data.get('regions', '')

        # 지역 문자열을 개별 지역 리스트로 분해
        regions = _parse_regions(regions_text)

        for region in regions:
            parsed_warnings.append({
                "title": warning_title,
                "region": region
            })

    return parsed_warnings

def _restructure_warnings(rows: List[Dict]) -> List[Dict]:
    """
    API 원본 응답을 파싱하여 새로운 구조의 특보 목록으로 재구성합니다.
    전국 단위로 조회된 단일 특보를 개별 지역/종류별 특보로 분해하는 것이 핵심.
    """
    if not rows:
        return []

    # 전국 단위 조회 결과(항목이 1개이고, stnId가 없음)인 경우 파싱 로직 적용
    if len(rows) == 1 and not rows[0].get("stnId"):
        raw_warning = rows[0]
        t6_text = raw_warning.get("t6", "")
        
        # t6 필드를 파싱하여 구조화된 목록 생성
        parsed_list = _parse_t6_string(t6_text)
        
        # 파싱된 각 항목에 원본의 공통 정보(발표시각 등)를 추가
        for item in parsed_list:
            item['tmFc'] = raw_warning.get('tmFc', '')
            item['tmEf'] = raw_warning.get('tmEf', '')
            item['other'] = raw_warning.get('other', '')
        
        return parsed_list

    # 이미 구조화된 경우(지역별 조회 등)는 그대로 반환
    return rows

# ==============================================================================
# 기존 클래스 (수정됨)
# ==============================================================================

class WeatherWarningAPI:
    def __init__(self, service_key: Optional[str] = None):
        load_dotenv()
        self.api_key = service_key or os.getenv("KMA_API_KEY")
        if not self.api_key:
            raise Exception("환경변수 KMA_API_KEY가 없습니다. .env에 KMA_API_KEY=디코딩키 설정")

        self.session = requests.Session()
        retries = Retry(total=5, connect=3, read=3, backoff_factor=0.8,
                        status_forcelist=[429, 500, 502, 503, 504],
                        allowed_methods=["GET"])
        self.session.mount("http://", HTTPAdapter(max_retries=retries))
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

    def get_weather_warnings(self, stn_ids: Optional[list] = None, num_rows: int = 500) -> List[Dict]:
        """
        기상특보를 조회합니다.
        stn_ids가 없으면 전국 단위로 조회하고, 그 결과를 파싱하여 재구성합니다.
        """
        # 전국 단위 조회 (stn_ids가 None일 때)
        if not stn_ids:
            params = {
                "serviceKey": self.api_key,
                "pageNo": "1",
                "numOfRows": str(num_rows),
                "dataType": "XML"
            }
            # _call_api 내부에서 파싱 및 재구성까지 모두 처리
            return self._call_api(params)

        # 특정 지역들 조회
        out = []
        for sid in stn_ids:
            params = {
                "serviceKey": self.api_key,
                "pageNo": "1",
                "numOfRows": str(num_rows),
                "dataType": "XML",
                "stnId": str(sid)
            }
            out.extend(self._call_api(params))
        return out

    def format_warning_info(self, warnings: List[Dict]) -> str:
        """재구성된 데이터 구조에 맞게 UI 표시용 텍스트를 포맷팅합니다."""
        if not warnings:
            return "🟢 현재 발효 중인 기상특보가 없습니다."

        # 발표시각(tmFc) 기준으로 정렬
        warnings = sorted(warnings, key=lambda z: z.get("tmFc", ""), reverse=True)
        lines = [f"🚨 현재 기상특보 현황 ({len(warnings)}건)", "="*60]

        for w in warnings:
            # 파싱된 데이터에는 'region' 키가 존재함
            region_info = w.get("region", f"지역코드_{w.get('stnId', 'N/A')}")
            lines.append(f"\n📍 {w.get('title', '기상특보')} | {region_info}")
            lines.append(f"   ⏰ 발표: {w.get('tmFc', '')}") # tmFc는 _restructure_warnings에서 복사해 줌
        return "\n".join(lines)

    def _call_api(self, params: Dict[str, str]) -> List[Dict]:
        try:
            r = self.session.get(API_URL, params=params, timeout=(15, 60))
            if r.status_code != 200:
                return []
            
            # XML 파싱 후, 결과를 재구성하는 로직 추가
            parsed_rows = self._parse_xml(r.text)
            return _restructure_warnings(parsed_rows)

        except Exception as e:
            print(f"❌ 요청 실패: {e}")
            return []

    def _parse_xml(self, xml_text: str) -> List[Dict]:
        """XML 응답을 파싱하여 딕셔너리 리스트로 변환 (원본 기능 유지)"""
        if not xml_text.strip(): return []
        try:
            root = ET.fromstring(xml_text.strip())
        except Exception as e:
            print(f"❌ XML 파싱 실패: {e}")
            return []

        if root.tag == "OpenAPI_ServiceResponse":
            print("❌ OpenAPI 오류 응답")
            return []

        code = (root.findtext(".//resultCode") or "").strip()
        if code and code not in {"0", "00"}:
            return []

        rows = []
        for it in root.findall(".//item"):
            row = {ch.tag: (ch.text or "").strip() for ch in list(it)}
            if not row.get("title"):
                # t6 필드 내용을 기반으로 대표 제목 생성
                t6_content = row.get("t6", "")
                if "폭염경보" in t6_content: row["title"] = "폭염경보"
                elif "폭염주의보" in t6_content: row["title"] = "폭염주의보"
                else: row["title"] = "기상특보"

            if "해제" not in row.get("title", ""):
                rows.append(row)
        return rows
    
    def get_region_codes(self):
        return {
            "전국": None, "서울": "108", "부산": "159", "대구": "143", "인천": "112",
            "광주": "156", "대전": "133", "울산": "152", "세종": "239", "경기": "109",
            "강원": "105", "충북": "131", "충남": "129", "전북": "146", "전남": "165",
            "경북": "137", "경남": "155", "제주": "184",
        }