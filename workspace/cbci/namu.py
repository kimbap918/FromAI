# namu.py
# pip install beautifulsoup4 lxml playwright
# playwright install chromium

from __future__ import annotations

import re
from typing import Dict, List, Tuple, Optional
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup, Tag, NavigableString
from playwright.sync_api import sync_playwright

BASE = "https://namu.wiki"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36"

# 인포박스 테이블 최소 신뢰 점수 (낮으면 동명이인/일반 문서 오탐 가능)
INFOBOX_MIN_SCORE = 10


def clean(s: str) -> str:
    return " ".join((s or "").replace("\xa0", " ").split()).strip()


def abs_url(u: str) -> str:
    return urljoin(BASE, u or "")


def build_url(title_ko: str) -> str:
    # 괄호는 safe에 포함
    return f"{BASE}/w/{quote(clean(title_ko), safe='()')}"


def strip_refs(text: str) -> str:
    t = clean(text)
    t = re.sub(r"\s*\[\d+\]\s*", "", t)
    t = re.sub(r"\s*\[[^\]]+\]\s*", "", t)
    return clean(t)


def extract_date(text: str) -> str:
    m = re.search(r"\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일", text)
    return clean(m.group(0)) if m else ""


def candidate_titles(name_ko: str) -> List[str]:
    """
    ✅ 기본 문서가 '인물 인포박스'를 못 주면 (기업인)으로 재시도
    """
    name_ko = clean(name_ko)
    if not name_ko:
        return []
    # 이미 (기업인)이면 1개만
    if name_ko.endswith("(기업인)"):
        return [name_ko]
    # 기본 + 기업인
    return [name_ko, f"{name_ko}(기업인)"]


def is_person_anchor(a: Tag) -> bool:
    if not a or a.name != "a":
        return False
    cls = a.get("class") or []
    return ("zkdXfE03" in cls) or ("i626Z3UJ" in cls)


def anchor_obj(a: Tag) -> Dict[str, str]:
    return {"name": strip_refs(a.get_text(" ", strip=True)), "url": abs_url(a.get("href", ""))}


