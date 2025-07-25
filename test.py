import time
from PIL import Image
from selenium import webdriver
from selenium.webdriver.common.by import By
from news.src.utils.driver_utils import initialize_driver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def get_foreign_stock_data_from_naver(driver, keyword: str):
    """
    네이버에서 해외 주식을 검색하고, 증권 페이지로 이동하여 텍스트 데이터를 추출
    :param keyword: 검색할 종목명 또는 티커 (예: 'AAPL', '테슬라')
    :return: 추출된 텍스트 데이터 딕셔너리
    """
    
    stock_data = {}

    try:
        # 1. 목표 URL로 직접 이동 (속도 개선)
        # .O는 나스닥 종목을 의미, 다른 시장은 코드가 다를 수 있음
        target_url = f"https://m.stock.naver.com/worldstock/stock/{keyword}.O/total"
        print(f"🚀 {target_url} 로 직접 이동합니다...")
        driver.get(target_url)

        # 2. 팝업 닫기 (존재하는 경우)
        try:
            print("팝업 닫기 버튼을 기다립니다...")
            # 버튼이 나타날 때까지 최대 5초 대기
            close_button = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "button[class*='ModalFrame-module_button-close']"))
            )
            time.sleep(0.5) # 애니메이션 등을 위한 추가 대기
            
            print("JavaScript로 팝업 닫기 버튼을 클릭합니다.")
            driver.execute_script("arguments[0].click();", close_button)
            print("✅ 팝업 닫기 완료.")
            time.sleep(0.5) # 팝업이 완전히 닫힐 때까지 대기

        except Exception:
            print("팝업이 없거나 닫는 데 실패했습니다. 데이터 추출을 계속 진행합니다.")

        # 3. 데이터 추출 (새로운 네이버 모바일 증권 페이지 기준)
        print("📊 데이터 추출 중...")
        
        # 페이지가 완전히 로드될 때까지 대기 (종목 이름이 나타날 때까지)
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".GraphMain_name__cEsOs"))
        )

        stock_data['ticker'] = keyword
        stock_data['name'] = driver.find_element(By.CSS_SELECTOR, ".GraphMain_name__cEsOs").text
        stock_data['price'] = driver.find_element(By.CSS_SELECTOR, ".GraphMain_price__H72B2").text
        change_element = driver.find_element(By.CSS_SELECTOR, "div[class*='VGap_stockGap']")
        change_parts = change_element.text.split('\n')
        stock_data['change'] = ' '.join(list(dict.fromkeys(change_parts)))

        # 시간 정보 추출
        time_elements = driver.find_elements(By.CSS_SELECTOR, ".GraphMain_date__GglkR .GraphMain_time__38Tp2")
        if len(time_elements) >= 2:
            stock_data['korea_time'] = time_elements[0].text.replace('\n', ' ')
            stock_data['us_time'] = time_elements[1].text.replace('\n', ' ')

        # '종목정보 더보기' 버튼 클릭하여 모든 정보 표시
        try:
            more_info_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "a.StockInfo_btnFold__XEUUS"))
            )
            driver.execute_script("arguments[0].click();", more_info_button)
            print("✅ '종목정보 더보기' 클릭 완료.")
            time.sleep(0.5) # 정보가 로드될 시간을 줍니다.
        except Exception:
            print("⚠️ '종목정보 더보기' 버튼을 찾을 수 없거나 이미 모든 정보가 표시되어 있습니다.")

        # 재무 정보 테이블 추출 (이제 모든 정보가 표시됨)
        financial_info_list = driver.find_elements(By.CSS_SELECTOR, "ul.StockInfo_list__V96U6 > li.StockInfo_item__puHWj")
        for item in financial_info_list:
            try:
                # 각 li 요소의 텍스트를 줄바꿈으로 분리
                parts = item.text.split('\n')
                if len(parts) >= 2:
                    # 첫 줄은 제목, 나머지는 값
                    title = parts[0].strip()
                    value = " ".join(parts[1:]).strip()
                    if title and value: # 제목과 값이 모두 유효한 경우에만 추가
                        stock_data[title] = value
            except Exception:
                continue # 특정 항목에서 오류 발생 시 다음으로 넘어감

        # 기업 개요 정보 추출
        try:
            overview_element = driver.find_element(By.CSS_SELECTOR, "div.Overview_text__zT3AI")
            stock_data['기업 개요'] = overview_element.text.strip()
        except Exception:
            print("⚠️ 기업 개요 정보를 찾을 수 없습니다.")

        print(f"✅ [{keyword}] 데이터 추출 성공!")

        return stock_data

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        return None



