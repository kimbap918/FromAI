import google.generativeai as genai
import os
import sys
from PIL import Image
from dotenv import load_dotenv
from news.src.utils.common_utils import get_today_kst_str, build_stock_prompt
from news.src.utils.exchange_utils import build_fx_prompt
from news.src.utils.weekly_stock_utils import (
    get_five_trading_days_ohlc,
    format_weekly_ohlc_for_prompt,
    build_weekly_stock_prompt,
)

# ==========================
# [Billing Helpers] 요금 계산
# ==========================
GEMINI_FLASH_PRICE = {
    "standard": {"in": 0.30, "out": 2.50},  # USD / 1M tokens
    "batch":    {"in": 0.15, "out": 1.25},
}

def _safe_get(obj, name, default=0):
    """usage_metadata가 객체/딕셔너리 어떤 형태든 안전하게 꺼내기"""
    if obj is None:
        return default
    if hasattr(obj, name):
        val = getattr(obj, name)
        return default if val is None else val
    if isinstance(obj, dict):
        val = obj.get(name, default)
        return default if val is None else val
    return default

def print_token_usage_and_cost(usage, pricing_tier: str = "standard"):
    """
    항상 '공급자 기준'(provider_total)으로 과금 계산:
      billed_out = total_token_count - prompt_token_count
    참고를 위해 text-only(candidates+thoughts)도 함께 출력하되, 비용 계산엔 사용하지 않음.
    """
    price_in  = GEMINI_FLASH_PRICE[pricing_tier]["in"]
    price_out = GEMINI_FLASH_PRICE[pricing_tier]["out"]

    prompt     = _safe_get(usage, "prompt_token_count", 0)
    candidates = _safe_get(usage, "candidates_token_count", 0)
    thoughts   = _safe_get(usage, "thoughts_token_count", 0)
    total      = _safe_get(usage, "total_token_count", prompt + candidates + thoughts)

    # 두 기준 동시 계산 (비용은 provider_total만 사용)
    billed_out_provider = max(total - prompt, 0)            # ← 과금 계산에 사용
    billed_out_textonly = max(candidates + thoughts, 0)     # 참고용

    in_cost  = prompt             / 1_000_000 * price_in
    out_cost = billed_out_provider / 1_000_000 * price_out

    print("\n=== 토큰 사용량 ===")
    print(f"입력 토큰: {prompt}")
    print(f"답변 토큰: {candidates}")
    print(f"추론 토큰: {thoughts}")
    print(f"전체 토큰(모델 보고): {total}")
    print(f"- 공급자 기준(= total - 입력): {billed_out_provider}  <-- 과금 기준")
    print(f"- 텍스트 기준(= 답변 + 추론):  {billed_out_textonly}  (참고용)")

    print("\n=== 비용 추정 (Gemini 2.5 Flash / {tier}) ===".format(
        tier="Batch" if pricing_tier == "batch" else "Standard"))
    print(f"입력 비용: ${in_cost:.6f}")
    print(f"출력 비용: ${out_cost:.6f}  <-- 공급자 기준")
    print(f"총  비용: ${in_cost + out_cost:.6f}")

    # 원자료도 함께 남겨 이슈 추적
    try:
        raw = getattr(usage, "__dict__", None) or dict(usage)
        print("\n[DEBUG] usage raw:", raw)
    except Exception:
        pass



