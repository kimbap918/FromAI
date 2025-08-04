def capture_and_generate_news(keyword: str, domain: str = "stock", progress_callback=None, debug=False):
    """
    키워드와 도메인에 따라 정보성 뉴스를 생성한다.
    :param keyword: 종목명/통화명/코인명 등
    :param domain: "stock", "fx", "coin" 등
    :param progress_callback: 진행상황 콜백 함수(옵션)
    :param debug: 디버그 출력 여부
    :return: LLM이 생성한 기사(제목, 본문, 해시태그)
    """
    from news.src.services.info_LLM import generate_info_news_from_text
    info_dict = {}
    is_stock = (domain == "stock")
    # ... (중략, 전체 구현 복사 필요) ...
    if progress_callback:
        progress_callback("LLM 기사 생성 중...")
    news = generate_info_news_from_text(keyword, info_dict, domain)
    if news:
        from news.src.utils.file_utils import save_news_to_file
        save_news_to_file(keyword, domain, news)
    return news


def build_stock_prompt(today_kst):
    # 다양한 포맷 지원: '2025년 7월 1일', '20250701', '2025-07-01', '2025.07.01' 등
    from datetime import datetime
    date_obj = None
    for fmt in ["%Y년 %m월 %d일", "%Y%m%d", "%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%Y %m %d"]:
        try:
            date_obj = datetime.strptime(today_kst.split()[0], fmt)
            break
        except Exception:
            continue
    if not date_obj:
        date_obj = datetime.now()
    # ... (중략, 전체 구현 복사 필요) ...
    return "[프롬프트 내용 반환]"

