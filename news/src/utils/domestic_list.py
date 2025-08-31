# ------------------------------------------------------------------
# 작성자 : 곽은규
# 작성일 : 2025-08-23
# 기능 : 신규상장을 API로 불러와서 데이터(캐쉬)로 저장하는 함수
# ------------------------------------------------------------------
import requests
from bs4 import BeautifulSoup
import datetime
import re
import FinanceDataReader as fdr

def main_process():
    """
    한국거래소(KRX) KIND 웹사이트에서 최신 상장 기업 목록을 스크레이핑.
    그 중 당일 신규 상장된 기업 목록만 필터링하여 반환.
    :return: 오늘 신규 상장된 기업 정보가 담긴 리스트. 각 요소는 {"title": ..., "code": ..., "date": ...} 형태의 딕셔너리.
    """
    listed_companies = [] # 스크레이핑한 모든 기업 정보를 담을 리스트
    
    # KRX 상장법인목록 페이지 URL
    base_url = "https://kind.krx.co.kr/corpgeneral/corpList.do"
    # 세션 유지를 위해 최초 접속하는 URL
    entry_url = "https://kind.krx.co.kr/corpgeneral/corpList.do?method=loadInitPage&marketType=stockMkt"

    # 세션(Session)을 사용하여 쿠키 등 연결 정보를 유지
    with requests.Session() as s:
        try:
            # 1. 초기 페이지에 접속하여 세션 활성화
            s.get(entry_url) 

            # 2. 목록 조회를 위한 POST 요청 데이터 설정 (상장일 내림차순 정렬)
            payload = {
                'method': 'searchCorpList',
                'pageIndex': '1',
                'currentPageSize': '15', # 최신 15개 항목만 조회
                'comAbbrv': '',
                'beginIndex': '',
                'orderMode': '3', # 3: 상장일 순
                'orderStat': 'D', # D: 내림차순 (최신순)
                'isurCd': '',
                'repIsuSrtCd': '',
                'searchCodeType': '',
                'marketType': '', 
                'searchType': '13',
                'industry': '',
                'fiscalYearEnd': 'all',
                'comAbbrvTmp': '',
                'location': 'all'
            }

            # 3. 실제 브라우저처럼 보이기 위한 헤더 설정
            headers = {
                'X-Requested-With': 'XMLHttpRequest', # Ajax 요청임을 명시
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36',
                'Referer': entry_url # 이전 페이지 정보
            }

            # 4. 설정된 데이터와 헤더로 POST 요청 전송
            response = s.post(base_url, data=payload, headers=headers)
            response.raise_for_status() # 요청 실패 시 예외 발생

            # 5. 응답받은 HTML 텍스트를 파싱
            soup = BeautifulSoup(response.text, 'html.parser')
            table_body = soup.find('tbody') # 기업 목록이 담긴 테이블의 tbody 요소 탐색
            
            if table_body:
                rows = table_body.find_all('tr') # 모든 행(tr)을 가져옴
                # 최신 10개 행에 대해서만 처리
                for row in rows[:10]:
                    cols = row.find_all('td') # 각 행의 열(td)을 가져옴
                    if len(cols) > 3: # 열이 4개 이상인지 확인 (회사명, 종목코드, 대표자, 상장일 등)
                        # 회사명 추출
                        a_tag = cols[0].find('a')
                        company_title = a_tag.get('title', '타이틀 없음').strip() if a_tag else '링크 태그 없음'
                        # 상장일 추출 (네 번째 열)
                        listing_date = cols[3].text.strip()
                        
                        # 종목코드 추출 (onclick 속성값에서 파싱)
                        stock_code = ''
                        if a_tag:
                            onclick_attr = a_tag.get('onclick', '')
                            # 정규표현식을 사용하여 companysummary_open('종목코드') 형태에서 숫자 부분 추출
                            if 'companysummary_open' in onclick_attr:
                                match = re.search(r"companysummary_open\('(\d+)'\)", onclick_attr)
                                if match:
                                    stock_code = match.group(1)
                                    stock_code += '0' # KRX에서 사용하는 코드 형식에 맞추기 위해 '0' 추가

                        # 추출한 정보를 딕셔너리 형태로 리스트에 추가
                        listed_companies.append({"title": company_title, "code": stock_code, "date": listing_date})
            else:
                print("[오류] 응답 HTML에서 'tbody'를 찾을 수 없습니다.")

        except requests.exceptions.RequestException as e:
            print(f"[오류] KRX 데이터 API에 접속하는 중 문제가 발생했습니다: {e}")
        except Exception as e:
            print(f"[오류] 데이터를 파싱하는 중 오류가 발생했습니다: {e}")

    # 6. 스크레이핑한 목록에서 오늘 날짜와 상장일이 일치하는 기업만 필터링
    today_str = datetime.date.today().strftime('%Y-%m-%d')
    todays_listings = [company for company in listed_companies if company.get('date') == today_str]

    # 콘솔에 결과 출력 (디버깅 및 확인용)
    if todays_listings:
        print("\n---------- 오늘 신규 상장 기업 목록 ----------")
        for item in todays_listings:
            print(f"타이틀: {item['title']:<25} | 종목코드: {item['code']:<10} | 상장일: {item['date']}")
        print("---------------------------------------------")
    else:
        print("\n[알림] 오늘 신규 상장된 기업 정보가 없습니다.")
    
    # 7. 오늘 신규 상장된 기업 목록을 반환
    return todays_listings
