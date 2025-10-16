# -*- coding: utf-8 -*-
"""
DCInside 댓글 생성 (Gemma3 버전, 단계별 로깅 포함)

⚡ 전체 프로세스 (LLM 2회 호출):
  1. 게시글의 키워드 추출
  1.5. 게시글 요약 생성 (감정 반영)
  2. 해당 게시글의 ±N개의 이웃 글 수집
  2.5. 키워드 기반 검색으로 관련 글 추가 수집
  3. 유사 키워드를 가진 글의 데이터 추출
  4. 해당 키워드를 가진 글들을 묶어서 데이터 정리
  5. 이 데이터를 토대로 댓글 작성 (LLM 1회)

조건:
- 댓글은 디시인사이드 갤러리 유저처럼 자연스럽고 짧게 작성
- 광고/과장/정형 문구/이모지 사용 금지
- 본문 상황·감정(특히 성공/실패, 기쁨/슬픔) 반드시 반영
"""

import os
import re
import html
import time
import argparse
import requests
import logging
import json
from urllib.parse import urlparse, parse_qs, urlencode
from bs4 import BeautifulSoup
from konlpy.tag import Okt  # fallback 키워드 추출용

# -----------------------------
# 설정 & 로거
# -----------------------------
UA = {"User-Agent": "Mozilla/5.0 (compatible; CommentBot/0.3)"}
DEFAULT_MODEL = os.getenv("GEMMA_MODEL", "gemma-3-12b-it")  # 사용할 Gemma3 모델
REQUEST_TIMEOUT = 15  # HTTP 요청 타임아웃 (초)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("comment-bot")

