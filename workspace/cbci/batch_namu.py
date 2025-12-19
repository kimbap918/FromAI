# batch_namu_from_groups.py
# 목적: groups_filtered.csv의 "총수(동일인)" 목록을 기반으로 나무위키 프로필을 일괄 수집
#
# 실행:
#   python batch_namu_from_groups.py --in groups_filtered.csv --out profiles.csv --out_dir namu_profiles --sleep 1.2 --refresh_bad
#
# 변경점(중요):
# - ✅ scrape(이름) 결과가 "빈 결과"면 scrape(이름(기업인))로 자동 재시도
# - ✅ profile_image만 있는 오탐을 "빈 결과"로 간주하도록 판정 강화
# - ✅ --refresh_bad 켜면 기존 캐시가 빈 결과일 때 재수집

from __future__ import annotations

import os
import re
import csv
import json
import time
import argparse
import random
from typing import Dict, Any, List, Optional

from namu import scrape  # namu.py 에 scrape()가 있다고 가정


# ---- 입력 CSV 컬럼 후보(헤더가 조금 달라도 자동 탐색) ----
CANDIDATE_NAME_COLS = ["총수(동일인)", "총수", "동일인", "smerNm", "ceo", "name"]
CANDIDATE_GROUP_COLS = ["기업집단", "unityGrupNm", "unity_grup_nm"]
CANDIDATE_GROUP_CODE_COLS = ["기업집단코드", "unityGrupCode", "unity_grup_code"]
CANDIDATE_REP_COLS = ["대표회사", "repreCmpny", "repre_cmpny"]
CANDIDATE_COUNT_COLS = ["계열사수", "sumCmpnyCo", "sum_cmpny_co"]


def sniff_dialect(path: str) -> csv.Dialect:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
    try:
        return csv.Sniffer().sniff(sample, delimiters=[",", "\t", ";", "|"])
    except Exception:
        class D(csv.Dialect):
            delimiter = ","
            quotechar = '"'
            doublequote = True
            skipinitialspace = True
            lineterminator = "\n"
            quoting = csv.QUOTE_MINIMAL
        return D


def pick_col(fieldnames: List[str], candidates: List[str]) -> Optional[str]:
    if not fieldnames:
        return None

    # 1) 완전 일치
    for c in candidates:
        if c in fieldnames:
            return c

    # 2) 공백/괄호 제거 후 매칭
    norm = lambda s: re.sub(r"[\s()]", "", (s or "")).lower()
    f_norm_map = {norm(fn): fn for fn in fieldnames}
    for c in candidates:
        key = norm(c)
        if key in f_norm_map:
            return f_norm_map[key]

    # 3) 포함 매칭
    for fn in fieldnames:
        for c in candidates:
            if norm(c) and norm(c) in norm(fn):
                return fn

    return None


def safe_filename(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"[\\/:*?\"<>|]", "_", name)
    name = re.sub(r"\s+", "_", name)
    return name


def join_people(arr: Any) -> str:
    if not arr:
        return ""
    if isinstance(arr, list):
        names = []
        for x in arr:
            if isinstance(x, dict):
                nm = (x.get("name") or "").strip()
                if nm:
                    names.append(nm)
            elif isinstance(x, str) and x.strip():
                names.append(x.strip())
        return "|".join(names)
    return ""


def siblings_to_text(siblings: Dict[str, Any]) -> str:
    if not siblings:
        return ""
    parts = []
    for k in ["형", "누나", "오빠", "언니", "동생", "미분류"]:
        v = siblings.get(k, [])
        t = join_people(v)
        if t:
            parts.append(f"{k}:{t}")
    return " / ".join(parts)


def flatten_family_map(family: Dict[str, Any]) -> str:
    fl = (family or {}).get("flatten", {})
    try:
        return json.dumps(fl, ensure_ascii=False)
    except Exception:
        return ""


def _norm_person_name(s: str) -> str:
    # 공백 제거 + 뒤쪽 괄호 구분자 제거
    s = (s or "").strip()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"\([^)]*\)$", "", s)  # trailing qualifier
    return s


