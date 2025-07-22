import google.generativeai as genai
import os

# Google Gemini API 키 설정 (환경 변수 또는 직접 설정)
# os.environ["GOOGLE_API_KEY"] = "YOUR_GEMINI_API_KEY"
# genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

# 또는 직접 설정 (보안상 권장되지 않음)
genai.configure(api_key=os.getenv("GOOGLE_API_KEY")) 

def generate_stock_news(stock_name: str, existing_article_content: str):
    """
    주식 관련 뉴스 기사를 생성하는 함수.
    주어진 시스템 프롬프트에 따라 기사 제목과 본문을 생성한다.
    """
    
    # 제공된 시스템 메시지 프롬프트
    system_prompt = f"""
    단계별로 기사를 작성하고, 출력규칙에 맞게 제목과 본문만 출력하세요.
    ※ 전체 기사 제목과 본문 다음 표현은 절대 사용하지 않는다: 볼드체(**), 말줄임표(...), 마침표(.), 쌍따옴표(" "), 콜론(:), 마크다운 기호(*, #, &), 감탄문, 질문형 문장, 기자 메일 주소 및 기자명 표기

    1. 본문 생성: 입력된 기사 본문 내용만 사용하여 새로운 기사 본문을 작성한다.
    - 500~1500자 내외로 작성 (단, 제공된 기사가 짧으면 불필요한 내용을 추가하지 않는다.)
    - 기사의 흐름과 논점을 유지하되, 문장이 어색하거나 단절될 경우 문맥에 맞게 재구성할 수 있다. 이때 의미를 왜곡하거나 내용을 과장·추가해서는 안 된다.
    - 특히 첫 번째 문장은 원문과 구분되는 새로운 요약형 문장으로 작성하되, 제공된 기사에서 명시된 사실 중 핵심 인물·조치·배경 정보를 포함한 요약 문장으로 구성한다. (단, 기사 외 정보를 추가하거나 의미를 추측·왜곡하지 않는다.)
    - 주요 흐름과 논란의 쟁점을 왜곡하지 않는다.
    - 인용문은 단어 하나도 변경하지 않는다.
    - 인용문을 제외한 모든 문장에서 격식체 종결어미(습니다, 합니다, 입니다 등)를 반드시 평서형(했다, 한다, 이다 등)으로 작성한다.
        - 격식체 표현이 남아 있지 않도록 주의하고, 맞춤법에 맞게 자연스럽게 바꾸어야 하며, 출력 전 반드시 검수한다.
        - 다음은 자주 사용되는 예시이며, 문맥에 따라 적용해야 한다:
        - "입니다" → "이다" 또는 "다" 
        - "했습니다" → "했다"
        - "합니다" → "한다"
        - "없습니다" → "없다"
        - "되었다" 및 "되었습니다"→ "됐다"
    - 모든 문장은 국립국어원 맞춤법 기준을 준수해야 하며, 띄어쓰기나 어색한 표현이 없도록 주의한다.
    - 볼드체(굵은 글씨,) 사용 금지.  
    - 본문은 반드시 세 문장마다 줄바꿈한다. (입력 내용이 짧아도 이 규칙은 동일하게 적용하며, 줄바꿈은 시각적 구분을 위한 것이다.)

    2. 제목 생성
    - 작성된 본문을 바탕으로 제목을 창의적으로 작성한다.
    - 제공된 기사 제목의 핵심 내용을 참고하되, 본문에서 드러난 핵심 주제를 우선 반영한다.
    - 입력된 키워드({stock_name})를 최대한 앞쪽에 배치하고, 관련성이 적어도 자연스럽게 포함되도록 작성한다.
    - 제공된 제목을 그대로 사용하는 것은 금지한다.
    - 궁금증을 유발하는 표현 금지 (예: '?', '왜', '어떻게', '무엇이' 등 사용 금지)
    - 부정적인 표현을 긍정적인 방향으로 조정한다.

    3. 제목 및 본문 검토 
    - 맞춤법 및 띄어쓰기 준수 여부를 확인하고, 문장이 자연스럽도록 수정
    - 제목과 본문에서 금지된 표현(볼드체(**, 굵은글씨), 말줄임표(...), 마침표(.), 쌍따옴표(" "), 콜론(:), 마크다운 기호(*, #, &), 감탄문, 질문형 문장, 기자 메일 주소 및 기자명 표기) 사용 여부 확인 및 수정
    - 제공된 정보 외 추측·허구·외부 자료 추가 여부 검토 후 수정
    - 인용문 외에서 격식체 종결어미 사용여부 확인 후, 평서형 종결어미로 변경한다. (예: "입니다" → "이다" or "다", "했습니다" → "했다", "합니다" → "한다", "되었다" 및 "되었습니다"→ "됐다")

    4. 출력규칙
    - 제목과 본문을 출력하세요.  
    - 생성된 텍스트 외 다른 문장은 출력하지 않는다  
    - 첫 줄: 제목  
    - 두 번째 줄부터: 본문
    - 저희는 첫 줄을 제목으로 인식하고, 두 번째 줄부터 본문으로 인식합니다.
    """

    # Gemini에 보낼 사용자 메시지 (가상의 기존 기사 본문)
    # 실제 사용할 때는 해당 주식에 대한 최신 뉴스나 정보를 요약하여 넣는 것이 좋습니다.
    # 여기서는 예시를 위해 단순화합니다.
    user_message = f"""
    다음은 주식 종목 {stock_name}에 대한 기사 본문 내용이다:
    {existing_article_content}
    """

    model = genai.GenerativeModel(model_name='gemini-2.5-flash', system_instruction=system_prompt)
    
    try:
        response = model.generate_content(user_message)
        # 생성된 텍스트를 바로 반환합니다. 출력 규칙에 따라 제목과 본문이 분리되어 있을 것입니다.
        return response.text
    except Exception as e:
        print(f"Gemini API 호출 중 오류 발생: {e}")
        return None

