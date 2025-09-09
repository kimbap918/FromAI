# realtime_crawler.py - 실시간 네이버 장소 정보 크롤링
# ===================================================================================
# 파일명     : realtime_crawler.py
# 작성자     : 하승주, 홍석원
# 최초작성일 : 2025-09-04
# 설명       : Selenium을 사용한 네이버 지도 실시간 크롤링 모듈
#              특정 장소의 최신 '소개' 정보만 선택적 수집 및 차단 완화 로직 포함
# ===================================================================================
#
# 【주요 기능】
# - Selenium을 사용한 네이버 지도 실시간 크롤링
# - 특정 장소의 최신 '소개' 정보만 선택적 수집
# - 사용량 차단 완화를 위한 스텔스 모드 및 재시도 로직
#
# 【크롤링 대상】
# - 네이버 지도 장소 상세 페이지 (map.naver.com/p/entry/place/{place_id})
# - 장소의 '정보' 탭 또는 홈 탭의 place_summary 영역
# - 텍스트 정보만 추출 (이미지, 링크 제외)
#
# 【안정성 기능】
# - 헤드리스 크롬 브라우저 사용
# - 고정 User-Agent 및 프로필 디렉토리 유지
# - CDP 명령어로 웹드라이버 탐지 우회
# - 차단 감지 시 자동 쿨다운 (25-50초)
#
# 【크롤링 절차】
# 1. 웜업: 네이버 지도 홈 먼저 방문
# 2. 대상 장소 페이지 로드
# 3. entryIframe으로 전환
# 4. '정보' 탭 클릭 → 펼쳐보기 → 내용 추출
# 5. 실패 시 홈 탭의 place_summary 시도
#
# 【오류 처리】
# - 타임아웃: 페이지 로드 20초, 요소 검색 2-5초
# - 재시도: 최대 3회, 각 단계별 독립적 재시도
# - 차단 감지: 특정 키워드 패턴 감지 시 중단
#
# 【사용처】
# - travel_logic.py: 기사 생성 전 최신 정보 업데이트
# - db_manager.py: update_introduction()과 연동
# ===================================================================================

import os
import re
import time
import random
from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# =========================
# 설정
# =========================
PAGELOAD_TIMEOUT = 20
IFRAME_TIMEOUT   = 8
FIND_TIMEOUT_S   = 2.0
FIND_TIMEOUT_M   = 5.0

