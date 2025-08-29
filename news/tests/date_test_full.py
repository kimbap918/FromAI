# date_test_full.py
import re
from datetime import date

# =========================
# 패턴 정의 (긴 것/정확한 것 우선)
# =========================
patterns = {
    "ymd": re.compile(r"(\d{4})[년.\- ]+(\d{1,2})[월.\- ]+(\d{1,2})[일.]?"),
    "ym": re.compile(r"(\d{4})년\s*(\d{1,2})월"),
    # 느슨한 연+월: "2022년 초부터 12월", "2022년 … 12월" 등 사이 텍스트 허용
    "ym_loose": re.compile(r"(\d{4})년[^0-9]{0,10}?(\d{1,2})월"),
    "md": re.compile(r"(\d{1,2})월\s*(\d{1,2})일"),
    "m": re.compile(r"(\d{1,2})월"),
    "year": re.compile(r"(\d{4})년"),
    # '27일' 같은 일(day) 단독 (뒤에 한글/영문/숫자 연결 단어는 제외)
    "d": re.compile(r"(?<!\d)(\d{1,2})일(?![가-힣A-Za-z0-9])"),
}

# =========================
# 앵커(맥락) 사전
# =========================
ANCHOR_YEAR_WORDS = {
    "지난해": -1, "작년": -1,
    "올해": 0, "금년": 0,
    "내년": 1,
}
ANCHOR_MONTH_WORDS = {
    "지난달": -1,
    "다음달": 1, "내달": 1,
}

def _roll_year_month(base_year: int, base_month: int, delta_months: int) -> tuple[int, int]:
    """월 증감(delta_months)을 연도 이동과 함께 보정"""
    m_total = (base_month - 1) + delta_months
    y = base_year + m_total // 12
    m = (m_total % 12) + 1
    return y, m

def _infer_anchor_before(s: str, idx: int, today: date) -> tuple[int | None, int | None, int]:
    """
    idx 이전의 텍스트에서 연/월 앵커를 추정.
    반환: (anchor_year, anchor_month, month_delta_for_words)
    - anchor_year: 숫자 연도 또는 올해/지난해/내년 해석값
    - anchor_month: 숫자 월(직접 숫자로 적힌 경우 또는 지난달/다음달 해석)
    - month_delta_for_words: 지난달/다음달 등 단어로만 주어진 상대 월의 원시 delta (연 이동 계산용)
    """
    left = s[:idx]
    anchor_year = None
    anchor_month = None
    month_delta = 0

    # 연 앵커 (가장 가까운 것 하나)
    yr_matches = list(re.finditer(r"(\d{4})년|지난해|작년|올해|금년|내년", left))
    if yr_matches:
        tok = yr_matches[-1].group(0)
        if tok.endswith("년") and tok[:-1].isdigit():
            anchor_year = int(tok[:-1])
        else:
            delta = ANCHOR_YEAR_WORDS.get(tok, 0)
            anchor_year = today.year + delta

    # 월 앵커 (가장 가까운 것 하나)
    mm_matches = list(re.finditer(r"(\d{1,2})월|지난달|다음달|내달", left))
    if mm_matches:
        tok = mm_matches[-1].group(0)
        if tok.endswith("월") and tok[:-1].isdigit():
            anchor_month = int(tok[:-1])
            month_delta = 0
        else:
            delta = ANCHOR_MONTH_WORDS.get(tok, 0)
            month_delta = delta
            # 실제 월 숫자는 치환 시점에 연동 계산 (여기선 힌트만)
            base_y = anchor_year if anchor_year is not None else today.year
            base_m = today.month
            y2, m2 = _roll_year_month(base_y, base_m, delta)
            # 여기서는 월 숫자 힌트만 남기되, y는 별도로 사용
            anchor_month = m2

    return anchor_year, anchor_month, month_delta

