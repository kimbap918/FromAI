# FastAPI + ngrok 운영 가이드 (MongoDB news/yna_news)

## 0) 전제 / 폴더

* 작업 폴더: `C:\Users\TDI\Desktop\company`
* FastAPI 파일: `6_fast_api.py` (내부에 `app = FastAPI(...)`)
* MongoDB: `news / yna_news`
* conda env: `ceo`

> ⚠️ 중요: **ngrok은 “FastAPI가 실제로 떠있는 포트”로만 연결**됩니다.
> FastAPI를 8001로 띄우면 ngrok도 반드시 8001로 연결해야 합니다.

---

## 🚀 감성 분석 기능 실행 가이드 (Sentiment Analysis Guide)

크롤러(`4_crawler.py`)에 통합된 감성 분석 기능을 활용하는 방법입니다.

### 1. 신규 수집 시 자동 분석
크롤러 실행 시 본문을 수집하도록 설정되어 있다면, 수집과 동시에 AI가 감성을 분석하여 DB에 저장합니다.
- **실행**: `python 4_crawler.py` (자동 수행)

### 2. 기존 데이터 백필 (Backfill)
DB에 이미 저장된 기사들 중 감성 분석이 누락되었거나, 새로운 로직으로 재분석이 필요한 경우 사용합니다.
- **감성 분석만 수행 (미분석 대상)**:
  ```bash
  python 4_crawler.py --backfill-sentiment --backfill-limit 500
  ```
- **전체 강제 재분석 (기존 데이터 덮어쓰기)**:
  ```bash
  python 4_crawler.py --backfill-sentiment --backfill-limit 500 --force
  ```

### 3. 분석 결과 CSV 추출
DB에 저장된 감성 분석 결과를 리포트용 CSV로 내보냅니다.
- **최신 100건 추출**: `python sentiment_to_csv.py`
- **개수 지정 추출**: `python sentiment_to_csv.py --limit 500`

---

## 부록) 복붙용 빠른 시작 가이드 (Windows, conda=ceo)

아래를 그대로 터미널에 단계별로 붙여넣으면 FastAPI 실행 → ngrok 공개 → 호출 테스트까지 완료됩니다.

### A. 필수 패키지 설치 (최초 1회)

```bat
conda activate ceo
pip install fastapi uvicorn pymongo python-dotenv
```

선택: 로컬 감성모델 사용 시(이미 설치돼 있으면 생략 가능)

```bat
pip install transformers torch --extra-index-url https://download.pytorch.org/whl/cpu
```

### B. 환경변수로 즉시 실행(테스트용)

```bat
conda activate ceo
cd C:\Users\TDI\Desktop\company

set "MONGO_URI=mongodb://<user>:<pass>@<host>:<port>/?authSource=news"
set "MONGO_DB=news"
set "MONGO_COL=yna_news"
set "API_KEY=<임의의_안전한_키>"

uvicorn 6_fast_api:app --host 127.0.0.1 --port 8000
```

새 터미널을 하나 더 열고 ngrok 실행:

```bat
conda activate ceo
ngrok http 127.0.0.1:8000 --region=jp
```

헬스 확인(브라우저):

```
https://<ngrok-도메인>/health
```

API 호출 확인(curl):

```bat
curl -H "x-api-key: <임의의_안전한_키>" "https://<ngrok-도메인>/news?limit=1"
```

### C. .env로 고정(운영 권장)

1) `.env` 파일 생성(수정):

```
MONGO_URI=mongodb://<user>:<pass>@<host>:<port>/?authSource=news
MONGO_DB=news
MONGO_COL=yna_news
API_KEY=<임의의_안전한_키>

# (선택) 감성 분석 설정
SENTIMENT_MODEL_NAME=monologg/koelectra-small-v3-nsmc
SENTIMENT_THRESHOLD=0.6
SENTIMENT_NEUTRAL_FLOOR=0.5
```

2) 서버 실행(새 터미널):

```bat
conda activate ceo
cd C:\Users\TDI\Desktop\company
uvicorn 6_fast_api:app --host 127.0.0.1 --port 8000
```

3) ngrok 실행(다른 터미널):

```bat
conda activate ceo
ngrok http 127.0.0.1:8000 --region=jp
```