def is_bad_profile_result(d: Any, expected_name: str) -> bool:
    """
    ✅ '페이지는 열렸지만 실질 정보가 없는' 결과를 실패로 판정
    - profile_image만 있는 경우도 실패
    - name_ko가 비거나, expected_name과 무관하면 실패
    - birth_date / family.flatten 등 핵심 정보가 너무 비면 실패
    """
    if not isinstance(d, dict):
        return True
    if d.get("error"):
        return True

    name_ko = (d.get("name_ko") or "").strip()
    position = (d.get("position") or "").strip()
    birth_date = (d.get("birth_date") or "").strip()

    fam = d.get("family") if isinstance(d.get("family"), dict) else {}
    flatten = fam.get("flatten") if isinstance(fam, dict) and isinstance(fam.get("flatten"), dict) else {}

    # 1) 이름이 비면 무조건 실패
    if not name_ko:
        return True

    # 2) 기대 이름과 무관하면 실패(동명이인 페이지 방지)
    exp = _norm_person_name(expected_name)
    got = _norm_person_name(name_ko)
    if exp and got and (exp not in got) and (got not in exp):
        return True

    # 3) 실질 정보 점수(이미지는 제외)
    score = 0
    if position:
        score += 1
    if birth_date:
        score += 1
    if flatten:
        score += 1

    # position만 있거나(=1) / 아무것도 없으면(=0) → 실패로 보고 (기업인) 재시도
    return score < 2


def is_bad_cached_profile(d: Any, expected_name: str) -> bool:
    # 캐시도 동일 판정 사용(중요: profile_image만으로 통과시키지 않음)
    return is_bad_profile_result(d, expected_name=expected_name)


