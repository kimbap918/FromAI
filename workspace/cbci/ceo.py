# kftc_all.py
# pip install requests
#
# 변경점:
# - ✅ EXCLUDED_GROUPS 목록에 포함된 기업집단(unityGrupNm)은 최종 저장/계열사 조회에서 제외

from __future__ import annotations

import os
import re
import csv
import time
import argparse
from typing import Dict, List, Tuple, Optional
from urllib.parse import urlencode

import requests
import xml.etree.ElementTree as ET


# 1) 기업집단 현황(총수/대표회사/계열사수/기업집단코드)
GROUP_URLS = [
    "https://apis.data.go.kr/1130000/appnGroupSttusList/appnGroupSttusListApi",
    "http://apis.data.go.kr/1130000/appnGroupSttusList/appnGroupSttusListApi",
]

# 2) 소속회사(계열사) 목록
AFFI_URLS = [
    "https://apis.data.go.kr/1130000/appnGroupAffiList/appnGroupAffiListApi",
    "http://apis.data.go.kr/1130000/appnGroupAffiList/appnGroupAffiListApi",
    "https://apis.data.go.kr/1130000/appnGroupAffiList/appnGroupAffiList",
    "http://apis.data.go.kr/1130000/appnGroupAffiList/appnGroupAffiList",
]

UA = "PressAI-KFTC/1.0"

# -----------------------
# ✅ 제외할 기업집단 목록
# -----------------------
EXCLUDED_GROUPS_RAW = """
영풍
하림
효성
장금상선
SM
에이치디씨
호반건설
코오롱
케이씨씨
DB
넥슨
오씨아이
엘엑스
세아
넷마블
이랜드
교보생명보험
다우키움
금호석유화학
대방건설
태영
삼천리
KG
에코프로
HL
동원
아모레퍼시픽
태광
크래프톤
글로벌세아
엠디엠
소노인터내셔널
애경
동국제강
BS(舊 보성)
삼양
엘아이지
중앙
유진
고려에이치씨
BGF
대광
반도홀딩스
대신
오케이금융그룹
하이트진로
농심
DN
현대해상화재보험
신영
파라다이스
아이에스지주
하이브
한솔
삼표
사조
원익
빗썸
""".strip()


def normalize_group_name(name: str) -> str:
    """
    비교 안정화:
    - 공백 제거
    - ASCII 영문은 대문자화
    - 기타 문자는 그대로
    """
    s = (name or "").strip()
    s = re.sub(r"\s+", "", s)
    # 영문만 대문자 처리
    out = []
    for ch in s:
        if "a" <= ch <= "z" or "A" <= ch <= "Z":
            out.append(ch.upper())
        else:
            out.append(ch)
    return "".join(out)


EXCLUDED_GROUPS = {normalize_group_name(x) for x in EXCLUDED_GROUPS_RAW.splitlines() if x.strip()}


# -----------------------
# 공통: 사람 총수 필터
# -----------------------
CORP_TOKENS = [
    "(주)", "㈜", "주식회사", "유한회사", "재단", "법인",
    "중앙회", "조합", "협회", "위원회", "공사", "공단",
    "은행", "보험", "증권", "지주", "홀딩스", "학교", "병원"
]


def looks_like_person_name(s: str) -> bool:
    """총수(동일인)가 사람 이름처럼 보이는지(기업/기관명 제거용)"""
    s = (s or "").strip()
    if not s:
        return False

    # 일반적인 한국인 성명(2~4자) 통과
    if re.fullmatch(r"[가-힣]{2,4}", s):
        return True

    # 법인/기관 토큰 포함은 제외
    if any(t in s for t in CORP_TOKENS):
        return False

    # 영문/숫자/괄호/공백이 섞이면 대부분 기관/법인으로 보고 제외
    if re.search(r"[A-Za-z0-9]", s) or "(" in s or ")" in s or " " in s:
        return False

    # 너무 길면 제외
    if len(s) >= 6:
        return False

    return True


# -----------------------
# 공통: API 호출(키 인코딩 이슈 대비)
# -----------------------
def http_get(url: str, params: Optional[dict] = None, timeout: int = 30) -> requests.Response:
    return requests.get(url, params=params, timeout=timeout, headers={"User-Agent": UA, "Accept": "application/xml"})


