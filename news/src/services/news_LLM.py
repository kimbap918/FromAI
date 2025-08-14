import os
import sys
import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
from newspaper import Article
from dotenv import load_dotenv
from datetime import datetime
import logging
try:
    from . import check_LLM
except ImportError:
    import check_LLM


def _ensure_env_loaded():
    if os.getenv("GOOGLE_API_KEY"):
        return
    # 1) 기본 현재 경로 시도
    load_dotenv()
    if os.getenv("GOOGLE_API_KEY"):
        return
    # 2) 모듈 파일 경로 시도
    module_dir = os.path.dirname(__file__)
    load_dotenv(os.path.join(module_dir, ".env"))
    if os.getenv("GOOGLE_API_KEY"):
        return
    # 3) PyInstaller 실행파일 경로 시도
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        load_dotenv(os.path.join(exe_dir, ".env"))
        if os.getenv("GOOGLE_API_KEY"):
            return
    # 4) PyInstaller 임시 해제 경로(_MEIPASS) 시도
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        load_dotenv(os.path.join(meipass, ".env"))


_ensure_env_loaded()

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError(".env에서 GOOGLE_API_KEY를 불러오지 못했습니다.")
genai.configure(api_key=api_key)

model = genai.GenerativeModel("gemini-2.5-flash")


