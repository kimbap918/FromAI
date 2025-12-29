"""
csv_to_mongo.py

생성된 CSV(yna_news_*.csv)를 읽어서 MongoDB에 업로드(upsert)합니다.

기본 저장 필드(요청 필드):
- Group, PERSON, CID, DATETIME, TITLE, CONTENT, URL

옵션:
- --with-image : CSV에 IMAGE_URL / IMAGE_URLS 컬럼이 있으면 Mongo에도 함께 저장(이미지 URL만)
- --only-ok    : CONTENT_STATUS==OK 인 행만 업로드(컬럼이 있을 때만 적용)

사용 예)
python csv_to_mongo.py --csv "yna_news_20251229_153000_last120d_company_plus_person_only.csv"
python csv_to_mongo.py --csv "file.csv" --db news --col yna_news --only-ok
python csv_to_mongo.py --csv "file.csv" --with-image
"""

import csv
import json
import argparse
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv
load_dotenv()


DEFAULT_MONGO_URI = os.getenv("MONGO_URI", "")
DEFAULT_DB = os.getenv("MONGO_DB", "news")
DEFAULT_COL = os.getenv("MONGO_COL", "yna_news")


def parse_datetime(dt_str: str):
    """
    CSV의 DATETIME이 'YYYY-mm-dd HH:MM:SS' 형태면 datetime으로 변환.
    실패하면 원문 문자열로 반환.
    """
    if not dt_str:
        return ""
    s = dt_str.strip()
    if not s:
        return ""
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return s


def parse_image_urls(raw: str) -> List[str]:
    """
    CSV의 IMAGE_URLS 파싱:
    - 우선 JSON 문자열(["url1","url2"])로 파싱 시도
    - 실패하면 | 또는 , 로 split
    """
    if not raw:
        return []
    s = raw.strip()
    if not s:
        return []

    # JSON list 형태 우선
    if (s.startswith("[") and s.endswith("]")) or (s.startswith('"[') and s.endswith(']"')):
        try:
            obj = json.loads(s)
            if isinstance(obj, list):
                return [str(x).strip() for x in obj if str(x).strip()]
        except Exception:
            pass

    # 구분자 split 폴백
    if "|" in s:
        parts = [p.strip() for p in s.split("|")]
    else:
        parts = [p.strip() for p in s.split(",")]

    # 중복 제거(순서 유지)
    out = []
    seen = set()
    for p in parts:
        if not p:
            continue
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


def row_to_doc(row: Dict[str, Any], with_image: bool = False) -> Dict[str, Any]:
    """
    CSV row -> MongoDB doc

    필수 컬럼(요청 7개):
      GROUP, PERSON, CID, DATETIME, TITLE, CONTENT, URL

    with_image=True 이면:
      IMAGE_URL, IMAGE_URLS (있을 때만)도 함께 저장
    """
    doc = {
        "Group": (row.get("GROUP") or "").strip(),
        "PERSON": (row.get("PERSON") or "").strip(),
        "CID": (row.get("CID") or "").strip(),
        "DATETIME": parse_datetime(row.get("DATETIME") or ""),
        "TITLE": (row.get("TITLE") or "").strip(),
        "CONTENT": (row.get("CONTENT") or "").strip(),
        "URL": (row.get("URL") or "").strip(),
    }

    if with_image:
        # CSV에 컬럼이 아예 없을 수도 있으니 안전하게
        img = (row.get("IMAGE_URL") or "").strip()
        imgs = row.get("IMAGE_URLS") or ""

        if img:
            doc["IMAGE_URL"] = img
        if imgs:
            doc["IMAGE_URLS"] = parse_image_urls(imgs)

    return doc


def upload_csv_to_mongo(
    csv_path: str,
    mongo_uri: str = DEFAULT_MONGO_URI,
    db_name: str = DEFAULT_DB,
    col_name: str = DEFAULT_COL,
    upsert: bool = True,
    only_ok: bool = False,
    batch_size: int = 500,
    with_image: bool = False,
):
    if not mongo_uri:
        raise RuntimeError("MONGO_URI is required. Set it in .env or pass with --uri.")
    client = MongoClient(mongo_uri)
    col = client[db_name][col_name]

    ops: List[UpdateOne] = []
    total_rows = 0
    skipped = 0
    sent = 0

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        required = {"GROUP", "PERSON", "CID", "DATETIME", "TITLE", "CONTENT", "URL"}
        fieldnames = set(reader.fieldnames or [])
        missing = required - fieldnames
        if missing:
            client.close()
            raise ValueError(f"CSV에 필요한 컬럼이 없습니다: {sorted(missing)}")

        # 이미지 옵션일 때는 컬럼이 없어도 에러는 내지 않음(있으면 저장)
        has_content_status = "CONTENT_STATUS" in fieldnames

        for row in reader:
            total_rows += 1

            cid = (row.get("CID") or "").strip()
            if not cid:
                skipped += 1
                continue

            if only_ok and has_content_status:
                if (row.get("CONTENT_STATUS") or "").strip() != "OK":
                    skipped += 1
                    continue

            doc = row_to_doc(row, with_image=with_image)

            ops.append(
                UpdateOne(
                    {"CID": cid},      # ✅ CID 기준 upsert
                    {"$set": doc},
                    upsert=upsert,
                )
            )

            if len(ops) >= batch_size:
                res = col.bulk_write(ops, ordered=False)
                sent += len(ops)
                ops.clear()
                print(
                    f"[업로드] rows={total_rows}, sent={sent}, skipped={skipped}, "
                    f"matched={res.matched_count}, modified={res.modified_count}, upserted={len(res.upserted_ids or {})}"
                )

        if ops:
            res = col.bulk_write(ops, ordered=False)
            sent += len(ops)
            ops.clear()
            print(
                f"[업로드] rows={total_rows}, sent={sent}, skipped={skipped}, "
                f"matched={res.matched_count}, modified={res.modified_count}, upserted={len(res.upserted_ids or {})}"
            )

    client.close()

    print("✅ 완료")
    print({
        "csv": csv_path,
        "total_rows": total_rows,
        "sent": sent,
        "skipped": skipped,
        "db": db_name,
        "collection": col_name,
        "upsert": upsert,
        "only_ok": only_ok,
        "with_image": with_image,
    })


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", required=True, help="업로드할 CSV 파일 경로")
    p.add_argument("--uri", default=DEFAULT_MONGO_URI, help="MongoDB URI")
    p.add_argument("--db", default=DEFAULT_DB, help="DB 이름")
    p.add_argument("--col", default=DEFAULT_COL, help="Collection 이름")
    p.add_argument("--no-upsert", action="store_true", help="upsert 비활성화(기본은 upsert)")
    p.add_argument("--only-ok", action="store_true", help="CONTENT_STATUS==OK 인 행만 업로드(컬럼이 있을 때만 적용)")
    p.add_argument("--batch-size", type=int, default=500, help="bulk_write 배치 크기")
    p.add_argument("--with-image", action="store_true", help="IMAGE_URL/IMAGE_URLS 컬럼이 있으면 Mongo에도 함께 저장(이미지 URL만)")
    args = p.parse_args()

    upload_csv_to_mongo(
        csv_path=args.csv,
        mongo_uri=args.uri,
        db_name=args.db,
        col_name=args.col,
        upsert=not args.no_upsert,
        only_ok=args.only_ok,
        batch_size=args.batch_size,
        with_image=args.with_image,
    )


if __name__ == "__main__":
    main()
