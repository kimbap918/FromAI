import datetime as _dt
from typing import List, Dict, Optional

import pandas as pd
import FinanceDataReader as fdr
import yfinance as yf
from news.src.utils.domestic_utils import finance, safe_fdr_datareader
from news.src.utils.ticker_resolver import resolve_ticker_via_yahoo


def _last_n_trading_days(df: pd.DataFrame, n: int) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    return df.tail(n)


def get_five_trading_days_ohlc(keyword: str) -> Optional[List[Dict[str, str]]]:
    """
    주어진 종목 키워드로 '이번 주(월요일~오늘(또는 직전 영업일))'의 거래일 OHLC를 반환합니다.
    - 오늘이 주중(월~금)이면 이번 주 월요일부터 오늘까지의 거래일을 반환합니다.
    - 오늘이 주말(토/일)일 경우에는 직전 금요일까지의 거래일을 반환합니다.
    반환 형식: [{"date": YYYY-MM-DD, "open": str, "high": str, "low": str, "close": str}, ...]
    (항목 수는 1~5일 등 유동적입니다.)
    """
    try:
        # 국내 종목 코드 조회 시도 (domestic_utils.py의 finance 함수 사용)
        is_foreign = False
        code = finance(keyword)
        
        if code:
            print(f"DEBUG: Found domestic stock code for '{keyword}': {code}")
        else:
            # 국내 종목이 아니면 해외 종목으로 간주
            is_foreign = True
            print(f"DEBUG: No matching domestic stock found for '{keyword}'. Trying foreign stocks...")

        from news.src.utils.common_utils import TZ
        now_kst = _dt.datetime.now(TZ)
        today = now_kst.date()
        print(f"[DEBUG] get_five_trading_days_ohlc - Current KST: {now_kst}")
        
        # [수정] 12월 31일(연말 휴장)이거나 주말이면 직전 거래일로 조정
        if today.month == 12 and today.day == 31:
             # 31일이 평일이면 하루 전(30일)으로 이동
             end_date = today - _dt.timedelta(days=1)
             if end_date.weekday() >= 5: # 30일도 주말이면 금요일로
                 end_date = end_date - _dt.timedelta(days=(end_date.weekday() - 4))
        elif today.weekday() >= 5:  # Sat=5, Sun=6
            end_date = today - _dt.timedelta(days=(today.weekday() - 4))
        else:
            end_date = today
        print(f"[DEBUG] get_five_trading_days_ohlc - end_date set to: {end_date}")

        # 이번 주 월요일 계산 (X) -> 최근 5거래일을 가져오기 위해 충분한 범위를 잡음
        start_search = end_date - _dt.timedelta(days=15)

        # 국내 종목이면 기존 코드 사용
        if not is_foreign:
            df = safe_fdr_datareader(code, start=start_search, end=end_date)
        else:
            # 해외 종목은 Yahoo resolver로 티커 검색을 먼저 시도
            # ... (ticker resolution logic) ...
            ticker = resolve_ticker_via_yahoo(keyword) if 'resolve_ticker_via_yahoo' in globals() else None
            if not ticker:
                 # 티커 검색 실패 시 이전 로직 유지
                 ticker = keyword.upper() if keyword.isalnum() else None
            
            if ticker:
                try:
                    stock = yf.Ticker(ticker)
                    # yfinance end_date는 exclusive하므로 +1일
                    df = stock.history(start=start_search, end=end_date + _dt.timedelta(days=1))
                except Exception:
                    df = None
            else:
                df = None

        if df is None or df.empty:
            return None

        # 유효한 데이터만 남기고 최근 5일만 선택
        df = df.dropna(subset=["Open", "High", "Low", "Close"]).copy()
        df = df.tail(5)
        
        if df.empty:
            return None

        rows: List[Dict[str, str]] = []
        for idx, row in df.iterrows():
            if hasattr(idx, 'date'):
                d = idx.date().isoformat()
            else:
                d = str(idx)[:10]
            # 소수점 처리 개선 (해외주식용)
            def format_number(val):
                if pd.isna(val):
                    return "N/A"
                # 1000 이상이면 정수로, 작으면 소수점 2자리까지
                if abs(val) >= 1000:
                    return f"{int(val):,}"
                return f"{val:.2f}"
            
            rows.append({
                "date": d,
                "open": format_number(row['Open']),
                "high": format_number(row['High']),
                "low": format_number(row['Low']),
                "close": format_number(row['Close']),
            })
        return rows
    except Exception:
        return None


def format_weekly_ohlc_for_prompt(rows: List[Dict[str, str]]) -> str:
    lines = []
    for r in rows or []:
        lines.append(f"- {r['date']} | 시가 {r['open']} | 고가 {r['high']} | 저가 {r['low']} | 종가 {r['close']}")
    return "\n".join(lines)