# ------------------------------------------------------------------
# 작성자 : 곽은규
# 기능 : 다양한 실행 환경(.py, PyInstaller)에서 .env 파일 로드
# ------------------------------------------------------------------
def _load_env_file():
    """
    GOOGLE_API_KEY 환경 변수가 로드되었는지 확인하고, 로드되지 않았다면 여러 예상 경로에서 .env 파일을 찾아 로드
    """
    if os.getenv("GOOGLE_API_KEY"):
        return
    
    # PyInstaller로 빌드된 경우와 개발 중인 경우를 구분
    if getattr(sys, "frozen", False):
        # exe로 빌드된 경우: 여러 경로에서 .env 파일 검색
        search_paths = [
            os.path.dirname(sys.executable),  # exe 실행 디렉토리
            os.path.join(os.path.expanduser("~"), "Desktop"),  # 바탕화면
            os.path.join(os.getenv("APPDATA", ""), "NewsGenerator"),  # APPDATA [임시 배포용 - 주석 처리]
            os.getcwd(),  # 현재 작업 디렉토리
        ]
        
        # _MEIPASS가 있으면 추가
        if hasattr(sys, '_MEIPASS'):
            search_paths.insert(0, sys._MEIPASS)
        
        for path in search_paths:
            if path and os.path.exists(path):
                env_path = os.path.join(path, ".env")
                if os.path.exists(env_path):
                    load_dotenv(env_path)
                    if os.getenv("GOOGLE_API_KEY"):
                        print(f"✅ .env 파일을 찾았습니다: {env_path}")
                        return
    else:
        # 개발 중인 경우: 기존 로직 유지
        if hasattr(sys, '_MEIPASS'):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))

        dotenv_path = os.path.join(base_path, '.env')
        if not os.path.exists(dotenv_path):
            dotenv_path = os.path.join(os.getcwd(), '.env')
        
        load_dotenv(dotenv_path)

# 환경 변수 로드
_load_env_file()

# API 키 확인
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError(".env에서 GOOGLE_API_KEY를 불러오지 못했습니다.")

genai.configure(api_key=api_key)

