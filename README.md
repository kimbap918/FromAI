# 통합 뉴스 도구

뉴스 재구성, 환율 차트, 주식 차트, 토스 관련 기능을 하나의 GUI 프로그램으로 통합한 도구입니다.

## 주요 기능

### 뉴스 재구성
- 기사 URL과 키워드를 입력하여 기사 내용을 추출 및 재구성
- AI를 활용한 자동 문장 최적화 및 요약
- 클립보드에 자동 복사 기능
- 다양한 언론사 포맷 지원

### 환율 차트
- 실시간 환율 정보 조회
- 네이버 환율 차트 자동 캡처
- 캡처된 이미지 클립보드 자동 복사
- 날짜별 폴더에 자동 저장
- 다양한 통화 쌍 지원

### 주식 차트
- 종목코드/회사명으로 주식 정보 조회
- 네이버 파이낸스 차트 자동 캡처
- 다양한 차트 기간 설정 가능 (일봉, 주봉, 월봉)
- 캡처된 이미지 클립보드 자동 복사
- 날짜별 폴더에 자동 저장

### 토스 관련 기능
- 토스 송금 내역 조회
- 계좌 잔고 확인
- 거래 내역 분석

## 권장 개발/빌드 환경
- Python 3.11.13 (newsbot 가상환경)
- pip, PyInstaller, 기타 requirements.txt의 모든 패키지

## 디렉토리 구조 (1.1.6 기준)

```
FromAI1.1.6/
├── gui_loader.py              # 메인 실행/빌드 엔트리포인트 (PyQt5 GUI)
├── gui_loader.spec            # PyInstaller 빌드 스펙 파일
├── download_nltk_data.py      # nltk 데이터 다운로드용 스크립트
├── requirements.txt           # Python 의존성 패키지 목록
├── .env                       # 환경 변수 설정 파일 (API 키 등)
├── news/                      # 뉴스 관련 모듈
│   └── src/
│       ├── components/        # PyQt5 UI 컴포넌트 (각 탭별 구현)
│       ├── services/          # 비즈니스 로직 및 AI 서비스
│       ├── utils/             # 유틸리티 함수 모음
│       └── assets/            # 아이콘 등 리소스 파일
├── travel/                    # 여행 관련 모듈 (향후 확장용)
├── dist/                      # 빌드된 실행파일이 생성되는 폴더
├── build/                     # 빌드 임시파일 (자동 생성)
├── nltk_data/                 # nltk 데이터 (자동 생성)
└── README.md                  # 메인 문서
```

## 개발/실행/빌드 방법

1. **의존성 설치**
   ```bash
   pip install -r requirements.txt
   ```

2. **nltk 데이터 다운로드(최초 1회만)**
   ```bash
   python download_nltk_data.py
   ```

3. **개발/테스트**
   - 개발 중에는 `python gui_loader.py`로 바로 실행
   - 기사 추출 등 리소스 경로는 상대경로로 관리

4. **빌드(실행파일 생성)**
   ```bash
   pyinstaller gui_loader.spec
   ```
   - 빌드 후 `dist/gui_loader.exe` 실행
   - `nltk_data` 폴더가 exe와 같은 폴더에 있어야 기사 추출 정상 동작

5. **빌드 옵션/리소스 관리**
   - 빌드 옵션, 포함 리소스, 아이콘 등은 모두 `gui_loader.spec`에서 관리
   - 옵션 변경 시 spec 파일만 수정하면 됨

## ⚠️ 주의/팁
- **build/** 폴더는 임시파일이므로 삭제해도 무방
- **dist/** 폴더의 exe와 `nltk_data` 폴더를 함께 배포해야 기사 추출 정상 동작
- **requirements.txt, gui_loader.spec**는 반드시 버전관리(git 등)로 보관
- **상대경로 사용**: 코드에서 파일/폴더 접근 시 항상 os.path.join, os.path.dirname(__file__) 등으로 경로 지정
- **User-Agent**: 기사 추출 시 User-Agent를 명시적으로 지정(이미 코드에 적용됨)

## 👨‍💻 기타
문의/협업: 제작자 최준혁 
