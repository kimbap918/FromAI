import os
import time
import re
import platform
import subprocess
from datetime import datetime
from PIL import Image
import io

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

try:
    import win32clipboard
    import win32con
    CLIPBOARD_AVAILABLE = True
except ImportError:
    CLIPBOARD_AVAILABLE = False

def copy_image_to_clipboard(image_path):
    if not CLIPBOARD_AVAILABLE:
        return False
    try:
        image = Image.open(image_path).convert('RGB')
        output = io.BytesIO()
        image.save(output, 'BMP')
        data = output.getvalue()[14:]
        output.close()
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_DIB, data)
        win32clipboard.CloseClipboard()
        return True
    except:
        try:
            win32clipboard.CloseClipboard()
        except:
            pass
        return False

def open_image(path):
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.run(["open", path])
        elif platform.system() == "Linux":
            subprocess.run(["xdg-open", path])
    except:
        pass

def wait_for_page_load(driver, timeout=10):
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except:
        pass

def has_tab_elements(driver):
    return bool(driver.find_elements(By.CSS_SELECTOR, "a.top_tab_link"))

def click_krx_tab(driver):
    try:
        elements = driver.find_elements(By.CSS_SELECTOR, "a.top_tab_link")
        for el in elements:
            if 'KRX' in el.text.upper() and el.is_displayed():
                driver.execute_script("arguments[0].click();", el)
                time.sleep(0.2)
                return True
    except:
        pass
    return False

def find_wrap_company_element(driver):
    selectors = ["div.wrap_company", "div[class='wrap_company']", "div[class*='wrap_company']", ".wrap_company"]
    for selector in selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for el in elements:
                if el.is_displayed():
                    return el
        except:
            continue
    return None

def extract_stock_name(driver):
    try:
        el = driver.find_element(By.CSS_SELECTOR, "div.wrap_company h2 a")
        name = el.text.strip()
        if name:
            return name
    except:
        pass
    return "Unknown"

def generate_output_path(stock_code: str, stock_name: str, base_folder: str = "주식차트") -> str:
    today = datetime.now().strftime("%Y%m%d")
    folder = os.path.join(base_folder, today)
    os.makedirs(folder, exist_ok=True)
    clean_name = stock_name.replace(" ", "").replace("/", "_").replace("\\", "_")
    filename = f"{stock_code}_{clean_name}.png"
    return os.path.join(folder, filename)

def capture_wrap_company_area(stock_code: str) -> str:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        url = f"https://finance.naver.com/item/main.naver?code={stock_code}"
        driver.get(url)
        wait_for_page_load(driver, 10)
        time.sleep(0.3)

        stock_name = extract_stock_name(driver)

        if has_tab_elements(driver):
            click_krx_tab(driver)
            time.sleep(0.3)

        el = find_wrap_company_element(driver)
        if not el:
            print("wrap_company 요소를 찾지 못했습니다.")
            return None

        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.3)

        screenshot_path = os.path.abspath("full_screenshot.png")
        driver.save_screenshot(screenshot_path)

        location = el.location
        zoom = driver.execute_script("return window.devicePixelRatio || 1;")
        start_x = int(location['x'] * zoom)
        start_y = int(location['y'] * zoom)
        width, height = 700, 515
        left = max(0, start_x)
        top = max(0, start_y)
        right = left + width
        bottom = top + height

        image = Image.open(screenshot_path)
        right = min(right, image.width)
        bottom = min(bottom, image.height)
        left = max(0, right - width)
        top = max(0, bottom - height)
        cropped = image.crop((left, top, right, bottom))

        output_path = generate_output_path(stock_code, stock_name)
        cropped.save(output_path)

        if os.path.exists(screenshot_path):
            os.remove(screenshot_path)

        return output_path

    except Exception as e:
        print(f"오류 발생: {e}")
        return None
    finally:
        try:
            driver.quit()
        except:
            pass

def get_stock_info_from_search(keyword: str):
    if keyword.isdigit() and len(keyword) == 6:
        return keyword

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,1024")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        search_url = f"https://search.naver.com/search.naver?query={keyword}+주식"
        print(f" 검색 시도: {search_url}")
        driver.get(search_url)
        time.sleep(0.5)

        finance_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='finance.naver.com/item/main']")
        for link in finance_links:
            href = link.get_attribute('href')
            match = re.search(r"code=(\d{6})", href)
            if match:
                stock_code = match.group(1)
                print(f" 코드 추출 성공: {stock_code}")
                return stock_code

        return None
    except Exception as e:
        print(f" 검색 중 오류: {e}")
        return None
    finally:
        driver.quit()

if __name__ == "__main__":
    print("주식 코드 또는 회사명을 입력하세요 (0: 종료)")
    while True:
        keyword = input("입력: ").strip()
        if keyword == "0":
            break
        stock_code = get_stock_info_from_search(keyword)
        if not stock_code:
            print("주식 코드를 찾을 수 없습니다.")
            continue
        image_path = capture_wrap_company_area(stock_code)
        if image_path:
            print(f"저장됨: {image_path}")
            if platform.system() == "Windows":
                copy_image_to_clipboard(image_path)
            open_image(image_path)
