# utils/driver_utils.py

import os
import platform
import requests
from bs4 import BeautifulSoup
from newspaper import Article
from typing import Callable, Optional, Tuple

try:
    from selenium import webdriver
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

import re
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from PIL import Image
from datetime import datetime
import io


# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-09
# 기능 : 셀레니움 크롬 드라이버 초기화 (공통 유틸)
# ------------------------------------------------------------------
def initialize_driver(headless: bool = True) -> 'webdriver.Chrome':
    """
    셀레니움 크롬 드라이버를 옵션과 함께 초기화하여 반환합니다.
    :param headless: 헤드리스 모드 여부
    :return: Chrome WebDriver 객체
    """
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080") # 해상도 고정
    chrome_options.add_argument("--force-device-scale-factor=1") # 배율 100% 강제
    chrome_options.add_argument("--disable-gpu")
    # suppress verbose Chrome logs
    chrome_options.add_argument("--log-level=3")  # fatal
    chrome_options.add_argument("--disable-logging")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    # User-Agent 추가
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    if headless:
        chrome_options.add_argument("--headless=new")

    try:
        import os
        service = Service(
            log_path='NUL' if os.name == 'nt' else os.devnull,
            service_args=['--silent']
        )
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        raise RuntimeError(f"크롬 드라이버 실행 실패: {e}")