def build_candidates(person_name: str) -> List[str]:
    person_name = (person_name or "").strip()
    if not person_name:
        return []
    if person_name.endswith("(기업인)"):
        return [person_name]
    return [person_name, f"{person_name}(기업인)"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_csv", required=True, help="입력 CSV (예: groups_filtered.csv)")
    ap.add_argument("--out", dest="out_csv", default="profiles.csv", help="출력 CSV")
    ap.add_argument("--out_dir", default="namu_profiles", help="인물별 JSON 캐시 저장 폴더")
    ap.add_argument("--sleep", type=float, default=1.2, help="요청 간 기본 sleep(초)")
    ap.add_argument("--jitter", type=float, default=0.6, help="sleep 랜덤 가산(0~jitter)")
    ap.add_argument("--limit", type=int, default=0, help="0이면 전체, 아니면 N명만 테스트")
    ap.add_argument("--headed", action="store_true", help="브라우저 표시(디버그)")
    ap.add_argument("--dump_on_fail", action="store_true", help="덤프 저장(문제 추적용)")
    ap.add_argument("--refresh_bad", action="store_true", help="✅ 캐시가 빈 결과면 재수집(덮어쓰기)")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    dialect = sniff_dialect(args.in_csv)
    with open(args.in_csv, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, dialect=dialect)
        fieldnames = reader.fieldnames or []

        name_col = pick_col(fieldnames, CANDIDATE_NAME_COLS)
        group_col = pick_col(fieldnames, CANDIDATE_GROUP_COLS)
        group_code_col = pick_col(fieldnames, CANDIDATE_GROUP_CODE_COLS)
        rep_col = pick_col(fieldnames, CANDIDATE_REP_COLS)
        count_col = pick_col(fieldnames, CANDIDATE_COUNT_COLS)

        if not name_col:
            raise RuntimeError(
                f"총수 이름 컬럼을 못 찾았어요.\n"
                f"현재 헤더: {fieldnames}\n"
                f"탐색 후보: {CANDIDATE_NAME_COLS}"
            )

        rows = list(reader)

    out_fields = [
        "기업집단", "기업집단코드", "총수(동일인)", "대표회사", "계열사수",
        "resolved_title", "source_url",
        "position", "name_ko", "name_hanja", "name_en", "birth_date", "profile_image",
        "father", "mother",
        "spouse", "children", "siblings",
        "family_flatten_json",
        "error",
    ]

    cache: Dict[str, Dict[str, Any]] = {}

    def fetch_one(person_name: str) -> Dict[str, Any]:
        if person_name in cache:
            return cache[person_name]

        json_path = os.path.join(args.out_dir, f"{safe_filename(person_name)}.json")

        # 파일 캐시
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as jf:
                    data = json.load(jf)

                if args.refresh_bad and is_bad_cached_profile(data, expected_name=person_name):
                    data = None
                else:
                    cache[person_name] = data
                    return data
            except Exception:
                pass

        # ✅ 핵심: '결과가 비면' (기업인)으로 재시도
        last: Dict[str, Any] = {}
        last_err = ""
        attempted = build_candidates(person_name)

        for q in attempted:
            try:
                d = scrape(q, headed=args.headed, debug=False, dump=args.dump_on_fail)

                # scrape가 resolved_title을 안 넣는 구현도 있으니, 여기서 보정
                if isinstance(d, dict):
                    d.setdefault("resolved_title", q)

                if not is_bad_profile_result(d, expected_name=person_name):
                    last = d
                    last_err = ""
                    break

                # 실패로 판단되면 다음 후보로
                last = d if isinstance(d, dict) else {}
                last_err = last.get("error", "") if isinstance(last, dict) else ""
            except Exception as e:
                last_err = str(e)
                last = {"error": last_err, "resolved_title": q}

        if isinstance(last, dict) and last_err and not last.get("error"):
            last["error"] = last_err

        # 저장(원래 person_name 기준으로 1개 파일에 최종 결과 저장)
        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump(last, jf, ensure_ascii=False, indent=2)

        cache[person_name] = last

        time.sleep(max(0.0, args.sleep + random.random() * args.jitter))
        return last

    out_rows = []
    processed = 0
    total = len(rows)

    for r in rows:
        name = (r.get(name_col) or "").strip()
        if not name:
            continue
        if args.limit and processed >= args.limit:
            break

        group_nm = (r.get(group_col) or "").strip() if group_col else ""
        group_cd = (r.get(group_code_col) or "").strip() if group_code_col else ""
        rep = (r.get(rep_col) or "").strip() if rep_col else ""
        cnt = (r.get(count_col) or "").strip() if count_col else ""

        data: Dict[str, Any] = {}
        err = ""
        try:
            data = fetch_one(name)
        except Exception as e:
            err = str(e)
            data = {"error": err}

        fam = (data or {}).get("family", {}) if isinstance(data, dict) else {}
        parents = (fam or {}).get("parents", {}) if isinstance(fam, dict) else {}
        father = ((parents or {}).get("father", {}) or {}).get("name", "")
        mother = ((parents or {}).get("mother", {}) or {}).get("name", "")

        siblings = siblings_to_text((fam or {}).get("siblings", {}) if isinstance(fam, dict) else {})
        spouse = join_people((fam or {}).get("spouse", []) if isinstance(fam, dict) else [])
        children = join_people((fam or {}).get("children", []) if isinstance(fam, dict) else [])

        row_out = {
            "기업집단": group_nm,
            "기업집단코드": group_cd,
            "총수(동일인)": name,
            "대표회사": rep,
            "계열사수": cnt,

            "resolved_title": (data or {}).get("resolved_title", "") if isinstance(data, dict) else "",
            "source_url": (data or {}).get("source_url", "") if isinstance(data, dict) else "",

            "position": (data or {}).get("position", "") if isinstance(data, dict) else "",
            "name_ko": (data or {}).get("name_ko", "") if isinstance(data, dict) else "",
            "name_hanja": (data or {}).get("name_hanja", "") if isinstance(data, dict) else "",
            "name_en": (data or {}).get("name_en", "") if isinstance(data, dict) else "",
            "birth_date": (data or {}).get("birth_date", "") if isinstance(data, dict) else "",
            "profile_image": (data or {}).get("profile_image", "") if isinstance(data, dict) else "",

            "father": father,
            "mother": mother,
            "spouse": spouse,
            "children": children,
            "siblings": siblings,
            "family_flatten_json": flatten_family_map(fam if isinstance(fam, dict) else {}),

            "error": (data or {}).get("error", "") if isinstance(data, dict) and data.get("error") else err,
        }

        out_rows.append(row_out)
        processed += 1

        ok = "OK" if not row_out["error"] else "FAIL"
        print(f"[{processed}/{total}] {name} -> {ok}  (resolved: {row_out['resolved_title']})")

    with open(args.out_csv, "w", encoding="utf-8-sig", newline="") as wf:
        w = csv.DictWriter(wf, fieldnames=out_fields)
        w.writeheader()
        w.writerows(out_rows)

    print(f"\n[OK] 완료: {args.out_csv}")
    print(f"[OK] 캐시 폴더: {args.out_dir} (재실행 시 이미 수집된 인물은 재사용)")


if __name__ == "__main__":
    main()
