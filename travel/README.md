# 여행 & 날씨 기사 생성기

## 1. 프로젝트 개요

이 프로젝트는 전국 여행지 데이터를 수집하고, 수집된 데이터와 실시간 날씨 정보를 바탕으로 AI를 통해 여행 및 날씨 관련 기사를 생성하는 데스크톱 애플리케이션입니다.

프로젝트는 크게 두 가지 주요 부분으로 구성됩니다.
1.  데이터 크롤러: 전국의 법정동 정보를 기반으로 네이버 지도의 장소 정보를 수집하여 데이터베이스를 구축합니다. (`crawl_main.py`)
2.  GUI 애플리케이션: 구축된 데이터를 활용하여 사용자가 원하는 조건의 여행지를 필터링하고, AI를 통해 기사를 생성하는 PyQt5 기반 프로그램입니다. (`article_generator_app.py`)

## 2. 주요 기능

### 데이터 수집
- 전국 법정동 CSV 파일을 기반으로 지역별 검색어 자동 생성
- Selenium을 이용해 네이버 지도에서 장소 정보(주소, 카테고리, 리뷰 수, 소개 등) 크롤링
- 수집된 데이터를 SQLite 데이터베이스에 저장 및 관리 (중복 방지 포함)
- 크롤링 진행 상황을 JSON 파일로 관리하여 중단 시 이어하기 기능 제공

### 기사 생성 애플리케이션
- 여행지 검색 및 필터링
  - 다단계 지역 필터 (도/시/군/구/동) 및 자동완성 검색 기능
  - 장소 카테고리 및 방문자 리뷰 키워드 기반의 상세 필터링
  - 리뷰 수, 이름, 주소 등 다양한 기준으로 결과 정렬
- AI 기사 생성
  - Google Gemini API를 활용한 자연스러운 여행 기사 자동 생성
  - 기사 생성 전, 선택한 장소의 최신 정보를 실시간으로 다시 크롤링하여 반영
  - 기사 내용에 현재 날씨 정보를 선택적으로 포함하는 기능
- 날씨 정보 및 기사
  - 기상청 API와 연동하여 전국 모든 지역의 상세 날씨 및 기상특보 조회
  - 조회된 날씨 데이터를 바탕으로 AI 날씨 기사 생성

## 3. 기술 스택

- GUI: PyQt5
- AI: Google Gemini
- 웹 크롤링: Selenium
- 데이터베이스: SQLite
- API 연동: 카카오 API, 기상청 공공데이터 API

## 4. 설치 및 설정

### 사전 요구사항
- Python 3.8 이상
- Google Chrome 브라우저

### 설치 과정
1.  가상환경 생성 (권장)
    ```bash
    python -m venv venv
    # Windows
    venv\Scripts\activate
    # macOS/Linux
    source venv/bin/activate
    ```

2.  의존성 설치
    ```bash
    pip install -r requirements.txt
    ```

### 환경변수 설정 (`.env`)
프로젝트 루트 폴더에 `.env` 파일을 생성하고 아래의 API 키를 입력합니다. 각 API 키는 해당 서비스의 개발자 센터에서 발급받을 수 있습니다.

```env
# Google Gemini AI API (기사 생성에 필수)
GOOGLE_API_KEY="발급받은 Google API 키"

# 카카오 API (날씨 조회 기능에 필요)
KAKAO_API_KEY="발급받은 Kakao API 키"

# 기상청 API (날씨 조회 기능에 필요)
KMA_API_KEY="발급받은 기상청 API 키"
```

## 5. 사용 방법

### 1단계: 데이터 수집 (최초 1회 또는 데이터 업데이트 시 실행)
애플리케이션을 사용하기 전에 여행지 데이터베이스를 구축해야 합니다.

1.  `crw_data` 폴더에 `전국 법정동.csv` 파일이 있는지 확인합니다.
2.  아래 명령어를 실행하여 데이터 수집을 시작합니다.
    ```bash
    python crawl_main.py
    ```
    - 크롤링은 시간이 오래 걸릴 수 있으며, 중간에 중단해도 `crawling_progress.json` 파일에 진행 상황이 저장되어 자동으로 이어집니다.
    - 완료되면 `crw_data` 폴더에 `naver_travel_places.db` 파일이 생성됩니다.

