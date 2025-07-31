import requests
import pandas as pd
import os, shutil
from datetime import datetime
from news.src.utils.capture_utils import (
    capture_wrap_company_area,
    capture_naver_foreign_stock_chart,
    get_stock_info_from_search,
    capture_and_generate_news
)

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.tossinvest.com/",
    "Origin": "https://www.tossinvest.com",
    "Content-Type": "application/json",
}

PAYLOAD = {
    "id": "realtime_stock",
    "filters": [
        "MARKET_CAP_GREATER_THAN_50M",
        "STOCKS_PRICE_GREATER_THAN_ONE_DOLLAR",
        "KRX_MANAGEMENT_STOCK"
    ],
    "duration": "realtime",
    "tag": "all"
}

# ✅ 토스증권 API 데이터 가져오기
def get_toss_stock_data(debug=False):
    ranking_url = "https://wts-cert-api.tossinvest.com/api/v2/dashboard/wts/overview/ranking"
    res = requests.post(ranking_url, headers=HEADERS, json=PAYLOAD)
    products = res.json().get("result", {}).get("products", [])

    code_to_info = {p["productCode"]: (p["name"], p["rank"]) for p in products}

    codes_str = "%2C".join(code_to_info.keys())
    price_url = f"https://wts-info-api.tossinvest.com/api/v3/stock-prices?meta=true&productCodes={codes_str}"
    res2 = requests.get(price_url, headers=HEADERS)
    items = res2.json().get("result", [])

    rows = []
    for item in items:
        code = item.get("productCode")
        base = item.get("base")
        close = item.get("close")
        change_rate = round((close - base) / base * 100, 2) if base else None

        name, rank = code_to_info.get(code, ("", 9999))
        price = item.get("closeKrw") or item.get("close")
        price_num = int(price) if isinstance(price, (int, float)) else 0

        rows.append({
            "순위": rank,
            "종목명": name,
            "현재가(KRW)": f"{price_num:,}",
            "현재가KRW_숫자": price_num,
            "등락": item.get("changeType"),
            "등락률(%)": change_rate
        })

    df = pd.DataFrame(rows)
    df = df.sort_values(by="순위").reset_index(drop=True)
    return df.drop(columns=["순위"])

# ✅ 필터링
def filter_toss_data(df, min_pct=None, max_pct=None, min_price=None, up_check=False, down_check=False, limit=None):
    df_filtered = df.copy()

    if min_pct is not None:
        df_filtered = df_filtered[df_filtered["등락률(%)"] >= min_pct]
    if max_pct is not None:
        df_filtered = df_filtered[df_filtered["등락률(%)"] <= max_pct]
    if min_price is not None:
        df_filtered = df_filtered[df_filtered["현재가KRW_숫자"] >= min_price]

    if up_check and not down_check:
        df_filtered = df_filtered[df_filtered["등락"] == "UP"]
    elif down_check and not up_check:
        df_filtered = df_filtered[df_filtered["등락"] == "DOWN"]

    if limit:
        df_filtered = df_filtered.head(limit)

    return df_filtered.drop(columns=["현재가KRW_숫자"])

# ✅ 기사 + 차트 생성
def generate_toss_articles_and_charts(names, folder, progress_callback=None, cancel_flag=None):
    success_cnt = 0

    for name in names:
        if cancel_flag and cancel_flag():
            if progress_callback:
                progress_callback("❌ 작업 취소됨")
            break

        if progress_callback:
            progress_callback(f"📄 {name} 기사+차트 생성 중...")

        stock_code = get_stock_info_from_search(name)
        img_path = None

        if stock_code:
            img_path, *_ = capture_wrap_company_area(stock_code)
        else:
            img_path, _, _ = capture_naver_foreign_stock_chart(name)

        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in name)

        if img_path and os.path.exists(img_path):
            new_img_path = os.path.join(folder, f"{safe_name}_chart.png")
            try:
                shutil.move(img_path, new_img_path)
            except:
                shutil.copy(img_path, new_img_path)

        news = capture_and_generate_news(name, domain="stock")
        if news:
            news_path = os.path.join(folder, f"{safe_name}_기사.txt")
            with open(news_path, "w", encoding="utf-8") as f:
                f.write(news)
            success_cnt += 1

    return success_cnt
