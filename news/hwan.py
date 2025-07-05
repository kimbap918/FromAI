import os
import time
import io
import platform
import subprocess
from datetime import datetime
from PIL import Image
import pyperclip
import webbrowser

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
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
        print("❌ 클립보드 복사가 지원되지 않는 환경입니다.")
        return
    image = Image.open(image_path).convert('RGB')
    output = io.BytesIO()
    image.save(output, 'BMP')
    data = output.getvalue()[14:]
    output.close()
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardData(win32con.CF_DIB, data)
    win32clipboard.CloseClipboard()
    print("✅ 이미지가 클립보드에 복사되었습니다.")

def capture_exchange_chart(keyword):
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        url = f"https://search.naver.com/search.naver?query={keyword}"
        driver.get(url)
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        time.sleep(1)

        top = driver.find_element(By.CSS_SELECTOR, "div.exchange_top.up")
        bottom = driver.find_element(By.CSS_SELECTOR, "div.invest_wrap")

        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", top)
        time.sleep(0.5)

        zoom = driver.execute_script("return window.devicePixelRatio || 1;")
        start_y = int(top.location['y'] * zoom)
        end_y = int((bottom.location['y'] + bottom.size['height']) * zoom)

        # 정밀 보정값 적용
        left_offset = 395
        crop_width = 670
        top_offset = -20
        bottom_trim = 20

        # 💡 전체 페이지 스크린샷을 메모리에서 바로 처리
        screenshot_bytes = driver.get_screenshot_as_png()
        image = Image.open(io.BytesIO(screenshot_bytes))

        top_coord = max(0, start_y + top_offset)
        bottom_coord = min(image.height, end_y - bottom_trim)

        cropped = image.crop((left_offset, top_coord, left_offset + crop_width, bottom_coord))

        # 통화코드 추출
        currency = top.text.split('\n')[0].strip().replace(' ', '')
        today = datetime.now().strftime('%Y%m%d')
        folder = os.path.join("환율차트", today)
        os.makedirs(folder, exist_ok=True)
        filename = f"{today}_{currency}_환율차트.png"
        output_path = os.path.join(folder, filename)
        cropped.save(output_path)
        print(f"✅ 저장됨: {output_path}")

        copy_image_to_clipboard(output_path)
        return output_path

    except Exception as e:
        print(f"오류 발생: {e}")
        return None
    finally:
        try:
            driver.quit()
        except:
            pass

if __name__ == "__main__":
    print("환율 차트 캡쳐")
    while True:
        keyword = input("환율 키워드를 입력하세요 (0 입력 시 종료): ").strip()
        if keyword == "0":
            break
        capture_exchange_chart(keyword)
