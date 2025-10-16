# -*- coding: utf-8 -*-
"""
DCInside 댓글 생성 (Gemma3 버전, 단계별 로깅 포함)

⚡ 전체 프로세스 (LLM 2회 호출):
  1. 게시글의 키워드와 요약을 추출 (LLM 1회)
  2. 해당 게시글의 ±N개의 이웃 글을 가져와서 정보 수집
  3. 유사한 키워드를 가진 글의 데이터 추출
  4. 해당 키워드를 가진 글들을 묶어서 데이터 정리
  5. 이 데이터를 토대로 댓글 작성 (LLM 1회)

조건:
- 본문 내용이 50자 이상일 때만 댓글 작성
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
                    config={
                        "temperature": temperature,
                        "max_output_tokens": max_tokens,
                    },
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
# STEP 1: 키워드 + 요약 동시 추출 (개선 버전)
# -----------------------------
def analyze_post(title: str, body: str, top_k: int = 8):
    logger.info("[STEP 1] 게시글 분석 시작 (키워드 + 요약)")

    prompt = (
        f"아래 게시글을 읽고 JSON으로만 결과를 작성해.\n"
        f"1) 핵심 키워드 {top_k}개를 'keywords' 배열로 출력 (본문 주제와 관련된 단어만).\n"
        f"2) 글쓴이의 상황과 감정을 'summary'라는 한 줄 문장으로 출력.\n"
        f"- 본문 그대로 복사하지 말고 요약문을 새로 작성.\n"
        f"- 반드시 JSON 하나만 출력. 다른 설명이나 텍스트 금지.\n\n"
        f"제목: {title}\n본문: {body}\n\n"
        "출력 예시:\n"
        "{\n"
        "  \"keywords\": [\"키워드1\", \"키워드2\", ...],\n"
        "  \"summary\": \"요약 문장 (최대 50자)\"\n"
        "}"
    )

    out = chat(
        [
            {"role": "system", "content": "너는 반드시 JSON만 출력하는 한국어 분석기야."},
            {"role": "user", "content": prompt},
        ],
        model=DEFAULT_MODEL,
        temperature=0.2,
        max_tokens=400,
        timeout=60,
        retry=2,
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
    logger.info("[STEP 3] 유사 키워드 가진 글 추출 시작")
    filtered = []
    for no, t, b in neighbors:
        content = t + " " + b
        if any(kw in content for kw in keywords):
            filtered.append((no, t, b))
            logger.info(f"[STEP 3] 키워드 매칭 → 글 {no} | 제목: {t[:40]} | 본문 일부: {b[:60]}")
    logger.info(f"[STEP 4] 최종 묶은 글 수: {len(filtered)}")
    logger.info(f"[STEP 4] 최종 묶인 글 목록:\n" + "\n".join([f"- {no}: {t[:50]}" for no, t, _ in filtered]))
    return filtered

# -----------------------------
# STEP 5: 댓글 생성
# -----------------------------
def generate_comment(title: str, body: str, related, keywords, summary: str):
    """
    [STEP 5] 게시글 내용 + 요약 + 키워드 + 관련 글들을 기반으로
    실제 디시인사이드 댓글처럼 자연스럽고 간결한 한두 문장을 생성한다.

    Args:
        title (str): 게시글 제목
        body (str): 게시글 본문
        related (list): 관련 글 데이터 (번호, 제목, 본문)
        keywords (list[str]): 추출된 핵심 키워드
        summary (str): 본문 요약

    Returns:
        str: 생성된 댓글 (실패 시 기본 문구)
    """
    logger.info("[STEP 5] 댓글 생성 시작")

    title_s = _sanitize_for_llm(title, 180)
    body_s = _sanitize_for_llm(body, 1200)

    neigh_s = []
    print("related ->", related[:3])
    for _, t, b in related[:3]:  # 최대 3개만 요약에 포함
        neigh_s.append(f"- { _sanitize_for_llm(t, 120) }: { _sanitize_for_llm(b, 160) }")

    context = (
        f"게시글 제목: {title_s}\n"
        f"본문: {body_s}\n"
        f"요약: {summary}\n"
        f"키워드: {', '.join(keywords)}\n\n"
        "관련된 다른 글:\n" + ("\n".join(neigh_s) if neigh_s else "(없음)")
    )

    base_prompt = (
        "다음은 디시인사이드 갤러리 게시글과 주변 글들입니다.\n"
        "실제 디시 이용자가 남길 법한 댓글을 1개만 작성하세요.\n"
        "본문 요약과 키워드를 반드시 반영해 글쓴이의 상황/감정에 공감하는 댓글을 작성하세요.\n"
        "완성된 문장을 다시 검토하여 게시글의 맥락에 맞는지 파악하고 비꼬는듯한 느낌이 들지않게 주의할것\n"
        "짧고 간결하게 작성하세요. 이모지, ~노?, 이기 등의 일베 용어 사용 금지\n\n" + context
    )

    # 디버깅 로그 추가
    logger.info("[STEP 5] 생성 프롬프트 (앞 500자):\n" + base_prompt[:500] + ("..." if len(base_prompt) > 500 else ""))
    logger.debug("[STEP 5] 전체 프롬프트:\n" + base_prompt)

    out = chat(
        [
            {"role": "system", "content": "너는 디시인사이드 유저처럼 댓글을 작성하는 봇이야."},
            {"role": "user", "content": base_prompt},
        ],
        model=DEFAULT_MODEL,
        temperature=0.6,
        max_tokens=200,
        timeout=60,
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
    parser.add_argument("--neighbors", type=int, default=10, help="±N 범위 내 이웃 글 수집 개수")
    args = parser.parse_args()

    # 대상 글 불러오기
    title, body = fetch_post(args.gid, args.no)
    if len(body) < args.min_len:
        logger.warning(f"본문이 {args.min_len}자 미만 → 댓글 작성 안 함 (현재 {len(body)}자)")
        return

    # STEP 1: 키워드 + 요약
    keywords, summary = analyze_post(title, body)

    # STEP 2: 이웃 글 수집
    neighbors = fetch_neighbors(args.gid, args.no, n=args.neighbors)

    # STEP 3 & 4: 관련 글 필터링
    related = filter_by_keywords(neighbors, keywords)

    # STEP 5: 댓글 생성
    comment = generate_comment(title, body, related, keywords, summary)

    print("\n=== 최종 댓글 ===\n", comment)

if __name__ == "__main__":
    import sys
    if len(sys.argv) == 1:
        # 기본 테스트용 파라미터
        sys.argv.extend(["--gid", "youngwoong", "--no", "355289"])
    main()
