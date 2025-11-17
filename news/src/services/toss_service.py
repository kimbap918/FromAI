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
def is_foreign_stock(product_code):
    if not isinstance(product_code, str):
        return False
    foreign_prefixes = ("US", "AMX", "NAS", "NYS")
    return any(product_code.startswith(prefix) for prefix in foreign_prefixes)

def is_domestic_stock(product_code):
    if not isinstance(product_code, str):
        return False
    # 한국 주식은 A로 시작하고, 숫자로만 구성된 코드를 가집니다.
    return product_code.startswith('A') and product_code[1:].isdigit()

def filter_by_market(df, only_domestic=False, only_foreign=False):
    if not isinstance(df, pd.DataFrame) or df.empty or 'productCode' not in df.columns:
        print("\n[Debug] 필터링할 데이터가 없거나 productCode 컬럼이 없습니다.")
        return df
    
    # 디버깅 정보 출력
    print(f"\n[Debug] 필터링 옵션 - only_domestic: {only_domestic}, only_foreign: {only_foreign}")
    print("[Debug] 필터링 전 데이터 수:", len(df))
    
    # 상위 5개 항목 디버깅 출력
    print("\n[Debug] 상위 5개 종목 코드:")
    for idx, code in enumerate(df['productCode'].head()):
        name = df.iloc[idx]['종목명'] if '종목명' in df.columns else 'N/A'
        print(f"- {code} ({name}): 외국주식={is_foreign_stock(code)}, 국내주식={is_domestic_stock(code)}")
    
    # 필터링 로직
    if only_domestic and not only_foreign:
        # 국내주식 필터링: A로 시작하고 숫자로만 구성된 코드
        mask = df['productCode'].astype(str).apply(is_domestic_stock)
        filtered = df[mask].copy()
        print(f"[Debug] 국내주식 필터링 후: {len(filtered)}개 항목")
        return filtered
    elif only_foreign and not only_domestic:
        # 외국주식 필터링: 외국주식 접두사로 시작하는 코드
        mask = df['productCode'].astype(str).apply(is_foreign_stock)
        filtered = df[mask].copy()
        print(f"[Debug] 해외주식 필터링 후: {len(filtered)}개 항목")
        
        # 필터링된 항목 디버깅 출력
        if not filtered.empty:
            print("\n[Debug] 필터링된 상위 5개 항목:")
            for idx, row in filtered.head().iterrows():
                code = row['productCode']
                name = row.get('종목명', 'N/A')
                print(f"- {code} ({name}): 외국주식={is_foreign_stock(code)}")
        
        return filtered
    
    # 필터링 옵션이 없는 경우 모든 항목 반환
    print("\n[Debug] 필터링 없음 - 모든 종목 반환")
    return df

def get_toss_stock_data(debug=False, start_rank=1, end_rank=None, abs_min=None, abs_max=None, only_down=False, only_domestic=False, only_foreign=False):
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
    
    # Add productCode to the DataFrame for filtering
    df['productCode'] = [item.get('productCode') for item in items]

    # 🔹 market 필터링
    df = filter_by_market(df, only_domestic=only_domestic, only_foreign=only_foreign)

    # 🔹 절댓값 등락률 필터링
    if abs_min is not None and abs_max is not None:
        df = df[df["등락률(%)"].apply(lambda x: abs(x) if x is not None else None).between(abs_min, abs_max)]
    if only_down:
        df = df[df["등락률(%)"] < 0]
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
    # 등락률 컬럼 숫자화 (비교 안전성 확보)
    if "등락률(%)" in df_filtered.columns:
        df_filtered["등락률(%)"] = pd.to_numeric(df_filtered["등락률(%)"], errors="coerce")

    # 방향 마스크
    if up_check and not down_check:
        dir_mask = (df_filtered["등락"] == "UP")
    elif down_check and not up_check:
        dir_mask = (df_filtered["등락"] == "DOWN")
    else:
        # 체크 없거나 둘 다 체크 시 양/음 모두 허용
        dir_mask = pd.Series([True] * len(df_filtered), index=df_filtered.index)

    # 등락률 마스크
    pct = df_filtered["등락률(%)"] if "등락률(%)" in df_filtered else pd.Series([None] * len(df_filtered), index=df_filtered.index)
    pct_mask = pd.Series([True] * len(df_filtered), index=df_filtered.index)

    if min_pct is not None and max_pct is not None:
        if up_check and not down_check:
            pct_mask = (pct >= min_pct) & (pct <= max_pct)
        elif down_check and not up_check:
            pct_mask = (pct <= -min_pct) & (pct >= -max_pct)
        else:
            # 양/음 모두 포함: 절댓값 범위로 판단
            pct_mask = pct.abs().between(min_pct, max_pct)
    elif min_pct is not None:
        if up_check and not down_check:
            pct_mask = (pct >= min_pct)
        elif down_check and not up_check:
            pct_mask = (pct <= -min_pct)
        else:
            pct_mask = (pct.abs() >= min_pct)
    elif max_pct is not None:
        if up_check and not down_check:
            pct_mask = (pct <= max_pct)
        elif down_check and not up_check:
            pct_mask = (pct >= -max_pct)
        else:
            pct_mask = (pct.abs() <= max_pct)

    # 방향 + 등락률 동시 적용
    df_filtered = df_filtered[dir_mask & pct_mask]

    # 가격 필터
    if min_price is not None:
        df_filtered = df_filtered[df_filtered["현재가KRW_숫자"] >= min_price]

    # 개수 제한
    if limit:
        df_filtered = df_filtered.head(limit)

    # UI에는 숫자 보조 컬럼 제거
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

