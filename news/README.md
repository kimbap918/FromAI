# 통합 뉴스 도구

뉴스 재구성, 환율 차트, 주식 차트 기능을 하나의 GUI 프로그램으로 통합한 도구입니다.

## 🚀 주요 기능

### 📰 뉴스 재구성
- 기사 URL과 키워드를 입력하여 기사 내용을 추출
- 추출된 내용을 클립보드에 자동 복사
- 챗봇과 연동하여 기사 재구성 지원

### 💱 환율 차트
- 환율 키워드 입력으로 네이버 환율 차트 캡처
- 캡처된 이미지를 클립보드에 자동 복사
- 날짜별 폴더에 자동 저장

### 📈 주식 차트
- 주식 코드 또는 회사명으로 주식 차트 캡처
- 캡처된 이미지를 클립보드에 자동 복사
- 날짜별 폴더에 자동 저장

## 📦 설치 방법

### 1. Python 환경 설정
```bash
# Python 3.8 이상 설치 필요
python --version
```

### 2. 필요한 패키지 설치
```bash
pip install -r requirements.txt
```

### 3. 프로그램 실행
```bash
python unified_gui.py
```

## 🔨 EXE 파일 빌드

### 방법 1: PyInstaller 사용 (권장)
```bash
# PyInstaller 설치
pip install pyinstaller

# EXE 파일 빌드
pyinstaller --onefile --windowed --name "통합뉴스도구" unified_gui.py
```

### 방법 2: 배치 파일 사용
```bash
# build.bat 파일 실행
build.bat
```

빌드 완료 후 `dist` 폴더에서 `통합뉴스도구.exe` 파일을 찾을 수 있습니다.

## 📖 사용법

### 뉴스 재구성
1. "📰 뉴스 재구성" 탭 선택
2. 기사 URL 입력 (예: https://news.naver.com/...)
3. 키워드 입력 (예: AI, 경제, 기술)
4. "📄 기사 추출" 버튼 클릭 혹은 엔터
5. 추출 완료 후 "🌐 챗봇 열기" 버튼으로 챗봇 열기
6. Ctrl+V로 추출된 내용 붙여넣기

### 환율 차트
1. "💱 환율 차트" 탭 선택
2. 환율 키워드 입력 (예: 달러, 유로, 엔화)
3. "📊 차트 캡처" 버튼 클릭 혹은 엔터
4. 캡처된 이미지가 클립보드에 복사되고 자동으로 열림

### 주식 차트
1. "📈 주식 차트" 탭 선택
2. 주식 코드 또는 회사명 입력 (예: 005930, 삼성전자)
3. "📊 차트 캡처" 버튼 클릭 혹은 엔터
4. 캡처된 이미지가 클립보드에 복사되고 자동으로 열림

## 📁 파일 구조

```
news/
├── unified_gui.py          # 메인 GUI 프로그램
├── requirements.txt         # 필요한 패키지 목록
├── setup.py               # cx_Freeze 빌드 설정
├── build.bat              # PyInstaller 빌드 스크립트
├── README.md              # 사용법 가이드
├── 주식차트/              # 주식 차트 저장 폴더
│   └── YYYYMMDD/
└── 환율차트/              # 환율 차트 저장 폴더
    └── YYYYMMDD/
```

## ⚠️ 주의사항

1. **Chrome 브라우저 필요**: Selenium을 사용하므로 Chrome 브라우저가 설치되어 있어야 합니다.
2. **인터넷 연결**: 모든 기능이 인터넷 연결을 필요로 합니다.
3. **Windows 권한**: 클립보드 기능을 위해 Windows 권한이 필요할 수 있습니다.

## 🔧 문제 해결

### Selenium 오류
```bash
# ChromeDriver 업데이트
pip install --upgrade webdriver-manager
```

### 클립보드 오류
```bash
# Windows 클립보드 라이브러리 재설치
pip uninstall pywin32
pip install pywin32
```

### PyQt5 오류
```bash
# PyQt5 재설치
pip uninstall PyQt5
pip install PyQt5
```

## 📞 지원

문제가 발생하면 다음을 확인해주세요:
1. Python 버전이 3.8 이상인지 확인
2. 모든 패키지가 올바르게 설치되었는지 확인
3. Chrome 브라우저가 설치되어 있는지 확인
4. 인터넷 연결이 안정적인지 확인

## 📝 라이선스

이 프로그램은 FromAI 및 관련 내부 프로젝트의 일부입니다.
외부 유출 및 상업적 이용을 금지합니다.
