import google.generativeai as genai
import os
from PIL import Image
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))


def generate_stock_news(stock_name: str, image_path: str):
    """
    텍스트와 주식 차트 이미지를 분석하여 뉴스 기사를 생성합니다.
    
    """
    system_prompt = f"""
    [시스템 메세지]
사용자가 키워드, 텍스트 정보, 그리고 차트 이미지를 제공합니다.
제공된 모든 정보를 종합적으로 분석하여 기사 문체로 작성합니다.

아래 [기사 생성 프로세스]를 단계별로 실행하고, 최종적으로 **[출력 형식]에 맞게 기사를 출력합니다.**

[기사 생성 프로세스(단계별 실행)]

1. 제공된 정보 인식
 1) 사용자가 입력한 키워드, 텍스트 데이터, 차트 이미지를 수집합니다.

2. 텍스트 정보 분석
 1) 제공된 텍스트(최신 뉴스 요약 등)의 핵심 내용을 파악합니다.
 2) 날짜가 포함된 데이터는 시점을 분석하여 문장에 반영합니다.

3. 차트 이미지 분석 (이미지 제공 시)
 - 제공된 차트 이미지에서 시각적 정보를 분석합니다.
 - **데이터의 시각적 패턴(예: 특정 구간의 급격한 변화, 주기성)과 핵심 지표(예: 최고/최저점, 평균선, 변동폭)를 파악합니다.**
 - 차트에서 보이는 추세(상승, 하락, 횡보)를 분석합니다.

4. 본문 작성 (종합 분석 기반)
 - **텍스트 정보와 이미지 분석 결과를 종합하여** 객관적인 시황 정보를 전달하는 기사 형식으로 작성합니다.
 - **뉴스 문체 (~이다, ~했다 체 사용)**를 사용합니다.
 - **핵심 요약으로 시작하여 상세 내용으로 전개합니다.** 기사의 주제(키워드)와 기준 시점, 가장 중요한 핵심 수치와 그 변화를 첫 문단에 제시합니다. ** 
 - **이후, 최고/최저치나 거래량, 강수량 같은 구체적인 데이터를 활용하여 시간의 흐름이나 논리적 순서에 따라 자연스럽게 서술합니다.**
 - **분석 내용 통합**: 텍스트 및 시각 자료에서 파악한 분석 결과를 본문에 자연스럽게 통합하여, 현상을 설명하는 객관적인 근거로 사용합니다.
 - **마무리**: 전일 종가나 시장 상황과 연관 지어 마무리합니다.
 - **객관성 원칙 준수**: 데이터로 증명할 수 없는 모든 추측, 예측, 제안 표현을 금지합니다. (예: '~일 것으로 보인다', '~할 전망이다', '~에 주목할 필요가 있다' 등의 표현은 절대 사용하지 않습니다.)
 - **가독성 원칙 준수**: 전문 용어를 사용할 경우, 독자의 이해를 돕기 위해 필요한 경우 간결한 부연 설명을 덧붙입니다.
 - 입력된 키워드(종목명)를 3~5회 자연스럽게 포함합니다.
 - 볼드체, 기울임체 등 서식은 사용하지 않습니다.

5. 제목 작성 방식
- **생성된 본문을 기반으로 추천 제목 3개 제공**
- 입력된 키워드를 최대한 제목 앞쪽에 배치
- **35자 내외, 간결한 헤드라인 형식으로 작성**
- **완전한 문장형이 아닌 핵심 키워드 중심으로 구성**
- **궁금증을 유발할 수 있도록 작성하되, 특수문자 없이 표현**
- **말줄임표"..." 사용금지, 말줄임표 "⋯", 마침표(.) 사용 금지, 특수문자 (?, !, " 등) 사용 금지**

6. 출력 형식 적용 (최종 제공)
기사 생성 후, 아래 출력 형식에 맞춰 제공

[출력 형식]
- 제목 (3개 제공)
- 해시태그 (10개 내외)
    """

    user_prompt = f"""
    다음은 주식 종목 '{stock_name}'에 대한 최신 뉴스 정보 요약과 차트 이미지이다. 이 두 가지 정보를 종합적으로 분석하여 기사를 작성하라.

    --- 제공된 텍스트 정보 ---
    
    --- 정보 끝 ---
    """

    user_message = f"아래 이미지는 '{stock_name}' 관련 주식 차트 또는 시세 정보입니다. 이미지를 분석해 기사 형식으로 작성하세요."

    model = genai.GenerativeModel(
        model_name='gemini-2.0-flash',
        system_instruction=system_prompt
    )

    try:
        img = Image.open(image_path)
        response = model.generate_content([
            user_message,
            img
        ])
        return response.text
    except Exception as e:
        print(f"Gemini Vision API 호출 중 오류 발생: {e}")
        return None


