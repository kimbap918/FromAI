# profile.py
# -*- coding: utf-8 -*-
"""
groups_filtered.csv(총수 리스트) -> 네이버 검색(unityGrupNm + 총수명 + 프로필) -> 인물 프로필 핵심정보 저장

실행:
  python profile.py
  python profile.py --headed

필수 설치:
  pip install playwright beautifulsoup4 lxml pandas
  playwright install chromium
"""

from __future__ import annotations

import csv
import json
import time
import hashlib
import argparse
import re
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


NAVER_SEARCH_BASE = "https://search.naver.com/search.naver"

# 필요한 것만(출생/소속/자녀)
KOR_LABEL_MAP = {
    "출생": "birth",
    "생년": "birth",
    "소속": "affiliation",
    "자녀": "children",
}

# 법인 표기 제거용(그룹명에도 붙는 경우 대비)
CORP_WORDS = ["(주)", "㈜", "주식회사", "유한회사"]

# 페이지 공통 UI 문구(오탐 방지)
SKIP_TEXTS = {
    "메뉴 영역으로 바로가기",
    "본문 영역으로 바로가기",
    "본문 바로가기",
    "네이버",
    "NAVER",
}


def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def clean_text(s: str) -> str:
    return " ".join((s or "").replace("\xa0", " ").split()).strip()


