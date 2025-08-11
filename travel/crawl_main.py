

# 네이버 플레이스 데이터를 크롤링하여 수집하는 스크립트입니다.


import os
import re
import csv
import time
import random
import gc
import json
import pandas as pd 
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.common.action_chains import ActionChains

# 새로 생성한 DB 매니저 임포트
import db_manager as db_manager

# --- 설정값 ---
SAVE_DIR = r"C:\Users\TDI\Desktop\FromAI-crw\crw_data"
CSV_FILE_PATH = os.path.join(SAVE_DIR, "전국 법정동.csv")
DB_PATH = os.path.join(SAVE_DIR, "naver_travel_places.db")
PROGRESS_FILE = os.path.join(SAVE_DIR, "crawling_progress.json")
MAX_PAGES_PER_QUERY = 1
MIN_VISITOR_REVIEWS = 10
MIN_BLOG_REVIEWS = 50

def setup_driver():
    """셀레니움 웹드라이버를 설정하고 반환합니다."""
    options = webdriver.ChromeOptions()
    options.add_argument('--start-maximized')
    # options.add_argument('--headless=new') # 필요 시 활성화
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument('--log-level=3')
    # 메모리 최적화 옵션
    options.add_argument('--memory-pressure-off')
    options.add_argument('--disable-background-timer-throttling')
    options.add_argument('--disable-renderer-backgrounding')
    options.add_argument('--disable-backgrounding-occluded-windows')
    options.add_argument('--disable-features=TranslateUI,VizDisplayCompositor')
    
    try:
        driver = webdriver.Chrome(options=options)
        return driver
    except Exception as e:
        print(f"[ERROR] 드라이버 설정 실패: {e}")
        return None

def load_search_queries(file_path):
    """CSV 파일에서 검색어 목록을 생성합니다."""
    queries = []
    try:
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            next(reader)  # 헤더 건너뛰기
            for row in reader:
                parts = [part.strip() for part in row[:3] if part.strip()] # 시, 군, 읍/면/동 까지만
                if parts:
                    query = " ".join(parts) + " 가볼만한곳"
                    if query not in queries:
                        queries.append(query)
    except FileNotFoundError:
        print(f"[ERROR] CSV 파일을 찾을 수 없습니다: {file_path}")
    except Exception as e:
        print(f"[ERROR] CSV 파일 읽기 실패: {e}")
    return queries

def save_progress(completed_queries):
    """진행 상황 (완료된 검색어 목록)을 JSON 파일로 저장합니다."""
    try:
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump({"completed_queries": completed_queries}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ERROR] 진행 상황 저장 실패: {e}")

def load_progress():
    """이전 진행 상황 (완료된 검색어 목록)을 불러옵니다."""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                completed = data.get("completed_queries", [])
                print(f"[INFO] 이전 진행 상황을 복구했습니다. {len(completed)}개의 검색어를 건너뜁니다.")
                return completed
        except (json.JSONDecodeError, KeyError) as e:
            print(f"[WARN] 진행 상황 파일을 읽을 수 없습니다. 새로 시작합니다. ({e})")
    return []

def cleanup_memory():
    """메모리 정리를 수행합니다."""
    gc.collect()
    time.sleep(0.5)

# --- 원본 코드의 유틸리티 함수들 (수정 없이 사용) ---
def switch_to_frame_safely(driver, frame_id, retries=5, delay=1.5):
    for _ in range(retries):
        try:
            driver.switch_to.default_content()
            WebDriverWait(driver, 10).until(EC.frame_to_be_available_and_switch_to_it((By.ID, frame_id)))
            return True
        except TimeoutException:
            time.sleep(delay)
    return False

