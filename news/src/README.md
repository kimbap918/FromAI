# src 디렉토리 구조 안내 (2025년 8월 기준)

이 문서는 `news/src` 하위의 주요 디렉토리(`components`, `services`, `utils`, `assets`)와 그 내부 파일들의 역할을 설명합니다.

---

## 📁 디렉토리 및 파일 구조

```
news/src/
├── assets/
│   └── icon.ico                # 프로그램 아이콘 파일
├── components/
│   ├── hwan_tab.py             # 환율 탭 UI 및 기능
│   ├── news_tab.py             # 뉴스 탭 UI 및 기능
│   ├── stock_tab.py            # 주식 탭 UI 및 기능
│   ├── toss_tab.py             # 토스 관련 탭 UI 및 기능
│   └── settings_dialog.py      # API KEY 설정 관련 기능     
├── services/
│   ├── article_generator.py    # 기사 생성 관련 서비스 로직
│   ├── info_LLM.py             # 정보 요약/생성 LLM 서비스
│   ├── news_LLM.py             # 뉴스 기사 LLM 서비스
│   └── toss_service.py         # 토스 관련 서비스 로직
└── utils/
    ├── article_utils.py        # 기사 파싱/처리 유틸리티
    ├── clipboard_utils.py      # 클립보드 관련 유틸리티
    ├── common_utils.py         # 공통 유틸리티 함수
    ├── domestic_utils.py       # 국내 뉴스/데이터 유틸리티
    ├── driver_utils.py         # Selenium WebDriver 유틸리티
    ├── exchange_utils.py       # 환율 관련 유틸리티
    └── foreign_utils.py        # 해외 뉴스/데이터 유틸리티
```

---

## 1. components

- 다양한 탭(GUI) 및 통합 UI 관련 컴포넌트가 위치합니다.
- 각 파일은 주로 그래픽 사용자 인터페이스와 직접적으로 연결된 기능을 담당합니다.

| 파일명         | 설명                           |
|----------------|------------------------------|
| hwan_tab.py    | 환율 관련 탭 UI 및 기능 구현      |
| news_tab.py    | 뉴스 관련 탭 UI 및 기능 구현      |
| stock_tab.py   | 주식 관련 탭 UI 및 기능 구현      |
| toss_tab.py    | 토스 관련 탭 UI 및 기능 구현      |
| settings_dialog.py    | API KEY 설정 관련 UI 기능 구현     |

## 2. services

- LLM(Gemini 등)을 활용한 기사 생성/요약, 정보 제공 등 핵심 서비스 로직이 위치합니다.

| 파일명               | 설명                                 |
|----------------------|------------------------------------|
| article_generator.py | 기사 자동 생성 로직                   |
| info_LLM.py          | 정보 요약/생성 LLM 서비스             |
| news_LLM.py          | 뉴스 기사 요약/생성 LLM 서비스         |
| toss_service.py      | 토스 관련 서비스 로직                  |

## 3. utils

- 기사 파싱, 데이터 처리, 클립보드, WebDriver 등 다양한 유틸리티 함수 및 모듈이 위치합니다.

| 파일명            | 설명                                 |
|-------------------|------------------------------------|
| article_utils.py  | 기사 본문 추출 및 파싱 함수             |
| clipboard_utils.py| 이미지 클립보드 복사 등 유틸리티         |
| common_utils.py   | 공통적으로 사용하는 유틸리티 함수        |
| domestic_utils.py | 국내 데이터/뉴스 관련 유틸리티           |
| driver_utils.py   | Selenium WebDriver 초기화 및 설정        |
| exchange_utils.py | 환율 데이터 처리 유틸리티                |
| foreign_utils.py  | 해외 데이터/뉴스 관련 유틸리티           |

## 4. assets

- 아이콘 등 앱에서 사용하는 정적 파일이 위치합니다.

| 파일명    | 설명         |
|-----------|------------|
| icon.ico  | 프로그램 아이콘 |

---