# =========================
# 상대표현 변환
# =========================
def _convert_relative_expression(target: date, today: date, mode: str, expr: str) -> str:
    """
    mode:
      - "y"        : 연도만
      - "ym"       : 연+월
      - "ymd"      : 연+월+일
      - "md"       : 월+일 (연도는 today 또는 앵커 기준)
      - "m"        : 월만
      - "d"        : 일만 (연/월은 today 또는 앵커 기준)
      - "ym_loose" : 느슨한 연+월 (처리는 ym과 동일)
    """
    # 동일 일자
    if mode in ("ymd", "d") and target == today:
        return f"{target.day}일"

    # 같은 해
    if target.year == today.year:
        # 같은 달
        if target.month == today.month:
            if mode in ("ymd", "md", "d"):
                return f"지난 {target.day}일" if target < today else f"오는 {target.day}일"
            if mode in ("m", "ym", "ym_loose"):
                return f"{target.month}월"

        # 직전 달 (연-월-일/월-일에만 특례)
        if mode in ("ymd", "md") and target.month == today.month - 1:
            return f"지난달 {target.day}일"

        # 같은 해 내 다른 달
        if target < today:
            if mode in ("ym", "ym_loose"):
                return f"지난 {target.year}년 {target.month}월"
            elif mode == "ymd":
                return f"지난 {target.year}년 {target.month}월 {target.day}일"
            elif mode == "md":
                return f"지난 {target.month}월 {target.day}일"
            elif mode == "m":
                return f"지난 {target.month}월"
            elif mode == "d":
                return f"지난 {target.day}일"
        else:
            if mode in ("ym", "ym_loose"):
                return f"오는 {target.year}년 {target.month}월"
            elif mode == "ymd":
                return f"오는 {target.year}년 {target.month}월 {target.day}일"
            elif mode == "md":
                return f"오는 {target.month}월 {target.day}일"
            elif mode == "m":
                return f"오는 {target.month}월"
            elif mode == "d":
                return f"오는 {target.day}일"

    # 다른 해
    if target < today:
        if mode == "y":
            return f"지난 {target.year}년"
        elif mode in ("ym", "ym_loose"):
            return f"지난 {target.year}년 {target.month}월"
        elif mode == "ymd":
            return f"지난 {target.year}년 {target.month}월 {target.day}일"
    else:
        if mode == "y":
            return f"오는 {target.year}년"
        elif mode in ("ym", "ym_loose"):
            return f"오는 {target.year}년 {target.month}월"
        elif mode == "ymd":
            return f"오는 {target.year}년 {target.month}월 {target.day}일"

    # 규칙 바깥: 원문 유지
    return expr

# =========================
# 개별 표현 파싱
# =========================
def parse_natural_date(expr: str, today: date) -> str:
    expr = expr.strip()

    # YYYY년 MM월 DD일
    if m := patterns["ymd"].fullmatch(expr):
        y, mo, d = map(int, m.groups())
        return _convert_relative_expression(date(y, mo, d), today, mode="ymd", expr=expr)

    # YYYY년 MM월 (정확)
    if m := patterns["ym"].fullmatch(expr):
        y, mo = map(int, m.groups())
        return _convert_relative_expression(date(y, mo, 1), today, mode="ym", expr=expr)

    # YYYY년 … MM월 (느슨)
    if m := patterns["ym_loose"].fullmatch(expr):
        y, mo = map(int, m.groups())
        return _convert_relative_expression(date(y, mo, 1), today, mode="ym_loose", expr=expr)

    # MM월 DD일
    if m := patterns["md"].fullmatch(expr):
        mo, d = map(int, m.groups())
        return _convert_relative_expression(date(today.year, mo, d), today, mode="md", expr=expr)

    # MM월
    if m := patterns["m"].fullmatch(expr):
        mo = int(m.group(1))
        return _convert_relative_expression(date(today.year, mo, 1), today, mode="m", expr=expr)

    # YYYY년
    if m := patterns["year"].fullmatch(expr):
        y = int(m.group(1))
        return _convert_relative_expression(date(y, 1, 1), today, mode="y", expr=expr)

    # DD일 (today의 연/월 사용)
    if m := patterns["d"].fullmatch(expr):
        d = int(m.group(1))
        return _convert_relative_expression(date(today.year, today.month, d), today, mode="d", expr=expr)

    return expr

# =========================
# 유틸: 좌측 토큰
# =========================
def _left_context(wording: str) -> str:
    """좌측 문맥 토큰: 끝의 공백/괄호를 제거하고 마지막 한 단어를 반환"""
    w = wording.rstrip()
    # 여는 괄호류 제거
    w = re.sub(r"[\(\[\{（〔]\s*$", "", w)
    # 마지막 "단어"만 추출
    m = re.search(r"([가-힣A-Za-z]+)\s*$", w)
    return m.group(1) if m else w[-2:] if len(w) >= 2 else w

