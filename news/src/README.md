# 통합 뉴스 도구v2.0.0 - 소스 코드 구조

이 문서는 `news/src` 하위의 주요 디렉토리와 파일들의 역할을 설명합니다. (2025년 8월 29일 기준)

## 📁 디렉토리 및 파일 구조

```
news/src/
├── assets/                     # 리소스 파일
│   └── icon.ico               # 프로그램 아이콘
│
├── components/                 # UI 컴포넌트 (PyQt5 기반)
│   ├── hwan_tab.py            # 환율 탭 UI 및 기능
│   ├── news_tab.py            # 뉴스 탭 UI 및 기능
│   ├── stock_tab.py           # 주식 탭 UI 및 기능
│   ├── toss_tab.py            # 토스 탭 UI 및 기능
│   └── settings_dialog.py     # 설정 다이얼로그
│
├── services/                   # 비즈니스 로직
│   ├── check_LLM.py           # 기사 검증 AI
│   ├── info_LLM.py            # 정보 요약/생성 AI
│   ├── news_LLM.py            # 뉴스 기사 처리 AI
│   └── toss_service.py        # 토스 API 연동 서비스
│
└── utils/                     # 유틸리티 함수 모음
    ├── article_utils.py       # 기사 파싱/처리
    ├── clipboard_utils.py     # 클립보드 유틸리티
    ├── common_utils.py        # 공통 유틸리티
    ├── data_manager.py        # 캐쉬 관리 유틸리티
    ├── date_utils.py          # 날짜 처리 유틸리티
    ├── domestic_list.py       # 국내 신규상장 관리 유틸리티
    ├── domestic_utils.py      # 국내 뉴스/데이터
    ├── driver_utils.py        # Selenium WebDriver
    ├── exchange_utils.py      # 환율 관련 유틸리티
    └── foreign_utils.py       # 해외 뉴스/데이터
```

---

## 1. Components (UI 컴포넌트)

PyQt5를 기반으로 한 GUI 컴포넌트들이 위치합니다. 각 탭별로 분리되어 있으며, 사용자 인터페이스와 관련된 로직을 담당합니다.

| 파일명 | 설명 |
|--------|------|
| hwan_tab.py | 환율 정보 조회 및 차트 캡처 기능 구현 |
| news_tab.py | 뉴스 기사 추출 및 재구성 기능 구현 |
| stock_tab.py | 주식 정보 조회 및 차트 캡처 기능 구현 |
| toss_tab.py | 토스 계좌 조회 및 거래 내역 기능 구현 |
| settings_dialog.py | API 키 및 환경 설정 다이얼로그 |

## 2. Services (비즈니스 로직)

주요 비즈니스 로직이 위치하며, API 호출, 데이터 처리, AI 모델 연동 등을 담당합니다.

| 파일명 | 설명 |
|--------|------|
| check_LLM.py | 생성된 기사의 사실 관계 검증 AI |
| info_LLM.py | 정보 요약 및 생성 AI |
| news_LLM.py | 뉴스 기사 처리 AI |
| toss_service.py | 토스 API 연동 서비스 |

## 3. Utils (유틸리티)

프로젝트 전반에서 재사용되는 유틸리티 함수들을 모아둔 디렉토리입니다.

| 파일명 | 설명 |
|--------|------|
| article_utils.py | 기사 파싱, 전처리, 포맷팅 유틸리티 |
| clipboard_utils.py | 클립보드 복사/붙여넣기 관련 유틸리티 |
| common_utils.py | 공통으로 사용되는 유틸리티 함수 및 프롬프트 |
| data_manager.py | 신규상장 목록 캐쉬 및 비교 유틸리티 |
| date_utils.py | 날짜 포맷 변환 및 처리 유틸리티 |
| domestic_list.py | 국내 신규상장 주식 수집 및 처리 |
| domestic_utils.py | 국내 뉴스/데이터 수집 및 처리 |
| driver_utils.py | Selenium WebDriver 설정 및 관리 |
| exchange_utils.py | 환율 정보 조회 및 처리 |
| foreign_utils.py | 해외 뉴스/데이터 수집 및 처리 |

## 4. Assets (리소스)

정적 리소스 파일들이 위치합니다.

| 파일/디렉토리 | 설명 |
|--------------|------|
| icon.ico | 프로그램 아이콘 |

---







