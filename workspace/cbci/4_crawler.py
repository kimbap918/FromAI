"""
4_crawler.py

✅ 목표:
- 날짜(days_back) 없이 자동 증분 크롤링 (연합뉴스 API)
- 마지막 크롤링 날짜 +1일 ~ 오늘까지 수집
- 삽입 전 중복 제거:
  1) CID 기준 (기업(GROUP) 단위)
  2) 제목 유사/중복 (기업(GROUP) 단위)
- 감성 분석 통합: 실시간 수집 시 AI 감성 분석 및 하이브리드 스코어링 적용

✅ 주요 기능:
1) 자동 증분 크롤링: MongoDB 및 파일 상태를 기반으로 중복 없이 최신 뉴스 수집
2) 감성 분석 백필: 기존에 저장된 기사들에 대한 사후 감성 분석 기능
3) 중복 정리: MongoDB 내의 기존 중복 데이터(CID/제목) 탐지 및 삭제

사용 예)
1) 일반 크롤링 (매일 자동 증분 + 감성 분석 포함):
   python 4_crawler.py

2) 감성 분석 백필 (미분석 기사 대상):
   python 4_crawler.py --backfill-sentiment --backfill-limit 500

3) 감성 분석 강제 재분석 (기존 결과 덮어쓰기):
   python 4_crawler.py --backfill-sentiment --backfill-limit 500 --force

4) 기존 중복 데이터 정리 (DRY RUN):
   python 4_crawler.py --cleanup-existing

5) 기존 중복 데이터 실제 삭제 적용:
   python 4_crawler.py --cleanup-existing --apply
"""

import requests
import csv
import json
import re
import time
import os
import sys
import argparse
import difflib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, time as dtime, date as ddate
from typing import Optional, Dict, Tuple, List, Any
from urllib.parse import urljoin
from urllib3.util import create_urllib3_context
from fake_useragent import UserAgent
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

load_dotenv()

# =========================
# ✅ 최초 실행 시 자동 수집 범위(사용자 설정 불필요)
# =========================
BOOTSTRAP_DAYS = 120  # state도 Mongo도 없으면 최근 120일부터 첫 수집

try:
    from pymongo import MongoClient, UpdateOne
    from bson import ObjectId
except Exception:
    MongoClient = None
    UpdateOne = None
    ObjectId = None

KST = ZoneInfo("Asia/Seoul")

# 감성 분석 서비스(로컬, 무비용)
try:
    from sentiment_service import service as sentiment_service
except Exception:
    sentiment_service = None


# =========================
# ✅ 설정(날짜 관련 설정 없음)
# =========================
@dataclass
class CrawlConfig:
    # 속도/페이징
    page_size: int = 15
    timeout: int = 10
    sleep_sec: float = 0.7
    max_pages: int = 20

    # 엔드포인트
    base_url: str = "https://ars.yna.co.kr/api/v2/search.basic"
    results_key: str = "YIB_KR_A"

    # 필터
    cattr: str = "A"
    div_code: str = "01,02,05,11"
    scope: str = "all"
    sort: str = "date"
    channel: str = "basic_kr"

    # 저장
    output_prefix: str = "yna_news"

    # 디버그
    debug_total: bool = True
    debug_top_keys: bool = False

    # 본문/이미지 크롤링
    fetch_content: bool = True
    fetch_image: bool = True
    content_timeout: int = 12
    content_sleep_sec: float = 0.35
    content_max_chars: int = 30000
    content_retries: int = 2
    content_retry_backoff: float = 1.3

    # MongoDB 업로드
    upload_to_mongo: bool = True
    mongo_uri: str = os.getenv("MONGO_URI", "")
    mongo_db: str = os.getenv("MONGO_DB", "news")
    mongo_collection: str = os.getenv("MONGO_COL", "yna_news")
    mongo_upsert: bool = True
    mongo_batch_size: int = 500
    mongo_ensure_unique_cid: bool = False  # 중복 정리 후 True 권장

    # ✅ 감성 분석 설정
    sentiment_enabled: bool = True
    sentiment_filter: List[str] = field(default_factory=list) # 예: ['positive', 'negative']만 유지

    # 마지막 크롤링 날짜(state) 저장 경로
    state_path: str = "crawler_state.json"

    # ✅ (삽입 전) CID/제목 중복 제거 옵션
    pre_insert_dedup_enable: bool = True

    # 1차 CID dedup: DB에도 같은 CID가 있으면 스킵(권장)
    pre_insert_skip_if_cid_exists_in_db: bool = True

    # 2차 제목 유사/중복 필터
    title_dedup_enable: bool = True
    title_similarity_threshold: float = 0.93   # difflib ratio
    title_jaccard_threshold: float = 0.88      # token jaccard
    title_dedup_db_lookup: bool = True         # DB 최근 기사와도 비교
    title_dedup_db_limit_per_group: int = 3000 # 그룹별 최근 N개 제목 로드
    title_dedup_compare_recent_keep: int = 300 # 배치 내 최근 유지 제목 비교 개수(속도)
    title_dedup_only_within_days: int = 3      # 너무 오래된 기사와는 비교 안 함(오탐 방지)
    title_dedup_verbose: bool = True

    # 추가 파라미터 주입(필요 시)
    extra_params: dict = field(default_factory=dict)


CONFIG = CrawlConfig(
    div_code="01,02,05,11",
    cattr="A",
    fetch_content=True,
    fetch_image=True,
    upload_to_mongo=True,
    debug_total=True,
    max_pages=20,
    mongo_ensure_unique_cid=False,
    state_path="crawler_state.json",
)


# =========================
# ✅ state: 마지막 크롤링 날짜 저장/로드
# =========================
def load_last_crawled_date(path: str) -> Optional[ddate]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        s = (obj.get("last_crawled_date_kst") or "").strip()
        if not s:
            return None
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def save_last_crawled_date(path: str, d: ddate) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "last_crawled_date_kst": d.strftime("%Y-%m-%d"),
                "saved_at_kst": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )


# =========================
# ✅ MongoDB에서 마지막 "시각"(datetime) 자동 감지
# =========================
def detect_last_dt_from_mongo(config: CrawlConfig) -> Optional[datetime]:
    """문서의 DATETIME 필드에서 가장 최신 시각을 datetime으로 반환.
    - 우선 BSON date 타입을 확인(정확한 시간)
    - 다음 문자열 타입(YYYY-MM-DD HH:MM:SS) 파싱
    - 둘 다 없으면 None
    """
    if not config.upload_to_mongo or not MongoClient or not config.mongo_uri:
        return None
    client = None
    try:
        client = MongoClient(config.mongo_uri, serverSelectionTimeoutMS=4000)
        col = client[config.mongo_db][config.mongo_collection]

        # 1) DATETIME(date) 최신
        doc = list(
            col.find({"DATETIME": {"$type": "date"}}, {"DATETIME": 1})
            .sort("DATETIME", -1)
            .limit(1)
        )
        if doc:
            dtv = doc[0].get("DATETIME")
            if isinstance(dtv, datetime):
                # BSON datetime은 UTC일 수 있으나, 본 코드는 naive로 취급
                return dtv.replace(tzinfo=None)

        # 2) DATETIME(string) 최신 (형식이 YYYY-MM-DD HH:MM:SS면 시간까지 반영)
        doc2 = list(
            col.find({"DATETIME": {"$type": "string"}}, {"DATETIME": 1})
            .sort("DATETIME", -1)
            .limit(1)
        )
        if doc2:
            s = (doc2[0].get("DATETIME") or "").strip()
            if s:
                try:
                    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass

        return None
    except Exception:
        return None
    finally:
        try:
            if client:
                client.close()
        except Exception:
            pass


