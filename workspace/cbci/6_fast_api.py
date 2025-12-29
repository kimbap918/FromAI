import os
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Query, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient, DESCENDING
from dotenv import load_dotenv
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "")
MONGO_DB  = os.getenv("MONGO_DB", "news")
MONGO_COL = os.getenv("MONGO_COL", "yna_news")
API_KEY   = os.getenv("API_KEY", "")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI is required")

client = MongoClient(MONGO_URI)
col = client[MONGO_DB][MONGO_COL]

app = FastAPI(title="CBC Mongo API", version="1.0")

# ✅ 다른 웹사이트에서 호출하려면 CORS 허용 필요
# 운영에서는 allow_origins를 * 대신 특정 도메인만 넣는 걸 추천
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

def auth(x_api_key: Optional[str]):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

def parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    # "2025-12-29 15:30:00" 또는 ISO 둘 다 대응
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    raise HTTPException(status_code=400, detail=f"Invalid datetime: {s}")

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/news")
def list_news(
    x_api_key: Optional[str] = Header(default=None),
    group: Optional[str] = None,
    person: Optional[str] = None,
    cid: Optional[str] = None,
    q: Optional[str] = None,  # 간단 검색(인덱스 권장)
    from_dt: Optional[str] = Query(default=None, alias="from"),
    to_dt: Optional[str] = Query(default=None, alias="to"),
    limit: int = Query(default=20, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
):
    auth(x_api_key)

    query: Dict[str, Any] = {}
    if group:
        query["Group"] = group
    if person:
        query["PERSON"] = person
    if cid:
        query["CID"] = cid

    fdt = parse_dt(from_dt)
    tdt = parse_dt(to_dt)
    if fdt or tdt:
        query["DATETIME"] = {}
        if fdt:
            query["DATETIME"]["$gte"] = fdt.strftime("%Y-%m-%d %H:%M:%S")
        if tdt:
            query["DATETIME"]["$lte"] = tdt.strftime("%Y-%m-%d %H:%M:%S")

    # q는 예시(텍스트 인덱스 만들면 더 좋음)
    if q:
        query["$or"] = [
            {"TITLE": {"$regex": q, "$options": "i"}},
            {"CONTENT": {"$regex": q, "$options": "i"}},
        ]

    projection = {"_id": 0}  # ObjectId 숨김
    cursor = col.find(query, projection).sort("DATETIME", DESCENDING).skip(skip).limit(limit)
    items = list(cursor)
    total = col.count_documents(query)

    return {"total": total, "skip": skip, "limit": limit, "items": items}

@app.get("/news/{cid}")
def get_news(cid: str, x_api_key: Optional[str] = Header(default=None)):
    auth(x_api_key)
    doc = col.find_one({"CID": cid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    return doc
