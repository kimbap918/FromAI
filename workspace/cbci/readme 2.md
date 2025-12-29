
# 0) 폴더/전제

* 작업 폴더: `C:\Users\TDI\Desktop\company`
* FastAPI 파일: `6_fast_api.py` (안에 `app = FastAPI(...)` 존재)
* Mongo 컬렉션: `news / yna_news`
* conda env: `ceo`

---

# 1) FastAPI 실행법

## 1-1) 패키지 설치(최초 1회)

```bat
conda activate ceo
pip install fastapi uvicorn pymongo python-dotenv
```

## 1-2) 환경변수 설정 (CMD에서 매번 실행)

> `6_fast_api.py`가 `MONGO_URI` 없으면 바로 죽으니 **uvicorn 실행 전에** 꼭 설정

```bat
conda activate ceo
cd C:\Users\TDI\Desktop\company

set "MONGO_URI=mongodb://news_mongodb_user:news!%40mon!go%40!db@218.145.67.56:37817/?authSource=news"
set "MONGO_DB=news"
set "MONGO_COL=yna_news"
```

(API 키를 코드에서 검사한다면)

```bat
set "API_KEY=change-me"
```

## 1-3) 실행

```bat
uvicorn 6_fast_api:app --host 0.0.0.0 --port 8000 --reload
```

## 1-4) 정상 확인

* 로컬 문서: `http://127.0.0.1:8000/docs`
* 샘플 조회: `http://127.0.0.1:8000/news?limit=3`

### 자주 나는 에러

* `RuntimeError: MONGO_URI is required` → 1-2 환경변수 누락
* `Address already in use` → 포트 충돌. 아래처럼 변경:

  ```bat
  uvicorn 6_fast_api:app --host 0.0.0.0 --port 8001 --reload
  ```

---

# 2) ngrok 실행법 (FastAPI를 외부(Base44)에서 접근 가능하게)

## 2-1) ngrok 준비 확인

(ceo에서 ngrok가 잡히는지)

```bat
conda activate ceo
where ngrok
ngrok version
```

`where ngrok`에

* `C:\Users\TDI\anaconda3\envs\ceo\Scripts\ngrok.exe`
  가 보이면 OK.

## 2-2) authtoken 등록(최초 1회)

> ngrok 대시보드에서 실제 토큰 복사 후 실행

```bat
ngrok config add-authtoken <진짜_토큰_붙여넣기>
```

## 2-3) 터널 실행 (FastAPI가 켜진 상태에서)

FastAPI가 `8000` 포트로 실행 중일 때, **새 CMD 창 하나 더 열고**:

```bat
conda activate ceo
cd C:\Users\TDI\Desktop\company
ngrok http 8000
```

정상 출력 예:

* `Forwarding  https://xxxx.ngrok-free.dev -> http://localhost:8000`
* Web Interface: `http://127.0.0.1:4040`

## 2-4) 외부 URL 확인

브라우저에서:

* `https://xxxx.ngrok-free.dev/docs`
* `https://xxxx.ngrok-free.dev/news?limit=3`

---

# 3) “실전 운영” 실행 순서(딱 이 순서대로)

## 터미널 1 (FastAPI)

```bat
conda activate ceo
cd C:\Users\TDI\Desktop\company
set "MONGO_URI=mongodb://news_mongodb_user... env 참고"
set "MONGO_DB=news"
set "MONGO_COL=yna_news"
uvicorn 6_fast_api:app --host 0.0.0.0 --port 8000 --reload
```

## 터미널 2 (ngrok)

```bat
conda activate ceo
ngrok http 8000
```

---

# 4) Base44에 붙일 때 핵심 메모

* Base44에서는 ngrok가 만들어준 **https 주소**를 `NEWS_API_BASE_URL`로 넣으면 됨
* ngrok 무료는 URL이 바뀔 수 있음 → 바뀌면 Base44 Secret도 갱신해야 함
* PC 꺼지면 API도 끊김(테스트/임시 운용용)

---