def call_openapi_any(
    urls: List[str],
    service_key: str,
    params: Dict[str, str],
    debug: bool = False
) -> str:
    """
    data.go.kr은 환경에 따라 ServiceKey/serviceKey, params/수동쿼리 조합이 다르게 먹는 경우가 있어
    가능한 조합을 모두 시도한다.
    """
    last_err = None

    # 1) requests params 방식 (ServiceKey/serviceKey)
    for url in urls:
        for key_name in ("ServiceKey", "serviceKey"):
            try:
                r = http_get(url, params={key_name: service_key, **params})
                if debug:
                    print("[DEBUG]", r.status_code, r.url)
                r.raise_for_status()
                return r.text
            except Exception as e:
                last_err = e

    # 2) 수동 쿼리 스트링 방식 (ServiceKey/serviceKey)
    for url in urls:
        for key_name in ("ServiceKey", "serviceKey"):
            try:
                qs = urlencode({key_name: service_key, **params}, doseq=True, safe="=/")
                full = f"{url}?{qs}"
                r = http_get(full, params=None)
                if debug:
                    print("[DEBUG]", r.status_code, full)
                r.raise_for_status()
                return r.text
            except Exception as e:
                last_err = e

    raise RuntimeError(f"OpenAPI 호출 실패. last_err={last_err}")


# -----------------------
# XML 파싱
# -----------------------
def parse_meta_and_items(xml_text: str, item_tag_candidates: List[str]) -> Tuple[dict, List[dict]]:
    root = ET.fromstring(xml_text)

    meta = {
        "resultCode": root.findtext(".//resultCode") or "",
        "resultMsg": root.findtext(".//resultMsg") or "",
        "totalCount": root.findtext(".//totalCount") or "0",
        "pageNo": root.findtext(".//pageNo") or "",
        "numOfRows": root.findtext(".//numOfRows") or "",
    }
    if meta["resultCode"] and meta["resultCode"] != "00":
        raise RuntimeError(f"API Error: {meta['resultCode']} / {meta['resultMsg']}")

    for tag in item_tag_candidates:
        nodes = root.findall(f".//{tag}")
        if nodes:
            rows = []
            for n in nodes:
                rows.append({c.tag: (c.text or "").strip() for c in list(n)})
            return meta, rows

    nodes = root.findall(".//item")
    if nodes:
        rows = []
        for n in nodes:
            rows.append({c.tag: (c.text or "").strip() for c in list(n)})
        return meta, rows

    return meta, []


def fetch_all_pages(
    urls: List[str],
    service_key: str,
    base_params: Dict[str, str],
    item_tags: List[str],
    num_of_rows: int,
    sleep_sec: float,
    debug: bool
) -> List[dict]:
    page = 1
    all_rows: List[dict] = []
    total = None

    while True:
        params = dict(base_params)
        params["pageNo"] = str(page)
        params["numOfRows"] = str(num_of_rows)

        xml = call_openapi_any(urls, service_key, params, debug=debug)
        meta, rows = parse_meta_and_items(xml, item_tags)

        if total is None:
            try:
                total = int(meta.get("totalCount") or "0")
            except ValueError:
                total = 0

        if not rows:
            break

        all_rows.extend(rows)

        if total and len(all_rows) >= total:
            break

        page += 1
        time.sleep(sleep_sec)

        if page > 1000:
            raise RuntimeError("페이지가 비정상적으로 많습니다. 파라미터를 확인하세요.")

    return all_rows


# -----------------------
# 계열사 사명 키 추정
# -----------------------
AFFI_NAME_KEYS = ["sosokCmpnyNm", "affiCmpnyNm", "cmpnyNm", "companyNm", "cmpnyNmKor"]


def pick_affiliate_name(rec: dict) -> str:
    for k in AFFI_NAME_KEYS:
        v = (rec.get(k) or "").strip()
        if v:
            return v
    for k, v in rec.items():
        if k.lower().endswith("nm") and (v or "").strip():
            return (v or "").strip()
    return ""


