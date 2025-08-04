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

# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-31
# 기능 : 토스증권 API를 이용한 종목 데이터 추출
# ------------------------------------------------------------------
def get_toss_stock_data(debug=False, start_rank=1, end_rank=None):
    ranking_url = "https://wts-cert-api.tossinvest.com/api/v2/dashboard/wts/overview/ranking"
    res = requests.post(ranking_url, headers=HEADERS, json=PAYLOAD)
    products = res.json().get("result", {}).get("products", [])

    # 🔹 productCode → (name, rank) 매핑 생성
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

    # 🔹 rank 기준으로 정렬 및 범위 필터링
    df = pd.DataFrame(rows)
    df = df.sort_values(by="순위").reset_index(drop=True)
    if end_rank is None:
        end_rank = df["순위"].max()
    df = df[(df["순위"] >= start_rank) & (df["순위"] <= end_rank)]
    df = df.reset_index(drop=True)
    return df  # 순위 컬럼 유지


# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-31
# 기능 : 토스증권 API를 이용한 종목 데이터 필터링
# ------------------------------------------------------------------
def filter_toss_data(df, min_pct=None, max_pct=None, min_price=None, up_check=False, down_check=False, limit=None):
    df_filtered = df.copy()

    if min_pct is not None:
        df_filtered = df_filtered[df_filtered["등락률(%)"] >= min_pct]
    if max_pct is not None:
        df_filtered = df_filtered[df_filtered["등락률(%)"] <= max_pct]
    if min_price is not None:
        df_filtered = df_filtered[df_filtered["현재가KRW_숫자"] >= min_price]  # 🔹 숫자 컬럼으로 비교

    if up_check and not down_check:
        df_filtered = df_filtered[df_filtered["등락"] == "UP"]
    elif down_check and not up_check:
        df_filtered = df_filtered[df_filtered["등락"] == "DOWN"]

    if limit:
        df_filtered = df_filtered.head(limit)

    return df_filtered.drop(columns=["현재가KRW_숫자"])  # UI에는 숫자 컬럼 제거


# ------------------------------------------------------------------
# 작성자 : 최준혁
# 작성일 : 2025-07-31
# 기능 : 토스증권 API를 이용한 종목 데이터 스타일링 (색상 표시)
# ------------------------------------------------------------------
def style_toss_df(df):
    df = df.copy()
    df["등락률(%)"] = df["등락률(%)"].apply(lambda x: f"{x:.2f}%" if x is not None else "")

    def color_change(val):
        if val == "UP":
            return "color: red; font-weight: bold"
        elif val == "DOWN":
            return "color: blue; font-weight: bold"
        return "color: black"

    styled = (
        df.style
        .applymap(color_change, subset=["등락"])
        .set_properties(**{"text-align": "center"})
        .set_properties(subset=["등락률(%)", "현재가(KRW)"], **{"text-align": "right"})
    )

    return styled