MAP_HOME = "https://map.naver.com/"
PROFILE_DIR = os.environ.get("CRAWL_PROFILE_DIR", str(Path.home() / ".realtime_chrome_profile"))
FIXED_UA = os.environ.get("CRAWL_UA",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# 차단 감지 → 쿨다운 범위(초)
COOLDOWN_ON_BLOCK = (25, 50)

# =========================
# 유틸
# =========================
def randsleep(a=0.25, b=0.6):
    time.sleep(random.uniform(a, b))

def looks_like_blocked(text: str) -> bool:
    if not text:
        return False
    pats = [
        r"비정상적인\s*접근", r"잠시\s*후\s*다시\s*시도",
        r"요청이\s*많", r"오류가\s*발생", r"403\s*Forbidden"
    ]
    return any(re.search(p, text) for p in pats)

# =========================
# 드라이버
# =========================
def setup_driver() -> Optional[webdriver.Chrome]:
    """셀레니움 웹드라이버를 설정하고 반환합니다."""
    options = webdriver.ChromeOptions()
    options.add_argument('--headless=new')  # 필요시 사용(차단에는 headful 권장)
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-gpu')
    options.add_argument("--disable-software-rasterizer")
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
    options.add_experimental_option('useAutomationExtension', False)

    # 세션 일관성(쿠키/스토리지 유지)
    Path(PROFILE_DIR).mkdir(parents=True, exist_ok=True)
    options.add_argument(f'--user-data-dir={PROFILE_DIR}')
    # 고정 UA
    options.add_argument(f'--user-agent={FIXED_UA}')
    # 언어/알림
    prefs = {
        "intl.accept_languages": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "profile.default_content_setting_values.notifications": 2
    }
    options.add_experimental_option("prefs", prefs)

    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(PAGELOAD_TIMEOUT)

        # 라이트 스텔스: 헤더/타임존/로케일 + webdriver 감춤
        try:
            driver.execute_cdp_cmd("Network.enable", {})
            driver.execute_cdp_cmd("Network.setExtraHTTPHeaders", {
                "headers": {
                    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Referer": "https://map.naver.com/"
                }
            })
            driver.execute_cdp_cmd("Emulation.setTimezoneOverride", {"timezoneId": "Asia/Seoul"})
            driver.execute_cdp_cmd("Emulation.setLocaleOverride", {"locale": "ko-KR"})
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument",
                                   {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"})
        except Exception as e:
            print(f"[STEALTH] CDP 설정 실패: {e}")

        return driver
    except Exception as e:
        print(f"[SYSTEM] 드라이버 설정 실패: {e}")
        return None

def warmup(driver):
    """맵 홈 먼저 방문하여 쿠키/리소스 적재 (직행 패턴 완화)"""
    try:
        driver.get(MAP_HOME)
        randsleep(0.6, 1.2)
    except Exception as e:
        print(f"[WARMUP] 실패: {e}")

# =========================
# 메인 크롤링
# =========================
def crawl_introduction(naver_place_id: str) -> Optional[str]:
    """
    안정성을 강화한 크롤러. 타임아웃/로그/웜업/라이트 스텔스 적용.
    셀렉터는 고정: 정보탭 veBoZ, 펼쳐보기 a.OWPIf
    """
    if not naver_place_id or not naver_place_id.isdigit():
        print(f"[VALIDATION] 유효하지 않은 ID: {naver_place_id}")
        return None

    url = f"https://map.naver.com/p/entry/place/{naver_place_id}"
    driver = setup_driver()
    if not driver:
        return None
        
    print(f"[CRAWL] ID {naver_place_id} 처리 시작.")
    
    try:
        # 0. 웜업
        warmup(driver)

        # 1. 페이지 로드
        try:
            print("  [STEP 1] 페이지 로드 시도...")
            driver.get(url)
            randsleep(0.4, 0.8)
            try:
                if looks_like_blocked(driver.find_element(By.TAG_NAME, "body").text):
                    cool = random.uniform(*COOLDOWN_ON_BLOCK)
                    print(f"  [BLOCK] 상위 문서 차단 신호 → {cool:.1f}s 대기")
                    time.sleep(cool)
                    return None
            except:
                pass
            print("  [STEP 1] 페이지 로드 완료.")
        except TimeoutException:
            print(f"  [FAIL] 페이지 로드 시간 초과 ({PAGELOAD_TIMEOUT}초). URL: {url}")
            return None

        # 2. IFrame 전환
        try:
            print("  [STEP 2] IFrame으로 전환 시도...")
            WebDriverWait(driver, IFRAME_TIMEOUT).until(
                EC.frame_to_be_available_and_switch_to_it((By.ID, "entryIframe"))
            )
            randsleep(0.2, 0.4)
            try:
                if looks_like_blocked(driver.find_element(By.TAG_NAME, "body").text):
                    cool = random.uniform(*COOLDOWN_ON_BLOCK)
                    print(f"  [BLOCK] iframe 차단 신호 → {cool:.1f}s 대기")
                    time.sleep(cool)
                    return None
            except:
                pass
            print("  [STEP 2] IFrame 전환 완료.")
        except TimeoutException:
            print("  [FAIL] IFrame(entryIframe)을 찾지 못했습니다.")
            return None

        introduction_text = None

        # 3. '정보' 탭 시도 (고정 셀렉터 유지)
        try:
            print("  [STEP 3] '정보' 탭 탐색 시도...")
            info_tab = WebDriverWait(driver, FIND_TIMEOUT_S).until(
                EC.element_to_be_clickable((By.XPATH, '//span[@class="veBoZ" and contains(text(),"정보")]'))
            )
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", info_tab)
            randsleep(0.15, 0.35)
            driver.execute_script("arguments[0].click();", info_tab)
            print("  [STEP 3] '정보' 탭 클릭 완료.")
            
            # 펼쳐보기 (고정 셀렉터 유지)
            try:
                unfold_btn = WebDriverWait(driver, FIND_TIMEOUT_S).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "a.OWPIf"))
                )
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", unfold_btn)
                randsleep(0.15, 0.35)
                driver.execute_script("arguments[0].click();", unfold_btn)
            except TimeoutException:
                pass  # 없어도 됨

            info_element = WebDriverWait(driver, FIND_TIMEOUT_M).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.AX_W3"))
            )
            introduction_text = info_element.text.strip()

        except TimeoutException:
            print("  [STEP 3] '정보' 탭을 찾지 못함. 홈 탭으로 대체 탐색합니다.")

        # 4. 홈 탭 시도 (대체)
        if not introduction_text:
            try:
                print("  [STEP 4] 홈 탭에서 'place_summary' 탐색 시도...")
                summary_element = WebDriverWait(driver, FIND_TIMEOUT_M).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".place_summary"))
                )
                introduction_text = summary_element.text.strip()
                print("  [STEP 4] 'place_summary' 내용 추출 성공.")

                # 더보기 버튼
                try:
                    unfold_btn = WebDriverWait(driver, FIND_TIMEOUT_S).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, ".Z4f_p"))
                    )
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", unfold_btn)
                    randsleep(0.15, 0.35)
                    driver.execute_script("arguments[0].click();", unfold_btn)
                    time.sleep(0.5)
                    summary_element = WebDriverWait(driver, FIND_TIMEOUT_S).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".place_summary"))
                    )
                    introduction_text = summary_element.text.strip()
                except TimeoutException:
                    pass  # 없어도 됨

            except TimeoutException:
                print("  [STEP 4] 홈 탭에서도 'place_summary'를 찾지 못했습니다.")

        # 5. 최종 결과 반환
        if introduction_text:
            print(f"  [SUCCESS] 최종 소개 정보 추출 완료.")
            return introduction_text
        else:
            print("  [FAIL] 모든 단계에서 소개 정보를 찾지 못했습니다.")
            return None

    except Exception as e:
        print(f"  [UNEXPECTED] 예측하지 못한 오류 발생: {e}")
        return None
    finally:
        # 6. 드라이버 종료 보장
        if driver:
            print("[CLEANUP] 드라이버 및 관련 프로세스를 종료합니다.")
            driver.quit()
            print("[CLEANUP] 모든 프로세스가 정상적으로 종료되었습니다.")

if __name__ == '__main__':
    test_place_ids = ["18967604"]
    for place_id in test_place_ids:
        print(f"\n--- 테스트 시작: ID {place_id} ---")
        intro = crawl_introduction(place_id)
        if intro:
            print(f"\n[결과] ID {place_id}\n{intro[:200]}...")
        else:
            print(f"\n[결과] ID {place_id}: 실패")