def robust_scroll_in_iframe(driver, max_scrolls=30, scroll_amount=1200):
    scroll_target = None
    try:
        scroll_target = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.Ryr1F"))
        )
    except TimeoutException:
        print("[WARN] 스크롤 대상을 찾지 못했습니다.")
        return

    prev_count, no_change_count = 0, 0
    for i in range(max_scrolls):
        items = driver.find_elements(By.CSS_SELECTOR, "li.S0Ns3.TPSle.QBNpp")
        curr_count = len(items)
        if curr_count == prev_count:
            no_change_count += 1
            if no_change_count >= 5:
                break
        else:
            no_change_count = 0
        prev_count = curr_count
        driver.execute_script("arguments[0].scrollBy(0, arguments[1]);", scroll_target, scroll_amount)
        time.sleep(random.uniform(0.8, 1.2))
        if i % 10 == 0:
            cleanup_memory()

def get_text_or_default(element, selector, default_value="정보 없음"):
    try:
        return element.find_element(By.CSS_SELECTOR, selector).text.strip()
    except (NoSuchElementException, StaleElementReferenceException):
        return default_value

def extract_review_count(review_text):
    match = re.search(r'\d[\d,]*', review_text)
    return int(match.group(0).replace(',', '')) if match else 0

def get_total_reviews_from_entry_iframe(driver):
    visitor_text = get_text_or_default(driver, "span.PXMot > a[href*='/review/visitor']", "방문자 리뷰 0")
    blog_text = get_text_or_default(driver, "span.PXMot > a[href*='/review/ugc']", "블로그 리뷰 0")
    return {
        "total_visitor_reviews_count": str(extract_review_count(visitor_text)),
        "total_blog_reviews_count": str(extract_review_count(blog_text)),
    }

def find_and_click_place_link(driver, item):
    selectors = [
        "a.place_bluelink", "a[href*='/place/']", "div.TYaxT", "span.xBZDS",
        ".S0Ns3.TPSle.QBNpp a", "div[role='button']",
    ]
    for selector in selectors:
        try:
            elements = item.find_elements(By.CSS_SELECTOR, selector)
            if elements and elements[0].is_displayed() and elements[0].is_enabled():
                driver.execute_script("arguments[0].click();", elements[0])
                WebDriverWait(driver, 8).until(lambda d: "place/" in d.current_url)
                return True
        except Exception:
            continue
    try:
        driver.execute_script("arguments[0].click();", item)
        WebDriverWait(driver, 8).until(lambda d: "place/" in d.current_url)
        return True
    except Exception:
        return False

def crawl_place_details(driver, db_conn, search_query, place_name):
    """개별 장소의 상세 정보를 크롤링합니다."""
    data = { "검색어": search_query }
    
    driver.switch_to.default_content()
    detail_url = driver.current_url
    match = re.search(r'/place/(\d+)', detail_url)
    data["naver_place_id"] = match.group(1) if match else f"URL_{random.randint(10000, 99999)}"

    # DB 중복 체크
    if db_manager.check_place_exists(db_conn, data["naver_place_id"]):
        print(f"  [스킵] '{place_name}' - 이미 DB에 저장된 장소입니다 (ID: {data['naver_place_id']})")
        return None

    if not switch_to_frame_safely(driver, "entryIframe"):
        print(f"  [ERROR] '{place_name}' - 상세 정보 프레임 전환 실패. 건너뜁니다.")
        return None

    # 리뷰 수
    reviews = get_total_reviews_from_entry_iframe(driver)
    data["총 방문자 리뷰 수"] = reviews["total_visitor_reviews_count"]
    data["총 블로그 리뷰 수"] = reviews["total_blog_reviews_count"]

    # 필터링
    if int(data["총 방문자 리뷰 수"]) < MIN_VISITOR_REVIEWS or int(data["총 블로그 리뷰 수"]) < MIN_BLOG_REVIEWS:
        print(f"  [필터 미통과] '{place_name}' - 리뷰 수 부족 (방문자: {data['총 방문자 리뷰 수']}, 블로그: {data['총 블로그 리뷰 수']})")
        return None

    # 주소
    jibun_address, road_address = "", ""
    addr_spans = driver.find_elements(By.CSS_SELECTOR, "span.LDgIH")
    for span in addr_spans:
        txt = span.text.strip()
        if txt.startswith("지번 "):
            jibun_address = txt.replace("지번 ", "")
        elif not road_address:
            road_address = txt
    data["주소"] = jibun_address or road_address or "정보 없음"

    # 정보/리뷰 탭 등 나머지 정보는 원본 코드 로직을 따름
    # (이 부분은 셀렉터 의존성이 높아, 원본 코드를 최대한 유지)
    try:
        # 정보 탭 로직 (간소화)
        info_tab = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, '//span[@class="veBoZ" and contains(text(),"정보")]')))
        info_tab.click()
        time.sleep(0.5)
        # 펼치기 버튼
        try:
            unfold_btn = driver.find_element(By.CSS_SELECTOR, "a.OWPIf")
            if unfold_btn.is_displayed(): unfold_btn.click()
            time.sleep(0.5)
        except: pass
    except: pass # 정보 탭 없어도 진행

    data["소개"] = get_text_or_default(driver, "div.T8RFa.CEyr5", "소개 정보 없음")
    keywords = [el.text.strip() for el in driver.find_elements(By.CSS_SELECTOR, "span.RLvZP") if el.text.strip()]
    data["키워드"] = ', '.join(keywords) if keywords else "키워드 정보 없음"

    try:
        # 리뷰 탭 클릭
        review_tab = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, '//span[@class="veBoZ" and contains(text(),"리뷰")]')))
        review_tab.click()
        WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.vfTO3")))
        time.sleep(1)
        
        visitor_review_elements = driver.find_elements(By.CSS_SELECTOR, "div.vfTO3")[:5]
        visitor_review_keywords = [el.find_element(By.CSS_SELECTOR, "span.t3JSf").text.strip('"') for el in visitor_review_elements]
        data["방문자 리뷰"] = ', '.join(visitor_review_keywords) if visitor_review_keywords else "정보 없음"
    except:
        data["방문자 리뷰"] = "정보 없음"

    return data