# 예시 사용법 (main.py에서 이 함수를 호출)
if __name__ == '__main__':
    # stock.py 임포트 (stock.py 파일이 같은 디렉토리에 있다고 가정)
    import stock

    while True:
        keyword = input("\n주식 코드 또는 회사명을 입력하세요 (0: 종료): ").strip()

        if keyword == "0":
            print("프로그램을 종료합니다.")
            break
        
        if not keyword:
            print("키워드를 입력해주세요.")
            continue

        print(f"\n🔍 처리 중: {keyword}")
        
        stock_code = keyword if (keyword.isdigit() and len(keyword) == 6) else stock.get_stock_info_from_search(keyword)
        
        if not stock_code:
            print("주식 코드를 찾을 수 없습니다. 정확한 주식 코드(6자리)를 입력해주세요.")
            continue
        
        print(f"대상 주식 코드: {stock_code}")
        
        # 가상의 기존 기사 본문 (실제 뉴스 데이터를 연동할 경우 이 부분을 수정해야 합니다.)
        # 여기서는 종목명과 코드만으로 가상의 내용을 생성합니다.
        # 더 나은 기사를 위해서는 해당 종목의 최근 실적, 이슈, 시장 동향 등의 실제 데이터가 필요합니다.
        # dummy_article_content = f"{keyword}({stock_code})는 최근 인공지능 관련 기술 개발에 박차를 가하고 있다. 회사는 지난 분기 실적 발표에서 예상치를 뛰어넘는 매출을 기록했으며, 이는 신규 AI 칩 출시와 글로벌 파트너십 확대에 따른 결과이다. 시장 전문가들은 {keyword}의 기술력이 앞으로도 꾸준히 성장할 것으로 전망하며, 목표 주가를 상향 조정하는 보고서를 발표했다. 하지만 일각에서는 글로벌 경제 불확실성과 반도체 시장의 공급 과잉 가능성을 우려하는 목소리도 나온다. 이와 관련하여 회사는 향후 시장 변동성에 대비한 전략을 마련 중이라고 밝혔다."
        
        print("\n--- 뉴스 기사 생성 중 ---")
        # image_path = stock.capture_wrap_company_area(stock_code) # 이 부분은 이미지 캡처 로직이 변경되었으므로 제거
        # if image_path:
        #     print("이미지를 클립보드에 복사 중입니다.")
        #     if stock.copy_image_to_clipboard(image_path):
        #         print("이미지가 클립보드에 복사되었습니다.")
        #         print("원하는 곳에 Ctrl+V로 붙여넣으세요.")
        #         stock.open_image(image_path)
        #     else:
        #         print("클립보드 복사 실패. 이미지 파일은 저장되었습니다.")
        #         print(f"저장된 파일: {image_path}")
        #         stock.open_image(image_path)
        # else:
        #     print("이미지 캡처 또는 저장에 실패했습니다.")

        # 이미지 캡처 로직을 직접 호출하여 이미지 경로를 얻음
        image_path = stock.capture_wrap_company_area(stock_code)
        if image_path:
            print(f"이미지 캡처 성공: {image_path}")
            generated_news = generate_stock_news(keyword, image_path)

            if generated_news:
                print(generated_news) # 제목과 본문이 포함된 결과 출력
            else:
                print("뉴스 기사 생성에 실패했습니다.")
        else:
            print("이미지 캡처에 실패했습니다. 이미지 파일을 확인해주세요.")

        print("\n--- 주식 차트 캡처 중 ---")
        # image_path = stock.capture_wrap_company_area(stock_code) # 이 부분은 이미지 캡처 로직이 변경되었으므로 제거
        # if image_path:
        #     print("이미지를 클립보드에 복사 중입니다.")
        #     if stock.copy_image_to_clipboard(image_path):
        #         print("이미지가 클립보드에 복사되었습니다.")
        #         print("원하는 곳에 Ctrl+V로 붙여넣으세요.")
        #         stock.open_image(image_path)
        #     else:
        #         print("클립보드 복사 실패. 이미지 파일은 저장되었습니다.")
        #         print(f"저장된 파일: {image_path}")
        #         stock.open_image(image_path)
        # else:
        #     print("이미지 캡처 또는 저장에 실패했습니다.")

        # 이미지 캡처 로직을 직접 호출하여 이미지 경로를 얻음
        image_path = stock.capture_wrap_company_area(stock_code)
        if image_path:
            print(f"이미지 캡처 성공: {image_path}")
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