# =========================
# ✅ MongoDB에서 마지막 날짜 자동 감지(하위 호환: date 단위)
# =========================
def detect_last_date_from_mongo(config: CrawlConfig) -> Optional[ddate]:
    if not config.upload_to_mongo or not MongoClient or not config.mongo_uri:
        return None
    client = None
    try:
        client = MongoClient(config.mongo_uri, serverSelectionTimeoutMS=4000)
        col = client[config.mongo_db][config.mongo_collection]

        # DATETIME(date) 최신
        doc = list(
            col.find({"DATETIME": {"$type": "date"}}, {"DATETIME": 1})
            .sort("DATETIME", -1)
            .limit(1)
        )
        if doc:
            dtv = doc[0].get("DATETIME")
            if isinstance(dtv, datetime):
                return dtv.date()

        # DATETIME(string) 최신 (형식이 YYYY-MM-DD HH:MM:SS면 문자열 정렬 OK)
        doc2 = list(
            col.find({"DATETIME": {"$type": "string"}}, {"DATETIME": 1})
            .sort("DATETIME", -1)
            .limit(1)
        )
        if doc2:
            s = (doc2[0].get("DATETIME") or "").strip()
            if s:
                try:
                    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").date()
                except Exception:
                    pass

        return None
    except Exception:
        return None
    finally:
        try:
            if client:
                client.close()
        except Exception:
            pass


# =========================
# ✅ 이번 실행의 since_dt 자동 계산 (시간 단위, 겹침 보장)
# =========================
def compute_since_dt_auto(config: CrawlConfig) -> Optional[datetime]:
    # 1) Mongo 최신 시각 우선
    last_dt = detect_last_dt_from_mongo(config)
    source = "mongo-dt" if last_dt else ""

    # 2) 하위호환: 날짜(state/mongo-date) 기반
    if last_dt is None:
        last_date = load_last_crawled_date(config.state_path)
        src2 = "state" if last_date else ""
        if last_date is None:
            last_date = detect_last_date_from_mongo(config)
            src2 = "mongo-date" if last_date else "bootstrap"
        if last_date is None:
            start_dt = (datetime.now(KST).replace(tzinfo=None) - timedelta(days=BOOTSTRAP_DAYS))
            print(f"🟡 state/mongo 없음 → 자동 부트스트랩: 최근 {BOOTSTRAP_DAYS}일 수집 (since={start_dt})")
            return start_dt
        # 날짜만 있을 때는 자정부터 시작(과거 로직 호환)
        last_dt = datetime.combine(last_date, dtime.max).replace(microsecond=0)
        source = src2

    # 3) 겹침(Overlap) 적용: 최근 수집 시각에서 일정 시간 이전으로 당겨 수집
    OVERLAP_MINUTES = 120  # 2시간 겹침으로 누락 방지
    since_dt = (last_dt - timedelta(minutes=OVERLAP_MINUTES))
    print(f"🟢 자동 증분 기준({source}): last_dt={last_dt} → overlap={OVERLAP_MINUTES}m → since={since_dt}")
    return since_dt


# =========================
# SSL 이슈 해결 어댑터
# =========================
class LegacySSLAdapter(requests.adapters.HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.load_default_certs()
        ctx.options |= 0x4  # ssl.OP_LEGACY_SERVER_CONNECT
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


# =========================
# UA/헤더
# =========================
def safe_user_agent():
    try:
        ua = UserAgent()
        return ua.random
    except Exception:
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )


def headers_for_api():
    return {
        "User-Agent": safe_user_agent(),
        "Referer": "https://www.yna.co.kr/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    }


def headers_for_html():
    return {
        "User-Agent": safe_user_agent(),
        "Referer": "https://www.yna.co.kr/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "keep-alive",
    }


# =========================
# 유틸(쿼리/정규화)
# =========================
def build_queries_company_plus_person(company_kw: str, person_kw: str) -> List[str]:
    company_kw = (company_kw or "").strip()
    person_kw = (person_kw or "").strip()
    if company_kw and person_kw:
        return [f"{company_kw} {person_kw}"]
    return []


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines).strip()


# =========================
# ✅ 제목 중복(유사도)용 정규화
# =========================
_TITLE_TAGS_RE = re.compile(r"(\[.*?\]|\(.*?\))")
_TITLE_PUNCT_RE = re.compile(r"[^\w가-힣\s]")
_TITLE_WS_RE = re.compile(r"\s+")
_COMMON_NOISE = [
    "속보", "종합", "단독", "사진", "영상", "그래픽", "인터뷰", "르포",
    "재송고", "수정", "정정", "추가", "업데이트"
]

def title_key(title: str) -> str:
    if not title:
        return ""
    t = title.strip()
    # 괄호/대괄호 태그 제거
    t = _TITLE_TAGS_RE.sub(" ", t)
    # 흔한 노이즈 단어 제거(너무 공격적이면 여기 줄이면 됨)
    for w in _COMMON_NOISE:
        t = re.sub(rf"\b{re.escape(w)}\b", " ", t, flags=re.IGNORECASE)
    t = t.lower()
    t = _TITLE_PUNCT_RE.sub(" ", t)
    t = _TITLE_WS_RE.sub(" ", t).strip()
    return t

def tokenize_title(tkey: str) -> List[str]:
    if not tkey:
        return []
    toks = [x for x in tkey.split() if x]
    # 1글자 토큰은 노이즈가 많아서 제거
    toks = [x for x in toks if len(x) >= 2]
    return toks