def crawl_area(driver, db_conn, search_query):
    """단일 검색어에 대한 크롤링을 수행합니다."""
    wait = WebDriverWait(driver, 15)

    
    try:
        # 1. 네이버 지도 진입 및 검색
        driver.set_page_load_timeout(60)
        driver.get("https://map.naver.com/p?c=15.00,0,0,0,dh")
        time.sleep(random.uniform(2, 3))

        search_box = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input.input_search")))
        search_box.clear()
        search_box.send_keys(search_query)
        search_box.send_keys(Keys.ENTER)
        time.sleep(random.uniform(3, 4))

        if not switch_to_frame_safely(driver, "searchIframe"):
            print(f"[ERROR] '{search_query}' - 장소 목록 프레임을 찾지 못했습니다.")
            return

        # 2. 페이지별 크롤링 (최대 3페이지)
        for page in range(1, MAX_PAGES_PER_QUERY + 1):
            print(f"\n===== '{search_query}' - {page}/{MAX_PAGES_PER_QUERY}페이지 크롤링 중 =====")
            robust_scroll_in_iframe(driver)
            
            place_items = driver.find_elements(By.CSS_SELECTOR, "li.S0Ns3.TPSle.QBNpp")
            if not place_items:
                print("  [INFO] 해당 페이지에 장소 목록이 없습니다.")
                break

            print(f"  [DEBUG] 발견된 장소 아이템 수: {len(place_items)}개")
            
            for rank, item in enumerate(place_items):
                page_data = []
                try:
                    # StaleElement 예방을 위해 목록 다시 찾기
                    current_items = driver.find_elements(By.CSS_SELECTOR, "li.S0Ns3.TPSle.QBNpp")
                    if rank >= len(current_items): continue
                    
                    item_to_click = current_items[rank]
                    
                    place_name = get_text_or_default(item_to_click, "span.xBZDS")
                    category = get_text_or_default(item_to_click, "span.LF32u")
                    print(f"  [처리 중] {rank+1}번째 '{place_name}' ({category})")

                    if not find_and_click_place_link(driver, item_to_click):
                        print(f"    [ERROR] '{place_name}' - 상세 페이지 진입 실패. 건너뜁니다.")
                        continue
                    
                    time.sleep(random.uniform(2.0, 3.0))
                    
                    # 상세 정보 크롤링
                    place_details = crawl_place_details(driver, db_conn, search_query, place_name)
                    
                    if place_details:
                        place_details["장소명"] = place_name
                        place_details["카테고리"] = category
                        page_data.append(place_details)
                        print(f"    [수집 완료] '{place_name}'")
                    else:
                        print(f"    [정보 없음] '{place_name}' - 상세 정보 수집에 실패했거나 필터링되었습니다.")

                except StaleElementReferenceException:
                    print("    [WARN] StaleElement 예외 발생. 다음 항목으로 넘어갑니다.")
                    continue # 현재 아이템만 건너뛰고 계속 진행
                except Exception as e:
                    print(f"    [ERROR] 장소 처리 중 예외 발생: {e}")
                finally:
                    # DB 저장 (5개 단위)
                    if page_data:
                        db_manager.save_places_to_db(db_conn, page_data)
                        page_data = []

                    # 메인 프레임으로 복귀
                    driver.switch_to.default_content()
                    if not switch_to_frame_safely(driver, "searchIframe"):
                        print("[FATAL] 검색 목록 프레임으로 복귀 실패. 현재 검색어 중단.")
                        return

            # 남은 데이터 저장
            if page_data:
                db_manager.save_places_to_db(db_conn, page_data)

            # 다음 페이지로 이동
            if page < MAX_PAGES_PER_QUERY:
                try:
                    next_btn = driver.find_element(By.CSS_SELECTOR, 'a.eUTV2[aria-disabled="false"]')
                    next_btn.click()
                    time.sleep(random.uniform(2,3))
                except Exception:
                    print("  [INFO] 다음 페이지가 없어 현재 검색어를 종료합니다.")
                    break
    
    except Exception as e:
        print(f"[ERROR] '{search_query}' 크롤링 중 심각한 오류 발생: {e}")


