import time
import traceback
from PIL import Image
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from news.src.utils.driver_utils import initialize_driver


def get_stock_data_from_search(driver, keyword: str):
    """
    종목명을 네이버에서 검색한 후, 증권 정보 페이지로 이동하여 팝업을 닫고 데이터 추출
    """
    stock_data = {}
    try:
        search_url = f"https://search.naver.com/search.naver?query={keyword}+주가"
        print(f"\n🔍 검색 페이지 이동: {search_url}")
        driver.get(search_url)

        # 1. 차트 영역 대기 및 내부 canvas 완전 로딩까지 대기
        chart_section = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "section.sc_new.cs_stock"))
        )
        # 차트 내 canvas가 등장할 때까지 추가 대기
        canvas = WebDriverWait(chart_section, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div#stock_normal_chart3 canvas"))
        )
        # 필요시 약간의 여유 대기 (렌더링 지연 방지)
        import time
        time.sleep(0.5)

        # 2. 전체 차트 wrap 기준 스크린샷
        wrap_elem = driver.find_element(By.CSS_SELECTOR, "div.api_cs_wrap")
        screenshot_path = f"{keyword}_chart.png"
        import os, io
        # 스크린샷 저장하고 성공 여부 확인
        success = wrap_elem.screenshot(screenshot_path)
        if not success or not os.path.exists(screenshot_path) or os.path.getsize(screenshot_path) == 0:
            # 파일이 비정상적이면 메모리로 받아서 처리
            png_bytes = wrap_elem.screenshot_as_png
            original_img = Image.open(io.BytesIO(png_bytes))
            original_img.save(screenshot_path)
            print("⚠️ 파일로 저장 실패, 메모리 바이트로 대체 저장 완료.")
        else:
            original_img = Image.open(screenshot_path)
        print("✅ 차트 wrap 스크린샷 저장 완료.")
        
        # 원본 이미지 크기 확인
        print(f"📏 원본 이미지 크기: {original_img.size} (가로 x 세로)")

        # 3. 크롭 기준 좌표 계산 준비
        wrap_location = wrap_elem.location
        wrap_size = wrap_elem.size
        # market_info는 있을 수도, 없을 수도 있음
        from selenium.common.exceptions import NoSuchElementException
        try:
            market_elem = driver.find_element(By.CSS_SELECTOR, "div.market_info")
            market_location = market_elem.location
            market_size = market_elem.size
        except NoSuchElementException:
            market_location = {"x": 0, "y": 0}
            market_size = {"width": 0, "height": 0}
        
        # 요소 위치 정보 출력
        print(f"📍 wrap_elem 위치: x={wrap_location['x']}, y={wrap_location['y']}, width={wrap_size['width']}, height={wrap_size['height']}")
        print(f"📍 market_elem 위치: x={market_location['x']}, y={market_location['y']}, width={market_size['width']}, height={market_size['height']}")

        # 디스플레이 배율을 가져와 crop 좌표 보정
        device_pixel_ratio = driver.execute_script("return window.devicePixelRatio")
        print(f"🖥️ Device Pixel Ratio: {device_pixel_ratio}")

        # 비율 조정: 좌우 여백 줄이고, 아래쪽 여백 추가
        margin_x = 0  # 좌우 여백 제거
        margin_bottom = int(wrap_size['height'] * 0.1)  # 아래쪽 10% 여백 추가

        # wrap_elem을 이미 스크린샷했으므로 좌표를 wrap 내부 기준으로 계산
        # invest_wrap 또는 fallback 요소 위치 계산
        from selenium.common.exceptions import NoSuchElementException
        rel_invest_bottom = None
        try:
            invest_elem = driver.find_element(By.CSS_SELECTOR, "div.invest_wrap._button_scroller")
            invest_location = invest_elem.location
            invest_size = invest_elem.size
            print(f"📍 invest_elem 위치: x={invest_location['x']}, y={invest_location['y']}, width={invest_size['width']}, height={invest_size['height']}")
            rel_invest_bottom = (invest_location['y'] - wrap_location['y']) + invest_size['height']
        except NoSuchElementException:
            print("⚠️ invest_wrap._button_scroller 요소를 찾지 못함, more_view 기준 사용 시도")
            try:
                more_view_elem = driver.find_element(By.CSS_SELECTOR, "div.more_view")
                rel_invest_bottom = more_view_elem.location['y'] - wrap_location['y']
                print(f"📍 more_view 위치: y={more_view_elem.location['y']}")
            except NoSuchElementException:
                print("⚠️ more_view 요소도 찾지 못함, wrap 전체 높이 사용")
                rel_invest_bottom = wrap_size['height']

        left = int(margin_x * device_pixel_ratio)
        top = 0  # wrap 이미지의 상단부터
        right = int((wrap_size['width'] - margin_x) * device_pixel_ratio)
        bottom = int(rel_invest_bottom * device_pixel_ratio)
        
        print(f"📐 Crop 좌표 (배율 적용): left={left}, top={top}, right={right}, bottom={bottom}")
        print(f"📐 Crop 크기: {right-left} x {bottom-top} (가로 x 세로)")

        img = Image.open(screenshot_path)
        img_width, img_height = img.size
        
        # crop 좌표를 원본 이미지 범위 내로 제한
        left = max(0, min(left, img_width))
        top = max(0, min(top, img_height))
        right = max(left, min(right, img_width))
        bottom = max(top, min(bottom, img_height))
        
        print(f"🔧 수정된 Crop 좌표: left={left}, top={top}, right={right}, bottom={bottom}")
        print(f"🔧 수정된 Crop 크기: {right-left} x {bottom-top} (가로 x 세로)")
        
        cropped_img = img.crop((left, top, right, bottom))
        cropped_img.save(screenshot_path)
        print(f"✅ market_info 아래까지만 잘라서 '{screenshot_path}' 경로에 저장했습니다.")

        # 2. "증권 정보 더보기" 클릭
        more_view = chart_section.find_element(By.CSS_SELECTOR, "div.more_view a")
        driver.execute_script("arguments[0].click();", more_view)
        print("✅ '증권 정보 더보기' 클릭")

        # 3. 증권 페이지 로딩 대기 (새 창/탭 전환 포함)
        before_handles = driver.window_handles
        driver.execute_script("arguments[0].click();", more_view)
        time.sleep(1)
        after_handles = driver.window_handles
        if len(after_handles) > len(before_handles):
            new_handle = list(set(after_handles) - set(before_handles))[0]
            driver.switch_to.window(new_handle)
            print("✅ 새 창/탭으로 전환 완료:", driver.current_url)
        else:
            print("ℹ️ 새 창/탭 없음, 기존 창에서 진행")
        # URL 체크 대신 주요 요소 등장 대기
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".GraphMain_name__cEsOs"))
        )
        time.sleep(1)

        # 4. 팝업 닫기 단계 생략 (팝업 무시)
        # print("📦 팝업 처리 생략")

        # 5. 데이터 추출 (상세 정보 포함)
        print("📊 데이터 추출 중...")
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".GraphMain_name__cEsOs"))
        )
        stock_data["keyword"] = keyword
        stock_data["name"] = driver.find_element(By.CSS_SELECTOR, ".GraphMain_name__cEsOs").text
        stock_data["price"] = driver.find_element(By.CSS_SELECTOR, ".GraphMain_price__H72B2").text
        change_el = driver.find_element(By.CSS_SELECTOR, "div[class*='VGap_stockGap']")
        stock_data["change"] = change_el.text.replace('\n', ' ')

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

        # 재무 정보 테이블 추출
        financial_info_list = driver.find_elements(By.CSS_SELECTOR, "ul.StockInfo_list__V96U6 > li.StockInfo_item__puHWj")
        for item in financial_info_list:
            try:
                parts = item.text.split('\n')
                if len(parts) >= 2:
                    title = parts[0].strip()
                    value = " ".join(parts[1:]).strip()
                    if title and value:
                        stock_data[title] = value
            except Exception:
                continue

        # 기업 개요 정보 추출
        try:
            overview_element = driver.find_element(By.CSS_SELECTOR, "div.Overview_text__zT3AI")
            stock_data['기업 개요'] = overview_element.text.strip()
        except Exception:
            print("⚠️ 기업 개요 정보를 찾을 수 없습니다.")

        print("✅ 데이터 추출 완료")
        return stock_data

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        traceback.print_exc()
        return None