def setup_logging(keyword: str) -> tuple:
    """
    키워드별 로그 폴더와 파일을 설정하고 로거를 반환합니다.
    """
    # 현재 날짜로 폴더명 생성
    current_date = datetime.now().strftime("%Y%m%d")
    
    # exe 빌드 시와 개발 시를 구분하여 경로 설정
    if getattr(sys, 'frozen', False):
        # exe 빌드 시: 실행 파일이 있는 디렉토리
        base_dir = os.path.dirname(sys.executable)
    else:
        # 개발 시: 현재 스크립트 위치에서 상위로 이동하여 FromAI1.1.3 2 찾기
        current_dir = os.path.dirname(os.path.dirname(__file__))  # news/src/services -> news/
        base_dir = current_dir
        
        # FromAI1.1.3 2 폴더를 찾을 때까지 상위 디렉토리로 이동
        while base_dir and not os.path.exists(os.path.join(base_dir, "FromAI1.1.3 2")):
            parent_dir = os.path.dirname(base_dir)
            if parent_dir == base_dir:  # 루트 디렉토리에 도달
                break
            base_dir = parent_dir
        
        # FromAI1.1.3 2 폴더가 없으면 현재 디렉토리 사용
        if not os.path.exists(os.path.join(base_dir, "FromAI1.1.3 2")):
            base_dir = current_dir
    
    # 폴더 경로 생성
    if getattr(sys, 'frozen', False):
        # exe 빌드 시: 실행 파일 루트에 직접 생성
        log_dir = os.path.join(base_dir, "기사 재생성", f"재생성{current_date}")
    else:
        # 개발 시: FromAI1.1.3 2 폴더 아래에 생성
        log_dir = os.path.join(base_dir, "FromAI1.1.3 2", "기사 재생성", f"재생성{current_date}")
    
    # 폴더 생성
    os.makedirs(log_dir, exist_ok=True)
    
    # 키워드로 파일명 생성 (특수문자 제거)
    safe_keyword = "".join(c for c in keyword if c.isalnum() or c in (' ', '-', '_')).strip()
    safe_keyword = safe_keyword.replace(' ', '_')
    
    # 로그 파일명 생성
    timestamp = datetime.now().strftime("%H%M%S")
    log_filename = f"{safe_keyword}.txt"
    log_filepath = os.path.join(log_dir, log_filename)
    
    # 로거 설정
    logger = logging.getLogger(f"news_llm_{keyword}_{timestamp}")
    logger.setLevel(logging.INFO)
    
    # 파일 핸들러 설정 (텍스트 파일로 저장)
    file_handler = logging.FileHandler(log_filepath, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # 콘솔 핸들러 설정
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 포맷터 설정 (콘솔용과 파일용을 다르게)
    console_formatter = logging.Formatter('%(message)s')  # 콘솔에는 메시지만
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')  # 파일에는 시간 포함
    
    file_handler.setFormatter(file_formatter)
    console_handler.setFormatter(console_formatter)
    
    # 핸들러 추가
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger, log_filepath


def log_and_print(logger, message: str, level: str = "info"):
    """
    로그와 콘솔에 동시에 메시지를 출력합니다.
    """
    if level == "info":
        logger.info(message)
    elif level == "warning":
        logger.warning(message)
    elif level == "error":
        logger.error(message)
    elif level == "debug":
        logger.debug(message)
    
    # 콘솔에도 출력 (로거가 이미 콘솔에 출력하므로 중복 방지)
    # print(message)


def extract_title_and_body(url, logger):
    log_and_print(logger, f"\n  📄 기사 추출 세부 과정:")
    log_and_print(logger, f"    - newspaper 라이브러리로 기사 다운로드 시도...")
    
    article = Article(url, language='ko')
    article.download()
    article.parse()
    title = article.title.strip()
    body = article.text.strip()
    
    log_and_print(logger, f"    - 다운로드된 제목: {title}")
    log_and_print(logger, f"    - 다운로드된 본문 길이: {len(body)}자")
    
    if len(body) < 50:
        log_and_print(logger, f"    ⚠️ 본문이 짧아 fallback으로 전환합니다.", "warning")
        log_and_print(logger, f"    - fallback: extract_naver_cp_article() 호출...")
        title, body = extract_naver_cp_article(url, logger)
        log_and_print(logger, f"    - fallback 결과 제목: {title}")
        log_and_print(logger, f"    - fallback 결과 본문 길이: {len(body)}자")
    else:
        log_and_print(logger, f"    ✅ 본문 길이 충분 - newspaper 결과 사용")
    
    return title, body


def extract_naver_cp_article(url, logger):
    log_and_print(logger, f"      🔄 네이버 CP 기사 fallback 처리:")
    log_and_print(logger, f"        - requests로 HTML 직접 다운로드...")
    
    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, 'html.parser')
    
    log_and_print(logger, f"        - HTML 다운로드 완료: {len(res.text)}자")
    
    title_tag = soup.select_one('h2.media_end_head_headline')
    title = title_tag.text.strip() if title_tag else "제목 없음"
    
    log_and_print(logger, f"        - 제목 태그 검색 결과: {'찾음' if title_tag else '찾지 못함'}")
    log_and_print(logger, f"        - 추출된 제목: {title}")
    
    body_area = soup.select_one('article#dic_area')
    body = body_area.get_text(separator="\n").strip() if body_area else "본문 없음"
    
    log_and_print(logger, f"        - 본문 영역 검색 결과: {'찾음' if body_area else '찾지 못함'}")
    log_and_print(logger, f"        - 추출된 본문 길이: {len(body)}자")
    
    return title, body


