# 기사 재구성 자동화 워크플로우 및 프롬프트 테스트
- 테스트 사용 모델 gemma3-27B
- 전체 과정은 [키워드 선정 → 기사 소싱 → 데이터 추출 → 광고 필터링 → 콘텐츠 생성]의 5단계로 진행

``` mermaid
graph TD
  %% 스타일 정의
  classDef input fill:#e1f5fe,stroke:#01579b,stroke-width:2px;
  classDef process fill:#f3e5f5,stroke:#4a148c,stroke-width:2px;
  classDef decision fill:#fff9c4,stroke:#fbc02d,stroke-width:2px;
  classDef output fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px;
  classDef stop fill:#ffebee,stroke:#b71c1c,stroke-width:2px;

  %% 1단계: 기획
  Start["User: 키워드 선정 및 구글 시트 입력"]:::input --> Select["기사 선정 및 클러스터링"]:::process

  %% 2단계: 필터링 조건
  Select --> CheckTime{매체별 유효 기간 만족 여부}:::decision
  CheckTime -->|No| Drop1["제외"]:::stop
  CheckTime -->|Yes| CheckBan{금지 키워드: 투표/순위/브랜드평판}:::decision

  CheckBan -->|Yes| Drop2["제외"]:::stop
  CheckBan -->|No| Extract["원문 URL 추출 및 정규화"]:::process

  %% 3단계: AI 광고 판별
  Extract --> AI_Check{AI 광고 판별: ad_news yes/no}:::decision
  AI_Check -->|Yes| Skip["Skip: 해당 키워드 건너뜀"]:::stop
  AI_Check -->|No| Gen["기사 재구성 및 생성"]:::output

  %% 4단계: 완료
  Gen --> End((최종 완료)):::output

```



## Phase 1. 기획 및 소싱 (Planning & Sourcing)

<br>

### Step 1. 키워드 선정 및 세팅
- **담당:** 슬희 매니저님 
- **액션:** 트렌드 키워드 선정 후 구글 시트(Google Sheets)에 입력

<br>

### Step 2. 기사 선정 (Filtering)


**1) 매체별 권장 사용 시점**

| **매체 분류**     | **기사 유효 기간 (작성일 기준)** |
| ------------- | --------------------- |
| **중앙 / 잡포스트** | 3일 전 ~ 14일 전          |
| **톱스타뉴스**     | 24시간 이내 ~ 14일 전       |
| **일반 연예 뉴스**  | 2일 전 ~ 7일 전           |


**2) 기사 선정 우선순위**
1. **클러스터링:** 동일 키워드로 묶인 기사 수가 많은 것 우선
2. **최신성:** 클러스터 조건 충족 시, 더 최신 기사 선택
    - _예: 동일 클러스터 내 [5일 전] vs [10일 전] → **5일 전 기사 채택**_
        

**3) 작성 금지 및 제외 대상**
> **아래 유형은 클러스터링 여부와 관계없이 제외.**
> - 연예 관련 투표 / 순위 / 브랜드 평판 관련 기사
> - 기업 브랜드 평판 관련 기사


<br>

## Phase 2. 데이터 처리 및 검증 (Processing & QC)

<br>

### Step 3. 데이터 추출
- **Input:** 선정된 기사 URL 리스트
- **Action:** URL 스크래핑 → 기사 본문 텍스트 추출
    

<br>

### Step 4. 광고성 기사 검증 (Ad Detection)
추출된 본문을 LLM을 통해 분석하여 '정상 기사'와 '광고성 기사'를 분류

**1) 판별 로직**
- **판별 모델:** 광고성 기사 판별 전용 LLM
    
- **Decision Flow:**
    - 🟢 `"ad_news": "no"` (정상) → **[Step 5. 기사 생성]** 단계로 이동
    - 🔴 `"ad_news": "yes"` (광고) → **해당 키워드 건너뜀 (Skip)**
        - _Note: 추후 다중화 등을 통해 대체 기사 탐색 로직 보강 필요_
            
**2) 판별 프롬프트 (System Prompt)**

<details>
  <summary>📄 프롬프트 전문 보기 (클릭)</summary>