def wait_and_close_top10_popup(driver, timeout=7):
    """
    WebDriverWait로 팝업 등장 대기 후 X버튼 클릭. timeout 내에 안 뜨면 그냥 넘어감.
    """
    try:
        print("팝업이 뜨기를 기다립니다...")
        close_btn = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button.BottomModalNoticeWrapper-module_button-close__dRRuc")
            )
        )
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", close_btn)
        print("✅ 팝업 닫기 완료")
    except Exception as e:
        print(f"⚠️ {timeout}초 내에 팝업이 뜨지 않음 또는 닫기 실패: {e}")
        # 필요시 DOM 강제 제거
        try:
            driver.execute_script('''
                const el = document.querySelector('[class*="BottomModalNoticeWrapper-module_notice-wrapper"]');
                if (el) el.remove();
            ''')
            print("✅ 팝업 DOM 제거 완료")
        except Exception:
            pass

# --- 실행 ---
if __name__ == "__main__":
    while True:
        keyword = input("\n🔍 검색할 종목명 입력 (예: 삼성전자, 애플 / 종료: q): ").strip()
        if keyword.lower() in ["q", "exit"]:
            print("👋 종료합니다")
            break
        if not keyword:
            print("⚠️ 종목명을 입력해주세요")
            continue

        driver = None
        try:
            driver = initialize_driver(headless=True)
            driver.set_window_size(1920, 1080)

            result = get_stock_data_from_search(driver, keyword)
            if result:
                print("\n📊 추출 결과:")
                for k, v in result.items():
                    print(f"{k}: {v}")
            else:
                print("❌ 데이터 수집 실패")
        finally:
            if driver:
                driver.quit()
                print("🔄 드라이버 재시작 완료")
