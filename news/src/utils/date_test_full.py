import re
from datetime import datetime, date

# 날짜 패턴 정의 (긴 것 우선)
patterns = {
    'ymd': r"(\d{4})[년.\- ]+(\d{1,2})[월.\- ]+(\d{1,2})[일.]?",
    'md': r"(\d{1,2})월\s*(\d{1,2})일",
    'ym': r"(\d{4})년\s*(\d{1,2})월",
    'm': r"(\d{1,2})월",
    'year_only': r"(\d{4})년"
}

def parse_natural_date(date_str: str, today: date) -> str:
    date_str = date_str.strip()

    if match := re.fullmatch(patterns['ymd'], date_str):
        y, m, d = map(int, match.groups())
        target = date(y, m, d)
        return _convert_relative_expression(target, today)

    elif match := re.fullmatch(patterns['md'], date_str):
        m, d = map(int, match.groups())
        y = today.year
        target = date(y, m, d)
        return _convert_relative_expression(target, today)

    elif match := re.fullmatch(patterns['ym'], date_str):
        y, m = map(int, match.groups())
        if y == today.year:
            if m < today.month:
                return f"지난 {m}월"
            elif m > today.month:
                return f"오는 {m}월"
            else:
                return f"{m}월"
        elif y < today.year:
            return f"지난 {str(y)[2:]}년 {m}월"
        else:
            return f"오는 {str(y)[2:]}년 {m}월"

    elif match := re.fullmatch(patterns['m'], date_str):
        m = int(match.group(1))
        if m == today.month:
            return f"{m}월"
        elif m > today.month:
            return f"오는 {m}월"
        else:
            return f"지난 {m}월"

    elif match := re.fullmatch(patterns['year_only'], date_str):
        y = int(match.group(1))
        if y == today.year:
            return f"{str(y)[2:]}년"
        elif y < today.year:
            return f"지난 {str(y)[2:]}년"
        else:
            return f"오는 {str(y)[2:]}년"

    return date_str

def _convert_relative_expression(target: date, today: date) -> str:
    if target == today:
        return f"{target.day}일"

    elif target.year == today.year:
        if target.month == today.month:
            return f"지난 {target.day}일" if target < today else f"오는 {target.day}일"
        elif target < today:
            return f"지난 {target.month}월 {target.day}일"
        else:
            return f"오는 {target.month}월 {target.day}일"

    elif target < today:
        return f"지난 {str(target.year)[2:]}년 {target.month}월 {target.day}일"

    else:
        return f"오는 {str(target.year)[2:]}년 {target.month}월 {target.day}일"


def replace_date_in_sentence(sentence: str, today: date) -> str:
    """문장에서 날짜 표현을 찾아 시제로 변환 (겹침 방지 포함)"""
    matched_spans = []

    def is_overlapping(start, end):
        return any(s <= start < e or s < end <= e for s, e in matched_spans)

    # 긴 패턴부터 적용
    for key in ['ymd', 'md', 'ym', 'm', 'year_only']:
        pattern = patterns[key]
        for match in re.finditer(pattern, sentence):
            start, end = match.span()
            if is_overlapping(start, end):
                continue
            date_expr = match.group(0)
            new_expr = parse_natural_date(date_expr, today)
            sentence = sentence[:start] + new_expr + sentence[end:]
            matched_spans.append((start, start + len(new_expr)))
    return sentence

# ✅ 사용 예시
today = date(2025, 7, 4)
test_cases = [
"""
제목
서울 7월 4일 오전 기온 27.2도, 폭염 특보 발효

본문
2025년 8월 4일 오전 11시 10분 기준, 서울 중구 태평로1가 지역의 기온은 27.2도로 측정되었다. 체감온도는 이보다 높은 28.8도로 나타났으며, 전날 같은 시각보다 1도 낮은 수치다. 현재 습도는 74%이며, 남풍이 시속 2.3m의 속도로 불고 있다. 1시간 강수량은 기록되지 않았다.
해당 지역에는 폭염영향예보와 함께 폭염 특보가 발효 중이다. 이는 무더위로 인한 건강 피해 우려가 있는 상황으로, 특히 야외 활동 시 열사병 예방을 위한 주의가 필요하다. 이날 일출 시각은 오전 5시 16분, 일몰은 오후 7시 57분으로 예보되어 있다.
대기질은 대체로 양호한 상태를 유지하고 있다. 초미세먼지(PM2.5)는 12㎍/㎥, 미세먼지(PM10)는 25㎍/㎥로 모두 ‘좋음’ 등급이며, 오존(O₃) 농도는 0.030ppm으로 ‘보통’ 수준이다. 서울 도심권의 대기 여건은 비교적 안정적인 편이나, 폭염 특보로 인한 야외 활동 자제 권고가 계속되고 있다.
"""
]

for s in test_cases:
    print(f"> 원문: {s}")
    print(f"→ 변환: {replace_date_in_sentence(s, today)}\n")