# -----------------------------
# Gemma3 래퍼
# -----------------------------
def _make_chat():
    """
    Gemma3 API를 초기화하고 재시도 로직을 포함한 chat 함수를 반환한다.

    반환:
        chat (function): messages를 입력받아 모델 응답 텍스트를 반환하는 함수
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY 환경변수가 없습니다. 예) export GOOGLE_API_KEY='AIza...'")

    from google import genai
    client = genai.Client(api_key=api_key)

    def _extract_text(resp):
        """
        Gemma3 응답 객체에서 텍스트만 안전하게 추출한다.
        - resp.text 가 있으면 그대로 반환
        - candidates.parts 에서 직접 추출 시도
        """
        try:
            if hasattr(resp, "text") and resp.text:
                return resp.text.strip()

            candidates = getattr(resp, "candidates", None) or []
            for c in candidates:
                content = getattr(c, "content", None)
                if not content:
                    continue
                parts = getattr(content, "parts", None) or []
                texts = [getattr(p, "text", "") for p in parts if getattr(p, "text", "")]
                if texts:
                    return " ".join(texts).strip()

            logger.error("_extract_text: 후보 없음")
        except Exception as e:
            logger.error(f"_extract_text 파싱 실패: {e}")
        return ""

    def chat(messages, *, model=DEFAULT_MODEL, temperature=0.6, max_tokens=300, timeout=60, retry=1):
        """
        LLM 대화 함수

        Args:
            messages (list[dict]): [{"role": "system"|"user", "content": "텍스트"}]
            model (str): 사용할 Gemma3 모델 이름
            temperature (float): 생성 다양성 조절
            max_tokens (int): 출력 토큰 최대 길이
            timeout (int): (현재 SDK에서 직접 지원 X, 무시됨)
            retry (int): 실패 시 재시도 횟수

        Returns:
            str: 모델이 생성한 텍스트 (없으면 빈 문자열)
        """
        system_instruction = next((m["content"] for m in messages if m.get("role") == "system"), "")
        user_texts = [m["content"] for m in messages if m.get("role") == "user"]

        # Gemma3 SDK에는 system_instruction 인자가 없으므로, system 내용을 프롬프트 앞에 붙인다
        if system_instruction:
            prompt_text = f"[시스템 지침]\n{system_instruction}\n\n" + "\n\n".join(user_texts)
        else:
            prompt_text = "\n\n".join(user_texts)

        for attempt in range(retry + 1):
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=prompt_text,
                    config={"temperature": temperature, "max_output_tokens": max_tokens},
                )
                text = _extract_text(resp)
                if text:
                    return text
            except Exception as e:
                logger.error(f"chat 호출 실패 (attempt {attempt+1}): {e}")
            time.sleep(1)

        return ""

    return chat

# Gemini chat 함수 초기화
chat = _make_chat()

# -----------------------------
# 텍스트 유틸
# -----------------------------
def clean_text(s: str) -> str:
    """HTML 엔티티 제거 + 공백 정리"""
    return re.sub(r"\s+", " ", html.unescape(s or "")).strip()

def _sanitize_for_llm(text: str, limit_chars: int):
    """
    LLM 입력에 맞도록 텍스트를 정리
    - URL/해시태그/@멘션 제거
    - 공백 정규화
    - 길이 제한 적용
    """
    text = html.unescape(text or "")
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"#[\w가-힣_]+", " ", text)
    text = re.sub(r"@[^\s]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit_chars:
        text = text[:limit_chars] + "…"
    return text

# -----------------------------
# STEP 1: 키워드 + 요약 추출
# -----------------------------
def analyze_post(title: str, body: str, top_k: int = 8):
    """
    [STEP 1] 게시글에서 핵심 키워드와 요약을 동시에 추출한다.
    - LLM을 호출하여 JSON 형태로 반환
    - 키워드 추출 실패 시 konlpy.Okt 명사 추출로 대체
    - 요약 실패 시 본문 앞 50자 사용
    """
    logger.info("[STEP 1] 게시글 분석 시작 (키워드 + 요약)")

    prompt = (
        f"아래 게시글을 읽고 JSON으로만 결과를 작성해.\n"
        f"1) 핵심 키워드 {top_k}개를 'keywords' 배열로 출력.\n"
        f"2) 글쓴이의 상황과 감정을 'summary'라는 한 줄 문장으로 출력.\n"
        f"- 반드시 JSON 하나만 출력.\n\n"
        f"제목: {title}\n본문: {body}\n"
    )

    out = chat(
        [
            {"role": "system", "content": "너는 반드시 JSON만 출력하는 한국어 분석기야."},
            {"role": "user", "content": prompt},
        ],
        model=DEFAULT_MODEL, temperature=0.2, max_tokens=400, retry=2,
    )

    keywords, summary = [], ""
    try:
        out = re.sub(r"```(json)?", "", out).strip()
        json_match = re.search(r"\{.*\}", out, re.S)
        if json_match:
            out = json_match.group(0)
        data = json.loads(out)
        keywords = data.get("keywords", [])
        summary = data.get("summary", "")
    except Exception as e:
        logger.warning(f"[STEP 1] JSON 파싱 실패, fallback 사용: {e}")
        okt = Okt()
        nouns = okt.nouns(title + " " + body)
        keywords = list({w for w in nouns if len(w) > 1})[:top_k]
        summary = body[:50] + "…"

    logger.info(f"[STEP 1] 추출된 키워드: {keywords}")
    logger.info(f"[STEP 1] 요약: {summary}")
    return keywords[:top_k], summary

# -----------------------------
# STEP 2: ±N개의 이웃 글 수집
# -----------------------------
def fetch_post(gid: str, no: int):
    """
    특정 글 번호의 제목과 본문을 크롤링한다.

    Args:
        gid (str): 갤러리 ID
        no (int): 글 번호

    Returns:
        (title: str, body: str)
    """
    url = f"https://gall.dcinside.com/mgallery/board/view/?id={gid}&no={no}"
    r = requests.get(url, headers=UA, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    title_node = soup.select_one(".title") or soup.select_one(".tit") or soup.find("title")
    body_node = soup.select_one(".write_div") or soup.select_one("#content")

    title = clean_text(title_node.get_text(" ", strip=True) if title_node else "")
    body = clean_text(body_node.get_text(" ", strip=True) if body_node else "")
    return title, body

def fetch_neighbors(gid: str, target_no: int, n: int = 5):
    """
    [STEP 2] 기준 글 번호 기준으로 ±n 범위의 이웃 글들을 수집한다.

    Args:
        gid (str): 갤러리 ID
        target_no (int): 기준 글 번호
        n (int): 앞뒤로 가져올 글 개수

    Returns:
        list of (no, title, body): 수집된 이웃 글 정보
    """
    logger.info(f"[STEP 2] ±{n} 이웃 글 수집 시작 (target={target_no})")
    neighbors = []
    for off in range(-n, n + 1):
        if off == 0:
            continue
        no = target_no + off
        try:
            t, b = fetch_post(gid, no)
            if t or b:
                neighbors.append((no, t, b))
                logger.info(f"[STEP 2] 이웃글 {no} 수집 완료: {t[:20]}...")
        except Exception as e:
            logger.warning(f"[STEP 2] 글 {no} 수집 실패: {e}")
        time.sleep(0.2)
    logger.info(f"[STEP 2] 총 {len(neighbors)}개의 이웃 글 수집 완료")
    return neighbors

# -----------------------------
# STEP 2.5: 키워드 검색
# -----------------------------
def _extract_no_from_href(href: str):
    """
    게시글 보기 링크의 href에서 글 번호(no)만 안전하게 추출한다.
    예) /mgallery/board/view/?id=youngwoong&no=355289&page=1 -> 355289
    """
    try:
        qs = parse_qs(urlparse(href).query)
        if "no" in qs and qs["no"]:
            return int(qs["no"][0])
        m = re.search(r"[?&]no=(\d+)", href)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return None

def search_gallery_by_keywords(gid: str, keywords, per_kw: int = 5, pages: int = 1):
    """
    [STEP 2.5] 갤러리 내 검색 페이지에서 핵심 키워드로 관련 글을 수집한다.
    - 검색 URL (mgallery): /mgallery/board/lists/?id={gid}&s_type=search_subject_memo&s_keyword={kw}&page={n}
    - kw 당 최대 per_kw개, pages만큼 순회
    - 제목/본문은 fetch_post 재사용
    - 중복 제거된 키워드만 사용
    """
    logger.info("[STEP 2.5] 키워드 검색 수집 시작")
    collected = {}
    base = "https://gall.dcinside.com/mgallery/board/lists/"
    unique_keywords = list(dict.fromkeys([kw for kw in keywords if kw and len(kw) > 1]))

    for kw in unique_keywords:
        got_for_kw = 0
        for page in range(1, pages + 1):
            try:
                params = {"id": gid, "s_type": "search_subject_memo", "s_keyword": kw, "page": page}
                url = f"{base}?{urlencode(params, doseq=True)}"
                r = requests.get(url, headers=UA, timeout=REQUEST_TIMEOUT)
                r.raise_for_status()
                soup = BeautifulSoup(r.text, "html.parser")
                links = soup.find_all("a", href=True)
                for a in links:
                    href = a["href"]
                    if "board/view/" not in href or "no=" not in href or f"id={gid}" not in href:
                        continue
                    no = _extract_no_from_href(href)
                    if not no or no in collected:
                        continue
                    title_guess = clean_text(a.get_text(" ", strip=True))
                    try:
                        t, b = fetch_post(gid, no)
                        title_final = t or title_guess
                        if title_final or b:
                            collected[no] = (no, title_final, b)
                            got_for_kw += 1
                            logger.info(f"[STEP 2.5] '{kw}' → 글 {no} | {title_final[:30]}...")
                    except Exception as fe:
                        logger.warning(f"[STEP 2.5] 글 {no} 본문 수집 실패: {fe}")
                    if got_for_kw >= per_kw:
                        break
                if got_for_kw >= per_kw:
                    break
            except Exception as e:
                logger.warning(f"[STEP 2.5] 검색 실패(kw='{kw}', page={page}): {e}")
            time.sleep(0.3)
    results = list(collected.values())
    logger.info(f"[STEP 2.5] 키워드 검색 수집 완료: 총 {len(results)}건")
    return results, unique_keywords

# -----------------------------
# STEP 3 & 4: 유사 키워드 기반 필터링 및 묶기
# -----------------------------
def filter_by_keywords(neighbors, keywords):
    """
    [STEP 3 & 4] 추출된 키워드와 이웃 글을 비교하여 연관된 글만 필터링하고 묶는다.

    Args:
        neighbors (list): (no, title, body) 튜플 리스트
        keywords (list[str]): 핵심 키워드 리스트

    Returns:
        list of (no, title, body): 키워드가 매칭된 관련 글 리스트
    """
    logger.info("[STEP 3] 키워드 필터링 시작")
    filtered = []
    for no, t, b in neighbors:
        content = (t or "") + " " + (b or "")
        if any(kw and kw in content for kw in keywords):
            filtered.append((no, t, b))
            logger.info(f"[STEP 3] 매칭 → 글 {no} | 제목: {t[:40]}")
    logger.info(f"[STEP 4] 최종 묶은 글 수: {len(filtered)}")
    return filtered

# -----------------------------
# STEP 5: 댓글 생성
# -----------------------------
def generate_comment(title: str, body: str, related, keywords, summary: str, search_keywords):
    """
    [STEP 5] 게시글 내용 + 요약 + 키워드 + 관련 글들을 기반으로
    실제 디시인사이드 댓글처럼 자연스럽고 간결한 한두 문장을 생성한다.

    Args:
        title (str): 게시글 제목
        body (str): 게시글 본문
        related (list): 관련 글 데이터 (번호, 제목, 본문)
        keywords (list[str]): 추출된 핵심 키워드
        summary (str): 본문 요약
        search_keywords (list[str]): 실제 갤러리 검색에 사용된 키워드

    Returns:
        str: 생성된 댓글 (실패 시 기본 문구)
    """
    logger.info("[STEP 5] 댓글 생성 시작")

    title_s = _sanitize_for_llm(title, 180)
    body_s = _sanitize_for_llm(body, 1200)

    neigh_s = []
    for _, t, b in related[:3]:  # 최대 3개만 요약에 포함
        neigh_s.append(f"- { _sanitize_for_llm(t, 120) }: { _sanitize_for_llm(b, 160) }")

    context = (
        f"게시글 제목: {title_s}\n"
        f"본문: {body_s}\n"
        f"요약: {summary}\n"
        f"키워드: {', '.join(keywords)}\n"
        f"검색 키워드: {', '.join(search_keywords)}\n\n"
        "관련된 다른 글:\n" + ("\n".join(neigh_s) if neigh_s else "(없음)")
    )

    base_prompt = (
        "다음은 디시인사이드 갤러리 게시글과 주변 글들입니다.\n"
        "실제 이용자가 남길 법한 댓글을 1개만 작성하세요.\n"
        "본문 요약과 키워드를 반영하고, 상황/감정에 공감할 것.\n"
        "비꼬는 톤, 광고, 이모지, 일베식 표현은 금지.\n\n" + context
    )

    out = chat(
        [{"role": "system", "content": "너는 디시인사이드 유저처럼 댓글을 작성하는 봇이야."},
         {"role": "user", "content": base_prompt}],
        model=DEFAULT_MODEL, temperature=0.6, max_tokens=200,
    )

    logger.info(f"[STEP 5] 생성된 댓글: {out}")
    return out or "(댓글 생성 실패)"

# -----------------------------
# 메인 실행
# -----------------------------
def main():
    parser = argparse.ArgumentParser(description="DCInside 게시글 기반 댓글 생성 (단계별 로깅)")
    parser.add_argument("--gid", default="youngwoong", help="갤러리 ID")
    parser.add_argument("--no", type=int, required=True, help="게시글 번호")
    parser.add_argument("--min-len", type=int, default=30, help="본문 최소 글자 수")
    parser.add_argument("--neighbors", type=int, default=5, help="±N 범위 내 이웃 글 수집 개수")
    args = parser.parse_args()

    # 대상 글 불러오기
    title, body = fetch_post(args.gid, args.no)
    if len(body) < args.min_len:
        logger.warning(f"본문 {args.min_len}자 미만 → 댓글 작성 안 함")
        return

    # STEP 1: 키워드 + 요약
    keywords, summary = analyze_post(title, body)

    # STEP 2: 이웃 글 수집
    neighbors = fetch_neighbors(args.gid, args.no, n=args.neighbors)

    # STEP 2.5: 키워드 검색으로 관련 글 수집
    search_hits, search_keywords = search_gallery_by_keywords(args.gid, keywords, per_kw=3, pages=1)

    # STEP 3 & 4: 관련 글 필터링 (이웃글 + 검색글 통합)
    pool = neighbors + search_hits
    related = filter_by_keywords(pool, keywords)

    # STEP 5: 댓글 생성
    comment = generate_comment(title, body, related, keywords, summary, search_keywords)

    print("\n=== 최종 댓글 ===\n", comment)

if __name__ == "__main__":
    import sys
    if len(sys.argv) == 1:
        # 기본 테스트용 파라미터
        sys.argv.extend(["--gid", "youngwoong", "--no", "355289"])
    main()