```text
# Role
당신은 저널리즘 텍스트 분석 AI입니다. 입력된 [content]의 기사 텍스트를 분석하여, 해당 기사가 공익적 정보 전달을 목적으로 하는 '일반 기사'인지, 특정 영리 목적(판촉)을 우선적으로 달성하기 위해 작성된 '광고성 기사(Advertorial)'인지 [keyword]의 기사를 판별한 후 JSON 형식으로 반환하십시오.

# Goal (High Precision Filter)
- 목표는 광고성 기사의 “완전 차단”이 아닌 “명백한 광고성만 배제”임을 명심할 것
- 애매하거나 근거가 약하면 항상 `ad_news: no`로 판정할 것 (보수적 판정)

# Definition (Advertorial)
뉴스 형식을 띠지만, 기사 구조·서술·정보 선택이 특정 대상(상품/서비스/브랜드/업체)의 이용·거래·전환을 직접적으로 촉진하도록 설계된 텍스트

# Minimal Detection Logic
아래 “결정 신호”가 기사 전체의 핵심 축인지 확인하라. 단순한 긍정 서술, 기능 설명, 인터뷰 톤만으로는 광고성으로 판단하지 말 것

## A. 결정 신호 (Decisive Signals)
A1) 독자(소비자)에게 특정 행동을 하도록 직접 유도하는 문장/구조가 중심
A2) 독자가 즉시 거래/이용을 실행할 수 있도록 하는 실행 정보(접점·경로·절차)가 핵심 서술
A3) 거래 조건을 구성하는 정보(대가·혜택·제한·조건·기간 등)가 핵심 서술
A4) 상업적 협업/유상 게재/판촉 목적을 드러내는 표지가 존재

## B. 보조 신호 (Supporting Signals)
B1) 정보 출처가 이해관계자 단일 관점에 과도하게 의존 (외부 검증 결여)
B2) 사실 전달보다 장점·효용·성과를 누적해 설득하는 구성 (전환 최적화)
B3) 특정 대상의 명칭/정체성이 불필요할 정도로 반복·강조됨

# Decision Rule (Conservative)
- `ad_news: yes` 조건:
  1) A4 존재 + 판촉 목적 정합
  2) A1~A3 중 "두 가지 이상" 동시 존재 + 기사 중심
  3) A1~A3 중 "한 가지"라도 기사 전체 지배(B2/B3 결합) + 독자 전환 직접 겨냥
- 그 외 모든 경우는 `ad_news: no`

# Exception Handling
- 공익적 맥락, 단순 안내/정리/기록 성격은 `ad_news: no`

# Output Format (JSON only)
{
  "ad_news": "yes" or "no",
  "reason": "결정 신호 중심으로 판단한 핵심 구조적 이유 한 문장 요약"
}

```
</details> 



<br>


## Phase 3. 콘텐츠 생성 (Production)

<br>


### Step 5. 기사 재구성 및 생성

- **Input:** 검증이 완료된 정상 기사 본문
- **Action:** 기사 재구성(News Recomposition) 로직에 따라 새로운 콘텐츠 생성 및 최종 검수


<br>



## 필터 기사 목록, 지표 계산 (Filtered news list & Score)

### 1. 필터 기사 목록
#### 1) 광고 기사를 광고 기사로 판단한 경우(TP)

1. https://www.apparelnews.co.kr/news/news_view/?idx=222117
	어비험즈, 엠버서더로 체리블렛 출신 허지원 발탁
2. https://www.apnews.kr/news/articleView.html?idxno=3037101
	스프라이트, '워터밤 2025' 성료…카리나와 상쾌한 에너지 전달
3. https://www.yna.co.kr/view/AKR20251212143400017?input=1195m
	[AI픽] LGU+, '구글 AI 프로' 제휴 상품 출시
4. https://www.dailian.co.kr/news/view/1494439/?sc=Naver
	모두투어, 프리미엄 수요 겨냥 '모두시그니처 대만' 신상품 출시
5. https://www.joongangenews.com/news/articleView.html?idxno=411327
	스프라이트X카리나, 매운맛 ‘찢었다’…새 광고 공개
6. https://fashionbiz.co.kr/article/215690
	나이키, 여성 최초 1마일 4분 돌파 프로젝트 ‘브레이킹 4’ 발표
7. https://www.paxetv.com/news/articleView.html?idxno=221071
	"특별함 더한 전용 디자인"...제네시스, 'G80 블랙' 판매 개시
8. https://n.news.naver.com/mnews/article/092/0002402366?sid=105
	KT, ‘12월 달달혜택’ 공개…케이크·공연 최대 반값