### 2단계: 기사 생성기 실행
데이터베이스 구축이 완료된 후, 메인 애플리케이션을 실행합니다.

```bash
python article_generator_app.py
```

## 6. 프로젝트 구조

- 메인 실행 및 데이터 수집
  - `article_generator_app.py`: PyQt5 애플리케이션의 메인 실행 파일. UI를 초기화하고 '여행' 및 '날씨' 탭을 생성하며, 데이터베이스, 챗봇, API 등 모든 구성 요소를 연결합니다.
  - `crawl_main.py`: 대규모 데이터 수집을 위한 메인 크롤러. '전국법정동.csv' 파일을 기반으로 검색어를 생성하고, Selenium을 이용해 네이버 지도에서 장소 정보를 수집하여 SQLite DB에 저장합니다. 크롤링 중단 시 이어하기 기능이 포함되어 있습니다.

- 핵심 기능: 여행 기사
  - `travel_tab.py`: '여행지 검색' 탭의 UI 이벤트를 처리하는 컨트롤러. 필터 변경, 검색, 기사 생성 등 사용자 요청을 받아 `travel_logic.py`에 전달하고 UI를 업데이트합니다.
  - `travel_logic.py`: 여행 관련 핵심 비즈니스 로직. UI와 독립적으로 동작하며, 복잡한 조건(지역, 카테고리, 리뷰)에 따른 장소 필터링 및 검색을 수행합니다. 또한, 실시간 크롤링 및 기사 생성을 백그라운드 스레드로 처리하여 UI 응답성을 유지합니다.
  - `chatbot_app.py`: Google Gemini API를 사용하여 여행 기사를 생성하는 모듈. 사용자 검색어, 선택된 장소 목록, 날씨 정보를 조합하여 상세한 프롬프트를 구성하고 AI를 호출합니다.
  - `prompts.py`: AI 여행 기사 생성을 위한 프롬프트 템플릿. AI의 역할, 기사 스타일, 준수 규칙 등을 상세히 정의하여 일관된 품질의 결과물을 생성하도록 유도합니다.
  - `realtime_crawler.py`: 기사 생성 직전, 특정 장소의 최신 '소개' 정보만 실시간으로 다시 수집하는 경량 크롤러. 정보의 최신성을 보장하며, 크롤링 차단 방지 기술이 적용되어 있습니다.

- 핵심 기능: 날씨 기사
  - `weather_tab.py`: '상세 날씨 조회' 탭의 UI를 제어하는 컨트롤러. 지역별 날씨 검색, 전국 기상특보 조회를 처리하고, `weather_api.py`와 `weather_ai_generator.py`를 호출하여 결과를 화면에 표시합니다.
  - `weather_api.py`: 날씨 데이터를 수집하는 모듈. 카카오 API로 입력된 지역명을 좌표로 변환한 뒤, 기상청 격자 좌표로 다시 변환하여 기상청 API를 호출합니다. 초단기실황과 단기예보 데이터를 조합하여 종합적인 날씨 정보를 생성합니다.
  - `weather_warning.py`: 기상청의 전국 기상특보를 조회하고 파싱하는 전용 모듈. 복잡한 단일 텍스트로 제공되는 전국 특보를 개별 특보(종류, 해당 지역) 목록으로 구조화하는 핵심 로직을 포함합니다.
  - `weather_ai_generator.py`: 날씨 데이터를 기반으로 AI 날씨 기사를 생성합니다. 일반 날씨 정보 또는 기상특보 상황에 맞춰 각각 다른 스타일의 기사를 생성하며, 동일한 특보에 대한 중복 기사 생성을 방지하는 순환 로직을 갖추고 있습니다.
  - `weather_article_prompts.py`: AI 날씨 기사 생성에 특화된 프롬프트 템플릿 모음. 일반 날씨와 기상특보 상황에 맞는 별도의 프롬프트를 제공하여, 각 시나리오에 최적화된 기사를 생성하도록 합니다.

- UI 및 공용 컴포넌트
  - `travel_ui.py`: '여행지 검색' 탭의 UI 레이아웃을 정의하는 View 역할의 파일. 위젯의 배치와 형태 등 순수 시각적 구조만 담당하며, 기능 로직은 포함하지 않습니다.
  - `ui_components.py`: 앱 전반에서 재사용되는 커스텀 PyQt5 위젯 모음. 다중 선택이 가능한 콤보박스(`CheckableComboBox`), 숫자 데이터의 올바른 정렬을 지원하는 테이블 아이템(`IntItem`) 등이 포함되어 있습니다.

