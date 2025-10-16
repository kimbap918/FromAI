# 🧭 Java Playwright Capture (Galaxy S20 Ultra)

## 📁 프로젝트 구조
- `src/main/java/Capture.java` — 메인 실행 파일 (패키지 없음)
- `pom.xml` — Maven 설정 (Playwright Java 의존성 포함)
- `urls.txt` — 캡처할 URL 목록 (줄바꿈/쉼표/세미콜론/공백 구분 가능)
- `capture.bat` — 간단 실행용 스크립트

---

## 🚀 실행 방법

### 1️⃣ 의존성 설치
```bash
mvn -q -DskipTests package
```

### 2️⃣ URL 목록 캡처 (기본: headless)
- 터미널을 연 뒤에 아래의 명령어를 실행하면 됩니다.
```bash
capture urls.txt
```
3️⃣ 창 띄워서 캡처
```bash
capture --headed urls.txt
```

## ⚙️ 주요 옵션
| 옵션             | 설명                   |
| -------------- | -------------------- |
| `--mode full`  | 전체 페이지 캡처            |
| `--headed`     | 창 띄우기                |
| `--logads`     | 광고 네트워크 로그 출력        |
| `--outdir DIR` | 저장 폴더 지정 (기본: 모바일캡처) |

