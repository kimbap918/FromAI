
# 재구성 기사/정보성 기사/토스 기사 파일 구조 및 workflow 설명

>PyQt5 기반의 **뉴스 재구성·정보성 기사(주식/토스)** 통합 도구입니다. LLM 처리는 **Gemini-2.5-Flash** 모델을 사용하며, 모듈은 Components(UI) · Services(비즈니스 로직 및 AI) · Utils(유틸)로 분리되어 있습니다.


## 목차

- [주요 기능](#주요-기능)
  - [1. 뉴스 재구성](#1-뉴스-재구성)
  - [2. 정보성 기사(주식/토스 기사 생성)](#2-정보성-기사주식토스-기사-생성)
  - [3. 토스 데이터 호출](#3-토스-데이터-호출)
  - [4. 공통 유틸](#4-공통-유틸)

- [아키텍처 구조](#아키텍처-구조)
  - [1. Components (UI 컴포넌트)](#1-components-ui-컴포넌트)
  - [2. Services (비즈니스-로직)](#2-services-비즈니스-로직)
  - [3. Utils (유틸리티)](#3-utils-유틸리티)
  - [4. Assets (리소스)](#4-assets-리소스)

- [주요 흐름](#주요-흐름)
  - [1. 뉴스 재구성](#1-뉴스-재구성-1)
  - [2. 정보성 기사](#2-정보성-기사)
  - [3. 토스 기사](#3-토스-기사)

- [흐름도별 디테일 설명](#흐름도별-디테일-설명)
  - [1. 뉴스 재구성 (NewsTab)](#1-뉴스-재구성-newstab)
  - [2. 정보성 기사 (StockTab)](#2-정보성-기사-stocktab)
  - [3. 토스 기사 (TossTab)](#3-토스-기사-tosstab)
  - [기타 - 환율 (HwanTab)](#기타--환율-hwantab)

<br>

## 주요 기능
### 1. 뉴스 재구성
- 기사 URL + 키워드 입력 → 기사 크롤링 후 본문 추출
- LLM(`news_LLM.py`)을 통한 기사 재구성 ([제목]/[해시태그]/[본문])
- `check_LLM.py`로 원문 vs 생성문 비교 → 오류/사실관계 검증
- PyQt5 UI에서 좌측(원문), 우측(재구성 결과) 동시 표시 및 **복사 버튼 제공**
- 날짜/시제 자동 변환 및 **날짜 강조(하이라이트)** 기능 포함
    

### 2. 정보성 기사(주식/토스 기사 생성)
- **국내**: Naver Finance 크롤링, 차트 캡처(`domestic_utils.py`)
- **해외**: Naver Search 차트 캡처(`foreign_utils.py`)
- 차트 이미지 + 투자정보 + 신규상장 여부(`data_manager.py`) → 기사 생성(`info_LLM.py`)
- Toss 인기 종목도(`toss_service.py`) 연동하여 기사 자동 생성
    

### 3. 토스 데이터 호출
- 토스증권 인기 종목 API 호출(`toss_service.py`)
- 등락률·시가총액·국내/해외 필터링
- PyQt5 UI(`toss_tab.py`)에서 조회 → 기사 자동 생성/저장 가능

### 4. 공통 유틸
- `common_utils.py`: 시제 변환, 파일 저장, 차트 캡처, 주식 프롬프트 공통 유틸 
- `driver_utils.py`: Selenium 초기화 / 크롤링 시 네이버 파워 링크 광고 JavaScript 이용한 제거
- `clipboard_utils.py`: 이미지 클립보드 복사 (Windows)
- `domestic_list.py`: 국내 주식 정보 추출 / 이미지 캡쳐 / 거래 정지 종목 구분
- `data_manager.py`: 신규상장 종목 캐시 관리

<br>


## 아키텍처 구조

```
FromAI/
├── gui_loader.py          # 메인 실행 (PyQt5 GUI)
├── requirements.txt       # 의존성 패키지
├── .env                   # API 키 (GOOGLE_API_KEY 등)
│
├── news/src/
│   ├── components/        # UI 레이어
│   │   ├── news_tab_test.py   # 뉴스 기사 크롤링 + 재구성 UI
│   │   ├── stock_tab.py       # 주식 차트 + 기사생성 UI
│   │   ├── toss_tab.py        # 토스 종목 조회 + 기사생성 UI
│   │   ├── hwan_tab.py        # 환율 조회 및 차트 캡처(구현하지 않아도 됨)
│   │   └── settings_dialog.py # API 키 및 환경 설정 다이얼로그
│   │
│   ├── services/          # 비즈니스 로직 & AI
│   │   ├── news_LLM.py        # 뉴스 기사 생성(재구성 기사)
│   │   ├── check_LLM.py       # 생성 기사 검증(재구성 기사)
│   │   ├── info_LLM.py        # 정보성 기사 생성(정보성 기사)
│   │   └── toss_service.py    # Toss API 연동(정보성 기사)
│   │
│   └── utils/             # 공통 유틸리티
│       ├── article_utils.py   # 기사 본문 추출(재구성 기사)
│       ├── domestic_utils.py  # 국내 주식 크롤링(정보성 기사)
│       ├── foreign_utils.py   # 해외 주식 크롤링(정보성 기사)
│       ├── data_manager.py    # 신규상장 캐시 관리(정보성 기사)
│       ├── common_utils.py    # 시제 처리/저장 유틸(정보성 기사)
│       ├── driver_utils.py    # Selenium 초기화/광고 제거
│       ├── clipboard_utils.py # 클립보드 복사
│       ├── domestic_list.py   # 신규상장 스크레이핑(정보성 기사)
│       └── ...

```

<br>

### 1. Components (UI 컴포넌트)

PyQt5를 기반으로 한 GUI 컴포넌트들이 위치합니다. 각 탭별로 분리되어 있으며, 사용자 인터페이스와 관련된 로직을 담당합니다.

| 파일명                | 설명                      |
| ------------------ | ----------------------- |
| hwan_tab.py        | 환율 정보 조회 및 차트 캡처 기능 UI  |
| news_tab.py        | 뉴스 기사 추출 및 재구성 기능  UI   |
| stock_tab.py       | 주식 정보 조회 및 차트 캡처 기능  UI |
| toss_tab.py        | 토스 종목 조회 및 기사 생성 기능  UI |
| settings_dialog.py | API 키 및 환경 설정 다이얼로그     |

<br>

### 2. Services (비즈니스 로직)

주요 비즈니스 로직이 위치하며, API 호출, 데이터 처리, AI 모델 연동 등을 담당합니다.

| 파일명             | 설명                  |
| --------------- | ------------------- |
| check_LLM.py    | 생성된 기사의 사실 관계 검증 AI |
| info_LLM.py     | 정보성 기사(주식) 생성 AI    |
| news_LLM.py     | 뉴스 재구성 AI           |
| toss_service.py | 토스 API 연동 서비스       |

<br>

### 3. Utils (유틸리티)

프로젝트 전반에서 재사용되는 유틸리티 함수들을 모아둔 디렉토리입니다.

| 파일명                | 설명                                |
| ------------------ | --------------------------------- |
| article_utils.py   | 기사 파싱, 전처리, 포맷팅 유틸리티              |
| clipboard_utils.py | 클립보드 복사/붙여넣기 관련 유틸리티              |
| common_utils.py    | 정보성 기사에서 공통으로 사용되는 유틸리티 함수 및 프롬프트 |
| data_manager.py    | 신규상장 목록 캐쉬 및 비교 유틸리티              |
| date_utils.py      | 날짜 포맷 변환 및 처리 유틸리티                |
| domestic_list.py   | 국내 신규상장 주식 수집 및 처리                |
| domestic_utils.py  | 국내 뉴스/데이터 수집 및 처리                 |
| driver_utils.py    | Selenium WebDriver 설정 및 관리        |
| exchange_utils.py  | 환율 정보 조회 및 처리                     |
| foreign_utils.py   | 해외 뉴스/데이터 수집 및 처리                 |

<br>

### 4. Assets (리소스)

정적 리소스 파일들이 위치합니다.

| 파일/디렉토리  | 설명       |
| -------- | -------- |
| icon.ico | 프로그램 아이콘 |

<br>


## 주요 흐름

### 1. 뉴스 재구성
``` less
[사용자 입력]  URL + 키워드
        │
        ▼
(크롤링) article_utils.extract_article_content()
  - OUT: (title, body)
  - 실패 시: 에러 메시지/재시도 안내
        │
        ▼
(기사 생성) news_LLM.generate_article()
  state = { url, keyword, title, body }
  ├─ 오늘(KST)·원문 작성일 확보
  ├─ 프롬프트 구성: generate_system_prompt()
  ├─ Gemini-2.5-flash 호출 → 초안 기사
  ├─ 출력 보정: ensure_output_sections([제목]/[해시태그]/[본문] 강제)
  └─ (옵션) Fast-pass/간이 일치성 체크로 조기 통과 판단
        │
        ▼
(사실 검증) check_LLM.check_article_facts()
  ├─ 검증 프롬프트: generate_check_prompt()
  ├─ LLM 응답 JSON 추출: _extract_json_block()
  ├─ 오류 목록 정규화: _normalize_nonfactual()
  ├─ verdict(OK/ERROR) 정규화: _normalize_verdict()
  ├─ 수정본 보장: _ensure_sections()
  └─ 수정본 누락 시 최소 패치: _auto_minimal_patch()
        │
        ▼
(병합) news_LLM.generate_article 내부에서
  - verdict == "OK"  → display_text = 생성 기사
  - verdict == "ERROR" → display_text = corrected_article(수정본)
  - verdict == "UNKNOWN"/파싱실패 → display_text = 경고문
        │
        ▼
(UI 반영)
  - 좌측: 원문 (title + body)
  - 우측: display_text (날짜 하이라이트 포함)
  - 복사 버튼/진행 메시지/에러 안내
        │
        ▼
(저장) common_utils.save_news_to_file(...)
  - 일자 폴더 규칙으로 .txt 저장
  - 필요 시 이미지/클립보드 연동

```


<br>

### 2. 정보성 기사
``` LESS
[사용자 입력: 종목명/코드]
        │   (PyQt5: stock_tab.py / toss_tab.py)
        ▼
입력 검증 · 버튼 상태 전환
        │
        ▼
common_utils.capture_and_generate_news()
        │  └─ domain: "domestic" / "foreign" / "toss" 자동 판별    
        ▼
┌─────────────────────────────────────────────────────────────┐
│  [분기] 국내 vs 해외 vs 토스                                 │
├─────────────────────────────────────────────────────────────┤
│  (국내) domestic_utils.capture_wrap_company_area(...)       │
│   ├─ 네이버 금융 종목 상세 페이지 진입                        │
│   ├─ 차트 영역 스크린샷 저장(회사·시세·투자정보 포함)          │
│   ├─ 핵심 텍스트 데이터 파싱(가격·등락·거래량 등)              │
│   └─ 거래정지/투자주의 여부 체크(check_investment_...)        │
│                                                             │
│  (해외) foreign_utils._capture_chart_section(...)           │
│   ├─ 네이버 검색(“티커/회사 + 주가”) 차트 식별                │
│   ├─ 차트 섹션 캡처(이미지 저장)                             │
│   └─ _extract_stock_data(...)로 시세 텍스트 추출             │
│                                                             │
│  (토스) toss_service.get_toss_stock_data(...)               │
│   ├─ 토스증권 데이터 크롤링 → 인기 종목 리스트 수집            │
│   ├─ 국내/해외 여부 및 등락률/가격 필터링                     │
│   └─ 선택 종목별 capture_and_generate_news 재호출            │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
info_LLM.generate_info_news(chart_image + 추출 데이터)
        │  └─ (내부) build_system_prompt()로 시스템 프롬프트 구성
        ▼
Gemini 2.5 모델 호출 → [제목]/[해시태그]/[본문] 생성
        │
        ▼
common_utils.save_news_to_file(출력 폴더, 파일명 규칙)
        │  └─ 날짜 폴더(예: “YYYYMMDD/”) 구조 유지
        ▼
UI 표시(본문 미리보기·복사 버튼) + 파일 저장 완료

```


<br>

### 3. 토스 기사
``` LESS
[사용자 입력: 필터(등락률/가격/순위...)]
        │ (PyQt5: toss_tab.py)
        ▼
toss_service.get_toss_stock_data()
 └─ 토스증권 API 호출 → 인기 종목 리스트
        │
        ▼
toss_service.filter_toss_data(...)  
 └─ 조건에 맞게 종목 필터링
        │
        ▼
ArticleGeneratorWorker 시작 (멀티 스레드)
 └─ 종목별 common_utils.capture_and_generate_news(...)
        │
        ▼
(내부는 StockTab 흐름 동일:  
domestic_utils / foreign_utils → info_LLM → 기사 생성)
        │
        ▼
결과 기사 저장 (토스기사/토스YYYYMMDD)  
        │
        ▼
UI 표시: 진행률/취소/완료 메시지 + 폴더 열기 버튼

```

<br>



## 흐름도별 디테일 설명

### 1. 뉴스 재구성 (NewsTab)

> TIP
>  뉴스 재구성은 “사람이 쓴 기사”를 리라이팅하는 대신 **사실검증** 단계를 내장해 신뢰성을 확보합니다(속도는 정보성 대비 느릴 수 있음).

<br>

**핵심 입·출력**

- `news_LLM.generate_article(state: dict) → dict`  
    `state`에는 최소 `url, title, body, keyword`가 들어가며, 반환에는 생성문, 사실검증 결과(`OK/ERROR/UNKNOWN`), 교정문(있을 경우), UI 표시에 쓰는 `display_text/display_kind` 등이 포함됩니다.
    
- `check_LLM.check_article_facts(generated, original)`은 LLM이 두 텍스트 차이를 **JSON**으로 내놓게 유도합니다. 파싱 불가시 `UNKNOWN` 처리, 정상일 때 `OK`/`ERROR`. `ERROR`면 교정문을 활용합니다.

<br>


**세부 동작**

- **크롤링 실패/본문 부족 처리**: 원문 본문이 지나치게 짧거나 추출 실패 시 바로 오류를 띄우고 사용자에게 재시도를 안내합니다.
    
- **프롬프트 구성 → 생성**: `generate_system_prompt()`에서 날짜/시제·출력형식을 강제하고, 이후 Gemini 호출로 초안 기사를 받습니다. `ensure_output_sections()`로 `[제목]/[해시태그]/[본문]` 블록을 보정합니다. (LLM 호출 시 `system_instruction`에 기본 규칙을 싣고, 사용자 프롬프트로 `keyword/제목/본문`을 전달)
    
- **사실검증 분기 & 병합**:
    - `OK` → 생성문 그대로 표출
    - `ERROR` → 교정문(`corrected_article`)을 최종 표출
    - `UNKNOWN` → 경고문 표출(파싱 실패 등)
        
- **UI/저장**: 좌측 원문·우측 결과(날짜 하이라이트)와 복사 버튼 제공. 저장은 `common_utils.save_news_to_file`로 날짜 폴더 규칙 아래 `.txt` 생성, Windows에선 자동 열기/클립보드 연동 가능(이미지·텍스트).

<br>

### 2. 정보성 기사 (StockTab)

>TIP  
  정보성 기사는 **차트·수치 데이터**를 기반으로 직접 작성되므로, 사실 검증 단계를 생략해 **빠른 처리 속도**를 제공합니다.  대신 원문 기사가 없는 만큼, 표현 다양성보다는 **정확한 수치 전달과 간결성**이 장점입니다.

<br>

**핵심 입·출력**

- **입력(국내)**: `domestic_utils.capture_wrap_company_area(code)`  
    네이버 금융 종목 상세에 진입해 **차트/시세요약/투자정보/기업개요**를 스크린샷·파싱하여 구조화(`chart_info`, `invest_info`)합니다. 필요 시 **거래정지/주의** 여부를 함께 확인합니다.
    
- **입력(해외)**: `foreign_utils._capture_chart_section(...)`  
    네이버 **검색(SERP) 차트 영역**을 식별해 캡처하고, `_extract_stock_data()`로 **이름/가격/등락** 등 텍스트 데이터를 추출합니다. SERP의 **파워링크 광고 제거**는 `driver_utils` 보조 함수를 사용합니다.
    
- **기사 생성(텍스트 기반)**:  
    `info_LLM.generate_info_news_from_text(keyword, info_dict, domain)`  
    수치 딕셔너리를 받아 도메인에 맞는 프롬프트를 생성하고 LLM 호출로 **기사 텍스트**를 만듭니다. 주식인 경우 프롬프트에 **[주식 정보] / [해외주식 정보]** 섹션을 붙여 문맥을 명확히 제공합니다.
    
- **기사 생성(이미지 기반)** _(선택)_:  
    `info_LLM.generate_info_news(keyword, image_path, is_stock)`  
    차트 이미지를 직접 입력해 기사를 생성할 수 있으나, 본 프로젝트는 **이미 수집한 텍스트 데이터 활용**을 주로 사용합니다.
    
- **출력**: `[제목] / [해시태그] / [본문]`  
    LLM 응답은 제목, 해시태그, 본문 3분할 한글 기사 형식으로 반환됩니다

<br>


**세부 동작**

1. **입력 검증 → 도메인 판별 → 데이터 수집**  
    `common_utils.capture_and_generate_news(name, …)`  
    전체 워크플로우를 단계별 총괄하며, **국내/해외/토스**를 자동 판별하고 데이터 캡처·파싱을 진행합니다. (진행률/취소 콜백 포함)
    
2. **프롬프트 구성 → LLM 호출**  
    `info_LLM.build_system_prompt(domain, data_dict)`  
    도메인 키에 따라 **[주식 정보] / [해외주식 정보]** 섹션이 자동 포함됩니다. 이렇게 구성된 프롬프트는 `generate_info_news*` 계열 함수에서 Gemini-2.5-flash 모델로 전달됩니다.
    
3. **본문 생성 및 템플릿 결합**  
    `info_LLM.create_template(output_text, keyword, domain)`  
    생성된 기사 텍스트 앞에 **간략 리드(템플릿)**를 붙여 가독성을 높입니다.
    
4. **저장·후처리**  
    `common_utils.save_news_and_image(final_output, image_path)`  
    결과를 날짜형 폴더(`YYYYMMDD/`) 규칙으로 저장합니다.
    
5. **UI 진행률/취소**
    
    - `stock_tab.StockWorker.run()`
    - `toss_tab.ArticleGeneratorWorker.run()`  
        종목별 처리 시작 전/중에 **전체/단계 진행률**을 갱신하고, **취소** 시 콜백을 통해 즉시 중단됩니다. (Stock/Toss 공통)

<br>

### 3. 토스 기사 (TossTab)

> **TIP**  
 토스 기사는 인기 종목 데이터를 **일괄 처리**할 수 있어 **대량 기사 자동화**에 적합합니다.  
 **실시간 인기 종목 트렌드**를 기사화할 때 강점을 발휘합니다.

<br>

**핵심 입·출력**

- **데이터 수집**  
    `toss_service.get_toss_stock_data(...)`  
    토스증권 인기 종목 리스트(순위·종목명·현재가·등락률 등)를 크롤링하여 DataFrame 형태로 반환합니다.
    
- **조건 필터링**  
    `toss_service.filter_toss_data(df, min_pct, max_pct, min_price, up_check, down_check, limit)`  
    UI에서 지정한 조건(등락률, 가격, 국내/해외 여부 등)에 따라 종목을 선별합니다.
    
- **기사 생성**  
    `common_utils.capture_and_generate_news(name, domain="toss", ...)`  
    각 종목에 대해 **국내/해외 분기 처리 + 캡처/파싱 + info_LLM 기사화**를 공통 경로로 실행합니다.
    
- **출력**  
    완성된 기사는 `[제목] / [해시태그] / [본문]` 구조로 작성되며, `토스기사/토스YYYYMMDD/종목명_toss_news.txt` 형태로 저장됩니다.
    
<br>


**세부 동작**

1. **필터 입력 → 종목 수집/필터링**
    - `toss_tab.TossWorker`(백그라운드 QThread 실행)
        `toss_service.get_toss_stock_data()` → `toss_service.filter_toss_data()` 순으로  
        인기 종목 리스트를 수집하고 조건에 맞게 선별합니다.
        
2. **종목별 기사화 시작**
    - `toss_tab.ArticleGeneratorWorker`가 동작하며, 선택된 종목 리스트를 순회합니다.
    - 각 종목명은 `common_utils.capture_and_generate_news(name, domain="toss", ...)`에 전달됩니다.
        
3. **내부 처리 파이프라인**
    - `common_utils.capture_and_generate_news`  
        → (국내) `domestic_utils.capture_wrap_company_area(...)`  
        → (해외) `foreign_utils._capture_chart_section(...)`  
        → 결과 데이터 기반 `info_LLM.generate_info_news_from_text(...)`
        
    - 이 과정을 통해 종목별 기사가 자동 생성됩니다.
        
4. **저장 및 후처리**
    - `common_utils.save_news_and_image(...)` 호출로 날짜 단위 폴더(`토스YYYYMMDD/`)에 저장됩니다.
        
5. **UI 반영**
    - `toss_tab.TossTab`은 전체 진행률(`progress_all`)과 단계별 진행률(`step_progress`)을 표시합니다.
    - 사용자가 취소하면 `ArticleGeneratorWorker.stop()`으로 즉시 중단됩니다.

<br>

### (기타) 환율 (HwanTab)

> **TIP**  
> 이 기능은 **구현하지 않아도 됩니다.** HwanTab과 환율 유틸이 없어도 전체 도구(뉴스 재구성/정보성/토스)는 정상 동작합니다.


<br>

---


