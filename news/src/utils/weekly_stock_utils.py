import datetime as _dt
from typing import List, Dict, Optional

import pandas as pd
import FinanceDataReader as fdr
from news.src.utils.domestic_utils import finance


def _last_n_trading_days(df: pd.DataFrame, n: int) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    return df.tail(n)


def get_five_trading_days_ohlc(keyword: str) -> Optional[List[Dict[str, str]]]:
    """
    주어진 종목 키워드로 5거래일 OHLC를 반환한다. (국내 주식 전용)
    반환 형식: [{"date": YYYY-MM-DD, "open": str, "high": str, "low": str, "close": str}, ...]
    """
    try:
        code = finance(keyword)
        if not code:
            return None
        end_date = _dt.date.today()
        start_date = end_date - _dt.timedelta(days=20)
        df = fdr.DataReader(code, start=start_date, end=end_date)
        if df is None or df.empty:
            return None
        df = df.dropna(subset=["Open", "High", "Low", "Close"]).copy()
        df = _last_n_trading_days(df, 5)
        rows: List[Dict[str, str]] = []
        for idx, row in df.iterrows():
            if hasattr(idx, 'date'):
                d = idx.date().isoformat()
            else:
                d = str(idx)[:10]
            rows.append({
                "date": d,
                "open": f"{int(row['Open']):,}" if not pd.isna(row['Open']) else "N/A",
                "high": f"{int(row['High']):,}" if not pd.isna(row['High']) else "N/A",
                "low": f"{int(row['Low']):,}" if not pd.isna(row['Low']) else "N/A",
                "close": f"{int(row['Close']):,}" if not pd.isna(row['Close']) else "N/A",
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
    return (
        "[Special Rules for Weekly OHLC]\n"
        "1. 제목 작성 형식:\n"
        "   다음 3가지 형식 중에서 선택하여 제목 3개를 생성할 것(데이터에 맞게 변형 가능):\n"
        "   - '[월] [주차] [종목명], [핵심 변동 내용]'\n"
        "     예시: '11월 1주차 삼성전자, 연중 최고가 경신 후 조정'\n"
        "   - '[월]월 [일]일 [종목명] 주가 [가격]원대 [특징]'\n"
        "     예시: '11월 5일 SK하이닉스 주가 12만원대 마감 변동성 확대'\n"
        "   - '[기간 키워드] [종목명] [주요 이슈/변화]'\n"
        "     예시: '최근 5거래일 카카오 13만원-15만원 등락'\n"
        "\n"
        "2. 기본 서술 원칙:\n"
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
        "   - 직전 거래일과의 비교 외 다른 기간과의 비교나 추세 분석 금지.\n"
        "\n"
        "4. 문체와 구성:\n"
        "   - 뉴스 기사체를 사용하되, 자연스러운 흐름을 유지할 것.\n"
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
        "- 마지막에 '간단 요약' 섹션을 한 문장(최대 25자 내외)로 추가하되, 이 요약은 전체적인 수치 정리(숫자 나열 허용)만 가능하고 전망 또는 시사점 서술 금지.\n"
        "- 출력 시 마크다운·특수문자(괄호·기호 등)를 사용하지 말 것.\n"
        "\n"
    )