#### 2) 광고가 아닌 기사를 정상 기사로 판단한 경우(TN)
1. https://www.edaily.co.kr/News/Read?newsId=02912646642397864&mediaCodeNo=257&OutLnkChk=Y
	LG유플러스, 제주교육청과 손잡고 교원 행정업무 줄인다
2. https://www.yna.co.kr/view/AKR20251216098700017?input=1195m
	창립 5주년 리벨리온 "논 엔비디아 흐름 선도 선봉장 될 것"
3. https://www.sedaily.com/NewsView/2H1R3F3V7C
	삼성·SK, 엔비디아에 HBM4 ‘사실상 공급’…가격·물량 최종 조율 남아 [갭 월드]
4. https://www.newsis.com/view/NISX20251215_0003441692
	공연 예매사이트도 해킹 당했다…플레이티켓 회원정보 유출
5. https://www.ajunews.com/view/20251216080003571 
	"최대 6000만원 무이자"...서울시 '보증금지원형 장기안심주택' 모집
6. https://view.asiae.co.kr/article/2025121508564785889
	LG유플러스, 구세군과 'QR코드 자선냄비' 캠페인 진행
7. https://www.nocutnews.co.kr/news/6443624?utm_source=naver&utm_medium=article&utm_campaign=20251216100650
	LG유플러스, 오픈AI 기술로 '똑똑한' 전화 응대 서비스 제공
8. https://zdnet.co.kr/view/?no=20251216104110
	엔비디아 '네모트론 3' 공개..."개인 PC로 나만의 AI 비서 구축"
9. https://m.entertain.naver.com/home/article/052/0002287983
	황찬성, 도쿄 추가 공연으로 일본 솔로 투어 마무리
10. https://n.news.naver.com/mnews/article/003/0013659778?sid=102
	[담양소식] 담양 원도심서 24~25일 성탄 특별공연 등
11. https://sports.khan.co.kr/article/202512120828003?pt=nv
	임영웅 웃다···올 매진!
12. https://www.xportsnews.com/article/2089339
	임영웅 팬클럽 '영웅시대 서부은평방', 은평구에 성금 1,000만 원 전달
13. https://m.entertain.naver.com/home/article/001/0015798004
	[가요소식] 군 복무 마친 NCT 태용, 내달 단독 콘서트
14. https://m.entertain.naver.com/home/article/437/0000469002
	세븐틴 에스쿱스X민규, 인천 공연 선예매 매진
15. https://m.entertain.naver.com/home/article/609/0001070007
	D-1 ‘아바타:불과 재’ 예매율 74%→47만명 넘겼다


#### 3) 광고가 아닌 기사를 광고 기사로 판단한 경우(FP)
1. https://www.etnews.com/20251216000274
	LGU+, RCS 기반 '안심문자' 도입…스미싱 원천 차단


#### 4) 광고인 기사를 정상 기사로 판단한 경우(FN)
현재 표본에서는 없음


<br>

# 필터링 성능

현재 사용 중인 광고 판별 LLM 모델의 성능 간단 테스트

### 1. Confusion Matrix (분류 결과)

|**구분**|**설명**|**건수**|**주요 사례**|
|---|---|---|---|
|**TP** (True Positive)|광고를 **광고로** 정확히 판단|**8건**|LGU+ 제휴상품, 스프라이트x카리나, 나이키 프로모션 등|
|**TN** (True Negative)|정상을 **정상으로** 정확히 판단|**15건**|기업 활동, 콘서트 소식, 사회 공헌, 단순 사건 보도 등|
|**FP** (False Positive)|정상을 **광고로** 잘못 판단 (오탐)|**1건**|LGU+ RCS 안심문자 (서비스 소개를 광고로 오인 추정)|
|**FN** (False Negative)|광고를 **정상으로** 잘못 판단 (미탐)|**0건**|_(현재 표본 내 발견되지 않음)_|

<br>

### 2. 성능 지표 (Metrics)

현재까지는 목표한 정상 기사 보존 에 적합한 성능을 보임
- **Precision (정밀도):** **88.9%**
    - 모델이 "광고"라고 지목한 것 중 실제 광고인 비율 ($8/9$)
- **Specificity (특이도):** **93.75%** 
    - 정상 기사를 버리지 않고 살려낸 비율 ($15/16$)
    - 오탐률(FPR) **6.25%**
- **Accuracy (정확도):** **95.83%** (FN=0 가정 시)
    - 전체적인 분류 정확도 ($23/24$)


