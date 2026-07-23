#!/usr/bin/env python3
"""Render an interactive HTML viewer for layout candidates."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from house_design.rendering import encode_html_json  # noqa: E402

PROGRAM_FILE = ROOT / "structured" / "room_program.json"
CANDIDATES_FILE = ROOT / "structured" / "candidates" / "layout_candidates.json"
OUTPUT_HTML = ROOT / "structured" / "candidates" / "viewer.html"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize(value: str) -> str:
    return " ".join((value or "").split())


def build_program_index(program: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for building in program.get("buildings", []):
        b_id = building.get("id", "")
        for floor in building.get("floors", []):
            f_id = floor.get("id", "")
            room_name_by_uid = {r.get("uid", ""): normalize(r.get("name", "")) for r in floor.get("rooms", [])}
            slots = []
            for cell in floor.get("plan_cells", []):
                order = int(cell.get("order", 0))
                slots.append(
                    {
                        "slot_id": f"slot-{order}",
                        "order": order,
                        "name": normalize(cell.get("name", "")),
                        "size_text": normalize(cell.get("size_text", "")),
                        "badges": cell.get("badges", []),
                        "classes": cell.get("classes", []),
                    }
                )
            slots.sort(key=lambda x: x["order"])
            index[(b_id, f_id)] = {
                "building_id": b_id,
                "floor_id": f_id,
                "title": normalize(floor.get("title", "")),
                "subtitle": normalize(floor.get("subtitle", "")),
                "tab_label": normalize(floor.get("tab_label", "")),
                "direction_badges": floor.get("direction_badges", []),
                "slots": slots,
                "room_name_by_uid": room_name_by_uid,
            }
    return index


def build_view_payload(program: dict[str, Any], candidates: dict[str, Any]) -> dict[str, Any]:
    program_index = build_program_index(program)
    floor_views = []

    for floor_result in candidates.get("floors", []):
        b_id = floor_result.get("building_id", "")
        f_id = floor_result.get("floor_id", "")
        meta = program_index.get((b_id, f_id), {})
        slots = meta.get("slots", [])
        room_name_by_uid = meta.get("room_name_by_uid", {})

        prepared_candidates = []
        for rank, candidate in enumerate(floor_result.get("candidates", []), start=1):
            pair_map = {}
            for pair in candidate.get("pair_details", []):
                slot_id = pair.get("slot_id", "")
                fit = pair.get("dimension_fit", {})
                fit_total = (fit.get("circulation", 0) + fit.get("daylight", 0) + fit.get("mep", 0)) / 3.0
                pair_map[slot_id] = {
                    "room_uid": pair.get("room_uid", ""),
                    "room_name": normalize(pair.get("room_name", "")),
                    "dimension_fit": fit,
                    "fit_total": round(fit_total, 3),
                }

            unplaced_uids = candidate.get("unplaced_room_uids", [])
            unplaced_names = [room_name_by_uid.get(uid, uid) for uid in unplaced_uids]
            prepared_candidates.append(
                {
                    "rank": rank,
                    "id": candidate.get("id", ""),
                    "strategy": candidate.get("strategy", ""),
                    "scores": candidate.get("scores", {}),
                    "rationale": candidate.get("rationale", []),
                    "pair_map": pair_map,
                    "unplaced_room_uids": unplaced_uids,
                    "unplaced_room_names": unplaced_names,
                    "unassigned_slots": candidate.get("unassigned_slots", []),
                    "weights": candidate.get("weights", {}),
                }
            )

        floor_views.append(
            {
                "building_id": b_id,
                "floor_id": f_id,
                "title": normalize(meta.get("title", floor_result.get("floor_title", ""))),
                "subtitle": normalize(meta.get("subtitle", "")),
                "tab_label": normalize(meta.get("tab_label", floor_result.get("tab_label", ""))),
                "direction_badges": meta.get("direction_badges", []),
                "room_count": floor_result.get("room_count", 0),
                "slot_count": floor_result.get("slot_count", 0),
                "best_candidate_id": floor_result.get("best_candidate_id", ""),
                "best_total_score": floor_result.get("best_total_score", 0),
                "slots": slots,
                "candidates": prepared_candidates,
            }
        )

    floor_views.sort(key=lambda x: (x["building_id"], x["floor_id"]))

    return {
        "generated_at": now_iso(),
        "source": {
            "program": PROGRAM_FILE.name,
            "candidates": CANDIDATES_FILE.name,
        },
        "summary": {
            "floor_count": len(floor_views),
            "building_ids": sorted({f["building_id"] for f in floor_views}),
        },
        "floors": floor_views,
    }


def render_html(payload: dict[str, Any]) -> str:
    data_json = encode_html_json(payload)
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>住宅配置候選檢視器</title>
  <style>
    :root {{
      --bg0: #0b1020;
      --bg1: #0f1b2e;
      --card: #121d33;
      --line: #2a3b5a;
      --text: #e8edf7;
      --muted: #9fb0cd;
      --accent1: #f2b705;
      --accent2: #19c3c5;
      --good: #36d399;
      --warn: #f8b84e;
      --bad: #ef7272;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Microsoft JhengHei", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at 12% 18%, rgba(25, 195, 197, 0.13), transparent 35%),
        radial-gradient(circle at 84% 24%, rgba(242, 183, 5, 0.16), transparent 40%),
        linear-gradient(145deg, var(--bg0), var(--bg1));
      min-height: 100vh;
    }}
    .app {{
      display: grid;
      grid-template-columns: 320px minmax(0, 1fr);
      min-height: 100vh;
      min-width: 0;
    }}
    .sidebar {{
      border-right: 1px solid var(--line);
      padding: 16px;
      background: rgba(11, 16, 32, 0.76);
      backdrop-filter: blur(10px);
    }}
    .brand {{
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 12px;
      margin-bottom: 14px;
      background: rgba(18, 29, 51, 0.55);
    }}
    .brand h1 {{
      margin: 0;
      font-size: 1rem;
      letter-spacing: .6px;
      color: var(--accent1);
    }}
    .brand p {{
      margin: 4px 0 0;
      font-size: .78rem;
      color: var(--muted);
    }}
    .floor-list {{
      display: flex;
      flex-direction: column;
      gap: 8px;
      max-height: calc(100vh - 140px);
      overflow: auto;
      padding-right: 4px;
    }}
    .floor-item {{
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 10px 11px;
      cursor: pointer;
      background: rgba(18, 29, 51, 0.50);
      transition: .18s ease;
    }}
    .floor-item:hover {{
      transform: translateY(-1px);
      border-color: #3f5d8d;
    }}
    .floor-item.active {{
      border-color: var(--accent2);
      box-shadow: 0 0 0 1px rgba(25, 195, 197, 0.32) inset;
      background: linear-gradient(140deg, rgba(25, 195, 197, 0.14), rgba(18, 29, 51, 0.62));
    }}
    .floor-head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
    }}
    .floor-name {{
      font-size: .86rem;
      font-weight: 700;
      line-height: 1.2;
    }}
    .score-pill {{
      font-size: .74rem;
      font-weight: 700;
      padding: 3px 7px;
      border-radius: 99px;
      background: rgba(255,255,255,0.08);
      color: #c7d6ef;
      white-space: nowrap;
    }}
    .floor-meta {{
      margin-top: 6px;
      color: var(--muted);
      font-size: .74rem;
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }}

    .content {{
      padding: 16px;
      display: grid;
      grid-template-rows: auto auto minmax(0, 1fr);
      gap: 12px;
      min-width: 0;
    }}
    .panel {{
      border: 1px solid var(--line);
      border-radius: 14px;
      background: rgba(18, 29, 51, 0.58);
      backdrop-filter: blur(8px);
    }}
    .panel.pad {{ padding: 12px 14px; }}
    .title {{
      margin: 0;
      font-size: 1.16rem;
      font-weight: 800;
      color: #f7f9fe;
    }}
    .sub {{
      margin-top: 4px;
      color: var(--muted);
      font-size: .82rem;
    }}
    .badge-row {{
      margin-top: 8px;
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }}
    .badge {{
      font-size: .72rem;
      color: #cee5ff;
      border: 1px solid #3a5279;
      border-radius: 999px;
      padding: 3px 8px;
      background: rgba(20, 34, 59, 0.7);
    }}
    .candidate-tabs {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      padding: 10px;
    }}
    .cand-btn {{
      border: 1px solid #38557f;
      border-radius: 10px;
      padding: 8px 10px;
      min-width: 125px;
      background: rgba(20, 34, 59, 0.65);
      cursor: pointer;
      color: #d9e6f7;
      text-align: left;
      transition: .15s ease;
      font-size: .79rem;
    }}
    .cand-btn:hover {{ transform: translateY(-1px); }}
    .cand-btn.active {{
      border-color: var(--accent1);
      box-shadow: 0 0 0 1px rgba(242,183,5,.32) inset;
      background: linear-gradient(145deg, rgba(242,183,5,.18), rgba(20, 34, 59, .65));
      color: #fff6dd;
    }}
    .cand-btn .id {{ font-weight: 800; display: block; }}
    .cand-btn .v {{ color: #9dc3e0; display: block; margin-top: 2px; }}

    .stage {{
      display: grid;
      grid-template-columns: minmax(0, 2.2fr) minmax(300px, 1fr);
      gap: 12px;
      min-height: 0;
      min-width: 0;
    }}
    .grid-panel {{
      padding: 10px;
      overflow: auto;
    }}
    .slot-grid {{
      display: grid;
      gap: 8px;
      grid-template-columns: repeat(var(--slot-columns, 4), minmax(0, 1fr));
    }}
    .slot-card {{
      border: 1px solid #3d567c;
      border-radius: 12px;
      padding: 8px;
      background: rgba(16, 28, 50, 0.7);
      min-height: 105px;
      display: grid;
      grid-template-rows: auto auto minmax(0, 1fr) auto;
      gap: 4px;
      min-width: 0;
    }}
    .slot-top {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: .73rem;
      color: #a8bddb;
    }}
    .slot-name {{
      font-size: .86rem;
      font-weight: 700;
      color: #dbe8f7;
      line-height: 1.15;
    }}
    .assign {{
      font-size: .8rem;
      font-weight: 700;
      color: #fff;
      line-height: 1.2;
      border-radius: 8px;
      padding: 4px 6px;
      background: rgba(255,255,255,0.05);
    }}
    .assign.none {{
      color: #8fa5c5;
      font-weight: 600;
    }}
    .slot-badges {{
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
    }}
    .slot-badges span {{
      font-size: .66rem;
      border: 1px solid #3a5279;
      color: #abc6e8;
      border-radius: 999px;
      padding: 2px 6px;
      background: rgba(18, 33, 58, 0.75);
    }}
    .fit-chip {{
      justify-self: end;
      font-size: .68rem;
      border-radius: 999px;
      padding: 2px 8px;
      border: 1px solid #3f5d8d;
      color: #d4e7ff;
    }}
    .fit-good {{ border-color: rgba(54,211,153,.7); color: #a7f3d0; }}
    .fit-mid {{ border-color: rgba(248,184,78,.7); color: #fde0b3; }}
    .fit-bad {{ border-color: rgba(239,114,114,.7); color: #fecaca; }}

    .score-panel {{
      padding: 12px;
      overflow: auto;
      display: grid;
      gap: 10px;
      align-content: start;
    }}
    .score-title {{
      font-size: .86rem;
      color: #dce7f7;
      font-weight: 700;
    }}
    .bar {{
      display: grid;
      grid-template-columns: 92px 1fr 44px;
      gap: 8px;
      align-items: center;
      font-size: .75rem;
      color: #b4c7e1;
    }}
    .bar-track {{
      height: 8px;
      border-radius: 999px;
      border: 1px solid #38557f;
      background: rgba(8, 13, 23, 0.6);
      overflow: hidden;
    }}
    .bar-fill {{
      height: 100%;
      background: linear-gradient(90deg, var(--accent2), var(--accent1));
    }}
    .small-list {{
      margin: 0;
      padding-left: 18px;
      color: #b9cae2;
      font-size: .77rem;
      line-height: 1.5;
    }}
    .muted {{
      color: #90a6c6;
      font-size: .75rem;
    }}
    @media (max-width: 1080px) {{
      .app {{ grid-template-columns: 1fr; }}
      .sidebar {{ border-right: 0; border-bottom: 1px solid var(--line); }}
      .floor-list {{ max-height: 260px; }}
      .stage {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 640px) {{
      body {{ overflow-x: hidden; }}
      .app {{ display: block; }}
      .sidebar {{ padding: 8px; }}
      .floor-list {{ max-height: 220px; }}
      .content {{ padding: 8px; }}
      .title {{ font-size: 1rem; overflow-wrap: anywhere; }}
      .sub {{ overflow-wrap: anywhere; }}
      .candidate-tabs {{ padding: 8px; }}
      .cand-btn {{ flex: 1 1 calc(50% - 8px); min-width: 0; }}
      .stage {{ display: block; }}
      .grid-panel, .score-panel {{ margin-top: 8px; }}
      .slot-grid {{ grid-template-columns: 1fr !important; }}
      .bar {{ grid-template-columns: 72px minmax(0, 1fr) 40px; }}
    }}
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="brand">
        <h1>住宅配置候選檢視器</h1>
        <p>Top1/Top3 候選切換 · 動線/採光/機電維修評分</p>
      </div>
      <div class="floor-list" id="floorList"></div>
    </aside>

    <main class="content">
      <section class="panel pad">
        <h2 class="title" id="title"></h2>
        <div class="sub" id="subtitle"></div>
        <div class="badge-row" id="badgeRow"></div>
      </section>

      <section class="panel">
        <div class="candidate-tabs" id="candidateTabs"></div>
      </section>

      <section class="stage">
        <section class="panel grid-panel">
          <div id="slotGrid" class="slot-grid"></div>
        </section>
        <section class="panel score-panel" id="scorePanel"></section>
      </section>
    </main>
  </div>

  <script>
    const DATA = {data_json};
    let floorIndex = 0;
    let candidateIndex = 0;

    function escapeHtml(str) {{
      return (str ?? '').toString()
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
    }}

    function floorDisplayName(f) {{
      const prefix = `[${{f.building_id}}]`;
      const core = `${{f.floor_id}} ${{f.title || ''}}`.trim();
      return `${{prefix}} ${{core}}`;
    }}

    function scoreClass(v) {{
      if (v >= 0.35) return 'fit-good';
      if (v >= 0.05) return 'fit-mid';
      return 'fit-bad';
    }}

    function columnsForSlots(n) {{
      if (n <= 6) return 3;
      if (n <= 10) return 4;
      if (n <= 14) return 5;
      return 6;
    }}

    function renderFloorList() {{
      const el = document.getElementById('floorList');
      el.innerHTML = DATA.floors.map((f, i) => `
        <div class="floor-item ${{i===floorIndex?'active':''}}" onclick="selectFloor(${{i}})">
          <div class="floor-head">
            <div class="floor-name">${{escapeHtml(floorDisplayName(f))}}</div>
            <div class="score-pill">Best ${{Number(f.best_total_score).toFixed(1)}}</div>
          </div>
          <div class="floor-meta">
            <span>${{escapeHtml(f.tab_label || 'No Tab Label')}}</span>
            <span>R${{f.room_count}} / S${{f.slot_count}}</span>
          </div>
        </div>
      `).join('');
    }}

    function renderHeader(floor) {{
      document.getElementById('title').textContent = floorDisplayName(floor);
      document.getElementById('subtitle').textContent = floor.subtitle || '無補充副標題';
      const badgeRow = document.getElementById('badgeRow');
      badgeRow.innerHTML = (floor.direction_badges || []).map(b => `<span class="badge">${{escapeHtml(b)}}</span>`).join('');
    }}

    function renderCandidateTabs(floor) {{
      const tabs = document.getElementById('candidateTabs');
      tabs.innerHTML = floor.candidates.map((c, i) => `
        <button class="cand-btn ${{i===candidateIndex?'active':''}}" onclick="selectCandidate(${{i}})">
          <span class="id">#${{c.rank}} · ${{escapeHtml(c.id)}}</span>
          <span class="v">Total: ${{Number(c.scores.total).toFixed(1)}}</span>
        </button>
      `).join('');
    }}

    function renderGrid(floor, candidate) {{
      const slotGrid = document.getElementById('slotGrid');
      const cols = columnsForSlots(floor.slots.length);
      slotGrid.style.setProperty('--slot-columns', cols);

      slotGrid.innerHTML = floor.slots.map(slot => {{
        const p = candidate.pair_map[slot.slot_id];
        const room = p ? p.room_name : '';
        const fitTotal = p ? Number(p.fit_total) : -0.5;
        const fitClass = scoreClass(fitTotal);
        const fitTxt = p ? `fit ${{(fitTotal*100).toFixed(0)}}%` : 'unassigned';
        const badges = (slot.badges || []).slice(0, 4).map(b => `<span>${{escapeHtml(b)}}</span>`).join('');
        return `
          <article class="slot-card">
            <div class="slot-top">
              <span>${{escapeHtml(slot.slot_id)}} · #${{slot.order}}</span>
              <span class="muted">${{escapeHtml(slot.size_text || '')}}</span>
            </div>
            <div class="slot-name">${{escapeHtml(slot.name || '(unnamed slot)')}}</div>
            <div class="assign ${{p ? '' : 'none'}}">${{escapeHtml(room || '— 未指派房間 —')}}</div>
            <div class="slot-badges">${{badges}}</div>
            <span class="fit-chip ${{fitClass}}">${{fitTxt}}</span>
          </article>
        `;
      }}).join('');
    }}

    function bar(label, value) {{
      const v = Number(value || 0);
      return `
        <div class="bar">
          <span>${{escapeHtml(label)}}</span>
          <div class="bar-track"><div class="bar-fill" style="width:${{Math.max(0, Math.min(100, v))}}%"></div></div>
          <span>${{v.toFixed(1)}}</span>
        </div>
      `;
    }}

    function renderScorePanel(candidate) {{
      const el = document.getElementById('scorePanel');
      const s = candidate.scores || {{}};
      const rationale = (candidate.rationale || []).map(x => `<li>${{escapeHtml(x)}}</li>`).join('');
      const unplaced = (candidate.unplaced_room_names || []).map(x => `<li>${{escapeHtml(x)}}</li>`).join('');
      const unassigned = (candidate.unassigned_slots || []).map(x => `<li>${{escapeHtml(x)}}</li>`).join('');

      el.innerHTML = `
        <div>
          <div class="score-title">候選策略：${{escapeHtml(candidate.id)}}</div>
          <div class="muted">權重 C/D/M = ${{candidate.weights?.circulation ?? 0}} / ${{candidate.weights?.daylight ?? 0}} / ${{candidate.weights?.mep ?? 0}}</div>
        </div>
        ${{bar('Total', s.total)}}
        ${{bar('Circulation', s.circulation)}}
        ${{bar('Daylight', s.daylight)}}
        ${{bar('MEP', s.mep)}}
        ${{bar('Utilization', s.utilization)}}
        <div>
          <div class="score-title">策略說明</div>
          <ul class="small-list">${{rationale || '<li>—</li>'}}</ul>
        </div>
        <div>
          <div class="score-title">未放入房間</div>
          <ul class="small-list">${{unplaced || '<li>無</li>'}}</ul>
        </div>
        <div>
          <div class="score-title">未使用格位</div>
          <ul class="small-list">${{unassigned || '<li>無</li>'}}</ul>
        </div>
      `;
    }}

    function render() {{
      if (!DATA.floors.length) return;
      const floor = DATA.floors[floorIndex];
      const candidate = floor.candidates[candidateIndex] || floor.candidates[0];
      if (!candidate) return;
      renderFloorList();
      renderHeader(floor);
      renderCandidateTabs(floor);
      renderGrid(floor, candidate);
      renderScorePanel(candidate);
    }}

    function selectFloor(i) {{
      floorIndex = i;
      candidateIndex = 0;
      render();
    }}
    function selectCandidate(i) {{
      candidateIndex = i;
      render();
    }}

    render();
  </script>
</body>
</html>
"""


def main() -> None:
    if not PROGRAM_FILE.exists():
        raise SystemExit(f"Missing {PROGRAM_FILE}. Run build_room_program.py first.")
    if not CANDIDATES_FILE.exists():
        raise SystemExit(f"Missing {CANDIDATES_FILE}. Run generate_layout_candidates.py first.")

    program = json.loads(PROGRAM_FILE.read_text(encoding="utf-8"))
    candidates = json.loads(CANDIDATES_FILE.read_text(encoding="utf-8"))
    payload = build_view_payload(program, candidates)

    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(render_html(payload), encoding="utf-8")
    print(f"Wrote viewer: {OUTPUT_HTML}")
    print(f"Generated at: {now_iso()}")
    print(f"Floors in viewer: {len(payload['floors'])}")


if __name__ == "__main__":
    main()