def normalize_keyword(s: str) -> str:
    """법인표기/괄호 등 제거해서 검색 키워드 안정화"""
    s = (s or "").strip()
    for w in CORP_WORDS:
        s = s.replace(w, "")
    s = re.sub(r"[()]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def build_search_url(query: str) -> str:
    # 파라미터 최소화
    params = {"where": "nexearch", "query": query}
    return f"{NAVER_SEARCH_BASE}?{urlencode(params)}"


def try_parse_json(s: str) -> Optional[Any]:
    try:
        return json.loads(s)
    except Exception:
        return None


def extract_jsonld_person(html: str) -> Dict[str, Any]:
    """JSON-LD(Person)가 있으면 우선 활용(없을 수도 있음)."""
    soup = BeautifulSoup(html, "lxml")
    out: Dict[str, Any] = {}

    for sc in soup.find_all("script", attrs={"type": "application/ld+json"}):
        data = try_parse_json(sc.get_text(strip=True))
        if not data:
            continue

        candidates: List[Any] = []
        if isinstance(data, dict):
            if "@graph" in data and isinstance(data["@graph"], list):
                candidates.extend(data["@graph"])
            else:
                candidates.append(data)
        elif isinstance(data, list):
            candidates.extend(data)

        for obj in candidates:
            if not isinstance(obj, dict):
                continue
            t = obj.get("@type")
            if t == "Person" or (isinstance(t, list) and "Person" in t):
                out["name"] = obj.get("name") or out.get("name")
                out["image"] = obj.get("image") or out.get("image")
                out["birthDate"] = obj.get("birthDate") or out.get("birthDate")
                out["jobTitle"] = obj.get("jobTitle") or out.get("jobTitle")

                works_for = obj.get("worksFor")
                if isinstance(works_for, dict):
                    out["worksFor"] = works_for.get("name")
                elif isinstance(works_for, list):
                    out["worksFor"] = ", ".join(
                        [w.get("name") for w in works_for if isinstance(w, dict) and w.get("name")]
                    )
                return out

    return out


def extract_profile_block_dtdd(html: str) -> Dict[str, str]:
    """
    화면 내 dt/dd 구조에서 출생/소속/자녀 best-effort 추출.
    네이버 DOM은 수시로 바뀔 수 있어 넓게 훑습니다.
    """
    soup = BeautifulSoup(html, "lxml")
    data: Dict[str, str] = {}

    for dl in soup.find_all("dl"):
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        if not dts or not dds or len(dts) != len(dds):
            continue

        for dt, dd in zip(dts, dds):
            k = clean_text(dt.get_text(" ", strip=True))
            v = clean_text(dd.get_text(" ", strip=True))
            if not k or not v:
                continue

            if k in KOR_LABEL_MAP:
                key = KOR_LABEL_MAP[k]
                if key in data and v not in data[key]:
                    data[key] = f"{data[key]} | {v}"
                else:
                    data[key] = v

    return data


def extract_profile_image(html: str) -> Optional[str]:
    """
    ✅ 1순위: 메인 프로필 썸네일 (사용자 제공 DOM)
      a.thumb_item[data-id="main_profile"] img.thumb_img
    """
    soup = BeautifulSoup(html, "lxml")

    node = soup.select_one('a.thumb_item[data-id="main_profile"] img.thumb_img')
    if node and node.get("src"):
        return node["src"]

    # fallback(덜 정확)
    for im in soup.find_all("img"):
        src = im.get("src") or ""
        alt = (im.get("alt") or "").strip()
        if not src:
            continue
        if ("pstatic" in src or "naver" in src) and any(x in alt for x in ["프로필", "인물", "사진"]):
            return src

    return None


def extract_title_name(html: str) -> Tuple[Optional[str], Optional[str]]:
    """
    ✅ 영문명 오탐 방지:
      - 영문명은 [A-Za-z] 포함 + 한글 미포함 + 콤마 없는 텍스트만
      - 없으면 None 반환 (저장 시 공백 처리)
    """
    soup = BeautifulSoup(html, "lxml")
    name_ko = None
    name_en = None

    candidates = soup.find_all(["strong", "h2", "h3", "a", "span"], limit=900)

    # 한글 이름 후보(2~4자)
    for c in candidates:
        t = clean_text(c.get_text(" ", strip=True))
        if not t or t in SKIP_TEXTS:
            continue
        if re.fullmatch(r"[가-힣]{2,4}", t):
            name_ko = t
            break

    # 영문 이름 후보(엄격)
    # 예: "Lee Jae-yong" / "Chung Mong-joon"
    for c in candidates:
        t = clean_text(c.get_text(" ", strip=True))
        if not t or t in SKIP_TEXTS:
            continue
        if "," in t:
            continue
        if re.search(r"[A-Za-z]", t) and not re.search(r"[가-힣]", t):
            if "http" in t.lower() or "www" in t.lower():
                continue
            if "바로가기" in t:
                continue
            if len(t) > 60:
                continue
            # 영문명처럼 보이는 패턴만(공백 1개 이상)
            if not re.fullmatch(r"[A-Za-z][A-Za-z .'\-]{2,}", t) or t.count(" ") < 1:
                continue
            name_en = t
            break

    return name_ko, name_en


def extract_pkid_os(html: str) -> Tuple[Optional[str], Optional[str]]:
    """페이지 내부 링크에서 pkid=1&os=xxxx 형태를 찾아 person_id로 활용."""
    soup = BeautifulSoup(html, "lxml")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "pkid=" in href and "os=" in href:
            try:
                pkid = href.split("pkid=")[1].split("&")[0]
                os_id = href.split("os=")[1].split("&")[0]
                if pkid and os_id:
                    return pkid, os_id
            except Exception:
                pass
    return None, None


@dataclass
class PersonRecordLite:
    person_id: str
    name_ko: str
    name_en: str
    birth_date: str
    roles: str
    company: str
    profile_image: str
    aliases: str      # JSON string list
    children: str

    source_naver_url: str
    naver_pkid: str
    naver_os: str

    kftc_unityGrupNm: str
    kftc_unityGrupCode: str
    kftc_repreCmpny: str
    kftc_ownerName: str


def make_aliases(name_ko: str, company: str, roles: str, name_en: str) -> List[str]:
    aliases: List[str] = []
    if name_ko:
        aliases.append(name_ko)
    if company and roles:
        aliases.append(f"{company} {roles}")
    elif company:
        aliases.append(company)

    name_en = (name_en or "").strip()
    if name_en:
        aliases.append(name_en)

    dedup: List[str] = []
    for a in aliases:
        a = clean_text(a)
        if a and a not in dedup:
            dedup.append(a)
    return dedup


def split_company_roles(affiliation: str) -> Tuple[str, str]:
    """예: '삼성전자(회장)' -> ('삼성전자', '회장')"""
    affiliation = clean_text(affiliation)
    if not affiliation:
        return "", ""

    if "(" in affiliation and ")" in affiliation:
        try:
            company = affiliation.split("(")[0].strip()
            roles = affiliation.split("(")[1].split(")")[0].strip()
            return company, roles
        except Exception:
            return affiliation, ""

    return affiliation, ""


def parse_to_record(
    html: str,
    search_url: str,
    kftc_row: Dict[str, str],
    group_keyword: str,
) -> PersonRecordLite:
    jsonld = extract_jsonld_person(html)
    dtdd = extract_profile_block_dtdd(html)

    _, name_en_guess = extract_title_name(html)
    pkid, os_id = extract_pkid_os(html)

    # ✅ 메인 프로필 썸네일 우선
    profile_img = extract_profile_image(html) or (jsonld.get("image") or "")

    # 이름: KFTC 우선
    name_ko = clean_text(kftc_row.get("smerNm", "")) or clean_text(jsonld.get("name") or "") or ""
    # ✅ 영문명 없으면 공백
    name_en = clean_text(name_en_guess or "")

    # 출생
    birth_date = dtdd.get("birth", "") or (jsonld.get("birthDate") or "")

    # 소속 -> company/roles
    affiliation = dtdd.get("affiliation", "") or (jsonld.get("worksFor") or "")
    company, roles = split_company_roles(affiliation)

    # roles 보강
    if not roles:
        roles = clean_text(jsonld.get("jobTitle") or "")

    # company가 비어있으면 그룹 키워드로 최소 보강(검색 기준 엔티티 확보 목적)
    if not company:
        company = group_keyword

    children = dtdd.get("children", "")

    # person_id: naver os 우선, 없으면 (이름|출생) 해시
    if os_id:
        person_id = f"naver:os:{os_id}"
    else:
        person_id = f"hash:{sha1(name_ko + '|' + birth_date)}"

    aliases = make_aliases(name_ko, company, roles, name_en)

    return PersonRecordLite(
        person_id=person_id,
        name_ko=name_ko,
        name_en=name_en,
        birth_date=birth_date,
        roles=roles,
        company=company,
        profile_image=profile_img or "",
        aliases=json.dumps(aliases, ensure_ascii=False),
        children=children,
        source_naver_url=search_url,
        naver_pkid=pkid or "",
        naver_os=os_id or "",
        kftc_unityGrupNm=kftc_row.get("unityGrupNm", ""),
        kftc_unityGrupCode=kftc_row.get("unityGrupCode", ""),
        kftc_repreCmpny=kftc_row.get("repreCmpny", ""),
        kftc_ownerName=kftc_row.get("smerNm", ""),
    )


def save_csv(path: str, rows: List[PersonRecordLite]) -> None:
    if not rows:
        return
    fieldnames = list(asdict(rows[0]).keys())
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))