def jaccard(a: List[str], b: List[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)

def sim_ratio(a: str, b: str) -> float:
    # difflib은 길이가 길어도 꽤 안정적
    return difflib.SequenceMatcher(None, a, b).ratio()

def is_title_duplicate(a_title: str, b_title: str, cfg: CrawlConfig) -> bool:
    ak = title_key(a_title)
    bk = title_key(b_title)
    if not ak or not bk:
        return False
    if ak == bk:
        return True
    r = sim_ratio(ak, bk)
    if r >= cfg.title_similarity_threshold:
        return True
    ja = jaccard(tokenize_title(ak), tokenize_title(bk))
    if ja >= cfg.title_jaccard_threshold:
        return True
    return False


# =========================
# ✅ 본문 정리(연합뉴스 UI 제거)
# =========================
_UI_TOKENS = ("구독", "구독중", "이전", "다음", "이미지 확대", "이미지확대")
_UI_LINE_RE = re.compile(r"^\s*(구독|구독중|이전|다음|이미지\s*확대|이미지확대)\s*$")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@yna\.co\.kr\b", re.IGNORECASE)
_OKJEBO_PHRASE_RE = re.compile(r"제보는\s*카카오톡\s*okjebo", re.IGNORECASE)
_COPYRIGHT_RE = re.compile(
    r"(저작권자\s*\(c\)\s*연합뉴스|무단\s*전재|재배포\s*금지|연합뉴스\s*무단|ⓒ\s*연합뉴스)",
    re.IGNORECASE,
)
_RELATED_HEADER_RE = re.compile(r"^\s*관련\s*뉴스\s*$|^\s*관련뉴스\s*$|^\s*관련\s*기사\s*$|^\s*관련기사\s*$")

def pre_split_glued_ui_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"(관련\s*뉴스|관련뉴스|관련\s*기사|관련기사)", r"\n\1\n", text)
    text = re.sub(r"(이전)\s*(다음)", r"\1\n\2", text)
    text = re.sub(r"(다음)(?=[가-힣])", r"\1\n", text)
    text = re.sub(r"(다음)(?=[A-Za-z0-9._%+-]+@)", r"\1\n", text)
    text = re.sub(r"(이미지\s*확대)(?=[가-힣])", r"\1\n", text)
    text = re.sub(r"(이미지확대)(?=[가-힣])", r"\1\n", text)
    text = re.sub(r"(다음)\s*(<저작권자)", r"\1\n\2", text)
    return text

def remove_reporter_ui_blocks_anywhere(lines: List[str]) -> List[str]:
    out = []
    i = 0
    n = len(lines)

    def is_name_like(s: str) -> bool:
        s = s.strip()
        if not (2 <= len(s) <= 10):
            return False
        return bool(re.fullmatch(r"[가-힣·\s]+", s))

    while i < n:
        cur = lines[i].strip()

        if i + 1 < n and lines[i + 1].strip() == "기자" and is_name_like(cur):
            i += 2
            while i < n:
                t = lines[i].strip()
                if _UI_LINE_RE.match(t):
                    i += 1
                    continue
                if any(tok in t for tok in _UI_TOKENS) and len(t) <= 24:
                    i += 1
                    continue
                break
            continue

        if re.fullmatch(r"[가-힣·\s]{2,10}\s*기자", cur):
            i += 1
            while i < n and _UI_LINE_RE.match(lines[i].strip()):
                i += 1
            continue

        out.append(lines[i])
        i += 1

    return out

def is_headline_like(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if len(s) < 8 or len(s) > 140:
        return False
    if _UI_LINE_RE.match(s) or s == "기자":
        return False
    if _OKJEBO_PHRASE_RE.search(s) or _COPYRIGHT_RE.search(s):
        return False
    if any(ch in s for ch in ["…", "\"", "“", "”", "(", ")", "·", "—", "-"]):
        return True
    if re.search(r"\d", s):
        return True
    if s.endswith(".") or s.endswith("다.") or s.endswith("다"):
        return False
    return False

def remove_related_news_blocks(lines: List[str]) -> List[str]:
    out = []
    i = 0
    n = len(lines)

    while i < n:
        ln = lines[i].strip()
        if _RELATED_HEADER_RE.match(ln):
            i += 1
            while i < n and is_headline_like(lines[i]):
                i += 1
            continue
        out.append(lines[i])
        i += 1

    return out

def clean_yna_content(text: str) -> str:
    if not text:
        return ""

    text = pre_split_glued_ui_text(text)
    text = _OKJEBO_PHRASE_RE.sub("", text)
    text = _EMAIL_RE.sub("", text)
    text = re.sub(r"\(\s*\)", "", text)

    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]

    lines = [ln for ln in lines if not _UI_LINE_RE.match(ln)]
    lines = remove_related_news_blocks(lines)
    lines = remove_reporter_ui_blocks_anywhere(lines)
    lines = [ln for ln in lines if not _OKJEBO_PHRASE_RE.search(ln)]

    cut_idx = None
    for idx, ln in enumerate(lines):
        if _COPYRIGHT_RE.search(ln):
            cut_idx = idx
            break
        if ln.startswith("<저작권자") or ln.startswith("＜저작권자"):
            cut_idx = idx
            break
    if cut_idx is not None:
        lines = lines[:cut_idx]

    cleaned = "\n".join(lines).strip()
    cleaned = re.sub(r"[ \t]+", " ", cleaned).strip()
    return cleaned


# =========================
# ✅ 이미지 URL 정리
# =========================
_IMG_HOST_PATH_RE = re.compile(r"^/img\d+\.yna\.co\.kr/")

def absolutize_img_url(src: str, base_url: str) -> str:
    if not src:
        return ""
    src = src.strip()
    if not src or src.startswith("data:"):
        return ""

    if src.startswith("http://") or src.startswith("https://"):
        return src
    if src.startswith("//"):
        return "https:" + src
    if _IMG_HOST_PATH_RE.match(src):
        return "https://" + src.lstrip("/")
    return urljoin(base_url, src)

def uniq_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        if not x:
            continue
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


# =========================
# 목록 API 호출(페이징 지원)
# =========================
def fetch_articles_paged(session: requests.Session, config: CrawlConfig, query: str, since_dt: datetime):
    collected = []
    last_raw = None

    for page_no in range(1, config.max_pages + 1):
        params = {
            "query": query,
            "page_no": page_no,
            "page_size": config.page_size,
            "scope": config.scope,
            "sort": config.sort,
            "channel": config.channel,
            "div_code": config.div_code,
            "cattr": config.cattr,
        }
        if config.extra_params:
            params.update(config.extra_params)

        resp = session.get(config.base_url, params=params, headers=headers_for_api(), timeout=config.timeout)
        resp.raise_for_status()
        data = resp.json()
        last_raw = data

        if config.debug_top_keys and page_no == 1:
            print("DEBUG top keys:", list(data.keys())[:10])

        if config.results_key not in data:
            break

        if config.debug_total and page_no == 1:
            total = data.get(config.results_key, {}).get("total")
            print(f"DEBUG total({query}):", total)

        results = data[config.results_key].get("result", []) or []
        if not results:
            break

        stop_paging = False
        for art in results:
            cid = art.get("CID")
            dt_str = art.get("DATETIME")
            title = art.get("TITLE") or ""

            if not cid or not dt_str:
                continue

            try:
                art_dt = datetime.strptime(dt_str, "%Y%m%d%H%M%S")  # KST 로컬로 간주
            except Exception:
                continue

            if art_dt < since_dt:
                stop_paging = True
                continue

            collected.append({
                "CID": cid,
                "TITLE": title.replace("<b>", "").replace("</b>", ""),
                "DATETIME": art_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "URL": f"https://www.yna.co.kr/view/{cid}",
            })

        if stop_paging:
            break
        if len(results) < config.page_size:
            break

        time.sleep(0.15)

    return collected, last_raw