# ------------------------------------------------------------------
# 작성자 : 곽은규
# 작성일 : 2025-07-17
# 기능 : 정보성 기사 생성을 위한 기본 시스템 프롬프트
# ------------------------------------------------------------------
BASE_SYSTEM_PROMPT = (
    """
    [System Message]
    사용자가 키워드, 텍스트 정보, 그리고 이미지를 제공합니다.
    제공된 모든 정보를 종합적으로 분석하여 기사 문체로 작성합니다.
    **최종 출력은 [제목], [해시태그], [본문]의 세 섹션으로 명확히 구분하여 반드시 작성할 것.** 
    
    [Role]
    - 당신은 데이터(키워드, 텍스트, 이미지)를 분석하여 독자가 이해하기 쉬운 기사를 작성하는 전문 기자입니다.
    - 당신의 최우선 역할은 '전문 기자'로서, 데이터 속에서 정확히 독자에게 전달하는 것입니다. 이것이 모든 작업의 핵심 목표입니다.
    - 특정 주제(예: 주식)에 대한 **[Special Rules for ...], [Style], [키워드 정보(user message)]** 태그가 별도로 제공됩니다.
    - 전제적인 구조와 1. [News Generation Process (Step-by-Step Execution)]를 면밀히 확인하고 2. **[Special Rules for ...], [General Style Standards]** 태그의 내용을 준수하여 3. [키워드 정보(user message)]가 제공하는 정보를 참고해 4. [Output Format] 형식에 맞게 출력해야 합니다.
    
    [News Generation Process (Step-by-Step Execution)]
    1. 제공된 정보 인식
        1) 사용자가 입력한 키워드, 텍스트 데이터, 이미지를 수집합니다.

    2. 텍스트 정보 분석
        1) 제공된 텍스트(최신 뉴스 요약 등)의 핵심 내용을 파악합니다.
        
    3. 이미지 or 차트이미지 분석 (이미지 제공 시)
        - 제공된 이미지 or 차트이미지에서 시각적 정보를 분석합니다.
        - **데이터의 시각적 패턴(예: 특정 구간의 급격한 변화, 주기성)과 핵심 지표(예: 최고/최저점, 평균선, 변동폭)를 파악합니다.**
        - 차트에서 보이는 추세(상승, 하락, 횡보)를 분석합니다.

    4. 본문 작성 (종합 분석 기반)
        - **텍스트 정보와 이미지 분석 결과를 종합하여** 객관적인 시황 정보를 전달하는 기사 형식으로 작성합니다. (500자 이상 800자 미만)
        - **핵심 요약으로 시작**: 기사 첫 문단에 현재 시점의 가장 중요한 정보를 요약하여 제시하세요.
        - **데이터 기반 서사 구축**:
            당신은 데이터의 관계를 파악하여 이야기를 만드는 전문 기자입니다.
            아래의 원칙에 따라 데이터를 유기적으로 해석하고 연결하여 하나의 완성된 글로 만드세요.

        1) 핵심 결과 식별 및 선언:
            모든 데이터 중 가장 중요하고 의미 있는 핵심 결과를 전체 이야기의 흐름을 이끌어가는 자연스러운 시작점 역할을 해야 한다.
        2) 과정 묘사:
            시작점, 경유지, 도착점 등 주요 수치를 서술할 때는 고정된 문장 패턴을 반복하지 말고, 흐름에 따라 다양한 문장 구조로 자연스럽게 기술할 것.  
            숫자 나열 대신 의미 있는 흐름을 전달하는 문장으로 재구성할 것.
        3) 비교를 통한 의미 해석:
            현재의 결과를 과거의 데이터와 비교하여 그 변화가 가지는 상대적인 의미와 맥락을 설명한다.
            이 비교를 통해 상승/하락, 변화의 방향성을 명확히 한다.
        4) 데이터 간의 논리적 연결:
            하나의 현상(핵심 지표의 변화)을 설명할 때, 다른 종류의 데이터(보조 지표)를 그 현상의 근거 혹은 원인으로 연결하여 분석의 깊이를 더해야 한다.
            두 데이터 간의 논리적 인과 관계나 상관 관계를 서술하여 주장에 대한 설득력을 높인다.

        - **객관성 유지**: 추측이나 예측성 표현('~일 전망이다', '~할 것으로 보인다')은 절대 사용하지 않습니다.
        - **문체**: 뉴스 기사 문체(~이다, ~했다)를 일관되게 사용하고, 서술식(~습니다, ~입니다) 문제와 서식(볼드, 기울임)은 절대 사용하지 않는다.
        - **가독성 원칙 준수**: 전문 용어를 사용할 경우, 독자의 이해를 돕기 위해 필요한 경우 간결한 부연 설명을 덧붙입니다.
        - 입력된 키워드(종목명)를 3~5회 자연스럽게 포함합니다.
        - **Markdown 문법을 절대 사용하지 않습니다.**

    5. 제목 작성 방식
        - **생성된 본문을 기반으로 추천 제목 3개 제공**
        - 입력된 키워드를 최대한 제목 앞쪽에 배치
        - **간결한 헤드라인 형식으로 작성**
        - **완전한 문장형이 아닌 핵심 키워드 중심으로 구성**
        - **궁금증을 유발할 수 있도록 작성하되, 특수문자 없이 표현하며 본문의 핵심 내용이나 주요 결과를 간결하게 요약하여 포함**
        - 제목에 한해 **특수문자 금지: 말줄임표("...", "⋯"), 더하기(+), 빼기(-), 마침표(.), 물음표(?), 느낌표(!), 괄호((), []) **

    6. 출력 형식 적용 (최종 제공)
        기사 생성 후, 아래 출력 형식에 맞춰 제공
        
        [Output Format]
        - 제목 (3개 제공, 각 제목 당 최대 35자 내외)
        - 해시태그 (10개 내외)
        - 본문 [News Generation Process (Step-by-Step Execution)] 양식에 맞는지 필히 확인
        -**아래 형식을 반드시, 그리고 정확히 준수하여 출력해야 합니다.** 각 섹션의 제목과 대괄호, 줄바꿈을 포함해야 합니다.  

        [제목]
        (여기에 생성한 제목 1)
        (여기에 생성한 제목 2)
        (여기에 생성한 제목 3)

        [해시태그]
        #(해시태그1) #(해시태그2) #(해시태그3) ...

        [본문]
        (여기에 생성한 본문 내용, 500자 이상 800자 미만)
"""
)

