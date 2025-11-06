import json
import os
from typing import Optional

import requests
import difflib
import FinanceDataReader as fdr


CACHE_FILE = os.path.join(os.path.dirname(__file__), "ticker_cache.json")

# 간단한 한글명 -> 심볼 매핑(우선순위 높음)
KOR_TO_SYMBOL = {
    "애플": "AAPL",
    "테슬라": "TSLA",
    "아마존": "AMZN",
    "마이크로소프트": "MSFT",
    "구글": "GOOGL",
    "알파벳": "GOOGL",
    "페이스북": "META",
    "메타": "META",
    "엔비디아": "NVDA",
    "넷플릭스": "NFLX",
}


def _normalize_kw(s: str) -> str:
    """간단 정규화: 공백 제거, 소문자화, 일부 특수문자 제거"""
    if not s:
        return ""
    return ''.join(ch for ch in s if ch.isalnum()).lower()


def _load_cache() -> dict:
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_cache(cache: dict) -> None:
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def resolve_ticker_via_yahoo(keyword: str) -> Optional[str]:
    """
    키워드(한글/영어)를 티커 심볼로 해석합니다.
    1. 내장된 한글->티커 매핑 확인
    2. 로컬 캐시 확인
    3. Yahoo Search API 시도
    4. FinanceDataReader 거래소 목록 검색
    Returns symbol (str) or None.
    """
    if not keyword:
        return None
    kw = keyword.strip()
    if not kw:
        return None

    print(f"\nDEBUG: Resolving ticker for '{kw}'")  # DEBUG

    # 1) First check built-in Korean mappings
    if kw in KOR_TO_SYMBOL:
        sym = KOR_TO_SYMBOL[kw]
        print(f"DEBUG: Found direct mapping: '{kw}' -> '{sym}'")  # DEBUG
        # Cache successful mapping
        try:
            cache = _load_cache()
            cache[kw] = sym
            _save_cache(cache)
        except Exception:
            pass
        return sym

    # Try normalized/fuzzy matching with built-in mappings
    try:
        norm_kw = _normalize_kw(kw)
        print(f"DEBUG: Normalized keyword: '{kw}' -> '{norm_kw}'")  # DEBUG
        
        # Try normalized exact match
        for k, v in KOR_TO_SYMBOL.items():
            if norm_kw == _normalize_kw(k):
                print(f"DEBUG: Found normalized match: '{k}' -> '{v}'")  # DEBUG
                cache = _load_cache()
                cache[kw] = v
                _save_cache(cache)
                return v

        # Try substring match
        for k, v in KOR_TO_SYMBOL.items():
            if _normalize_kw(k) in norm_kw or norm_kw in _normalize_kw(k):
                print(f"DEBUG: Found substring match: '{k}' -> '{v}'")  # DEBUG
                cache = _load_cache()
                cache[kw] = v
                _save_cache(cache)
                return v

        # Try fuzzy match
        kor_keys = list(KOR_TO_SYMBOL.keys())
        # Try original keyword first, then normalized
        matches = difflib.get_close_matches(kw, kor_keys, n=1, cutoff=0.7)
        if not matches:
            matches = difflib.get_close_matches(norm_kw, kor_keys, n=1, cutoff=0.7)
        if matches:
            sym = KOR_TO_SYMBOL.get(matches[0])
            print(f"DEBUG: Found fuzzy match: '{matches[0]}' -> '{sym}'")  # DEBUG
            cache = _load_cache()
            cache[kw] = sym
            _save_cache(cache)
            return sym
        print("DEBUG: No matches in built-in mappings")  # DEBUG
    except Exception as e:
        print(f"DEBUG: Error in built-in mapping check: {str(e)}")  # DEBUG

    # 2) Check cache
    cache = _load_cache()
    if kw in cache:
        cached = cache.get(kw)
        print(f"DEBUG: Found in cache: '{kw}' -> '{cached}'")  # DEBUG
        return cached

    # 3) Try Yahoo search
    print("DEBUG: Trying Yahoo Finance search API")  # DEBUG
    try:
        url = "https://query2.finance.yahoo.com/v1/finance/search"
        params = {"q": kw}
        resp = requests.get(url, params=params, timeout=5)
        print(f"DEBUG: Yahoo API response status: {resp.status_code}")  # DEBUG
        
        if resp.status_code == 200:
            data = resp.json()
            quotes = data.get("quotes") or []
            print(f"DEBUG: Found {len(quotes)} results from Yahoo")  # DEBUG
            
            if quotes:
                # Try exact symbol match first
                for q in quotes:
                    sym = q.get("symbol")
                    if sym and sym.lower() == kw.lower():
                        print(f"DEBUG: Found exact symbol match: '{sym}'")  # DEBUG
                        cache[kw] = sym
                        _save_cache(cache)
                        return sym

                # Then try name matches
                lower_kw = kw.lower()
                norm_kw = _normalize_kw(kw)
                for q in quotes:
                    short = (q.get("shortname") or "").lower()
                    longn = (q.get("longname") or "").lower()
                    if (lower_kw in short or lower_kw in longn or 
                        norm_kw in _normalize_kw(short) or norm_kw in _normalize_kw(longn)):
                        sym = q.get("symbol")
                        if sym:
                            print(f"DEBUG: Found by name match: '{sym}' ({short} / {longn})")  # DEBUG
                            cache[kw] = sym
                            _save_cache(cache)
                            return sym
    except Exception as e:
        print(f"DEBUG: Yahoo search failed: {str(e)}")  # DEBUG

    # 4) Fallback: use FinanceDataReader listings
    print("DEBUG: Trying FinanceDataReader exchange listings")  # DEBUG
    try:
        exchanges = ["NASDAQ", "NYSE", "AMEX"]
        normalized_kw = _normalize_kw(kw)
        for ex in exchanges:
            print(f"DEBUG: Checking {ex} listing")  # DEBUG
            try:
                listing = fdr.StockListing(ex)
                if listing is None:
                    continue
                
                # First try exact symbol match
                if "Symbol" in listing.columns:
                    exact = listing[listing["Symbol"].astype(str).str.upper() == kw.upper()]
                    if not exact.empty:
                        sym = exact.iloc[0]["Symbol"]
                        print(f"DEBUG: Found in {ex} by exact symbol: '{sym}'")  # DEBUG
                        cache[kw] = sym
                        _save_cache(cache)
                        return sym

                # Then try fuzzy name match
                if "Name" in listing.columns:
                    names = listing["Name"].astype(str)
                    # Try original keyword first
                    matches = difflib.get_close_matches(kw, names, n=1, cutoff=0.8)
                    if not matches:
                        # Then try normalized
                        matches = difflib.get_close_matches(normalized_kw, names.apply(_normalize_kw), n=1, cutoff=0.8)
                    if matches:
                        matched = listing[listing["Name"] == matches[0]]
                        if not matched.empty and "Symbol" in matched.columns:
                            sym = matched.iloc[0]["Symbol"]
                            print(f"DEBUG: Found in {ex} by name match: '{sym}' (matched: {matches[0]})")  # DEBUG
                            cache[kw] = sym
                            _save_cache(cache)
                            return sym
            except Exception as e:
                print(f"DEBUG: Error checking {ex}: {str(e)}")  # DEBUG
                continue
    except Exception as e:
        print(f"DEBUG: FinanceDataReader search failed: {str(e)}")  # DEBUG

    # No matches found
    print(f"DEBUG: No ticker found for '{kw}'")  # DEBUG
    cache[kw] = None  # Cache the failure too
    _save_cache(cache)
    return None