# =========================
# ✅ 본문/이미지 추출(HTML)
# =========================
def try_extract_from_jsonld_text(soup: BeautifulSoup):
    scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
    for sc in scripts:
        raw = sc.get_text(strip=True)
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue

        candidates = obj if isinstance(obj, list) else [obj]
        for it in candidates:
            if not isinstance(it, dict):
                continue
            body = it.get("articleBody") or it.get("description")
            if isinstance(body, str):
                body = clean_yna_content(normalize_text(body))
                if len(body) >= 80:
                    return body, "jsonld"
    return "", ""

def best_text_block_by_heuristic(soup: BeautifulSoup):
    best_text = ""
    best_src = ""
    best_score = 0

    for tag in soup.find_all(["article", "div", "section"], limit=4000):
        ident = " ".join(
            filter(
                None,
                [
                    tag.get("id", ""),
                    " ".join(tag.get("class", []) if tag.get("class") else []),
                ],
            )
        ).lower()

        if any(x in ident for x in ["nav", "menu", "footer", "header", "aside", "banner", "ad", "promo", "related", "share"]):
            continue

        text = normalize_text(tag.get_text("\n"))
        if len(text) < 250:
            continue

        p_cnt = len(tag.find_all("p"))
        score = len(text) + p_cnt * 120

        a_cnt = len(tag.find_all("a"))
        if a_cnt >= 25 and p_cnt == 0:
            continue

        if score > best_score:
            best_score = score
            best_text = text
            best_src = "heuristic"

    best_text = clean_yna_content(best_text)
    return best_text, best_src

def extract_yna_content(html: str):
    soup = BeautifulSoup(html, "html.parser")

    for t in soup(["script", "style", "noscript"]):
        t.decompose()

    body, src = try_extract_from_jsonld_text(soup)
    if body:
        return body, src

    selectors = [
        "#articleBodyContents",
        "#articleBody",
        "#articleWrap",
        ".story-news",
        ".article",
        ".content01",
        "article",
    ]

    best_text = ""
    best_src = ""
    for sel in selectors:
        node = soup.select_one(sel)
        if not node:
            continue
        text = clean_yna_content(normalize_text(node.get_text("\n")))
        if len(text) > len(best_text):
            best_text = text
            best_src = f"selector:{sel}"

    if best_text and len(best_text) >= 80:
        return best_text, best_src

    text2, src2 = best_text_block_by_heuristic(soup)
    if text2 and len(text2) >= 80:
        return text2, src2

    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        text3 = clean_yna_content(normalize_text(meta["content"]))
        if len(text3) >= 40:
            return text3, "meta:description"

    return "", "empty"

def extract_yna_images(html: str, article_url: str):
    soup = BeautifulSoup(html, "html.parser")
    urls = []
    source = "empty"

    m = soup.find("meta", attrs={"property": "og:image"})
    if m and m.get("content"):
        u = absolutize_img_url(m["content"], article_url)
        if u:
            urls.append(u)
            source = "meta:og:image"

    m = soup.find("meta", attrs={"name": "twitter:image"})
    if m and m.get("content"):
        u = absolutize_img_url(m["content"], article_url)
        if u:
            urls.append(u)
            if source == "empty":
                source = "meta:twitter:image"

    scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
    for sc in scripts:
        raw = sc.get_text(strip=True)
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        candidates = obj if isinstance(obj, list) else [obj]
        for it in candidates:
            if not isinstance(it, dict):
                continue
            img = it.get("image")
            img_url = ""
            if isinstance(img, str):
                img_url = img
            elif isinstance(img, list) and img:
                img_url = img[0] if isinstance(img[0], str) else ""
            elif isinstance(img, dict):
                img_url = img.get("url") or img.get("@id") or ""
            img_url = absolutize_img_url(img_url, article_url)
            if img_url:
                urls.append(img_url)
                if source == "empty":
                    source = "jsonld:image"

    for img_tag in soup.select("figure.image-zone01 img"):
        cand = img_tag.get("src") or img_tag.get("data-src") or img_tag.get("data-original")
        cand = absolutize_img_url(cand, article_url)
        if cand:
            urls.append(cand)
            if source == "empty":
                source = "selector:figure.image-zone01"

    selectors = [
        "#articleBodyContents img",
        "#articleBody img",
        "#articleWrap img",
        ".story-news img",
        ".article img",
        ".content01 img",
        "article img",
    ]
    for sel in selectors:
        for img_tag in soup.select(sel):
            cand = img_tag.get("src") or img_tag.get("data-src") or img_tag.get("data-original")
            cand = absolutize_img_url(cand, article_url)
            if cand:
                urls.append(cand)
                if source == "empty":
                    source = f"selector:{sel}"

    urls = uniq_keep_order(urls)
    primary = urls[0] if urls else ""
    return primary, urls, source

def fetch_article_page(session: requests.Session, config: CrawlConfig, url: str):
    last_err = ""
    for attempt in range(config.content_retries + 1):
        try:
            resp = session.get(url, headers=headers_for_html(), timeout=config.content_timeout)
            status = resp.status_code

            if status in (403, 429, 500, 502, 503, 504) and attempt < config.content_retries:
                time.sleep(config.content_retry_backoff ** (attempt + 1))
                continue

            resp.raise_for_status()

            if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
                resp.encoding = resp.apparent_encoding

            html = resp.text

            content, content_source = extract_yna_content(html)
            if config.content_max_chars and len(content) > config.content_max_chars:
                content = content[: config.content_max_chars].rstrip() + "\n...(truncated)"

            image_url, image_urls, image_source = ("", [], "disabled")
            if config.fetch_image:
                image_url, image_urls, image_source = extract_yna_images(html, url)

            if not content or len(content.strip()) < 80:
                return {
                    "content": "",
                    "content_len": 0,
                    "content_status": f"EMPTY_HTTP_{status}",
                    "content_source": content_source,
                    "image_url": image_url,
                    "image_urls": image_urls,
                    "image_source": image_source,
                }

            return {
                "content": content,
                "content_len": len(content),
                "content_status": "OK",
                "content_source": content_source,
                "image_url": image_url,
                "image_urls": image_urls,
                "image_source": image_source,
            }

        except Exception as e:
            last_err = str(e)
            if attempt < config.content_retries:
                time.sleep(config.content_retry_backoff ** (attempt + 1))
                continue

    return {
        "content": "",
        "content_len": 0,
        "content_status": f"ERROR:{last_err[:120]}",
        "content_source": "error",
        "image_url": "",
        "image_urls": [],
        "image_source": "error",
    }


