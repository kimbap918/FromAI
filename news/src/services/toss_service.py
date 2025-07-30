import requests
import pandas as pd

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


def get_toss_stock_data():
    ranking_url = "https://wts-cert-api.tossinvest.com/api/v2/dashboard/wts/overview/ranking"
    res = requests.post(ranking_url, headers=HEADERS, json=PAYLOAD)
    products = res.json().get("result", {}).get("products", [])
    code_to_name = {p["productCode"]: p["name"] for p in products}

    codes_str = "%2C".join(code_to_name.keys())
    price_url = f"https://wts-info-api.tossinvest.com/api/v3/stock-prices?meta=true&productCodes={codes_str}"
    res2 = requests.get(price_url, headers=HEADERS)
    items = res2.json().get("result", [])

    rows = []
    for item in items:
        code = item.get("productCode")
        base = item.get("base")
        close = item.get("close")
        change_rate = round((close - base) / base * 100, 2) if base else None

        rows.append({
            "종목명": code_to_name.get(code, ""),
            "현재가(KRW)": item.get("closeKrw"),
            "등락": item.get("changeType"),
            "등락률(%)": change_rate
        })

    return pd.DataFrame(rows)


def filter_toss_data(df, min_pct=None, max_pct=None, min_price=None, up_check=False, down_check=False, limit=None):
    if min_pct is not None:
        df = df[df["등락률(%)"] >= min_pct]
    if max_pct is not None:
        df = df[df["등락률(%)"] <= max_pct]
    if min_price is not None:
        df = df[df["현재가(KRW)"] >= min_price]

    if up_check and not down_check:
        df = df[df["등락"] == "UP"]
    elif down_check and not up_check:
        df = df[df["등락"] == "DOWN"]

    if limit:
        df = df.head(limit)

    return df