# ------------------------------------------------------------------
# 작성자 : 곽은규
# 기능 : 기본 시스템 프롬프트에 특정 도메인(주식)의 규칙을 추가
# ------------------------------------------------------------------
def build_system_prompt(keyword, today_kst, is_stock=False):
    """
    기본 시스템 프롬프트를 생성하고, is_stock이 True일 경우 주식 관련 특별 규칙을 추가
    :param keyword: 기사 키워드
    :param today_kst: 오늘 날짜(KST) 문자열
    :param is_stock: 주식 관련 기사인지 여부
    :return: 최종 시스템 프롬프트 문자열
    """
    prompt = BASE_SYSTEM_PROMPT.format(keyword=keyword, today_kst=today_kst)
    # Debug: 기본 시스템 프롬프트가 제대로 생성되는지 길이와 앞부분을 출력
    try:
        print("[DEBUG] BASE_SYSTEM_PROMPT 길이:", len(prompt))
        print("[DEBUG] BASE_SYSTEM_PROMPT 미리보기:\n" + (prompt[:1000] if len(prompt) > 1000 else prompt))
    except Exception:
        pass
    if is_stock:
        stock_prompt = build_stock_prompt(today_kst)
        prompt += "\n" + stock_prompt
        print(prompt)
    return prompt


# ------------------------------------------------------------------
# 작성자 : 곽은규
# 기능 : 이미지와 키워드를 입력받아 정보성 기사 생성 (Vision 모델 사용)
# 현재 상태: 미사용 함수 
# ------------------------------------------------------------------
def generate_info_news(keyword: str, image_path: str, is_stock: bool,
                       pricing_tier: str = "standard",
                       thinking_budget_tokens: int | None = None):
    """
    **현재 사용하지 않는 함수입니다.**
    주어진 이미지(차트 등)를 Gemini Vision 모델로 분석하여 정보성 기사를 생성
    :param keyword: 기사 생성에 사용할 키워드 (예: 주식명)
    :param image_path: 분석할 이미지 파일 경로
    :param is_stock: 주식 관련 이미지인지 여부 (프롬프트 분기용)
    :param pricing_tier: "standard" 또는 "batch"
    :param thinking_budget_tokens: 추론 토큰 예산 (0=끄기, 예: 256=켜기)
    :return: LLM이 생성한 기사 텍스트, 오류 발생 시 None
    """
    today_kst = get_today_kst_str()
    system_prompt = build_system_prompt(keyword, today_kst, is_stock=is_stock)

    user_message = f"아래 이미지는 '{keyword}' 관련 이미지 입니다. 이미지의 내용을 면밀히 분석해 기사 형식으로 작성하세요."

    gen_config = None
    if thinking_budget_tokens is not None:
        # SDK별 차이를 흡수하기 위해 가장 호환성 높은 키를 시도
        gen_config = {"thinking": {"budgetTokens": thinking_budget_tokens}}

    model = genai.GenerativeModel(
        model_name='gemini-2.5-flash',
        system_instruction=system_prompt,
        generation_config=gen_config
    )

    try:
        img = Image.open(image_path)
        response = model.generate_content([
            user_message,
            img
        ])
        # 토큰/비용 출력
        usage = getattr(response, 'usage_metadata', None)
        if usage:
            print_token_usage_and_cost(usage, pricing_tier=pricing_tier)

        # 생성된 응답 반환
        return response.text
    except Exception as e:
        print(f"Gemini Vision API 호출 중 오류 발생: {e}")
        return None