if __name__ == "__main__":
    os.makedirs(SAVE_DIR, exist_ok=True)
    db_manager.initialize_db(DB_PATH)

    all_queries = load_search_queries(CSV_FILE_PATH)
    completed_queries = load_progress()
    
    queries_to_do = [q for q in all_queries if q not in completed_queries]

    print(f"\n[시작] 총 {len(all_queries)}개의 검색어 중 {len(queries_to_do)}개가 남았습니다.")
    
    driver = None  # 반복문 바깥에서 선언해서 재사용할 수 있게 함

    for i, query in enumerate(queries_to_do):
        print(f"\n{'='*60}")
        print(f"[{i+1}/{len(queries_to_do)}] 다음 검색어 처리 시작: {query}")
        print(f"{'='*60}")

        # ✅ 10개마다 driver 재시작
        if i % 1 == 0 and i != 0:
            if driver:
                print("[INFO] 드라이버 재시작 중... 메모리 절약을 위해 종료 후 재실행")
                driver.quit()
                cleanup_memory()
                driver = None

        # ✅ driver가 없으면 새로 생성
        if not driver:
            driver = setup_driver()
            if not driver:
                print("[FATAL] 드라이버를 시작할 수 없어 현재 검색어를 건너뜁니다.")
                continue

        db_conn = None
        try:
            db_conn = db_manager.create_connection(DB_PATH)
            if not db_conn:
                print("[FATAL] DB에 연결할 수 없어 현재 검색어를 건너뜁니다.")
                continue

            crawl_area(driver, db_conn, query)

            # 진행 상황 저장
            completed_queries.append(query)
            save_progress(completed_queries)
            print(f"\n[완료] '{query}' 검색어 처리 완료.")

        except KeyboardInterrupt:
            print("\n[중단] 사용자에 의해 프로그램이 중단되었습니다.")
            save_progress(completed_queries)
            break
        except Exception as e:
            print(f"[FATAL ERROR] '{query}' 처리 중 예기치 않은 오류 발생: {e}")
        finally:
            if db_conn:
                db_conn.close()
            cleanup_memory()
            time.sleep(random.uniform(3, 5))

    # ✅ 전체 끝난 후에 driver 종료
    if driver:
        driver.quit()

    print("\n[최종 완료] 모든 검색어 처리가 완료되었습니다.")
