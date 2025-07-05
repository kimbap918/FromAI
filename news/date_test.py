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

# 사용 예시
today = date(2025, 7, 4)
test_cases = [
    # 일 단독
    "7월 4일",
    "7월 4일 출시", # -> 4일 출시
    "7월 5일 공개", # -> 오는 5일 공개
    "7월 2일 오픈", # -> 지난 2일 오픈
    "6월 15일 종료", # -> 지난 15일 종료

    # 월 단독
    "7월 행사 개최", # -> 7월 행사 개최
    "6월 발표했다", # -> 지난 6월 발표했다
    "8월 오픈 예정", # -> 오는 8월 오픈 예정
    "5월 논의됐다", # -> 지난 5월 논의됐다

    # 년 단독
    "2025년 출시", # -> 25년 출시
    "25년 출시", # -> 25년 출시
    "2024년 시공 완료", # -> 지난 24년 시공 완료
    "2027년 개봉", # -> 오는 27년 개봉

    # 년+월
    "2025년 7월 행사", # -> 25년 7월 행사
    "2025년 6월 출시", # -> 지난 25년 6월 출시
    "2025년 8월 방영", # -> 오는 25년 8월 방영
    "2026년 3월 공개", # -> 지난 26년 3월 공개
    "2024년 12월 오픈", # -> 지난 24년 12월 오픈

    # 년+월+일
    "2025년 7월 2일 개봉", # -> 지난 2일 개봉
    "2025년 7월 4일 오픈", # -> 4일 오픈
    "2025년 7월 5일 공개", # -> 오는 5일 공개
    "2025년 6월 1일 시행", # -> 지난 1일 시행
    "2026년 8월 10일 종료", # -> 지난 10일 종료

    # 조합형 자연 문장
    "6월 1일 법안 시행", # -> 지난 1일 법안 시행
    "2025년 8월까지 착공", # -> 지난 8월까지 착공
    "2027년 5월까지 개발 완료", # -> 오는 5월까지 개발 완료
    "8월 개막 예정", # -> 오는 8월 개막 예정
    "5월 20일 발표했다" # -> 지난 20일 발표했다
]

for s in test_cases:
    print(replace_date_in_sentence(s, today))