def get_foreign_stock_data_from_naver_direct(ticker: str):
    """
    종목 티커를 기반으로 네이버 증권 페이지 URL을 직접 생성하여 접속하고 데이터를 추출합니다.
    모든 기능 테스트는 이 파일 안에서만 이루어집니다.
    :param ticker: 해외주식 티커 (예: 'AAPL', 'TSLA')
    :return: 추출된 텍스트 데이터 딕셔너리 또는 실패 시 None
    """
    target_url = f"https://m.stock.naver.com/worldstock/stock/{ticker}/total"
    print(f"🎯 [{ticker}] 목표 URL로 직접 이동: {target_url}")

    # 기능 테스트를 위해 브라우저 창을 직접 확인합니다.
    driver = initialize_driver(headless=False)
    stock_data = {}

    try:
        driver.get(target_url)

        # 팝업 닫기 (존재하는 경우)
        try:
            close_button = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "button[class*='ModalFrame-module_button-close']"))
            )
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", close_button)
            print("✅ 팝업 닫기 성공 또는 팝업 없음")
        except Exception:
            pass # 팝업이 없으면 그냥 진행

        # 데이터 추출 (사용자가 알려준 새 선택자 기반)
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".GraphMain_name__cEsOs"))
        )

        stock_data['ticker'] = ticker
        stock_data['name'] = driver.find_element(By.CSS_SELECTOR, ".GraphMain_name__cEsOs").text
        stock_data['price'] = driver.find_element(By.CSS_SELECTOR, ".GraphMain_price__H72B2").text
        change_element = driver.find_element(By.CSS_SELECTOR, "div[class*='VGap_stockGap']")
        stock_data['change'] = change_element.text



        print(f"✅ [{ticker}] 데이터 추출 성공!")
        return stock_data

    except Exception as e:
        print(f"❌ [{ticker}] 데이터 추출 중 오류 발생: {e}")
        return None

    finally:
        print("테스트 종료. 브라우저를 닫습니다.")
        if 'driver' in locals():
            driver.quit()

def capture_stock_chart_screenshot(driver, keyword):
    """네이버 검색 결과에서 주식 차트를 스크린샷으로 저장합니다."""
    try:
        print(f"\n📈 '{keyword} 주가' 차트 스크린샷 캡처를 시작합니다...")
        search_url = f"https://search.naver.com/search.naver?query={keyword}+주가"
        driver.get(search_url)
        print(f"✅ {search_url} 로 이동 완료.")

        # 차트가 포함된 섹션 요소 기다리기
        chart_section_selector = "section.sc_new.cs_stock"
        chart_element = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, chart_section_selector))
        )
        print("✅ 차트 영역 발견!")

        # 실제 차트 그래픽(SVG path)이 렌더링될 때까지 대기
        try:
            print("⏳ 차트 그래픽이 렌더링되기를 기다립니다...")
            chart_graphic_selector = f"{chart_section_selector} svg g path"
            WebDriverWait(driver, 2).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, chart_graphic_selector))
            )
            print("✅ 차트 렌더링 완료!")
            time.sleep(0.5)  # 최종 렌더링 안정화를 위해 잠시 대기
        except Exception as e:
            print(f"❌ 차트 렌더링 대기 중 오류 발생: {e}")
            print("⚠️ 렌더링 확인에 실패했지만, 스크린샷을 강행합니다.")

        # 스크린샷 저장 후 자르기
        screenshot_path = f"{keyword}_chart.png"
        chart_element.screenshot(screenshot_path)
        
        # Pillow를 사용하여 이미지 하단 자르기
        img = Image.open(screenshot_path)
        width, height = img.size
        # 아래쪽 정보 영역을 잘라내기 위해 높이 조정 
        crop_area = (0, 0, width, height - 150)
        cropped_img = img.crop(crop_area)
        cropped_img.save(screenshot_path)
        
        print(f"✅ 차트 스크린샷을 잘라서 '{screenshot_path}' 경로에 저장했습니다.")
        return True
    except Exception as e:
        print(f"❌ 차트 스크린샷 캡처 중 오류 발생: {e}")
        return False

# --- 실행 예시 ---
if __name__ == "__main__":
    # 테스트하고 싶은 해외 종목을 여기에 입력하세요.
    stock_keyword = "AAPL"
    driver = None  # finally 블록에서 사용하기 위해 초기화

    try:
        # 1. 드라이버 초기화
        driver = initialize_driver(headless=False)

        # 2. 네이버 증권에서 데이터 스크래핑
        print("--- 네이버 증권 데이터 스크래핑 시작 ---")
        stock_data = get_foreign_stock_data_from_naver(driver, stock_keyword)

        if stock_data:
            print("\n--- 최종 추출 데이터 ---")
            for key, value in stock_data.items():
                print(f"{key}: {value}")
            print("---------------------")

            # 3. 네이버 검색에서 차트 스크린샷 캡처
            capture_stock_chart_screenshot(driver, stock_keyword)
        else:
            print(f"\n{stock_keyword}에 대한 데이터 추출에 실패했습니다.")

    except Exception as e:
        print(f"전체 실행 중 오류가 발생했습니다: {e}")

    finally:
        if driver:
            driver.quit()
            print("\n👋 드라이버를 종료합니다.")