4) 테스트:

```bat
curl -H "x-api-key: <임의의_안전한_키>" "https://<ngrok-도메인>/news?limit=1"
```

참고:
- 루트(/)는 404가 정상입니다. /health 또는 /news로 호출하세요.
- 401(Invalid API key)이면 서버의 API_KEY와 요청 헤더의 값이 정확히 일치하는지 확인 후 서버 재시작.
- ngrok 충돌(ERR_NGROK_334) 시 기존 터널 창에서 Ctrl+C로 종료 후 재시작.

---

## End-to-End 실행 절차 (FastAPI → ngrok → Base44) [복붙 가능]

### 1) 의존성 설치 (최초 1회)

```bat
conda activate ceo
pip install fastapi uvicorn pymongo python-dotenv
:: 선택: 로컬 감성모델 사용 시
pip install transformers torch --extra-index-url https://download.pytorch.org/whl/cpu
```

### 2) .env 준비(권장)

`C:\Users\TDI\Desktop\company\.env` 예시:

```
MONGO_URI=mongodb://<user>:<pass>@<host>:<port>/?authSource=news
MONGO_DB=news
MONGO_COL=yna_news
API_KEY=<안전한_API_KEY>

# (선택) 감성 분석 설정
SENTIMENT_MODEL_NAME=monologg/koelectra-small-v3-nsmc
SENTIMENT_THRESHOLD=0.6
SENTIMENT_NEUTRAL_FLOOR=0.5
```

### 3) FastAPI 실행 (터미널 1)

```bat
conda activate ceo
cd C:\Users\TDI\Desktop\company
uvicorn 6_fast_api:app --host 127.0.0.1 --port 8000
```

테스트:

```
http://127.0.0.1:8000/health
```

### 4) ngrok 실행 (터미널 2)

```bat
conda activate ceo
ngrok config add-authtoken <ngrok_토큰>  :: 최초 1회만
ngrok http 127.0.0.1:8000 --region=jp
```

출력된 Forwarding URL 예: `https://xxxx.ngrok-free.dev`

헬스 체크:

```
https://xxxx.ngrok-free.dev/health
```

뉴스 API 테스트(curl):

```bat
curl -H "x-api-key: <안전한_API_KEY>" "https://xxxx.ngrok-free.dev/news?limit=1"
```

### 5) Base44 설정

- 환경변수(시크릿)
  - `NEWS_API_BASE_URL` = `https://xxxx.ngrok-free.dev`
  - `NEWS_API_KEY` = `.env`의 `API_KEY`와 동일

- Axios 예시

```js
import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.NEWS_API_BASE_URL,
  headers: { 'x-api-key': import.meta.env.NEWS_API_KEY }
})

export async function fetchNews(params = { limit: 20, skip: 0 }) {
  const { data } = await api.get('/news', { params })
  return data
}
```

메모:
- ngrok URL은 재시작 시 변경될 수 있음 → `NEWS_API_BASE_URL`도 갱신 필요
- 루트(/)는 404가 정상, `/health` 또는 `/news` 사용
- 인증 활성화 시 모든 `/news` 호출에 `x-api-key` 필수

---

## 배치 파일로 한 번에 실행 (start_api_and_ngrok.bat)

프로젝트 루트에 `start_api_and_ngrok.bat`를 추가했습니다. 더블클릭 한 번으로 FastAPI와 ngrok을 각각 새 콘솔 창에서 실행합니다.

### 사용법

```bat
:: 파일 위치: C:\Users\TDI\Desktop\company\start_api_and_ngrok.bat
:: 실행 방법 1) 파일 더블클릭
:: 실행 방법 2) 터미널에서
C:\Users\TDI\Desktop\company> start_api_and_ngrok.bat
```

실행되면 다음이 자동으로 이루어집니다.
- conda env `ceo` 활성화
- `uvicorn 6_fast_api:app --host 127.0.0.1 --port 8000` 실행 (새 창)
- `ngrok http 127.0.0.1:8000 --region=jp` 실행 (새 창)

### 사전 준비
- conda 환경 이름: `ceo`
- `.env`에 Mongo 설정과 `API_KEY` 값 존재
- ngrok 설치 및 `ngrok config add-authtoken <토큰>` 완료(최초 1회)