def save_jsonl(path: str, rows: List[PersonRecordLite]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--groups_csv", default="groups_filtered.csv")
    ap.add_argument("--out_csv", default="owners_people_profiles.csv")
    ap.add_argument("--out_jsonl", default="owners_people_profiles.jsonl")
    ap.add_argument("--sleep", type=float, default=1.5)
    ap.add_argument("--headed", action="store_true", help="브라우저 창 띄우기(기본은 헤드리스)")
    ap.add_argument("--save_html_dir", default="", help="디버깅용 HTML 저장 폴더(옵션)")
    args = ap.parse_args()

    # CSV 로드(인코딩 이슈 대비)
    try:
        df = pd.read_csv(args.groups_csv, dtype=str, encoding="utf-8-sig").fillna("")
    except Exception:
        df = pd.read_csv(args.groups_csv, dtype=str).fillna("")

    # 필수 컬럼 체크/보강
    for col in ["smerNm", "unityGrupNm", "unityGrupCode", "repreCmpny"]:
        if col not in df.columns:
            df[col] = ""

    # ✅ (이름, unityGrupNm) 기준 중복 제거 (검색 기준과 동일하게)
    df["_dedupe_key"] = df["smerNm"].str.strip() + "|" + df["unityGrupNm"].str.strip()
    df = df.drop_duplicates("_dedupe_key").drop(columns=["_dedupe_key"])

    rows_out: List[PersonRecordLite] = []
    errors: List[Dict[str, str]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=(not args.headed))
        context = browser.new_context(
            locale="ko-KR",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        total = len(df)
        for _, r in df.iterrows():
            owner = clean_text(r.get("smerNm", ""))
            unity = clean_text(r.get("unityGrupNm", ""))
            repre = clean_text(r.get("repreCmpny", ""))

            if not owner:
                continue

            # ✅ 검색 키워드는 unityGrupNm 우선(요구사항)
            kw = normalize_keyword(unity) or normalize_keyword(repre)
            query = f"{kw} {owner} 프로필".strip() if kw else f"{owner} 프로필"
            url = build_search_url(query)

            print(f"[{len(rows_out)+1}/{total}] GET {query}")

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(0.8)
                html = page.content()

                rec = parse_to_record(
                    html=html,
                    search_url=url,
                    kftc_row=r.to_dict(),
                    group_keyword=kw,
                )
                rows_out.append(rec)

                # 디버깅용 HTML 저장
                if args.save_html_dir:
                    import os
                    os.makedirs(args.save_html_dir, exist_ok=True)
                    safe_name = sha1(owner + "|" + kw)[:12]
                    with open(f"{args.save_html_dir}/{safe_name}.html", "w", encoding="utf-8") as f:
                        f.write(html)

            except Exception as e:
                errors.append({
                    "owner": owner,
                    "unityGrupNm": unity,
                    "keyword": kw,
                    "unityGrupCode": r.get("unityGrupCode", ""),
                    "error": str(e),
                    "url": url,
                })
                print("  [WARN] 실패:", e)

            time.sleep(args.sleep)

        context.close()
        browser.close()

    if rows_out:
        save_csv(args.out_csv, rows_out)
        save_jsonl(args.out_jsonl, rows_out)
        print(f"[OK] 저장 완료: {args.out_csv} / {args.out_jsonl} ({len(rows_out)}명)")

    if errors:
        err_path = "owners_people_profiles_errors.csv"
        with open(err_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(errors[0].keys()))
            w.writeheader()
            for er in errors:
                w.writerow(er)
        print(f"[WARN] 에러 로그 저장: {err_path} ({len(errors)}건)")


if __name__ == "__main__":
    main()