def generate_system_prompt(keyword: str) -> str:
    prompt = (
        """[시스템 메세지]
        키워드, 기사 제목,  본문 순으로 사용자가 입력한다.
        단계별로 기사를 작성하고, **[출력 형식]에 맞게 출력한다.**

        1. 제목 생성
        - 제공된 기사 제목을 인용하고, 생성된 본문을 반영하여 **추천 제목 3개**를 생성한다.
        - 입력된 키워드를 최대한 앞쪽에 배치하고, 관련성이 적어도 자연스럽게 포함되도록 작성한다.
        - 궁금증을 유발하는 표현 금지 (예: '?', '왜', '어떻게', '무엇이' 등 사용 금지)
        - 사용 금지 기호: 마침표(.), 콜론(:), 마크다운 기호(*, #, &), Markdown 문법
        - 사용 가능 기호: 쉼표(,), 따옴표(' '), 쌍따옴표(" ") 
        - 부정적인 표현을 긍정적인 방향으로 조정한다.

        2. 본문 생성: 입력된 기사 본문 내용만 사용하여 새로운 기사 본문을 작성한다.
        - 500~1000자 내외로 작성 (단, 제공된 기사가 짧으면 불필요한 내용을 추가하지 않는다.)
        - 기사의 흐름과 논점을 유지하고, 의미를 변형하지 않는다.
        - 주요 흐름과 논란의 쟁점을 왜곡하지 않는다.
        - **인용문은 단어 하나도 변경하지 않는다.**
        - 격식체 종결어미 금지 (예: "입니다" → "이다", "했습니다" → "했다", "합니다" → "한다")
        - 맞춤법을 준수하고, 부적절한 표현 수정한다.
        -  제목과 본문에서 **'...' 사용 금지.**  
        - **볼드체(굵은 글씨) 사용 금지.**  

        3. 제목 및 본문 검토 
        -  제목과 본문에서 **금지된 기호(…, *, , #, &) 사용 여부 확인 및 수정
        - 제공된 정보 외 추측·허구·외부 자료 추가 여부 검토 후 수정

        4. 키워드 생성
        - 생성된 본문을 기반으로 5개 내외의 핵심 키워드를 추출한다.

        5. 출력형식에 맞게 출력한다.  
        [출력 형식]  
        - 제목 (3개 제공, 각 제목 당 최대 35자 내외)
        - 해시태그 (5개 내외)
        - 본문 내용
        -**아래 예시 형식을 반드시, 그리고 정확히 준수할것** 

        [제목]
        (여기에 생성한 제목 1)
        (여기에 생성한 제목 2)
        (여기에 생성한 제목 3)

        [해시태그]
        #(해시태그1) #(해시태그2) #(해시태그3) ...

        [본문]
        (여기에 생성한 본문 내용)"""
    )
    return prompt


def _is_fact_ok(check_result: dict) -> bool:
    """
    check_LLM가 돌려준 JSON 결과가 '문제 없음' 범주인지 판정
    """
    if not check_result or "json" not in check_result or not check_result["json"]:
        return False
    return check_result["json"].get("verdict") == "OK"