# -----------------------
# CSV 저장
# -----------------------
def save_csv(path: str, fieldnames: List[str], rows: List[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--presentnYear",
        default=os.getenv("PRESENTN_YEAR", "202505"),
        help="지정년월 YYYYMM (예: 202501). 미지정 시 PRESENTN_YEAR 또는 기본 202505 사용"
    )
    ap.add_argument("--sleep", type=float, default=0.15, help="요청 간 딜레이(초)")
    ap.add_argument("--numOfRows", type=int, default=200, help="그룹 조회 페이지당 개수")
    ap.add_argument("--affiNumOfRows", type=int, default=1000, help="계열사 조회 페이지당 개수")
    ap.add_argument("--out_groups", default="groups_filtered.csv", help="기업집단 CSV")
    ap.add_argument("--out_affiliates", default="affiliates.csv", help="계열사 CSV")
    ap.add_argument("--debug", action="store_true", help="디버그 출력")
    args = ap.parse_args()

    service_key = os.getenv("DATA_GO_KR_SERVICE_KEY", "").strip()
    if not service_key:
        raise SystemExit("환경변수 DATA_GO_KR_SERVICE_KEY에 (Decoding) 인증키를 설정하세요.")

    # 1) 기업집단 목록 전체 조회
    groups_raw = fetch_all_pages(
        GROUP_URLS,
        service_key,
        base_params={"presentnYear": args.presentnYear},
        item_tags=["appnGroupSttus"],
        num_of_rows=args.numOfRows,
        sleep_sec=args.sleep,
        debug=args.debug,
    )

    # 2) 사람 총수만 + ✅ 제외 기업집단 제거
    groups = []
    excluded_count = 0
    excluded_names = []

    for g in groups_raw:
        smer = (g.get("smerNm") or "").strip()
        grup_nm = (g.get("unityGrupNm") or "").strip()

        # 사람 총수 필터
        if not looks_like_person_name(smer):
            continue

        # ✅ 제외 목록 필터
        if normalize_group_name(grup_nm) in EXCLUDED_GROUPS:
            excluded_count += 1
            excluded_names.append(grup_nm)
            continue

        groups.append(g)

    if excluded_count:
        print(f"[INFO] 제외된 기업집단: {excluded_count}건")
        if args.debug:
            print("[INFO] 제외 목록(실제 매칭):", ", ".join(excluded_names))

    # groups CSV 저장(핵심 필드)
    group_fields = [
        "presentnYear", "unityGrupNm", "unityGrupCode", "smerNm", "repreCmpny",
        "sumCmpnyCo", "invstmntLmtt", "entrprsCl"
    ]
    groups_out = []
    for g in groups:
        groups_out.append({
            "presentnYear": args.presentnYear,
            "unityGrupNm": g.get("unityGrupNm", ""),
            "unityGrupCode": g.get("unityGrupCode", ""),
            "smerNm": g.get("smerNm", ""),
            "repreCmpny": g.get("repreCmpny", ""),
            "sumCmpnyCo": g.get("sumCmpnyCo", ""),
            "invstmntLmtt": g.get("invstmntLmtt", ""),
            "entrprsCl": g.get("entrprsCl", ""),
        })

    save_csv(args.out_groups, group_fields, groups_out)
    print(f"[OK] 기업집단(사람 총수만, 제외목록 적용) 저장: {args.out_groups}  ({len(groups_out)}건)")

    # 3) 각 기업집단코드로 계열사 전부 조회
    affiliates_out: List[dict] = []
    errors: List[dict] = []

    for idx, g in enumerate(groups, start=1):
        code = (g.get("unityGrupCode") or "").strip()
        name = (g.get("unityGrupNm") or "").strip()
        owner = (g.get("smerNm") or "").strip()

        if not code:
            continue

        print(f"  [{idx}/{len(groups)}] 계열사 조회: {name} ({code}) / 총수={owner}")

        try:
            affis_raw = fetch_all_pages(
                AFFI_URLS,
                service_key,
                base_params={"presentnYear": args.presentnYear, "unityGrupCode": code},
                item_tags=["appnGroupAffi"],
                num_of_rows=args.affiNumOfRows,
                sleep_sec=args.sleep,
                debug=args.debug,
            )

            for a in affis_raw:
                affiliates_out.append({
                    "presentnYear": args.presentnYear,
                    "unityGrupNm": name,
                    "unityGrupCode": code,
                    "ownerName": owner,
                    "affiliateName": pick_affiliate_name(a),
                })

        except Exception as e:
            errors.append({
                "presentnYear": args.presentnYear,
                "unityGrupNm": name,
                "unityGrupCode": code,
                "ownerName": owner,
                "error": str(e),
            })
            print("    [WARN] 실패:", e)

    # affiliates CSV 저장
    affi_fields = ["presentnYear", "unityGrupNm", "unityGrupCode", "ownerName", "affiliateName"]
    save_csv(args.out_affiliates, affi_fields, affiliates_out)
    print(f"[OK] 계열사 저장(제외목록 적용): {args.out_affiliates}  ({len(affiliates_out)}건)")

    # 에러가 있으면 별도 파일 저장
    if errors:
        err_path = "affiliates_errors.csv"
        save_csv(err_path, ["presentnYear", "unityGrupNm", "unityGrupCode", "ownerName", "error"], errors)
        print(f"[WARN] 계열사 조회 실패 그룹 존재 → {err_path} 확인 ({len(errors)}건)")


if __name__ == "__main__":
    main()