- 유틸리티 및 설정
  - `db_manager.py`: SQLite 데이터베이스와의 모든 상호작용을 관리하는 데이터 접근 계층. DB 초기화, 데이터 저장 및 계층적 지역 검색 등 복잡한 쿼리를 수행하는 함수들을 제공합니다.
  - `category_utils.py`: 네이버 지도의 다양한 장소 카테고리를 표준화된 UI용 카테고리로 통합하는 유틸리티. 키워드 매칭을 통해 필터링 효율을 높입니다.
  - `visitor_reviews_utils.py`: '주차하기 편해요'와 같은 방문자 리뷰 키워드를 '접근성/편의성' 등 표준화된 태그로 변환하여, 리뷰 기반 필터링을 가능하게 합니다.
  - `config.py`: API 키, URL 등 프로젝트의 전역 설정을 관리합니다. `.env` 파일에서 민감한 정보를 안전하게 로드하여 코드와 분리합니다.
  - `data.py`: 대한민국 행정구역 목록이나 지역명 축약어 등, 코드 내에서 사용되는 정적 데이터를 보관합니다.

- 기타 스크립트
  - `crw_data/brand_remove.py`: 데이터 정제용 보조 스크립트. 수집된 DB에서 '스타벅스'와 같이 여행지에 해당하지 않는 프랜차이즈 브랜드 데이터를 삭제하는 역할을 합니다.
 
## 7. 워크플로우
## 시스템 아키텍처

```text
┌─────────────────────────────────────────────────────────────┐
│                   메인 애플리케이션                          │
│              (article_generator_app.py)                     │
└─────────────────┬───────────────────────────────────────────┘
                  │
        ┌─────────┴─────────┐
        │                   │
    ┌───▼────┐        ┌────▼────┐
    │여행지 탭│        │ 날씨 탭 │
    │        │        │        │
    └────────┘        └────────┘
```

## 데이터 플로우 아키텍처

### 1. 데이터 수집 단계 (크롤링)

```text
[개발자] crawl_main.py 실행
        │
        ▼
(초기화) crawl_main.py: load_search_queries() - 전국법정동.csv 로드
  - "강원도 강릉시 교동 가볼만한곳" 형태 검색어 생성
  - crawl_main.py: load_progress() - JSON으로 중단점 관리
        │
        ▼
(크롤링) crawl_main.py: crawl_area() - Selenium + 네이버 지도
  ├─ driver.get("https://map.naver.com/p?c=15.00,0,0,0,dh")
  ├─ crawl_main.py: switch_to_frame_safely(driver, "searchIframe")
  ├─ crawl_main.py: robust_scroll_in_iframe() - 장소 목록 스크롤
  └─ crawl_main.py: crawl_place_details()
      ├─ crawl_main.py: switch_to_frame_safely(driver, "entryIframe")
      ├─ 주소, 카테고리, 리뷰수, 키워드, 소개글 추출
      └─ db_manager.py: check_place_exists() - 중복 체크
        │
        ▼
(저장) db_manager.py: save_places_to_db()
  - SQLite DB에 장소 데이터 축적
  - crawl_main.py: save_progress() - 진행상황 JSON 저장
```

### 2. 여행지 검색 & 기사 생성 워크플로우