def build_weekly_stock_prompt() -> str:
    from news.src.utils.common_utils import TZ  # TZ 추가
    now_kst = _dt.datetime.now(TZ)  # 현재 한국 시간
    print(f"[DEBUG] build_weekly_stock_prompt - Current KST: {now_kst}")
    
    # 장 시작/마감 시간 정의 (한국 시간)
    market_open_time = _dt.time(9, 0)   # 오전 9:00
    market_close_time = _dt.time(15, 30)  # 오후 3:30
    current_time = now_kst.time()
    
    # 장 상태 확인
    is_market_open = market_open_time <= current_time < market_close_time
    market_status = "장중" if is_market_open else "장마감"
    
    # 주중/주말 확인
    weekday = now_kst.weekday()
    is_weekend = weekday >= 5  # 5=토요일, 6=일요일
    
    # 최종 시장 상태 결정
    # [수정] 12월 31일은 연말 휴장이므로 항상 장마감 처리
    if (now_kst.month == 12 and now_kst.day == 31) or is_weekend:
        final_status = "장마감"  # 주말/휴장은 항상 장마감
    else:
        final_status = market_status
        
    return (
        f"[Context]\n"
        f"- 현재 시점 (KST): {now_kst.strftime('%Y-%m-%d %H:%M')}\n"
        f"- 오늘 날짜: {now_kst.strftime('%Y년 %m월 %d일')}\n"
        f"- 분석 성격: {final_status}\n\n"
        f"[Special Rules for Weekly OHLC - 현재 {final_status}]\n"
    "1. 제목 작성 형식 (현재 시점 반영):\n"
    "   다음 4가지 형식 중에서 선택하여 제목 3개를 생성할 것(데이터에 맞게 변형 가능):\n"
    "   - '[월] [주차] [종목명], [핵심 변동 내용]'\n"
    "     예시: '11월 1주차 삼성전자, 연중 최고가 경신 후 조정'\n"
    "   - '[월] N주간 [종목명] 변동 현황'\n"
    "     예시: '11월 1주간 삼성전자 변동 현황' 또는 '11월 2주간 카카오 변동 현황'\n"
    "   - '[월]월 [일]일 [종목명] 주가 [가격]원대 [특징]'\n"
    "     예시: '11월 5일 SK하이닉스 주가 12만원대 마감 변동성 확대'\n"
    "   - '[월]월 [일]일 [기간 키워드] [종목명] [주요 이슈/변화]'\n"
    "     예시: '11월 5일 최근 5거래일 카카오 13만원-15만원 등락'\n"

        "\n"
        "2. 기본 서술 원칙 (시점별 작성 기준):\n"
        "   - 장중 작성 시: 최근 거래일의 데이터는 '~움직이고 있다', '~보이고 있다' 등 현재 진행형 사용.\n"
        "   - 장마감 작성 시: 모든 거래일의 데이터를 '~마감했다', '~기록했다' 등 완료형으로 서술.\n"
        "   - 제공된 최근 5거래일 OHLC 데이터를 활용하되, 자연스러운 기사체로 서술할 것.\n"
        "   - 수치를 단순 나열하지 말고, 각 거래일의 특징적인 가격 움직임을 서술형으로 표현.\n"
        "   - 거래일별로 내용이 분절되지 않도록 하고, 문단 간 자연스러운 연결을 유지할 것.\n"
        "\n"
        "2. 필수 포함 사항:\n"
        "   - 시가/종가 기준 가격 변동과 일중 변동폭(고가/저가) 중 의미 있는 내용을 선별하여 서술.\n"
        "   - 직전 거래일과의 비교를 통해 가격 변화의 맥락을 자연스럽게 설명.\n"
        "   - 변동폭이 큰 거래일이나 특이사항이 있는 거래일은 상세히 설명.\n"
        "\n"
        "3. 작성 규칙:\n"
        "   - 숫자는 쉼표로 구분하고(예: 64,600원), 등락률은 소수점 첫째 자리까지 표기할 것.\n"
        "   - 시간대/시각 언급이나 예측성 표현(전망, 기대 등) 사용 금지.\n"
        "   - 감정적 표현이나 투자 조언을 암시하는 표현 사용 금지.\n"
        "   - 감정·권유·주관 어휘 금지: 투자자들, 관심, 주목, 기대, 풀이, 분석 등.\n"

        "   - 직전 거래일과의 비교 외 다른 기간과의 비교나 추세 분석 금지.\n"
        "\n"
        "4. 문체와 구성:\n"
        "   - 뉴스 기사체를 사용하되, 딱딱한 나열보다 자연스러운 흐름을 유지할 것.\n"
        "   - 문단 구분을 적절히 활용하여 가독성을 확보할 것.\n"
        "   - 마지막 문단에서는 핵심적인 가격 변동 내용을 간단히 정리.\n"
        "   - 마크다운이나 특수문자는 사용하지 말 것.\n"
        "\n"
        "5. 금지 사항:\n"
        "   - 날짜나 수치를 기계적으로 나열하는 형식 사용 금지.\n"
        "   - '일자별 브리핑'이나 '요약' 등의 형식적 구분 사용 금지.\n"
        "   - 미래에 대한 전망이나 투자 관점의 해석 금지.\n"
        "   - 감정적 수식어나 과장된 표현 사용 금지.\n"
        "  4) 숫자는 쉼표 구분(예: 64,600원)을 사용하고, 등락률은 소수점 둘째 자리까지 표기(예: 1.21%)하되 불필요한 단위를 섞지 말 것.\n"
        "  5) 각 일자 항목은 독립적으로 이해 가능해야 하며, 불필요한 중복 서술을 피할 것.\n"
        "- 출력 시 마크다운·특수문자(괄호·기호 등)를 사용하지 말 것.\n"
        "\n"
    )