def enrich_rows_with_content_and_image(session: requests.Session, config: CrawlConfig, flat_rows: List[dict]):
    if not flat_rows:
        return
    print("\n[DETAIL] 본문/이미지 크롤링 시작...")
    for i, row in enumerate(flat_rows, 1):
        url = row.get("URL")
        if not url:
            row["CONTENT"] = ""
            row["CONTENT_LEN"] = 0
            row["CONTENT_STATUS"] = "NO_URL"
            row["CONTENT_SOURCE"] = "none"
            row["IMAGE_URL"] = ""
            row["IMAGE_URLS"] = "[]"
            row["IMAGE_SOURCE"] = "none"
            row["SENTIMENT_LABEL"] = "neutral"
            row["SENTIMENT_SCORE"] = 0.0
            continue

        r = fetch_article_page(session, config, url)

        row["CONTENT"] = r["content"]
        row["CONTENT_LEN"] = r["content_len"]
        row["CONTENT_STATUS"] = r["content_status"]
        row["CONTENT_SOURCE"] = r["content_source"]

        row["IMAGE_URL"] = r.get("image_url", "")
        row["IMAGE_URLS"] = json.dumps(r.get("image_urls", []), ensure_ascii=False)
        row["IMAGE_SOURCE"] = r.get("image_source", "")

        # ✅ 감성 분석 수행
        s_label, s_score = "neutral", 0.0
        if config.sentiment_enabled and sentiment_service:
            text_for_sent = (r["content"].strip() or row.get("TITLE", "").strip())
            if text_for_sent:
                try:
                    s_label, s_score = sentiment_service.predict(text_for_sent)
                except Exception:
                    pass
        row["SENTIMENT_LABEL"] = s_label
        row["SENTIMENT_SCORE"] = float(s_score)

        if i % 10 == 0 or i == len(flat_rows):
            ok_cnt = sum(1 for rr in flat_rows if rr.get("CONTENT_STATUS") == "OK")
            img_cnt = sum(1 for rr in flat_rows if rr.get("IMAGE_URL"))
            print(f"  - 진행 {i}/{len(flat_rows)} | CONTENT_OK {ok_cnt} | IMAGE(primary) {img_cnt}")

        time.sleep(config.content_sleep_sec)

    # ✅ 감성 필터 적용 (있을 경우)
    if config.sentiment_filter:
        before_cnt = len(flat_rows)
        flat_rows[:] = [r for r in flat_rows if r.get("SENTIMENT_LABEL") in config.sentiment_filter]
        after_cnt = len(flat_rows)
        if before_cnt != after_cnt:
            print(f"🔍 감성 필터 적용: {before_cnt}건 -> {after_cnt}건 (필터: {config.sentiment_filter})")

    print("[DETAIL] 본문/이미지 크롤링 완료.\n")


# =========================
# 저장(CSV)
# =========================
def make_output_filename(config: CrawlConfig, since_dt: datetime) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    since_tag = since_dt.strftime("%Y%m%d")
    today_tag = datetime.now(KST).strftime("%Y%m%d")
    return f"{config.output_prefix}_{ts}_{since_tag}_to_{today_tag}_company_plus_person_only.csv"

def save_results_csv(flat_rows: List[dict], out_path: str):
    fieldnames = [
        "GROUP",
        "COMPANY_KEYWORD",
        "PERSON",
        "QUERY_USED",
        "CID",
        "DATETIME",
        "TITLE",
        "URL",
        "CONTENT",
        "CONTENT_LEN",
        "CONTENT_STATUS",
        "CONTENT_SOURCE",
        "IMAGE_URL",
        "IMAGE_URLS",
        "IMAGE_SOURCE",
        "SENTIMENT_LABEL",
        "SENTIMENT_SCORE",
    ]
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(flat_rows)


# =========================
# ✅ MongoDB doc 변환
# =========================
def parse_dt_any(val: Any) -> Optional[datetime]:
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        s = val.strip()
        try:
            return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None
    return None

def build_mongo_doc_from_row(row: dict) -> dict:
    dt_val = (row.get("DATETIME", "") or "").strip()
    dt_obj = None
    try:
        if dt_val:
            dt_obj = datetime.strptime(dt_val, "%Y-%m-%d %H:%M:%S")
    except Exception:
        dt_obj = None

    title = row.get("TITLE", "") or ""
    content = row.get("CONTENT", "") or ""
    text_for_sent = (content.strip() or title.strip())
    # 기본값은 "" 또는 None으로 두어 백필 대상이 될 수 있게 함 (이미 분석된 경우는 제외)
    s_label = row.get("SENTIMENT_LABEL", "")
    s_score = row.get("SENTIMENT_SCORE", None)

    # row에 이미 있으면 (크롤링 단계에서 채워짐) 그대로 사용, 없으면 여기서 한 번 더 시도 (옵션)
    if not s_label and sentiment_service is not None and text_for_sent:
        try:
            s_label, s_score = sentiment_service.predict(text_for_sent)
        except Exception:
            s_label, s_score = "neutral", 0.0

    return {
        "Group": row.get("GROUP", ""),
        "PERSON": row.get("PERSON", ""),
        "CID": (row.get("CID", "") or "").strip(),
        "DATETIME": dt_obj if dt_obj else dt_val,
        "TITLE": title,
        "CONTENT": content,
        "URL": row.get("URL", ""),
        "IMAGE_URL": row.get("IMAGE_URL", ""),
        "IMAGE_URLS": json.loads(row.get("IMAGE_URLS", "[]")) if row.get("IMAGE_URLS") else [],
        "sentiment_label": s_label,
        "sentiment_score": float(s_score),
    }


# =========================
# ✅ (삽입 전) 중복 제거 로직 (기업 GROUP 단위)
# =========================
def load_existing_cids_for_group(col, group: str, limit: int = 50000) -> set:
    """
    그룹별로 최근 문서에서 CID를 로드.
    엄청 큰 컬렉션이면 limit 조절.
    """
    cids = set()
    cur = col.find({"Group": group, "CID": {"$exists": True, "$ne": ""}}, {"CID": 1}).sort("_id", -1).limit(limit)
    for d in cur:
        cid = (d.get("CID") or "").strip()
        if cid:
            cids.add(cid)
    return cids

def load_existing_titles_for_group(col, group: str, cfg: CrawlConfig) -> List[Tuple[str, str]]:
    """
    그룹별 최근 N개 제목 로드 -> (title_key, original_title)
    """
    out: List[Tuple[str, str]] = []
    cur = col.find({"Group": group, "TITLE": {"$exists": True, "$ne": ""}}, {"TITLE": 1, "DATETIME": 1}).sort("_id", -1).limit(cfg.title_dedup_db_limit_per_group)
    cutoff = datetime.now(KST).replace(tzinfo=None) - timedelta(days=cfg.title_dedup_only_within_days)
    for d in cur:
        t = (d.get("TITLE") or "").strip()
        if not t:
            continue
        dtv = parse_dt_any(d.get("DATETIME"))
        # 오래된 기사는 비교 대상에서 제외(오탐 줄이기)
        if dtv and dtv < cutoff:
            continue
        out.append((title_key(t), t))
    return out