```text
[사용자 입력] 지역/카테고리/리뷰 필터 선택
        │
        ▼
(검색) travel_tab.py: search_places()
  └─ travel_logic.py: search_places(filters)
      ├─ db_manager.py: search_places_advanced_with_dong()
      ├─ travel_logic.py: _place_matches_filters()
      │   ├─ category_utils.py: normalize_category_for_ui()
      │   └─ visitor_reviews_utils.py: normalize_review_for_ui()
      └─ travel_logic.py: _apply_review_count_filter()
        │
        ▼
travel_tab.py: _populate_table() - 검색 결과 테이블 표시
        │
        ▼
[사용자 선택] 체크박스로 장소 선택 후 generate_article()
        │
        ▼
(실시간 크롤링) travel_logic.py: start_article_generation()
  └─ travel_logic.py: CrawlerWorker 스레드
      └─ realtime_crawler.py: crawl_introduction()
          ├─ realtime_crawler.py: setup_driver() - Selenium 헤드리스 크롬
          ├─ realtime_crawler.py: warmup() - 네이버 지도 홈 방문
          ├─ driver.get(f"https://map.naver.com/p/entry/place/{place_id}")
          ├─ switch_to.frame("entryIframe")
          ├─ 정보탭 클릭 + 펼쳐보기
          └─ div.AX_W3 텍스트 추출
        │
        ▼
(날씨 정보) 옵션 선택시 weather_api.py: get_weather_data()
        │
        ▼
(AI 기사 생성) travel_logic.py: ArticleWorker 스레드
  └─ chatbot_app.py: TravelChatbot.recommend_travel_article()
      ├─ prompts.py: TRAVEL_ARTICLE_PROMPT.format()
      ├─ genai.GenerativeModel('models/gemini-2.5-flash')
      ├─ chatbot_app.py: _normalize_spaces() - 공백 정리
      └─ chatbot_app.py: _fix_titles() - 제목 형식 통일
        │
        ▼
travel_tab.py: result_text_edit.setText() - 기사 표시
```

### 3. 날씨 정보 조회 & 기사 생성 워크플로우

```text
[사용자 입력] 지역명 입력
        │
        ▼
(지역 정규화) weather_tab.py: search_weather()
  └─ weather_tab.py: WeatherThread.run()
      └─ weather_api.py: get_weather_data()
          ├─ weather_api.py: find_region() - SIMPLE_REGION_MAPPING 활용
          ├─ weather_api.py: get_coordinates_from_address() - 카카오 API
          │   └─ requests.get(KAKAO_COORD_URL)
          ├─ weather_api.py: convert_to_grid() - 위경도→기상청 격자
          └─ weather_api.py: get_weather_with_fallback()
              ├─ weather_api.py: try_current_weather() - 초단기실황
              └─ weather_api.py: try_forecast_weather() - 단기예보
        │
        ▼
weather_tab.py: _on_weather_ok() - 날씨 정보 표시
        │
        ▼
[사용자 클릭] 기상특보 조회
        │
        ▼
(기상특보 조회) weather_tab.py: search_warnings()
  └─ weather_tab.py: WeatherWarningThread.run()
      └─ weather_warning.py: get_weather_warnings()
          ├─ requests.get(API_URL) - 기상청 특보 API
          ├─ weather_warning.py: _parse_xml() - XML 응답 파싱
          └─ weather_warning.py: _restructure_warnings()
              └─ weather_warning.py: _parse_t6_string() - 특보 문자열 파싱
        │
        ▼
weather_tab.py: _on_warning_ok() - 특보 현황 표시
        │
        ▼
[사용자 클릭] AI 기사 생성
        │
        ▼
(AI 기사 생성) weather_tab.py: generate_weather_article()
  └─ weather_tab.py: ArticleGenerationThread.run()
      └─ weather_ai_generator.py: WeatherArticleGenerator
          ├─ weather_ai_generator.py: generate_weather_article() 또는 generate_warning_article()
          ├─ weather_article_prompts.py: GeminiWeatherPrompts 사용
          ├─ weather_ai_generator.py: _call_gemini_api() - requests.post(gemini_url)
          └─ weather_ai_generator.py: _parse_response() - 제목/본문/해시태그 분리
        │
        ▼
weather_tab.py: article_display.setText() - 기사 표시
```

## 모듈 의존성

```
article_generator_app.py (메인)
├── travel_tab.py (여행 탭)
│   ├── travel_ui.py (UI 컴포넌트)
│   ├── travel_logic.py (여행 로직)
│   ├── db_manager.py (DB 연결)
│   ├── realtime_crawler.py (실시간 크롤링)
│   ├── category_utils.py (카테고리 정규화)
│   ├── visitor_reviews_utils.py (리뷰 정규화)
│   └── chatbot_app.py (AI 기사 생성)
├── weather_tab.py (날씨 탭)
│   ├── weather_api.py (날씨 데이터)
│   ├── weather_warning.py (기상특보)
│   ├── weather_ai_generator.py (AI 기사)
│   └── weather_article_prompts.py (프롬프트)
└── 공통 유틸리티
    ├── ui_components.py (커스텀 위젯)
    └── config.py (설정 관리)
```

## 8. 개발자

- 하승주, 홍석원