# =========================
# 메인 치환
# =========================
def replace_date_in_sentence(sentence: str, today: date) -> str:
    """문장에서 날짜 표현을 찾아 규칙에 따라 시제로 변환 (겹침+컨텍스트+앵커 반영)"""

    # 0) 인용문/괄호 안 보호
    protected_regions = []
    for match in re.finditer(r"[\"\'\‘\“][^\"\'\’\”]+[\"\'\’\”]", sentence):
        protected_regions.append((match.start(), match.end()))

    matches = []
    # 1) 탐색 우선순위: ymd > ym > ym_loose > md > m > year > d
    for key in ["ymd", "ym", "ym_loose", "md", "m", "year", "d"]:
        for m in patterns[key].finditer(sentence):
            start, end = m.span()
            # 보호/중복 구간 skip
            if any(s <= start < e or s < end <= e for s, e in protected_regions) or \
               any(s <= start < e or s < end <= e for s, e, _, _ in matches):
                continue
            matches.append((start, end, key, m.group(0)))

    # 2) 뒤에서부터 치환(앞 인덱스 보존)
    matches.sort(key=lambda x: x[0], reverse=True)

    s = sentence
    for start, end, key, text in matches:
        # 좌측 컨텍스트 확인 (직전 한 단어)
        left = s[max(0, start-25):start]
        left_token = _left_context(left)

        # A) 중복 방지: '지난*/오는/내년/다음달/내달' 직후는 건드리지 않음
        if left_token.startswith("지난") or left_token in ("오는", "내년", "다음달", "내달"):
            continue

        # B) 특례: md가 '어제'인 경우 (같은 달 & 오늘보다 하루 전)
        if key == "md":
            mo, d = map(int, patterns["md"].match(text).groups())
            if today.month == mo and today.day == d + 1:
                s = s[:start] + f"지난 {d}일" + s[end:]
                continue

        # C) 앵커 추정 (특히 m, d, md에 중요)
        anchor_year, anchor_month, month_delta = _infer_anchor_before(s, start, today)

        # D) 각 패턴별 변환
        if key == "m":
            mo = int(patterns["m"].match(text).group(1))
            y = anchor_year if anchor_year is not None else today.year
            # '지난해/내년 + 다음달' 등의 조합은 이미 앵커 계산에서 월 숫자 힌트를 제공
            new_expr = _convert_relative_expression(date(y, mo, 1), today, mode="ym", expr=text)

        elif key == "d":
            d = int(patterns["d"].match(text).group(1))
            y = anchor_year if anchor_year is not None else today.year
            mo = anchor_month if anchor_month is not None else today.month
            new_expr = _convert_relative_expression(date(y, mo, d), today, mode="d", expr=text)

        elif key == "md":
            mo, d = map(int, patterns["md"].match(text).groups())
            y = anchor_year if anchor_year is not None else today.year
            # anchor_month가 있고 mo와 충돌하면 mo 우선(문장 내 명시 값이 더 강함)
            new_expr = _convert_relative_expression(date(y, mo, d), today, mode="md", expr=text)

        elif key in ("ym", "ym_loose"):
            y, mo = map(int, re.search(r"(\d{4}).*?(\d{1,2})", text).groups())
            new_expr = _convert_relative_expression(date(y, mo, 1), today, mode=key, expr=text)

        elif key == "ymd":
            y, mo, d = map(int, patterns["ymd"].match(text).groups())
            new_expr = _convert_relative_expression(date(y, mo, d), today, mode="ymd", expr=text)

        elif key == "year":
            y = int(patterns["year"].match(text).group(1))
            new_expr = _convert_relative_expression(date(y, 1, 1), today, mode="y", expr=text)

        else:
            # 안전장치
            new_expr = parse_natural_date(text, today)

        s = s[:start] + new_expr + s[end:]

    return s