def dedup_rows_before_insert(flat_rows: List[dict], cfg: CrawlConfig, col=None) -> Tuple[List[dict], dict]:
    """
    반환:
      - filtered_rows
      - stats
    """
    stats = {
        "input": len(flat_rows),
        "cid_removed_batch": 0,
        "cid_skipped_db": 0,
        "title_removed_batch": 0,
        "title_skipped_db": 0,
        "kept": 0,
    }

    if not cfg.pre_insert_dedup_enable or not flat_rows:
        stats["kept"] = len(flat_rows)
        return flat_rows, stats

    # 그룹별로 처리
    by_group: Dict[str, List[dict]] = {}
    for r in flat_rows:
        g = (r.get("GROUP") or "").strip()
        by_group.setdefault(g, []).append(r)

    filtered_all: List[dict] = []

    for g, rows in by_group.items():
        # DATETIME 최신 우선(유사도 dedup에서 최신을 남기기)
        def _dtv(rr):
            try:
                return datetime.strptime((rr.get("DATETIME") or ""), "%Y-%m-%d %H:%M:%S")
            except Exception:
                return datetime.min
        rows_sorted = sorted(rows, key=_dtv, reverse=True)

        # 1) CID 배치 내부 중복 제거
        seen_cid = set()
        rows_cid_unique: List[dict] = []
        for r in rows_sorted:
            cid = (r.get("CID") or "").strip()
            if not cid:
                continue
            if cid in seen_cid:
                stats["cid_removed_batch"] += 1
                continue
            seen_cid.add(cid)
            rows_cid_unique.append(r)

        # 1-2) DB에 CID가 이미 있으면 스킵(선택)
        existing_cids = set()
        if col is not None and cfg.pre_insert_skip_if_cid_exists_in_db:
            # 그룹별 CID set(최근 기준)
            existing_cids = load_existing_cids_for_group(col, g, limit=50000)

        rows_after_cid_db: List[dict] = []
        for r in rows_cid_unique:
            cid = (r.get("CID") or "").strip()
            if existing_cids and cid in existing_cids:
                stats["cid_skipped_db"] += 1
                continue
            rows_after_cid_db.append(r)

        # 2) 제목 유사/중복 제거
        if not cfg.title_dedup_enable:
            filtered_all.extend(rows_after_cid_db)
            continue

        # DB 최근 제목 로드(선택)
        existing_title_keys: List[str] = []
        existing_titles_orig: List[str] = []
        if col is not None and cfg.title_dedup_db_lookup:
            ex = load_existing_titles_for_group(col, g, cfg)
            existing_title_keys = [k for k, _ in ex if k]
            existing_titles_orig = [t for _, t in ex]

        kept: List[dict] = []
        kept_title_keys: List[str] = []
        kept_titles_orig: List[str] = []

        for r in rows_after_cid_db:
            t = (r.get("TITLE") or "").strip()
            tk = title_key(t)
            if not tk:
                kept.append(r)
                continue

            # (A) 배치 내 중복 검사(최근 kept N개만 비교)
            dup_in_batch = False
            start_idx = max(0, len(kept_title_keys) - cfg.title_dedup_compare_recent_keep)
            for k2, t2 in zip(kept_title_keys[start_idx:], kept_titles_orig[start_idx:]):
                if not k2:
                    continue
                # key 동일이면 즉시 duplicate
                if tk == k2:
                    dup_in_batch = True
                    break
                # 유사도 검사
                if is_title_duplicate(t, t2, cfg):
                    dup_in_batch = True
                    break
            if dup_in_batch:
                stats["title_removed_batch"] += 1
                continue

            # (B) DB 기존 기사와 중복 검사(선택)
            dup_in_db = False
            if existing_title_keys:
                # key 동일이면 빠르게 중복 처리
                if tk in existing_title_keys:
                    dup_in_db = True
                else:
                    # 너무 많이 비교하면 느려서, 최근 N개 원문 타이틀만 대략 비교
                    # (N=3000이면 difflib가 느릴 수 있어 "key 기반" 먼저, 그다음 제한 비교)
                    limit_compare = min(len(existing_titles_orig), 400)
                    for t2 in existing_titles_orig[:limit_compare]:
                        if is_title_duplicate(t, t2, cfg):
                            dup_in_db = True
                            break

            if dup_in_db:
                stats["title_skipped_db"] += 1
                continue

            kept.append(r)
            kept_title_keys.append(tk)
            kept_titles_orig.append(t)

        if cfg.title_dedup_verbose:
            print(f"[DEDUP] Group={g} | in={len(rows)} -> cid_unique={len(rows_cid_unique)} -> after_db_cid={len(rows_after_cid_db)} -> kept={len(kept)}")

        filtered_all.extend(kept)

    stats["kept"] = len(filtered_all)
    return filtered_all, stats


# =========================
# ✅ MongoDB 업로드 (삽입 전 dedup 포함)
# =========================
def upload_rows_to_mongo(flat_rows: List[dict], config: CrawlConfig):
    if not MongoClient or not UpdateOne:
        raise RuntimeError("pymongo가 설치되지 않았습니다. pip install pymongo")
    if not config.mongo_uri:
        raise RuntimeError("MONGO_URI is required. Set it in .env")

    client = MongoClient(config.mongo_uri)
    col = client[config.mongo_db][config.mongo_collection]

    # (선택) CID unique index
    if config.mongo_ensure_unique_cid:
        try:
            col.create_index([("CID", 1)], unique=True, background=True, name="uniq_CID")
            print("✅ Mongo index ensured: CID unique")
        except Exception as e:
            print("⚠️ Mongo CID unique index 생성 실패(이미 중복이 있거나 권한 문제):", e)

    # ✅ 삽입 전 중복 제거
    filtered_rows, st = dedup_rows_before_insert(flat_rows, config, col=col)
    print("✅ PRE-INSERT DEDUP STATS:", st)

    ops = []
    sent = 0

    for row in filtered_rows:
        cid = (row.get("CID") or "").strip()
        if not cid:
            continue

        doc = build_mongo_doc_from_row(row)

        ops.append(
            UpdateOne(
                {"CID": cid},       # ✅ CID 기준 upsert
                {"$set": doc},
                upsert=config.mongo_upsert,
            )
        )

        if len(ops) >= config.mongo_batch_size:
            result = col.bulk_write(ops, ordered=False)
            sent += len(ops)
            ops.clear()
            print("✅ Mongo bulk 업로드:", {
                "sent": sent,
                "matched": result.matched_count,
                "modified": result.modified_count,
                "upserted": len(result.upserted_ids or {}),
            })

    if ops:
        result = col.bulk_write(ops, ordered=False)
        sent += len(ops)
        ops.clear()
        print("✅ Mongo bulk 업로드:", {
            "sent": sent,
            "matched": result.matched_count,
            "modified": result.modified_count,
            "upserted": len(result.upserted_ids or {}),
        })

    try:
        client.close()
    except Exception:
        pass