### 포트/리전 변경
배치 파일 상단 변수 수정:

```
set PORT=8000
set HOST=127.0.0.1
set NGROK_REGION=jp
```

### 테스트
- 헬스: `https://<ngrok-도메인>/health`
- 뉴스:
  ```bat
  curl -H "x-api-key: <API_KEY>" "https://<ngrok-도메인>/news?limit=1"
  ```
- ngrok Inspector: `http://127.0.0.1:4040`

### 종료 방법
- 각 콘솔 창에서 `Ctrl + C` → `Y`
- 또는 창 닫기

### 트러블슈팅
- `ERR_NGROK_334`: 기존 ngrok 터널이 살아있음 → ngrok 창 종료 후 재실행
- `Invalid API key`: 요청 헤더의 `x-api-key`가 `.env`의 `API_KEY`와 일치하는지 확인 → 서버 재시작
- 루트 `Not Found`: 루트(/)는 라우트 없음 → `/health` 또는 `/news` 경로 호출


---

## 하이브리드 감성 분석 스코어링 로직 (Sentiment Scoring Logic)

현재 시스템은 **뉴스 도메인에 특화된 AI 모델**과 **가중치 기반 키워드 분석**을 결합한 하이브리드 엔진을 사용하여 높은 정확도를 제공합니다.

### 1. 핵심 구성 요소
- **AI 엔진**: `FISA-conclave/klue-roberta-news-sentiment` (뉴스 전문 분석 모델)
- **키워드 엔진**: 비즈니스 맥락을 반영한 3단계 가중치(Weight) 사전
- **융합 알고리즘**: AI의 문맥 이해력 + 키워드의 도메인 지식 결합

### 2. 가중치 계층 시스템 (Keyword Tiers)
단순 출현 횟수가 아닌, 단어의 중요도에 따라 감성 점수에 기여합니다.
- **Tier 3 (Critical - 2.0)**: 기사 성격을 결정짓는 핵심 키워드
  - 긍정: `신년사`, `비전`, `사상최대`, `신기록`, `팀스피릿`
  - 부정: `횡령`, `배임`, `파산`, `압수수색`, `적자전환`
- **Tier 2 (Strong - 1.5)**: 강력한 감성 신호
  - 긍정: `호재`, `흑자`, `승인`, `체결`, `상생`
  - 부정: `위기`, `패소`, `징계`, `과징금`, `수사`
- **Tier 1 (Standard - 1.0~1.3)**: 일반적인 지표성 단어
  - 긍정: `상승`, `개선`, `확대`, `혁신`, `도약`
  - 부정: `하락`, `부진`, `지연`, `악화`, `손실`

### 3. 정교한 결정 알고리즘
1. **시너지 증폭 (Momentum Boost)**:
   AI 예측 결과와 키워드 가중치 방향이 일치할 때, 확신도(Score)를 **최대 0.15** 추가로 증폭시켜 확실한 결과값을 제공합니다.
   
2. **거부권 시스템 (Veto Mechanism)**:
   AI가 문맥적으로 긍정(Positive)이라 판단하더라도, 본문에 `수사`, `혐의`, `배임` 등 **Tier 2 이상의 부정이 1.5점 이상** 감지되면 AI 신호를 중화시켜 오답을 방지합니다.

3. **기업 전략 보너스 (Strategy Anchor)**:
   비즈니스 선언(예: "백년 기업을 만들자")이 AI에 의해 부정으로 오해받는 것을 방지하기 위해, `신년사`, `비전` 등의 앵커 단어에는 **강력한 긍정 보정(+0.35~0.4)**을 적용합니다.

4. **텍스트 노이즈 정제**:
   분석 전 HTML 특수문자(`&quot;` 등)를 제거하고, 본문의 길이에 따라 신뢰도를 보정(짧을수록 보수적 판정)합니다.

### 4. 결과값 해석
- **Label**: `positive`, `negative`, `neutral`
- **Score**: `0.55 ~ 1.0` (높을수록 분석 결과의 확신도가 높음)
- **Neutral Range**: 증거가 희박하거나(evidence < margin) AI 신뢰도가 낮으면 자동으로 `neutral`로 분류하여 잘못된 필터링을 최소화합니다.