# =========================
# ✅ 테스트
# =========================
if __name__ == "__main__":
    today = date(2025, 8, 28)
    tests = [
        # 문제 상황들
        "지난해 12월 통계에 따르면 …",                               # 그대로 두거나 '지난 2024년 12월' 판단 X (원문 유지)
        "지난해 12월에 발표했다.",                                   # 월만 치환하지 않음 (앵커로 과거 맥락)
        "지난해 11월 30일에 발표했다.",                               # 과거 문맥 유지
        "지난해 12월, 한국은행이 27일 발표한 자료에 따르면 …",          # '27일' → '지난 27일'로 자연 변환(같은 달 과거)
        "지난 2022년 초부터 12월까지 진행됐다.",                       # ym_loose로 과거 처리 일관
        "지난 2022년 초부터 오는 12월까지 진행됐다.",                  # '오는' 오판 방지 (과거 맥락 유지)
        "한국은행이 27일 발표한 통계에 따르면 …",                      # day-only 처리: '지난 27일'로 변환 (같은 달 과거면)
        "일반 신용대출 금리는 지난해 오는 12월(",                      # '지난해' 앵커로 인해 '오는 12월' 오판 방지
        # 긴 본문 샘플
        """



주택담보대출, 주택담보대출 금리, 두 달 연속 상승…“가산금리 인상 영향”, 지난달 은행권 가계대출 금리는 8개월 연속 하락했으나 주택담보대출 금리는 두 달 연속 상승했다. 일부 은행의 대출 가산금리 인상과 우대금리 축소 등의 영향이다.

한국은행이 27일 발표한 ‘7월 금융기관 가중평균금리’ 통계를 보면, 예금은행의 이달 가계대출 금리(신규취급액 기준)는 연 4.20%로 전월보다 0.01%포인트 낮아졌다. 8개월 연속 하락이다.

세부적으로 보면 주택담보대출(3.96%)은 0.03%포인트, 전세자금대출(3.75%)은 0.04%포인트, 일반 신용대출(5.34%)은 0.31%포인트 각각 상승했다. 반면 상대적으로 금리 수준이 높은 일반 신용대출 비중이 축소돼 가계대출 금리는 0.01%포인트 하락했다. 주택담보대출·전세자금대출 금리는 2개월 연속 상승했고, 일반 신용대출 금리는 지난해 12월(6.15%) 이후 8개월 만에 상승 전환했다.

주담대 금리 상승은 가산금리가 오르고 우대금리 등을 축소한 영향으로 풀이된다. 김민수 한은 금융통계팀장은 “지난달 지표금리인 은행채 5년물 금리가 보합세였지만 일부 은행이 지난 5~6월 가산금리를 인상하고 우대금리를 축소한 영향이 1~3개월 시차를 두고 나타났다”고 설명했다.

특히 일반 신용대출의 비중 축소도 가계대출 금리 하락에 영향을 미쳤다. 김 팀장은 “일반 신용대출 금리 상승은 6·27 대책으로 신용대출 한도가 연소득 이내로 제한되면서 기존에 연소득을 초과해 상대적으로 낮은 금리로 대출을 받을 수 있었던 고신용 차주의 신규대출 비중이 축소된 데 따른 것”이라고 했다.

예금은행의 저축성 수신(예금) 금리(신규취급액 기준)도 연 2.55%에서 2.51%로 0.04%포인트 낮아졌다. 지난해 10월(3.37%) 이후 10개월 연속 하락세다. 정기예금 등 순수저축성예금 금리(2.50%)와 양도성예금증서(CD) 등 시장형 금융상품 금리(2.54%)가 각 0.04%포인트, 0.01%포인트 내렸다.

은행 신규 취급액 기준 예대금리차는 1.55%포인트로 0.01%포인트 증가했다. 대출금리 하락 폭보다 예금금리 하락 폭이 더 컸기 때문이다. 다만 잔액 기준 예대금리차는 2.18%포인트로 0.02%포인트 감소했다.

비은행금융기관의 경우 예금금리(1년 만기 정기예금·예탁금 기준)는 상호저축은행을 제외하고 모두 하락했고, 대출금리(일반대출 기준)는 상호저축은행을 제외하고 모두 상승했다.

"""
    ]
    for t in tests:
        print("--------------------------------------------------")
        print(t)
        print("→", replace_date_in_sentence(t, today))
