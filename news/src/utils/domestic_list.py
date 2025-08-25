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
    listed_companies = []
    
    base_url = "https://kind.krx.co.kr/corpgeneral/corpList.do"
    entry_url = "https://kind.krx.co.kr/corpgeneral/corpList.do?method=loadInitPage&marketType=stockMkt"

    with requests.Session() as s:
        try:
            s.get(entry_url) 

            payload = {
                'method': 'searchCorpList',
                'pageIndex': '1',
                'currentPageSize': '15',
                'comAbbrv': '',
                'beginIndex': '',
                'orderMode': '3',
                'orderStat': 'D',
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

            headers = {
                'X-Requested-With': 'XMLHttpRequest',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36',
                'Referer': entry_url
            }

            response = s.post(base_url, data=payload, headers=headers)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            table_body = soup.find('tbody')
            
            if table_body:
                rows = table_body.find_all('tr')
                for row in rows[:10]:
                    cols = row.find_all('td')
                    if len(cols) > 3:
                        a_tag = cols[0].find('a')
                        if a_tag:
                            company_title = a_tag.get('title', '타이틀 없음').strip()
                        else:
                            company_title = '링크 태그 없음'
                        listing_date = cols[3].text.strip()
                        
                        stock_code = ''
                        a_tag = cols[0].find('a')
                        if a_tag:
                            onclick_attr = a_tag.get('onclick', '')
                            if 'companysummary_open' in onclick_attr:
                                match = re.search(r"companysummary_open\('(\d+)'\)", onclick_attr)
                                if match:
                                    stock_code = match.group(1)
                                    stock_code += '0'

                        listed_companies.append({"title": company_title, "code": stock_code, "date": listing_date})
            else:
                print("[오류] 응답 HTML에서 'tbody'를 찾을 수 없습니다.")

        except requests.exceptions.RequestException as e:
            print(f"[오류] KRX 데이터 API에 접속하는 중 문제가 발생했습니다: {e}")
        except Exception as e:
            print(f"[오류] 데이터를 파싱하는 중 오류가 발생했습니다: {e}")

    today_str = datetime.date.today().strftime('%Y-%m-%d')
    todays_listings = [company for company in listed_companies if company.get('date') == today_str]

    if todays_listings:
        print("\n---------- 오늘 신규 상장 기업 목록 ----------")
        for item in todays_listings:
            print(f"타이틀: {item['title']:<25} | 종목코드: {item['code']:<10} | 상장일: {item['date']}")
        print("---------------------------------------------")
    else:
        print("\n[알림] 오늘 신규 상장된 기업 정보가 없습니다.")
    
    return todays_listings