# 예시 사용법 (main.py에서 이 함수를 호출)
if __name__ == '__main__':
    # stock.py 임포트 (stock.py 파일이 같은 디렉토리에 있다고 가정)
    import stock

    while True:
        keyword = input("\n주식 코드 또는 회사명을 입력하세요 (0: 종료): ").strip()

        if keyword == "0":
            print("프로그램을 종료한다.")
            break
        
        if not keyword:
            print("키워드를 입력해라.")
            continue

        print(f"\n🔍 처리 중: {keyword}")
        
        stock_code = keyword if (keyword.isdigit() and len(keyword) == 6) else stock.get_stock_info_from_search(keyword)
        
        if not stock_code:
            print("주식 코드를 찾을 수 없다. 정확한 주식 코드(6자리)를 입력해라.")
            continue
        
        print(f"대상 주식 코드: {stock_code}")
        
        # 가상의 기존 기사 본문 (실제 뉴스 데이터를 연동할 경우 이 부분을 수정해야 합니다.)
        # 여기서는 종목명과 코드만으로 가상의 내용을 생성합니다.
        # 더 나은 기사를 위해서는 해당 종목의 최근 실적, 이슈, 시장 동향 등의 실제 데이터가 필요합니다.
        dummy_article_content = f"{keyword}({stock_code})는 최근 인공지능 관련 기술 개발에 박차를 가하고 있다. 회사는 지난 분기 실적 발표에서 예상치를 뛰어넘는 매출을 기록했으며, 이는 신규 AI 칩 출시와 글로벌 파트너십 확대에 따른 결과이다. 시장 전문가들은 {keyword}의 기술력이 앞으로도 꾸준히 성장할 것으로 전망하며, 목표 주가를 상향 조정하는 보고서를 발표했다. 하지만 일각에서는 글로벌 경제 불확실성과 반도체 시장의 공급 과잉 가능성을 우려하는 목소리도 나온다. 이와 관련하여 회사는 향후 시장 변동성에 대비한 전략을 마련 중이라고 밝혔다."
        
        print("\n--- 뉴스 기사 생성 중 ---")
        generated_news = generate_stock_news(keyword, dummy_article_content)

        if generated_news:
            print(generated_news) # 제목과 본문이 포함된 결과 출력
        else:
            print("뉴스 기사 생성에 실패했습니다.")

        print("\n--- 주식 차트 캡처 중 ---")
        image_path = stock.capture_wrap_company_area(stock_code)

        if image_path:
            print("이미지를 클립보드에 복사 중입니다.")
            if stock.copy_image_to_clipboard(image_path):
                print("이미지가 클립보드에 복사되었습니다.")
                print("원하는 곳에 Ctrl+V로 붙여넣으세요.")
                stock.open_image(image_path)
            else:
                print("클립보드 복사 실패. 이미지 파일은 저장되었습니다.")
                print(f"저장된 파일: {image_path}")
                stock.open_image(image_path)
        else:
            print("이미지 캡처 또는 저장에 실패했습니다.")
        
        print("\n" + "-" * 50)
        print("다음 작업을 계속하거나 0을 입력하여 종료하세요.")