# -----------------------------
# Playwright: "인물 인포박스" 후보 테이블만 선택
# -----------------------------
def fetch_infobox_outer_html(url: str, headed: bool = False) -> Tuple[str, int, str]:
    """
    return: (infobox_outer_html, score, page_html)
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=(not headed))
        page = browser.new_page(user_agent=UA, locale="ko-KR")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(300)

        # ✅ 인물 인포박스 특징(네가 준 클래스/구조)에 더 강하게 맞춤
        result = page.evaluate(
            """() => {
                const tables = Array.from(document.querySelectorAll('table'));
                const labels = ['출생','부모','배우자','자녀','형제자매','현직'];

                function labelScore(t){
                    // th/td 첫 컬럼에서 label이 얼마나 나오는지
                    const rows = Array.from(t.querySelectorAll('tr'));
                    let hits = 0;
                    for (const tr of rows){
                        const th = tr.querySelector('th');
                        if (th && labels.includes(th.innerText.trim())) hits += 1;
                        const tds = tr.querySelectorAll('td');
                        if (tds.length >= 2 && labels.includes((tds[0].innerText||'').trim())) hits += 1;
                    }
                    return hits;
                }

                function score(t){
                    const hasStrong = !!t.querySelector('div.IBdgNaCn strong');
                    const hasProfileImg = !!t.querySelector('img.xzxn3I3c');
                    const hit = labelScore(t);

                    let s = 0;
                    if (hasStrong) s += 8;
                    if (hasProfileImg) s += 4;
                    s += hit * 5;

                    // 너무 큰 표는 본문 표일 확률
                    const len = (t.innerText || '').length;
                    if (len > 12000) s -= 5;

                    return s;
                }

                let best = null;
                let bestScore = -1;
                for (const t of tables){
                    const sc = score(t);
                    if (sc > bestScore){
                        bestScore = sc;
                        best = t;
                    }
                }
                return {bestScore, hasBest: !!best};
            }"""
        )

        bestScore = int(result["bestScore"]) if result else -1

        if not result or not result.get("hasBest") or bestScore < INFOBOX_MIN_SCORE:
            html = page.content()
            browser.close()
            return "", bestScore, html

        # best table 다시 찾기 (evaluate로 best handle을 직접 넘기기 어려워서 다시 선택)
        # bestScore 기준으로 동일 로직으로 재선택
        handle = page.evaluate_handle(
            """() => {
                const tables = Array.from(document.querySelectorAll('table'));
                const labels = ['출생','부모','배우자','자녀','형제자매','현직'];

                function labelScore(t){
                    const rows = Array.from(t.querySelectorAll('tr'));
                    let hits = 0;
                    for (const tr of rows){
                        const th = tr.querySelector('th');
                        if (th && labels.includes(th.innerText.trim())) hits += 1;
                        const tds = tr.querySelectorAll('td');
                        if (tds.length >= 2 && labels.includes((tds[0].innerText||'').trim())) hits += 1;
                    }
                    return hits;
                }

                function score(t){
                    const hasStrong = !!t.querySelector('div.IBdgNaCn strong');
                    const hasProfileImg = !!t.querySelector('img.xzxn3I3c');
                    const hit = labelScore(t);

                    let s = 0;
                    if (hasStrong) s += 8;
                    if (hasProfileImg) s += 4;
                    s += hit * 5;

                    const len = (t.innerText || '').length;
                    if (len > 12000) s -= 5;

                    return s;
                }

                let best = null;
                let bestScore = -1;
                for (const t of tables){
                    const sc = score(t);
                    if (sc > bestScore){
                        bestScore = sc;
                        best = t;
                    }
                }
                return best;
            }"""
        )

        # infobox 내부만 펼치기
        try:
            page.evaluate(
                """(box) => {
                    if (!box) return;
                    box.querySelectorAll('details').forEach(d => d.open = true);
                    const dts = Array.from(box.querySelectorAll('dl.VtrGmvDQ dt'));
                    for (const dt of dts){
                        try{ dt.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true})); }catch(e){}
                    }
                }""",
                handle,
            )
        except Exception:
            pass

        page.wait_for_timeout(250)
        infobox_html = page.evaluate("(box) => box ? box.outerHTML : ''", handle)
        page_html = page.content()
        browser.close()
        return infobox_html, bestScore, page_html


# -----------------------------
# Soup parsing
# -----------------------------
def find_value_cell_by_label(infobox: Tag, label: str) -> Optional[Tag]:
    for tr in infobox.select("tr"):
        th = tr.find("th")
        tds = tr.find_all("td")
        if th and clean(th.get_text(" ", strip=True)) == label and tds:
            return tds[0].select_one("div.IBdgNaCn") or tds[0]
        if len(tds) >= 2 and clean(tds[0].get_text(" ", strip=True)) == label:
            return tds[1].select_one("div.IBdgNaCn") or tds[1]
    return None


def pick_header_strong(infobox: Tag, target_name_ko: str) -> Optional[Tag]:
    cands = infobox.select("div.IBdgNaCn strong")
    if not cands:
        return None

    best = None
    best_score = -1
    for st in cands:
        txt = clean(st.get_text(" ", strip=True))
        if not txt:
            continue
        score = 0
        if target_name_ko and target_name_ko in txt:
            score += 10
        if "|" in txt:
            score += 3
        if re.search(r"[一-龥]", txt):
            score += 3
        if re.search(r"[A-Za-z]", txt):
            score += 2
        if len(txt) < 4:
            score -= 3
        if score > best_score:
            best_score = score
            best = st
    return best


def parse_1to4_from_strong(st: Tag, target_name_ko: str) -> Dict[str, str]:
    lines = [clean(x) for x in st.get_text("\n", strip=True).split("\n") if clean(x)]

    position = ""
    name_ko = ""
    name_hanja = ""
    name_en = ""

    name_idx = -1
    if target_name_ko:
        for i, ln in enumerate(lines):
            if ln == target_name_ko:
                name_idx = i
                name_ko = ln
                break

    if name_idx == -1:
        for i, ln in enumerate(lines):
            if re.fullmatch(r"[가-힣]{2,4}", ln):
                name_idx = i
                name_ko = ln
                break

    if name_idx > 0:
        position = clean(" ".join(lines[:name_idx]))
    elif lines:
        position = lines[0]

    tail = clean(" ".join(lines[name_idx + 1 :])) if name_idx != -1 else clean(" ".join(lines[1:]))

    if "|" in tail:
        left, right = [clean(x) for x in tail.split("|", 1)]
        if re.search(r"[一-龥]", left):
            name_hanja = left
        name_en = right
    else:
        m_h = re.search(r"[一-龥]{2,12}", tail)
        if m_h:
            name_hanja = m_h.group(0)
        m_e = re.search(r"\b[A-Za-z][A-Za-z .'\-]{2,}\b", tail)
        if m_e:
            cand = clean(m_e.group(0))
            if cand.count(" ") >= 1:
                name_en = cand

    return {"position": position, "name_ko": name_ko, "name_hanja": name_hanja, "name_en": name_en}


def pick_profile_image(infobox: Tag) -> str:
    # ✅ 프로필 이미지는 img.xzxn3I3c만 인정 + svg는 가급적 제외
    imgs = infobox.select("img.xzxn3I3c")
    best = ""
    best_score = -10
    for im in imgs:
        src = im.get("src") or im.get("data-src") or ""
        src = abs_url(src)
        if not src:
            continue
        s = 0
        sl = src.lower()
        if any(sl.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]):
            s += 5
        if sl.endswith(".svg"):
            s -= 4
        if "i.namu.wiki" in sl:
            s += 1
        if s > best_score:
            best_score = s
            best = src
    return best


def extract_birth_date(infobox: Tag) -> str:
    v = find_value_cell_by_label(infobox, "출생")
    if not v:
        return ""
    for a in v.select("a.zkdXfE03"):
        t = clean(a.get("title", "")) or clean(a.get_text(" ", strip=True))
        d = extract_date(t)
        if d:
            return d
    return extract_date(v.get_text(" ", strip=True))


def extract_parents(infobox: Tag) -> Dict[str, Dict[str, str]]:
    v = find_value_cell_by_label(infobox, "부모")
    out = {"father": {"name": "", "url": ""}, "mother": {"name": "", "url": ""}}
    if not v:
        return out

    current = None
    for node in v.children:
        if isinstance(node, NavigableString):
            t = clean(str(node))
            if not t:
                continue
            if "아버지" in t or t.strip() == "부":
                current = "father"
            if "어머니" in t or t.strip() == "모":
                current = "mother"
            continue

        if isinstance(node, Tag) and node.name == "a" and is_person_anchor(node):
            if current in ("father", "mother"):
                out[current] = anchor_obj(node)

    return out


def extract_siblings(infobox: Tag) -> Dict[str, List[Dict[str, str]]]:
    v = find_value_cell_by_label(infobox, "형제자매") or find_value_cell_by_label(infobox, "형제")
    out = {"형": [], "누나": [], "오빠": [], "언니": [], "동생": [], "미분류": []}
    if not v:
        return out

    current = "미분류"
    rel_map = {"형": "형", "누나": "누나", "오빠": "오빠", "언니": "언니", "남동생": "동생", "여동생": "동생", "동생": "동생"}

    for node in v.children:
        if isinstance(node, NavigableString):
            t = clean(str(node))
            for k, rel in rel_map.items():
                if k in t:
                    current = rel
                    break
            continue

        if isinstance(node, Tag) and node.name == "a" and is_person_anchor(node):
            obj = anchor_obj(node)
            if obj["name"]:
                out[current].append(obj)

    # dedupe
    for k in out:
        seen = set()
        uniq = []
        for p in out[k]:
            key = (p.get("name", ""), p.get("url", ""))
            if p.get("name") and key not in seen:
                seen.add(key)
                uniq.append(p)
        out[k] = uniq

    return out


def extract_spouse(infobox: Tag) -> List[Dict[str, str]]:
    v = find_value_cell_by_label(infobox, "배우자")
    if not v:
        return []
    out = []
    for a in v.select("a"):
        if is_person_anchor(a):
            obj = anchor_obj(a)
            if obj["name"]:
                out.append(obj)
    return out


def extract_children(infobox: Tag) -> List[Dict[str, str]]:
    v = find_value_cell_by_label(infobox, "자녀")
    if not v:
        return []
    out = []
    for a in v.select("a"):
        if is_person_anchor(a):
            obj = anchor_obj(a)
            if obj["name"]:
                out.append(obj)
    return out


def flatten_family(parents, siblings, spouse, children) -> Dict[str, str]:
    out = {}
    if parents.get("father", {}).get("name"):
        out["부"] = parents["father"]["name"]
    if parents.get("mother", {}).get("name"):
        out["모"] = parents["mother"]["name"]
    for rel in ["형", "누나", "오빠", "언니", "동생"]:
        for i, p in enumerate(siblings.get(rel, []), start=1):
            out[f"{rel}{i}"] = p["name"]
    for i, p in enumerate(spouse, start=1):
        out[f"배우자{i}"] = p["name"]
    for i, p in enumerate(children, start=1):
        out[f"자녀{i}"] = p["name"]
    return out


def is_valid_profile(target_name: str, header: Dict[str, str], birth_date: str,
                     parents: Dict, siblings: Dict, spouse: List, children: List) -> bool:
    """
    ✅ "페이지 열림"이 아니라 "인물 프로필로서 유효"한지 판단
    - strong에서 이름이 잡혀야 함
    - 그리고 출생/가족 중 최소 1개 이상 있어야 함 (이미지만 있는 오판 제외)
    """
    t = clean(target_name)
    n = clean(header.get("name_ko", ""))

    if not n:
        return False
    if t and (t not in n) and (n not in t):
        return False

    has_family = False
    if birth_date:
        has_family = True
    if parents.get("father", {}).get("name") or parents.get("mother", {}).get("name"):
        has_family = True
    if any(siblings.get(k) for k in siblings.keys()):
        has_family = True
    if spouse or children:
        has_family = True

    return has_family


def scrape(name_ko: str, headed: bool = False, debug: bool = False, dump: bool = False) -> Dict[str, object]:
    last_err = ""
    attempts = []

    for title in candidate_titles(name_ko):
        url = build_url(title)
        attempts.append(title)

        infobox_html, score, page_html = fetch_infobox_outer_html(url, headed=headed)

        if dump:
            safe_title = re.sub(r"[\\/:*?\"<>|]", "_", title)
            with open(f"debug_infobox_{safe_title}.html", "w", encoding="utf-8") as f:
                f.write(infobox_html or "")
            with open(f"debug_page_{safe_title}.html", "w", encoding="utf-8") as f:
                f.write(page_html or "")

        if not infobox_html:
            last_err = f"infobox not found/low score({score}) for {title}"
            continue

        soup = BeautifulSoup(infobox_html, "lxml")
        infobox = soup.select_one("table") or soup

        st = pick_header_strong(infobox, name_ko)
        if not st:
            last_err = f"no strong header for {title}"
            continue

        header = parse_1to4_from_strong(st, name_ko)
        birth_date = extract_birth_date(infobox)
        parents = extract_parents(infobox)
        siblings = extract_siblings(infobox)
        spouse = extract_spouse(infobox)
        children = extract_children(infobox)

        # ✅ 결과가 비면 '실패'로 보고 (기업인)으로 재시도
        if not is_valid_profile(name_ko, header, birth_date, parents, siblings, spouse, children):
            last_err = f"parsed but invalid/empty for {title}"
            continue

        profile_image = pick_profile_image(infobox)

        return {
            "source": "namu.wiki",
            "source_url": url,
            "resolved_title": title,
            "attempted_titles": attempts,
            "position": header.get("position", ""),
            "name_ko": header.get("name_ko", ""),
            "name_hanja": header.get("name_hanja", ""),
            "name_en": header.get("name_en", ""),
            "profile_image": profile_image,
            "birth_date": birth_date,
            "family": {
                "parents": parents,
                "siblings": siblings,
                "spouse": spouse,
                "children": children,
                "flatten": flatten_family(parents, siblings, spouse, children),
            },
        }

    return {
        "source": "namu.wiki",
        "source_url": build_url(name_ko),
        "resolved_title": "",
        "attempted_titles": attempts,
        "error": last_err or "all candidates failed",
    }