# =========================
# ✅ (옵션) MongoDB 기존 중복 정리: GROUP 단위
# =========================
def cleanup_existing_duplicates(col, groups: List[str], cfg: CrawlConfig, apply: bool = False) -> dict:
    """
    1) CID 중복 삭제
    2) 제목 중복 삭제(정규화 동일 + 유사도)
    기본은 DRY RUN (apply=False)
    """
    report = {
        "apply": apply,
        "groups": len(groups),
        "cid_dups_found": 0,
        "cid_docs_to_delete": 0,
        "title_dups_found": 0,
        "title_docs_to_delete": 0,
    }

    now_cutoff = datetime.now(KST).replace(tzinfo=None) - timedelta(days=max(cfg.title_dedup_only_within_days, 7))

    for g in groups:
        # ---------- 1) CID 중복 ----------
        pipeline = [
            {"$match": {"Group": g, "CID": {"$exists": True, "$ne": ""}}},
            {"$group": {"_id": "$CID", "ids": {"$push": "$_id"}, "count": {"$sum": 1}}},
            {"$match": {"count": {"$gt": 1}}},
        ]
        dups = list(col.aggregate(pipeline, allowDiskUse=True))
        if dups:
            report["cid_dups_found"] += len(dups)

        for d in dups:
            ids = d["ids"]
            # 어떤 걸 남길지 결정: DATETIME 최신, 없으면 _id 최신
            docs = list(col.find({"_id": {"$in": ids}}, {"DATETIME": 1, "TITLE": 1}))
            def _score(doc):
                dtv = parse_dt_any(doc.get("DATETIME"))
                # dt 없으면 _id의 생성시각
                oid = doc.get("_id")
                oid_time = oid.generation_time.replace(tzinfo=None) if hasattr(oid, "generation_time") else datetime.min
                return dtv if dtv else oid_time
            docs_sorted = sorted(docs, key=_score, reverse=True)
            keep_id = docs_sorted[0]["_id"]
            del_ids = [x["_id"] for x in docs_sorted[1:]]
            report["cid_docs_to_delete"] += len(del_ids)

            if apply and del_ids:
                col.delete_many({"_id": {"$in": del_ids}})

        # ---------- 2) 제목 중복 ----------
        # 최근 문서 위주로만(오탐/시간 이슈 방지)
        cur = col.find({"Group": g, "TITLE": {"$exists": True, "$ne": ""}}, {"TITLE": 1, "DATETIME": 1}).sort("_id", -1).limit(20000)
        kept_keys: List[str] = []
        kept_titles: List[str] = []
        kept_ids: List[Any] = []
        to_delete: List[Any] = []

        for doc in cur:
            dtv = parse_dt_any(doc.get("DATETIME"))
            if dtv and dtv < now_cutoff:
                # 너무 오래된 건 비교/정리 대상에서 제외
                continue

            tid = doc["_id"]
            t = (doc.get("TITLE") or "").strip()
            tk = title_key(t)
            if not tk:
                kept_ids.append(tid)
                kept_titles.append(t)
                kept_keys.append(tk)
                continue

            dup = False
            start_idx = max(0, len(kept_keys) - cfg.title_dedup_compare_recent_keep)
            for k2, t2 in zip(kept_keys[start_idx:], kept_titles[start_idx:]):
                if not k2:
                    continue
                if tk == k2:
                    dup = True
                    break
                if is_title_duplicate(t, t2, cfg):
                    dup = True
                    break

            if dup:
                to_delete.append(tid)
            else:
                kept_ids.append(tid)
                kept_titles.append(t)
                kept_keys.append(tk)

        if to_delete:
            report["title_dups_found"] += 1
            report["title_docs_to_delete"] += len(to_delete)
            if apply:
                col.delete_many({"_id": {"$in": to_delete}})

        print(f"[CLEANUP] Group={g} | cid_dups={len(dups)} | title_del={len(to_delete)} | apply={apply}")

    return report

# =========================
# ✅ (옵션) MongoDB 기존 기사 감성 분석 채우기 (Backfill)
# =========================
def backfill_sentiment_in_mongo(config: CrawlConfig, limit: int = 1000, force: bool = False):
    if not MongoClient or not sentiment_service:
        print("❌ MongoClient 또는 sentiment_service가 로드되지 않았습니다.")
        return

    client = MongoClient(config.mongo_uri)
    col = client[config.mongo_db][config.mongo_collection]

    # sentiment_label이 없거나, 비어있거나, 분석되지 않은 기본값(neutral + 0.0)인 경우 찾기
    if force:
        # 강제 모드: 모든 기사 대상 (최신순)
        query = {}
        print("⚠️ 강제 재분석 모드 (--force): 모든 기존 기사를 대상으로 합니다.")
    else:
        query = {
            "$or": [
                {"sentiment_label": {"$exists": False}},
                {"sentiment_label": None},
                {"sentiment_label": ""},
                {"$and": [{"sentiment_label": "neutral"}, {"sentiment_score": 0.0}]} # 기본값으로 들어간 것들 재분석
            ]
        }

    total_to_process = col.count_documents(query)
    print(f"🔍 감성 분석이 필요한 기존 기사: {total_to_process}건 (처리 제한: {limit}건)")

    docs = list(col.find(query).sort("DATETIME", -1).limit(limit))
    if not docs:
        print("✅ 처리할 대상이 없습니다.")
        client.close()
        return

    ops = []
    processed = 0
    for d in docs:
        text = (d.get("CONTENT") or d.get("TITLE") or "").strip()
        if not text:
            label, score = "neutral", 0.0
        else:
            try:
                label, score = sentiment_service.predict(text)
            except Exception:
                label, score = "neutral", 0.0

        ops.append(
            UpdateOne(
                {"_id": d["_id"]},
                {"$set": {"sentiment_label": label, "sentiment_score": float(score)}}
            )
        )
        processed += 1

        if len(ops) >= config.mongo_batch_size:
            col.bulk_write(ops, ordered=False)
            ops.clear()
            print(f"  - 진행 중... {processed}/{len(docs)}")

    if ops:
        col.bulk_write(ops, ordered=False)

    print(f"✅ 백필 완료: {processed}건 처리됨")
    client.close()