def generate_article(state: dict) -> dict:
    url = state.get("url")
    keyword = state.get("keyword")

    # 로거 설정
    logger, log_filepath = setup_logging(keyword)
    
    log_and_print(logger, "\n" + "="*80)
    log_and_print(logger, "📰 NEWS_LLM - 기사 재구성 시작")
    log_and_print(logger, "="*80)
    log_and_print(logger, f"\n📥 입력 데이터:")
    log_and_print(logger, f"  - URL: {url}")
    log_and_print(logger, f"  - 키워드: {keyword}")
    log_and_print(logger, f"  - 로그 파일: {log_filepath}")

    try:
        log_and_print(logger, f"\n🔗 기사 추출 단계:")
        log_and_print(logger, f"  - URL에서 기사 다운로드 및 파싱 중...")
        title, body = extract_title_and_body(url, logger)
        log_and_print(logger, f"  ✅ 기사 추출 완료")
        log_and_print(logger, f"  - 제목: {title}")
        log_and_print(logger, f"  - 본문 길이: {len(body)}자")
        
        
        # 전체 기사 내용을 로그에 저장
        log_and_print(logger, f"\n📋 전체 원본 기사:")
        log_and_print(logger, f"{'='*80}")
        log_and_print(logger, f"제목: {title}")
        log_and_print(logger, f"{'='*40}")
        log_and_print(logger, body)
        log_and_print(logger, f"{'='*80}")
        
        log_and_print(logger, f"\n🤖 AI 프롬프트 생성:")
        system_prompt = generate_system_prompt(keyword)
        user_request = f"키워드: {keyword}\n제목: {title}\n본문: {body}"
        log_and_print(logger, f"  - 시스템 프롬프트 길이: {len(system_prompt)}자")
        log_and_print(logger, f"  - 사용자 요청 길이: {len(user_request)}자")
        
        
        # 전체 프롬프트 내용을 로그에 저장
        log_and_print(logger, f"\n📋 전체 시스템 프롬프트:")
        log_and_print(logger, f"{'='*80}")
        log_and_print(logger, system_prompt)
        log_and_print(logger, f"{'='*80}")
        
        log_and_print(logger, f"\n📋 전체 사용자 요청:")
        log_and_print(logger, f"{'='*80}")
        log_and_print(logger, user_request)
        log_and_print(logger, f"{'='*80}")
 
        contents = [
            {'role': 'user', 'parts': [{'text': system_prompt}]},
            {'role': 'model', 'parts': [{'text': '이해했습니다. 규칙을 따르겠습니다.'}]},
            {'role': 'user', 'parts': [{'text': user_request}]}
        ]
 
        log_and_print(logger, f"\n⏳ Gemini AI 호출 중...")
        log_and_print(logger, f"  - 모델: gemini-2.5-flash")
        log_and_print(logger, f"  - 요청 내용 길이: {len(str(contents))}자")
         
        response = model.generate_content(contents)
        article_text = response.text.strip()
         
        log_and_print(logger, f"\n📤 AI 응답 결과:")
        log_and_print(logger, f"  - 응답 길이: {len(article_text)}자")
        
        
        # 전체 AI 응답 내용을 로그에 저장
        log_and_print(logger, f"\n📋 전체 AI 응답:")
        log_and_print(logger, f"{'='*80}")
        log_and_print(logger, article_text)
        log_and_print(logger, f"{'='*80}")
         
        log_and_print(logger, f"\n📊 기사 길이 비교:")
        log_and_print(logger, f"  - 원본 기사: {len(body)}자")
        log_and_print(logger, f"  - 재구성된 기사: {len(article_text)}자")
        log_and_print(logger, f"  - 길이 변화: {len(article_text) - len(body)}자")
 
        log_and_print(logger, f"\n🔍 사실관계 검증 단계:")
        log_and_print(logger, f"  - check_LLM.check_article_facts() 호출...")
        fact_check_result = check_LLM.check_article_facts(article_text, body, keyword)
        log_and_print(logger, f"  ✅ 사실관계 검증 완료")
        log_and_print(logger, f"  - 검증 결과 타입: {type(fact_check_result)}")
        log_and_print(logger, f"  - 검증 결과 키: {list(fact_check_result.keys()) if isinstance(fact_check_result, dict) else 'N/A'}")
 
        # --- 핵심 분기 ---
        log_and_print(logger, f"\n🎯 결과 분기 결정:")
        if _is_fact_ok(fact_check_result):
            log_and_print(logger, f"  ✅ 사실관계 문제 없음 - 재구성된 기사 사용")
            display_text = article_text
            display_kind = "article"
        else:
            log_and_print(logger, f"  ⚠️ 사실관계 문제 발견 - 수정된 기사 확인 중...")
            if fact_check_result["error"] is None and fact_check_result["json"]:
                corrected_article = fact_check_result["json"].get("corrected_article", "")
                if corrected_article:
                    log_and_print(logger, f"  ✅ 수정된 기사 사용")
                    display_text = corrected_article
                    display_kind = "corrected_article"
                else:
                    log_and_print(logger, f"  ⚠️ 수정된 기사 없음 - 재구성된 기사 사용")
                    display_text = article_text
                    display_kind = "article"
            else:
                log_and_print(logger, f"  ❌ 검증 실패 - 재구성된 기사 사용")
                display_text = article_text
                display_kind = "article"
         
        log_and_print(logger, f"\n📋 최종 결과:")
        log_and_print(logger, f"  - display_kind: {display_kind}")
        log_and_print(logger, f"  - display_text 길이: {len(display_text)}자")
        
        
        # 전체 최종 결과 내용을 로그에 저장
        log_and_print(logger, f"\n📋 전체 최종 결과:")
        log_and_print(logger, f"{'='*80}")
        log_and_print(logger, display_text)
        log_and_print(logger, f"{'='*80}")
         
         # 사실관계 검증 결과도 전체 내용 저장
        if fact_check_result and "explanation" in fact_check_result:
            log_and_print(logger, f"\n📋 전체 사실관계 검증 결과:")
            log_and_print(logger, f"{'='*80}")
            log_and_print(logger, fact_check_result["explanation"])
            log_and_print(logger, f"{'='*80}")
             
            if fact_check_result.get("json"):
                log_and_print(logger, f"\n📋 JSON 검증 결과:")
                log_and_print(logger, f"{'='*80}")
                import json
                log_and_print(logger, json.dumps(fact_check_result["json"], ensure_ascii=False, indent=2))
                log_and_print(logger, f"{'='*80}")

        result = {
            "url": url,
            "keyword": keyword,
            "title": title,
            "original_body": body,
            "generated_article": article_text,   # 원본도 보관
            "fact_check_result": fact_check_result,  # 전체 검증 결과 보관
            "corrected_article": fact_check_result.get("json", {}).get("corrected_article", "") if fact_check_result.get("json") else "",  # 수정된 기사
            "display_text": display_text,        # ★ UI/CLI에서 그대로 사용
            "display_kind": display_kind,        # ("article" | "corrected_article")
            "error": None
        }
        
        log_and_print(logger, f"\n📤 반환 데이터 구조:")
        log_and_print(logger, f"  - 반환 키 개수: {len(result)}")
        log_and_print(logger, f"  - 반환 키 목록: {list(result.keys())}")
        
        # 최종 결과를 로그 파일에 저장
        log_and_print(logger, f"\n💾 최종 결과를 로그 파일에 저장 완료")
        log_and_print(logger, f"  - 로그 파일 경로: {log_filepath}")
        
        log_and_print(logger, "\n" + "="*80)
        log_and_print(logger, "📰 NEWS_LLM - 기사 재구성 완료")
        log_and_print(logger, "="*80)
        
        return result
        
    except Exception as e:
        log_and_print(logger, f"\n❌ 예외 발생: {str(e)}", "error")
        log_and_print(logger, "\n" + "="*80, "error")
        log_and_print(logger, "📰 NEWS_LLM - 기사 재구성 실패", "error")
        log_and_print(logger, "="*80, "error")
        
        return {
            "url": url,
            "keyword": keyword,
            "title": "",
            "original_body": "",
            "generated_article": "",
            "fact_check_result": "",
            "display_text": f"오류: {str(e)}",
            "display_kind": "error",
            "error": str(e)
        }


if __name__ == "__main__":
    print("🔗 기사 URL과 키워드를 입력하면 Gemini가 재작성한 기사로 변환해줍니다.")
    url = input("기사 URL을 입력하세요: ").strip()
    keyword = input("핵심 키워드를 입력하세요: ").strip()

    print(f"\n📝 키워드: {keyword}")
    print(f"🔗 URL: {url}")
    print("="*50)
    print("처리 과정이 시작됩니다. 모든 과정은 로그 파일에 저장됩니다.")
    print("="*50)

    result = generate_article({"url": url, "keyword": keyword})

    if result["error"]:
        print("❌ 오류 발생:", result["error"])
    else:
        # 핵심: 분기된 결과만 출력
        print("\n✅ 결과:\n")
        print(result["display_text"])
        
        # 로그 파일 경로 표시
        print(f"\n📁 로그 파일이 저장되었습니다.")
        print(f"   폴더 구조: FromAI1.1.3 2/기사 재생성/재생성{datetime.now().strftime('%Y%m%d')}/")
        print(f"   파일명: {keyword}.txt")
        print(f"   FromAI1.1.3 2 폴더 바로 아래에 '기사 재생성' 폴더가 생성되었습니다.")
