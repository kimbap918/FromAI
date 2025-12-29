# make_profile_viewer.py
# 사용: python viewer.py profiles.csv output.html
# (output.html 생략 시: profile_viewer.html)

import json
import html as html_lib
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


def read_csv_robust(csv_path: str) -> pd.DataFrame:
    """인코딩 이슈를 최대한 피해서 CSV 로드"""
    encodings = ["utf-8-sig", "utf-8", "cp949", "euc-kr"]
    last_err = None
    for enc in encodings:
        try:
            return pd.read_csv(csv_path, encoding=enc)
        except Exception as e:
            last_err = e
    raise RuntimeError(f"CSV를 읽지 못했습니다. 파일/인코딩을 확인해주세요: {last_err}")


def generate_profile_viewer_html(df: pd.DataFrame, title: str) -> str:
    df = df.fillna("")

    # family summary 생성 (컬럼이 있어도/없어도 동작)
    def family_summary(row: dict) -> str:
        parts = []
        mapping = [
            ("father", "부"),
            ("mother", "모"),
            ("spouse", "배우자"),
            ("children", "자녀"),
            ("siblings", "형제자매"),
        ]
        for k, label in mapping:
            v = str(row.get(k, "")).strip()
            if v:
                parts.append(f"{label}:{v}")
        return " / ".join(parts)

    records = df.to_dict(orient="records")

    # _id, _family_summary, 링크/이미지 필드 준비
    for i, r in enumerate(records, start=1):
        r["_id"] = i
        r["_family_summary"] = family_summary(r)
        r["_source_url"] = str(r.get("source_url", "")).strip()
        r["_profile_image"] = str(r.get("profile_image", "")).strip()

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # HTML 템플릿 (이전과 동일 UI)
    html_out = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html_lib.escape(title)}</title>
  <style>
    :root {{
      --bg: #0b0f17;
      --panel: rgba(255,255,255,0.06);
      --panel-2: rgba(255,255,255,0.10);
      --text: rgba(255,255,255,0.92);
      --muted: rgba(255,255,255,0.65);
      --line: rgba(255,255,255,0.12);
      --chip: rgba(255,255,255,0.10);
      --accent: #7dd3fc;
      --danger: #fb7185;
      --radius: 14px;
      --shadow: 0 10px 30px rgba(0,0,0,0.35);
      --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      --sans: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple SD Gothic Neo", "Noto Sans KR", "Malgun Gothic", sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: var(--sans);
      background: radial-gradient(900px 600px at 30% 0%, rgba(125, 211, 252, 0.18), transparent 60%),
                  radial-gradient(900px 600px at 80% 20%, rgba(251, 113, 133, 0.12), transparent 55%),
                  var(--bg);
      color: var(--text);
    }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .container {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 22px 18px 40px;
    }}
    header {{
      display: flex;
      gap: 14px;
      align-items: flex-start;
      justify-content: space-between;
      flex-wrap: wrap;
      margin-bottom: 14px;
    }}
    .title {{
      display: flex;
      flex-direction: column;
      gap: 6px;
      min-width: 280px;
    }}
    h1 {{
      font-size: 20px;
      margin: 0;
      letter-spacing: -0.02em;
    }}
    .subtitle {{
      color: var(--muted);
      font-size: 13px;
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
    }}
    .chip {{
      display: inline-flex;
      gap: 8px;
      align-items: center;
      padding: 6px 10px;
      border-radius: 999px;
      background: var(--chip);
      border: 1px solid var(--line);
      color: var(--muted);
      font-size: 12px;
    }}
    .controls {{
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }}
    .search {{
      display: flex;
      gap: 10px;
      align-items: center;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 10px 12px;
      box-shadow: var(--shadow);
      min-width: min(520px, 100%);
    }}
    .search input {{
      width: 100%;
      border: 0;
      outline: none;
      background: transparent;
      color: var(--text);
      font-size: 14px;
    }}
    .search input::placeholder {{ color: rgba(255,255,255,0.45); }}
    .btn {{
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--text);
      border-radius: 12px;
      padding: 10px 12px;
      cursor: pointer;
      transition: transform .08s ease, background .12s ease;
      box-shadow: var(--shadow);
      font-size: 13px;
      display: inline-flex;
      gap: 8px;
      align-items: center;
      user-select: none;
    }}
    .btn:hover {{ background: var(--panel-2); }}
    .btn:active {{ transform: translateY(1px); }}
    .btn.secondary {{ box-shadow: none; background: transparent; }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      overflow: hidden;
      box-shadow: var(--shadow);
    }}
    .table-wrap {{ overflow: auto; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 980px;
    }}
    thead th {{
      position: sticky;
      top: 0;
      z-index: 5;
      background: rgba(11, 15, 23, 0.9);
      backdrop-filter: blur(10px);
      border-bottom: 1px solid var(--line);
      font-size: 12px;
      text-align: left;
      padding: 12px 10px;
      color: rgba(255,255,255,0.85);
      cursor: pointer;
      white-space: nowrap;
    }}
    thead th .sort {{
      opacity: 0.7;
      font-size: 11px;
      margin-left: 6px;
    }}
    tbody td {{
      border-bottom: 1px solid var(--line);
      padding: 12px 10px;
      vertical-align: middle;
      font-size: 13px;
      color: rgba(255,255,255,0.88);
    }}
    tbody tr:hover {{ background: rgba(255,255,255,0.04); }}
    .col-id {{
      width: 52px;
      color: rgba(255,255,255,0.65);
      font-family: var(--mono);
      font-size: 12px;
    }}
    .person {{
      display: flex;
      gap: 10px;
      align-items: center;
      min-width: 240px;
    }}
    .avatar {{
      width: 40px;
      height: 54px;
      border-radius: 10px;
      overflow: hidden;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.06);
      flex: 0 0 auto;
    }}
    .avatar img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }}
    .name {{
      display: flex;
      flex-direction: column;
      gap: 2px;
      line-height: 1.15;
    }}
    .name .ko {{
      font-weight: 700;
      letter-spacing: -0.01em;
    }}
    .name .meta {{
      color: var(--muted);
      font-size: 12px;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 5px 9px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.05);
      color: rgba(255,255,255,0.80);
      font-size: 12px;
      white-space: nowrap;
    }}
    .mono {{
      font-family: var(--mono);
      font-size: 12px;
      color: rgba(255,255,255,0.72);
      white-space: nowrap;
    }}
    .muted {{ color: var(--muted); font-size: 12px; }}
    .wrap {{
      max-width: 320px;
      white-space: normal;
      line-height: 1.3;
    }}
    .actions {{
      display: flex;
      gap: 8px;
      align-items: center;
      justify-content: flex-end;
      white-space: nowrap;
    }}
    .footer {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
      padding: 12px 12px;
      border-top: 1px solid var(--line);
      background: rgba(255,255,255,0.03);
    }}
    .pager {{
      display: inline-flex;
      gap: 8px;
      align-items: center;
    }}
    .pager .count {{
      color: var(--muted);
      font-size: 12px;
    }}
    .select {{
      padding: 8px 10px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.06);
      color: var(--text);
      outline: none;
    }}

    .cards {{
      display: none;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 12px;
      padding: 12px;
    }}
    .card {{
      border: 1px solid var(--line);
      border-radius: 16px;
      background: rgba(255,255,255,0.06);
      overflow: hidden;
      box-shadow: 0 10px 24px rgba(0,0,0,0.25);
    }}
    .card .top {{
      display: flex;
      gap: 12px;
      padding: 12px;
      align-items: center;
    }}
    .card .avatar {{
      width: 52px;
      height: 70px;
      border-radius: 12px;
    }}
    .card .body {{
      padding: 0 12px 12px;
      color: rgba(255,255,255,0.88);
      font-size: 13px;
      line-height: 1.35;
    }}
    .kv {{
      display: grid;
      grid-template-columns: 78px 1fr;
      gap: 6px 10px;
      margin-top: 10px;
      color: rgba(255,255,255,0.86);
    }}
    .kv .k {{
      color: rgba(255,255,255,0.62);
      font-size: 12px;
    }}
    .card .links {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 10px;
    }}

    dialog {{
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 0;
      background: rgba(18, 23, 34, 0.92);
      color: var(--text);
      width: min(880px, 96vw);
      box-shadow: 0 20px 60px rgba(0,0,0,0.55);
    }}
    dialog::backdrop {{
      background: rgba(0,0,0,0.55);
      backdrop-filter: blur(3px);
    }}
    .modal-header {{
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: center;
      background: rgba(255,255,255,0.03);
    }}
    .modal-title {{
      display: flex;
      gap: 12px;
      align-items: center;
    }}
    .modal-title .avatar {{
      width: 56px;
      height: 76px;
      border-radius: 14px;
    }}
    .modal-title .t {{
      display: flex;
      flex-direction: column;
      gap: 2px;
    }}
    .modal-title .t .ko {{ font-weight: 800; font-size: 16px; }}
    .modal-title .t .sub {{ color: var(--muted); font-size: 12px; }}
    .modal-body {{ padding: 16px; }}
    .grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 14px;
    }}
    .box {{
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.04);
      border-radius: 16px;
      padding: 12px;
    }}
    .box h3 {{
      margin: 0 0 10px 0;
      font-size: 13px;
      color: rgba(255,255,255,0.86);
      letter-spacing: -0.01em;
    }}
    .dl {{
      display: grid;
      grid-template-columns: 110px 1fr;
      gap: 8px 10px;
      font-size: 13px;
      line-height: 1.35;
    }}
    .dl .dt {{ color: var(--muted); }}
    .dl .dd {{
      color: rgba(255,255,255,0.90);
      word-break: break-word;
    }}
    .pre {{
      font-family: var(--mono);
      white-space: pre-wrap;
      font-size: 12px;
      color: rgba(255,255,255,0.82);
    }}
    @media (max-width: 880px) {{
      .search {{ min-width: 100%; }}
      table {{ min-width: 860px; }}
      .grid {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 640px) {{
      .table-wrap {{ display: none; }}
      .cards {{ display: grid; }}
      .btn.toggle-table {{ display: none; }}
      .btn.toggle-cards {{ display: none; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="title">
        <h1>{html_lib.escape(title)}</h1>
        <div class="subtitle">
          <span class="chip">행 수 <b id="statTotal">-</b></span>
          <span class="chip">표시 <b id="statShown">-</b></span>
          <span class="chip">생성 <span class="mono">{html_lib.escape(generated_at)}</span></span>
          <span class="chip">검색: 모든 컬럼 통합</span>
        </div>
      </div>

      <div class="controls">
        <div class="search">
          <span class="muted">🔎</span>
          <input id="q" placeholder="예: 이재용, 삼성전자, 1968, 홍라희, SK…" autocomplete="off" />
          <button class="btn secondary" id="clearBtn" title="검색어 지우기">지우기</button>
        </div>
        <button class="btn toggle-table" id="viewTableBtn" title="테이블 보기">📋 테이블</button>
        <button class="btn toggle-cards" id="viewCardsBtn" title="카드 보기">🪪 카드</button>
      </div>
    </header>

    <section class="panel">
      <div class="table-wrap" id="tableWrap">
        <table id="tbl">
          <thead>
            <tr>
              <th data-key="_id"># <span class="sort" id="sort-_id"></span></th>
              <th data-key="기업집단">기업집단 <span class="sort" id="sort-기업집단"></span></th>
              <th data-key="name_ko">인물 <span class="sort" id="sort-name_ko"></span></th>
              <th data-key="position">직함 <span class="sort" id="sort-position"></span></th>
              <th data-key="birth_date">출생 <span class="sort" id="sort-birth_date"></span></th>
              <th data-key="대표회사">대표회사 <span class="sort" id="sort-대표회사"></span></th>
              <th data-key="계열사수">계열사수 <span class="sort" id="sort-계열사수"></span></th>
              <th data-key="_family_summary">가족요약 <span class="sort" id="sort-_family_summary"></span></th>
              <th data-key="source_url">출처 <span class="sort" id="sort-source_url"></span></th>
              <th data-key="actions"> </th>
            </tr>
          </thead>
          <tbody id="tbody"></tbody>
        </table>
      </div>

      <div class="cards" id="cards"></div>

      <div class="footer">
        <div class="pager">
          <button class="btn" id="prevBtn">← 이전</button>
          <button class="btn" id="nextBtn">다음 →</button>
          <span class="count" id="pageInfo">-</span>
        </div>
        <div class="pager">
          <span class="count">페이지당</span>
          <select class="select" id="pageSize">
            <option value="10">10</option>
            <option value="15" selected>15</option>
            <option value="25">25</option>
            <option value="999999">전체</option>
          </select>
        </div>
      </div>
    </section>
  </div>

  <dialog id="dlg">
    <div class="modal-header">
      <div class="modal-title">
        <div class="avatar"><img id="dlgImg" alt="" /></div>
        <div class="t">
          <div class="ko" id="dlgName">-</div>
          <div class="sub" id="dlgSub">-</div>
        </div>
      </div>
      <div class="actions">
        <a class="btn" id="dlgSource" target="_blank" rel="noopener">출처 열기</a>
        <button class="btn" id="dlgClose">닫기</button>
      </div>
    </div>
    <div class="modal-body">
      <div class="grid">
        <div class="box">
          <h3>기본 정보</h3>
          <div class="dl" id="dlgBasic"></div>
        </div>
        <div class="box">
          <h3>가족 정보</h3>
          <div class="dl" id="dlgFamily"></div>
        </div>
      </div>

      <div class="box" style="margin-top:14px;">
        <h3>원본 데이터 (JSON)</h3>
        <div class="pre" id="dlgJson"></div>
      </div>
    </div>
  </dialog>

  <script>
    const DATA = {json.dumps(records, ensure_ascii=False)};

    let state = {{
      q: "",
      sortKey: "_id",
      sortDir: "asc",
      page: 1,
      pageSize: 15,
      view: "table"
    }};

    const $ = (id) => document.getElementById(id);

    function normalize(v) {{
      return String(v ?? "").trim().toLowerCase();
    }}

    function buildIndex(row) {{
      const keys = Object.keys(row);
      let out = [];
      for (const k of keys) {{
        if (k === "family_flatten_json") continue;
        out.push(String(row[k] ?? ""));
      }}
      return out.join(" | ").toLowerCase();
    }}

    const INDEX = DATA.map(r => ({{ id: r._id, text: buildIndex(r) }}));

    function applyFilter() {{
      const q = normalize(state.q);
      if (!q) return DATA.slice();
      return DATA.filter((row, idx) => INDEX[idx].text.includes(q));
    }}

    function compare(a, b, key) {{
      const va = a[key] ?? "";
      const vb = b[key] ?? "";
      const na = Number(va);
      const nb = Number(vb);
      const aIsNum = String(va).trim() !== "" && !Number.isNaN(na);
      const bIsNum = String(vb).trim() !== "" && !Number.isNaN(nb);

      if (aIsNum && bIsNum) return na - nb;
      return String(va).localeCompare(String(vb), "ko");
    }}

    function applySort(rows) {{
      const key = state.sortKey;
      const dir = state.sortDir;
      const sorted = rows.slice().sort((a, b) => compare(a, b, key));
      if (dir === "desc") sorted.reverse();
      return sorted;
    }}

    function applyPage(rows) {{
      const total = rows.length;
      const size = state.pageSize;
      const totalPages = Math.max(1, Math.ceil(total / size));
      state.page = Math.min(state.page, totalPages);

      const start = (state.page - 1) * size;
      const end = start + size;
      return {{
        pageRows: rows.slice(start, end),
        total,
        totalPages
      }};
    }}

    function setSortIndicators() {{
      document.querySelectorAll("thead th[data-key]").forEach(th => {{
        const k = th.getAttribute("data-key");
        const el = document.getElementById("sort-" + k);
        if (!el) return;
        el.textContent = (k === state.sortKey) ? (state.sortDir === "asc" ? "▲" : "▼") : "";
      }});
    }}

    function escapeHtml(s) {{
      return String(s ?? "").replace(/[&<>"']/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}}[c]));
    }}

    function pick(r, key, fallback="") {{
      return (r && r[key] !== undefined && String(r[key]).trim() !== "") ? r[key] : fallback;
    }}

    function renderTable(rows) {{
      const tb = $("tbody");
      tb.innerHTML = rows.map(r => {{
        const img = pick(r, "_profile_image", "");
        const source = pick(r, "_source_url", "");
        const name = pick(r, "name_ko", pick(r, "총수(동일인)", "-"));
        const meta = [
          pick(r, "name_en", ""),
          pick(r, "name_hanja", "")
        ].filter(Boolean).join(" · ");

        const sourceLink = source ? `<a href="${{escapeHtml(source)}}" target="_blank" rel="noopener">링크</a>` : `<span class="muted">-</span>`;
        const family = r._family_summary ? `<span class="wrap">${{escapeHtml(r._family_summary)}}</span>` : `<span class="muted">-</span>`;

        return `
          <tr>
            <td class="col-id">${{r._id}}</td>
            <td><span class="badge">${{escapeHtml(pick(r, "기업집단", "-"))}}</span></td>
            <td>
              <div class="person">
                <div class="avatar"><img src="${{escapeHtml(img)}}" alt=""/></div>
                <div class="name">
                  <div class="ko">${{escapeHtml(name)}}</div>
                  <div class="meta">${{escapeHtml(meta)}}</div>
                </div>
              </div>
            </td>
            <td class="wrap">${{escapeHtml(pick(r, "position", "-"))}}</td>
            <td class="mono">${{escapeHtml(pick(r, "birth_date", "-"))}}</td>
            <td class="wrap">${{escapeHtml(pick(r, "대표회사", "-"))}}</td>
            <td class="mono">${{escapeHtml(pick(r, "계열사수", "-"))}}</td>
            <td>${{family}}</td>
            <td>${{sourceLink}}</td>
            <td>
              <div class="actions">
                <button class="btn" onclick="openDetail(${{r._id}})">상세</button>
              </div>
            </td>
          </tr>
        `;
      }}).join("");
    }}

    function renderCards(rows) {{
      const wrap = $("cards");
      wrap.innerHTML = rows.map(r => {{
        const img = pick(r, "_profile_image", "");
        const source = pick(r, "_source_url", "");
        const name = pick(r, "name_ko", pick(r, "총수(동일인)", "-"));
        return `
          <div class="card">
            <div class="top">
              <div class="avatar"><img src="${{escapeHtml(img)}}" alt=""/></div>
              <div class="name">
                <div class="ko">${{escapeHtml(name)}}</div>
                <div class="meta">${{escapeHtml(pick(r, "position", "-"))}}</div>
              </div>
            </div>
            <div class="body">
              <div class="badge">${{escapeHtml(pick(r, "기업집단", "-"))}}</div>
              <div class="kv">
                <div class="k">출생</div><div>${{escapeHtml(pick(r, "birth_date", "-"))}}</div>
                <div class="k">대표회사</div><div>${{escapeHtml(pick(r, "대표회사", "-"))}}</div>
                <div class="k">계열사수</div><div>${{escapeHtml(pick(r, "계열사수", "-"))}}</div>
                <div class="k">가족</div><div>${{escapeHtml(pick(r, "_family_summary", "-"))}}</div>
              </div>
              <div class="links">
                ${{
                  source ? `<a class="btn secondary" href="${{escapeHtml(source)}}" target="_blank" rel="noopener">출처</a>` : `<span class="muted">출처 없음</span>`
                }}
                <button class="btn secondary" onclick="openDetail(${{r._id}})">상세</button>
              </div>
            </div>
          </div>
        `;
      }}).join("");
    }}

    function updateStats(total, shown) {{
      $("statTotal").textContent = total;
      $("statShown").textContent = shown;
    }}

    function render() {{
      const filtered = applyFilter();
      const sorted = applySort(filtered);
      const {{ pageRows, total, totalPages }} = applyPage(sorted);

      updateStats(DATA.length, total);
      setSortIndicators();

      if (state.view === "cards") {{
        $("tableWrap").style.display = "none";
        $("cards").style.display = "grid";
        renderCards(pageRows);
      }} else {{
        $("tableWrap").style.display = "block";
        $("cards").style.display = "none";
        renderTable(pageRows);
      }}

      $("pageInfo").textContent = `페이지 ${{state.page}} / ${{totalPages}} · 결과 ${{total}}건`;
      $("prevBtn").disabled = state.page <= 1;
      $("nextBtn").disabled = state.page >= totalPages;
    }}

    function setView(view) {{
      state.view = view;
      render();
    }}

    $("q").addEventListener("input", (e) => {{
      state.q = e.target.value;
      state.page = 1;
      render();
    }});

    $("clearBtn").addEventListener("click", () => {{
      state.q = "";
      $("q").value = "";
      state.page = 1;
      render();
    }});

    $("prevBtn").addEventListener("click", () => {{
      state.page = Math.max(1, state.page - 1);
      render();
    }});
    $("nextBtn").addEventListener("click", () => {{
      state.page = state.page + 1;
      render();
    }});

    $("pageSize").addEventListener("change", (e) => {{
      const v = Number(e.target.value);
      state.pageSize = (v >= 999999) ? 999999999 : v;
      state.page = 1;
      render();
    }});

    $("viewTableBtn").addEventListener("click", () => setView("table"));
    $("viewCardsBtn").addEventListener("click", () => setView("cards"));

    document.querySelectorAll("thead th[data-key]").forEach(th => {{
      th.addEventListener("click", () => {{
        const key = th.getAttribute("data-key");
        if (!key || key === "actions") return;

        if (state.sortKey === key) {{
          state.sortDir = (state.sortDir === "asc") ? "desc" : "asc";
        }} else {{
          state.sortKey = key;
          state.sortDir = "asc";
        }}
        state.page = 1;
        render();
      }});
    }});

    function asDlRow(k, v) {{
      return `<div class="dt">${{escapeHtml(k)}}</div><div class="dd">${{escapeHtml(v || "-")}}</div>`;
    }}

    window.openDetail = function(id) {{
      const r = DATA.find(x => x._id === id);
      if (!r) return;

      $("dlgImg").src = pick(r, "_profile_image", "");
      $("dlgName").textContent = pick(r, "name_ko", pick(r, "총수(동일인)", "-"));
      $("dlgSub").textContent = `${{pick(r, "기업집단", "-")}} · ${{pick(r, "position", "-")}}`;

      const basic = [];
      basic.push(asDlRow("기업집단코드", pick(r, "기업집단코드", "-")));
      basic.push(asDlRow("대표회사", pick(r, "대표회사", "-")));
      basic.push(asDlRow("계열사수", pick(r, "계열사수", "-")));
      basic.push(asDlRow("영문명", pick(r, "name_en", "-")));
      basic.push(asDlRow("한자명", pick(r, "name_hanja", "-")));
      basic.push(asDlRow("출생", pick(r, "birth_date", "-")));
      basic.push(asDlRow("resolved_title", pick(r, "resolved_title", "-")));
      basic.push(asDlRow("총수(동일인)", pick(r, "총수(동일인)", "-")));
      $("dlgBasic").innerHTML = basic.join("");

      const fam = [];
      fam.push(asDlRow("부", pick(r, "father", "-")));
      fam.push(asDlRow("모", pick(r, "mother", "-")));
      fam.push(asDlRow("배우자", pick(r, "spouse", "-")));
      fam.push(asDlRow("자녀", pick(r, "children", "-")));
      fam.push(asDlRow("형제자매", pick(r, "siblings", "-")));
      $("dlgFamily").innerHTML = fam.join("");

      const source = pick(r, "_source_url", "");
      if (source) {{
        $("dlgSource").href = source;
        $("dlgSource").style.display = "inline-flex";
      }} else {{
        $("dlgSource").style.display = "none";
      }}

      $("dlgJson").textContent = JSON.stringify(Object.assign({{}}, r), null, 2);
      $("dlg").showModal();
    }}

    $("dlgClose").addEventListener("click", () => $("dlg").close());
    $("dlg").addEventListener("click", (e) => {{
      const rect = $("dlg").getBoundingClientRect();
      const inDialog = (
        rect.top <= e.clientY && e.clientY <= rect.bottom &&
        rect.left <= e.clientX && e.clientX <= rect.right
      );
      if (!inDialog) $("dlg").close();
    }});

    render();
  </script>
</body>
</html>
"""
    return html_out


def main():
    if len(sys.argv) < 2:
        print("사용법: python make_profile_viewer.py <input_profile.csv> [output.html]")
        sys.exit(1)

    input_csv = sys.argv[1]
    output_html = sys.argv[2] if len(sys.argv) >= 3 else "profile_viewer.html"

    df = read_csv_robust(input_csv)
    title = f"{Path(input_csv).stem} - HTML 뷰어"

    html_text = generate_profile_viewer_html(df, title=title)
    Path(output_html).write_text(html_text, encoding="utf-8")

    print(f"완료: {output_html}")


if __name__ == "__main__":
    main()