# =========================
# search_groups 로드(옵션)
# =========================
def load_search_groups_from_csv(config: CrawlConfig) -> Dict[str, Tuple[str, str]]:
    groups: Dict[str, Tuple[str, str]] = {}
    with open(config.groups_csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            g = (row.get(config.groups_csv_group_col) or "").strip()
            c = (row.get(config.groups_csv_company_col) or "").strip()
            p = (row.get(config.groups_csv_person_col) or "").strip()
            if not g:
                continue
            if not c or not p:
                continue
            groups[g] = (c, p)
    return groups


# =========================
# 메인 크롤러
# =========================
def get_news(search_groups: Dict[str, Tuple[str, str]], config: CrawlConfig, since_dt: datetime):
    print(f"조회 기준 시간: {since_dt.strftime('%Y-%m-%d %H:%M:%S')} 이후 기사")
    print(f"적용 필터: cattr={config.cattr}, div_code={config.div_code}")
    print(f"페이징: max_pages={config.max_pages} / page_size={config.page_size}")
    print(f"본문(fetch_content)={config.fetch_content} / 이미지(fetch_image)={config.fetch_image}")
    print(f"그룹 수: {len(search_groups)}\n")

    session = requests.Session()
    session.mount("https://", LegacySSLAdapter())

    final_results = {}
    flat_rows = []

    for group_name, (company_kw, person_kw) in search_groups.items():
        group_articles = []
        seen_cids_group = set()

        queries = build_queries_company_plus_person(company_kw, person_kw)
        if not queries:
            print(f"⚠️ 그룹 '{group_name}' 스킵: company/person 누락 (company='{company_kw}', person='{person_kw}')")
            final_results[group_name] = []
            continue

        for q in queries:
            try:
                articles, _raw = fetch_articles_paged(session, config, q, since_dt)

                added = 0
                for a in articles:
                    cid = a["CID"]
                    if cid in seen_cids_group:
                        continue
                    seen_cids_group.add(cid)

                    a["KEYWORD_FOUND"] = q
                    group_articles.append(a)
                    added += 1

                    flat_rows.append(
                        {
                            "GROUP": group_name,
                            "COMPANY_KEYWORD": company_kw,
                            "PERSON": person_kw,
                            "QUERY_USED": q,
                            "CID": cid,
                            "DATETIME": a["DATETIME"],
                            "TITLE": a["TITLE"],
                            "URL": a["URL"],
                            "CONTENT": "",
                            "CONTENT_LEN": 0,
                            "CONTENT_STATUS": "PENDING",
                            "CONTENT_SOURCE": "",
                            "IMAGE_URL": "",
                            "IMAGE_URLS": "[]",
                            "IMAGE_SOURCE": "",
                            "SENTIMENT_LABEL": "neutral",
                            "SENTIMENT_SCORE": 0.0,
                        }
                    )

                print(f"✔ 그룹 '{group_name}' / 쿼리 '{q}' 완료 (추가 {added}건, 그룹누적 {len(group_articles)}건)")
                time.sleep(config.sleep_sec)

            except Exception as e:
                print(f"❌ 그룹 '{group_name}' / 쿼리 '{q}' 오류: {e}")

        final_results[group_name] = group_articles

    if config.fetch_content and flat_rows:
        enrich_rows_with_content_and_image(session, config, flat_rows)

    return final_results, flat_rows


# =========================
# 실행부
# =========================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cleanup-existing", action="store_true", help="MongoDB에 이미 들어간 중복(CID/제목)을 정리(기본 DRY RUN)")
    ap.add_argument("--apply", action="store_true", help="--cleanup-existing 와 같이 사용: 실제 삭제 적용")
    ap.add_argument("--backfill-sentiment", action="store_true", help="MongoDB의 기존 기사 중 감성 분석이 없는 것들을 처리")
    ap.add_argument("--backfill-limit", type=int, default=1000, help="백필 시 한 번에 처리할 최대 기사 수")
    ap.add_argument("--force", action="store_true", help="강제로 모든 대상(이미 분석된 것 포함) 재분석")
    args = ap.parse_args()

    # 1) search_groups 준비
    # (원하면 CSV 로드로 바꾸세요)
    search_groups = {
        "유진그룹": ("유진그룹", "유경선"),
        "BGF": ("BGF", "홍석조"),
        "현대해상": ("현대해상", "정몽윤"),
        "하이브": ("하이브", "방시혁"),
        "한솔": ("한솔", "조동길"),
        "삼성": ("삼성전자", "이재용"),
        "SK": ("SK", "최태원"),
        "현대자동차": ("현대자동차", "정의선"),
        "LG": ("LG", "구광모"),
        "롯데": ("롯데", "신동빈"),
        "한화": ("한화", "김승연"),
        "HD현대": ("HD현대", "정몽준"),
        "GS": ("GS", "허창수"),
        "신세계": ("신세계", "이명희"),
        "한진": ("한진", "조원태"),
        "CJ": ("CJ", "이재현"),
        "LS": ("LS", "구자은"),
        "카카오": ("카카오", "김범수"),
        "두산": ("두산", "박정원"),
        "DL": ("DL", "이해욱"),
        "중흥건설": ("중흥건설", "정창선"),
        "셀트리온": ("셀트리온", "서정진"),
        "네이버": ("네이버", "이해진"),
        "현대백화점": ("현대백화점", "정지선"),
        "한국앤컴퍼니그룹": ("한국앤컴퍼니그룹", "조양래"),
        "부영": ("부영", "이중근"),
        "하림": ("하림", "김홍국"),
        "효성": ("효성", "조현준"),
        "SM": ("SM", "우오현"),
        "HDC": ("HDC", "정몽규"),
        "호반건설": ("호반건설", "김상열"),
        "코오롱": ("코오롱", "이웅열"),
        "KCC": ("KCC", "정몽진"),
        "DB": ("DB", "김준기"),
        "OCI": ("OCI", "이우현"),
        "LX": ("LX", "구본준"),
        "넷마블": ("넷마블", "방준혁"),
        "이랜드": ("이랜드", "박성수"),
        "교보생명보험": ("교보생명보험", "신창재"),
        "다우키움": ("다우키움", "김익래"),
        "금호석유화학": ("금호석유화학", "박찬구"),
        "태영": ("태영", "윤세영"),
        "KG": ("KG", "곽재선"),
        "HL": ("HL", "정몽원"),
        "동원": ("동원", "김남정"),
        "아모레퍼시픽": ("아모레퍼시픽", "서경배"),
        "태광": ("태광", "이호진"),
        "크래프톤": ("크래프톤", "장병규"),
        "애경": ("애경", "장영신"),
        "동국제강": ("동국제강", "장세주"),
        "중앙": ("중앙", "홍석현"),
    }

    # (옵션) 기존 Mongo 중복 정리
    if args.cleanup_existing:
        if not MongoClient or not CONFIG.mongo_uri:
            print("❌ MongoClient 또는 MONGO_URI가 없습니다.")
            sys.exit(1)
        client = MongoClient(CONFIG.mongo_uri)
        col = client[CONFIG.mongo_db][CONFIG.mongo_collection]
        rep = cleanup_existing_duplicates(col, list(search_groups.keys()), CONFIG, apply=args.apply)
        print("✅ CLEANUP REPORT:", rep)
        client.close()

    # 1-2) 기존 기사 감성 분석 백필
    if args.backfill_sentiment:
        backfill_sentiment_in_mongo(CONFIG, limit=args.backfill_limit, force=args.force)
        # 백필만 하고 끝내려면 여기서 return
        # return


    # ✅ 2) 날짜 자동 계산
    since_dt = compute_since_dt_auto(CONFIG)
    if since_dt is None:
        sys.exit(0)

    # 3) 수집
    _news_data, flat_rows = get_news(search_groups, CONFIG, since_dt)

    # 4) CSV 저장(원하면 끄거나 경로 변경)
    out_csv = make_output_filename(CONFIG, since_dt)
    save_results_csv(flat_rows, out_csv)
    print(f"\n✅ CSV 저장 완료: {out_csv}")

    # 5) MongoDB 업로드(삽입 전 CID+제목 dedup 수행)
    if CONFIG.upload_to_mongo:
        upload_rows_to_mongo(flat_rows, CONFIG)

    # ✅ 6) state 저장: "오늘 날짜"
    save_last_crawled_date(CONFIG.state_path, datetime.now(KST).date())
    print(f"✅ state 저장 완료: {CONFIG.state_path}")

if __name__ == "__main__":
    main()