# ------------------------------------------------------------------
# 작성자 : 곽은규
# 기능 : 텍스트 데이터(딕셔너리)와 키워드를 입력받아 정보성 기사 생성
# ------------------------------------------------------------------
def generate_info_news_from_text(keyword: str, info_dict: dict, domain: str = "generic",
                                 pricing_tier: str = "standard",
                                 thinking_budget_tokens: int | None = None):
    """
    정제된 텍스트 데이터(딕셔너리)를 기반으로 Gemini 모델을 사용하여 정보성 기사를 생성
    :param keyword: 기사 생성에 사용할 키워드
    :param info_dict: 기사 내용으로 사용할 정제된 데이터 딕셔너리
    :param domain: 데이터의 종류 (예: 'stock', 'fx', 'coin', 'week')
    :param pricing_tier: "standard" 또는 "batch" (요금 단가)
    :param thinking_budget_tokens: 추론 토큰 예산 (0=끄기, 예: 256=켜기)
    :return: LLM이 생성한 기사 텍스트
    """
    today_kst = get_today_kst_str()
    # 주간 도메인에서는 명확히 BASE_SYSTEM_PROMPT + weekly_prompt 형태만 사용하도록 강제
    if domain == "week":
        # BASE_SYSTEM_PROMPT에 .format을 적용해 기본 시스템 메시지를 생성
        system_prompt = BASE_SYSTEM_PROMPT.format(keyword=keyword, today_kst=today_kst)
    else:
        # 일반 주식/토스 도메인은 기존 로직(주식 전용 규칙 포함) 사용
        system_prompt = build_system_prompt(keyword, today_kst, is_stock = domain in ["stock", "toss"])

    # Debug: 최종 system_prompt가 모델에 전달되기 전 길이 및 미리보기 출력
    try:
        print("[DEBUG] 최종 system_prompt 길이:", len(system_prompt))
        print("[DEBUG] 최종 system_prompt 미리보기:\n" + (system_prompt[:1000] if len(system_prompt) > 1000 else system_prompt))
    except Exception:
        pass

    def _format_dict_for_prompt(data_dict):
        def _is_time_label(k: str) -> bool:
            try:
                return isinstance(k, str) and len(k) in (4,5) and ":" in k and int(k.split(":")[0]) in range(0,24)
            except Exception:
                return False

        def _walk(obj, indent=0):
            lines = []
            if isinstance(obj, dict):
                items = list(obj.items())
                # 시간 라벨 형식이면 키로 정렬
                if all(_is_time_label(k) for k, _ in items):
                    items.sort(key=lambda kv: kv[0])
                for k, v in items:
                    if isinstance(v, dict):
                        lines.append(" " * indent + f"{k}:")
                        lines.extend(_walk(v, indent + 2))
                    else:
                        lines.append(" " * indent + f"{k}: {v}")
            else:
                lines.append(" " * indent + str(obj))
            return lines

        return "\n".join(_walk(data_dict, 0))

    info_str = _format_dict_for_prompt(info_dict)

    # 도메인별 프롬프트/정보 포맷 분기
    if domain in ["stock", "toss"]:
        is_foreign_stock = any(k in info_dict for k in ["name", "price", "change"])
        if is_foreign_stock:
            user_message = (
                f"아래는 '{keyword}'의 해외주식 시세 및 재무정보입니다. "
                f"이 데이터는 모두 '{keyword}'(회사)의 실제 시세 및 재무정보입니다. "
                f"이 데이터를 바탕으로 기사 형식으로 분석해 주세요.\n"
                f"[해외주식 정보]\n{info_str}"
            )
        else:
            user_message = (
                f"아래는 '{keyword}'의 주식 시세 및 재무정보입니다. "
                f"이 데이터는 모두 '{keyword}'(회사)의 실제 시세 및 재무정보입니다. "
                f"이 데이터를 바탕으로 기사 형식으로 분석해 주세요.\n"
                f"[주식 정보]\n{info_str}"
            )
    elif domain == "week":
        # 주간 기사 전용: 기본 주식 정보 포맷 + 주간 OHLC와 전용 규칙 주입
        user_message = (
            f"아래는 '{keyword}'의 주식 시세 및 재무정보입니다. "
            f"이 데이터는 모두 '{keyword}'(회사)의 실제 시세 및 재무정보입니다. "
            f"이 데이터를 바탕으로 기사 형식으로 분석해 주세요.\n"
            f"[주식 정보]\n{info_str}"
        )
        try:
            # 우선 info_dict에 symbol이 있는지 확인하여 우선 사용
            weekly_rows = None
            if isinstance(info_dict, dict) and info_dict.get('symbol'):
                sym = info_dict.get('symbol')
                try:
                    print(f"[DEBUG] weekly OHLC 시도: symbol 사용 -> {sym}")
                    weekly_rows = get_five_trading_days_ohlc(sym)
                except Exception:
                    weekly_rows = None

            # symbol로 실패하거나 없으면 기본 키워드로 시도
            if not weekly_rows:
                try:
                    weekly_rows = get_five_trading_days_ohlc(keyword)
                except Exception:
                    weekly_rows = None

        except Exception:
            weekly_rows = None
        # 해외 종목의 경우 추가 재시도: info_dict의 영문명/이름으로 재시도
        if not weekly_rows and isinstance(info_dict, dict):
            try:
                alt_name = info_dict.get('name') or info_dict.get('Name') or info_dict.get('keyword')
                if alt_name and alt_name != keyword:
                    print(f"[DEBUG] weekly OHLC 재시도: 대체 이름 사용 -> {alt_name}")
                    weekly_rows = get_five_trading_days_ohlc(alt_name)
            except Exception:
                weekly_rows = None
        if weekly_rows:
            weekly_text = format_weekly_ohlc_for_prompt(weekly_rows)
            user_message = user_message + "\n" + "[주간 OHLC (최근 5거래일)]\n" + weekly_text
        weekly_prompt = build_weekly_stock_prompt()
        system_prompt = system_prompt + "\n" + weekly_prompt
        # Debug: 주간 도메인일 때 weekly prompt가 실제로 시스템 프롬프트에 포함되었는지 확인
        try:
            print("[DEBUG] Weekly prompt 길이:", len(weekly_prompt))
            print("[DEBUG] Weekly prompt 미리보기:\n" + (weekly_prompt[:1000] if len(weekly_prompt) > 1000 else weekly_prompt))
        except Exception:
            pass
    elif domain == "fx":
        user_message = (
            f"아래는 '{keyword}'의 환율 정보입니다. "
            f"이 데이터는 모두 '{keyword}'(통화)의 실제 환율 정보입니다. "
            f"이 데이터를 바탕으로 기사 형식으로 분석해 주세요.\n"
            f"[환율 정보]\n{info_str}"
        )
        # 다중 통화(종합) 여부 판단: 통화목록 키가 있고 2개 이상일 때
        include_aggregate_tag = False
        try:
            if isinstance(info_dict, dict) and "통화목록" in info_dict:
                lst = info_dict.get("통화목록") or []
                include_aggregate_tag = isinstance(lst, (list, tuple)) and len(lst) > 1
        except Exception:
            include_aggregate_tag = False
        fx_prompt = build_fx_prompt(today_kst, include_aggregate_tag=include_aggregate_tag)
        system_prompt = system_prompt + "\n" + fx_prompt
        print("[DEBUG] FX 프롬프트 주입 완료 (exchange_utils): 길이=", len(fx_prompt), ", include_aggregate_tag=", include_aggregate_tag)
        try:
            print("\n[FX 프롬프트 미리보기]\n" + fx_prompt + "\n")
        except Exception:
            pass

    elif domain == "coin":
        user_message = (
            f"아래는 '{keyword}'의 암호화폐(코인) 정보입니다. "
            f"이 데이터는 모두 '{keyword}'(코인)의 실제 시세 및 정보입니다. "
            f"이 데이터를 바탕으로 기사 형식으로 분석해 주세요.\n"
            f"[코인 정보]\n{info_str}"
        )
    else:
        user_message = (
            f"아래는 '{keyword}'의 정보입니다. "
            f"이 데이터를 바탕으로 기사 형식으로 분석해 주세요.\n"
            f"[정보]\n{info_str}"
        )

    print("\n[키워드 정보(user message)]\n" + user_message + "\n")

    gen_config = None
    if thinking_budget_tokens is not None:
        gen_config = {"thinking": {"budgetTokens": thinking_budget_tokens}}

    model = genai.GenerativeModel(
        model_name='gemini-2.5-flash',
        system_instruction=system_prompt,
        generation_config=gen_config
    )

    response = model.generate_content(user_message)
    print("[LLM 응답 결과]\n" + response.text + "\n")
    
    # 토큰/비용 출력 (필드가 없으면 보정)
    usage = getattr(response, 'usage_metadata', None)
    if usage:
        print_token_usage_and_cost(usage, pricing_tier=pricing_tier)
    else:
        print("\n(참고) usage_metadata가 제공되지 않았습니다. SDK/버전을 확인하세요.")
    
    return response.text
