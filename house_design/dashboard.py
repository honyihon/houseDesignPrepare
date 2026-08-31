from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from house_design.contracts import ROOT


CONCEPT_PATH = ROOT / "Docs/design/house-review-dashboard-concept.png"


def _safe_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def dashboard_html(report: dict[str, Any]) -> str:
    payload = _safe_json(report)
    title = html.escape(
        f"住宅設計檢核中心 · {report.get('revision', {}).get('revision_id', '')}"
    )
    document = r'''<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>__TITLE__</title>
  <style>
    :root {
      --canvas: #ffffff;
      --surface: #f7f9fb;
      --surface-strong: #eef3f7;
      --ink: #102a43;
      --muted: #66788a;
      --line: #d6e0e8;
      --line-strong: #bdcbd6;
      --teal: #0a7c83;
      --teal-hover: #086a70;
      --red: #c93737;
      --amber: #c87912;
      --green: #23834a;
      --gray: #8795a1;
      --blue: #2d6cdf;
      --radius-sm: 6px;
      --radius: 9px;
      --font: "Noto Sans TC", "Microsoft JhengHei", system-ui, -apple-system, sans-serif;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; min-height: 100%; background: var(--canvas); color: var(--ink); font-family: var(--font); }
    button, select, input { font: 600 14px/1.25 var(--font); color: inherit; }
    button, select { min-height: 38px; }
    button:focus-visible, select:focus-visible, [tabindex]:focus-visible { outline: 3px solid rgba(45,108,223,.25); outline-offset: 2px; }
    .app-header { height: 68px; border-bottom: 1px solid var(--line); display: grid; grid-template-columns: 260px minmax(220px, 1fr) auto; align-items: center; gap: 24px; padding: 0 22px; position: sticky; top: 0; z-index: 20; background: rgba(255,255,255,.98); }
    .brand { display: flex; align-items: center; gap: 12px; font-size: 23px; font-weight: 800; letter-spacing: .02em; white-space: nowrap; }
    .brand-mark { width: 34px; height: 34px; display: grid; grid-template-columns: repeat(3, 1fr); align-items: end; gap: 3px; padding: 4px; border: 2px solid var(--ink); border-radius: 3px; }
    .brand-mark i { display: block; border: 1.5px solid var(--ink); border-bottom: 0; }
    .brand-mark i:nth-child(1) { height: 17px; } .brand-mark i:nth-child(2) { height: 25px; } .brand-mark i:nth-child(3) { height: 20px; }
    .revision-picker { justify-self: center; width: min(320px, 100%); border: 1px solid var(--line-strong); border-radius: var(--radius-sm); padding: 0 12px; background: white; }
    .header-actions { display: flex; gap: 10px; }
    .button { border: 1px solid var(--teal); border-radius: var(--radius-sm); padding: 0 15px; background: white; color: var(--teal); cursor: pointer; display: inline-flex; gap: 8px; align-items: center; justify-content: center; }
    .button:hover { background: #eefafa; }
    .button.primary { background: var(--teal); color: white; }
    .button.primary:hover { background: var(--teal-hover); }
    .app-shell { display: grid; grid-template-columns: 232px minmax(0, 1fr); min-height: calc(100vh - 68px); }
    .sidebar { border-right: 1px solid var(--line); padding: 14px 12px 24px; background: #fbfcfd; overflow: auto; }
    .nav { display: grid; gap: 4px; padding-bottom: 16px; border-bottom: 1px solid var(--line); }
    .nav button { border: 0; background: transparent; border-radius: var(--radius-sm); padding: 0 12px; text-align: left; cursor: pointer; display: flex; align-items: center; gap: 10px; color: #29445d; }
    .nav button:hover, .nav button.active { background: #eaf1f7; color: var(--ink); }
    .nav button.active { box-shadow: inset 3px 0 var(--ink); font-weight: 800; }
    .nav-icon { width: 18px; height: 18px; display: inline-grid; place-items: center; font-size: 12px; border: 1.5px solid currentColor; border-radius: 4px; }
    .location-tree { padding: 16px 3px 0; }
    .building { margin-bottom: 13px; }
    .building-title { border: 0; background: transparent; width: 100%; display: flex; align-items: center; gap: 8px; min-height: 34px; padding: 0 7px; cursor: pointer; font-weight: 800; }
    .building-title::before { content: "⌄"; font-size: 14px; color: var(--muted); }
    .floor-list { margin: 1px 0 0 23px; border-left: 1px dotted var(--line-strong); display: grid; }
    .floor-button { border: 0; background: transparent; min-height: 34px; text-align: left; padding: 0 14px; margin-left: -1px; cursor: pointer; position: relative; border-radius: var(--radius-sm); }
    .floor-button::before { content: ""; position: absolute; left: 0; top: 50%; width: 9px; border-top: 1px dotted var(--line-strong); }
    .floor-button:hover, .floor-button.selected { background: #e8f2ff; color: #194e90; box-shadow: inset 0 0 0 1px #9ac3f4; }
    main { padding: 16px; min-width: 0; background: var(--canvas); }
    .readiness { border: 1px solid var(--line); border-radius: var(--radius); min-height: 120px; padding: 18px; display: grid; grid-template-columns: 175px minmax(0, 1fr); gap: 20px; align-items: center; }
    .readiness h1 { font-size: 16px; margin: 0 0 8px; }
    .readiness-value { font-size: 44px; font-weight: 800; line-height: 1; letter-spacing: -.04em; }
    .readiness-value small { font-size: 21px; }
    .readiness-caption { margin-top: 8px; color: var(--muted); font-size: 12px; }
    .fact-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(118px, 1fr)); border: 1px solid var(--line); min-height: 72px; }
    .fact { display: grid; grid-template-columns: 28px 1fr; align-items: center; padding: 10px 14px; border-right: 1px solid var(--line); gap: 8px; }
    .fact:last-child { border-right: 0; }
    .fact strong, .fact span { display: block; }
    .fact strong { font-size: 14px; }
    .fact span { color: var(--muted); font-size: 12px; margin-top: 3px; }
    .fact-symbol { width: 23px; height: 23px; border-radius: 50%; display: grid; place-items: center; color: white; background: var(--gray); font-size: 13px; }
    .fact.known .fact-symbol { background: var(--green); }
    .predesign-readiness { border: 1px solid var(--line); border-radius: var(--radius); margin-top: 12px; padding: 15px 18px; display: grid; grid-template-columns: 205px minmax(0, 1fr); gap: 18px; align-items: center; background: #fbfcfd; }
    .predesign-summary h2 { margin: 0 0 7px; font-size: 16px; }
    .predesign-summary strong { display: block; font-size: 25px; }
    .predesign-summary span { display: block; color: var(--muted); font-size: 12px; margin-top: 5px; }
    .phase-list { display: grid; grid-template-columns: repeat(4, minmax(115px, 1fr)); gap: 7px; }
    .phase-card { border: 1px solid var(--line); border-radius: 6px; background: white; padding: 8px 10px; min-height: 54px; }
    .phase-card.current { border-color: #8eb9ea; background: #edf6ff; }
    .phase-card strong, .phase-card span { display: block; }
    .phase-card strong { font-size: 12px; }
    .phase-card span { font-size: 11px; color: var(--muted); margin-top: 4px; }
    .model3d-readiness { border: 1px solid var(--line); border-radius: var(--radius); margin-top: 12px; padding: 16px 18px; background: #fbfcfd; scroll-margin-top: 80px; }
    .model3d-readiness.blocked { border-color: #e7baba; background: #fffafa; }
    .model3d-readiness.ready { border-color: #a8d3b9; background: #f8fdf9; }
    .model3d-header { display: flex; align-items: center; gap: 12px; }
    .model3d-header h2 { margin: 0 auto 0 0; font-size: 16px; }
    .model3d-status { display: inline-flex; align-items: center; min-height: 28px; padding: 0 10px; border-radius: 999px; font-size: 12px; font-weight: 800; color: white; background: var(--gray); }
    .model3d-readiness.blocked .model3d-status { background: var(--red); }
    .model3d-readiness.ready .model3d-status { background: var(--green); }
    .model3d-summary { margin: 8px 0 13px; color: #435a6f; font-size: 13px; line-height: 1.55; }
    .model3d-metrics { display: grid; grid-template-columns: repeat(4, minmax(115px, 1fr)); border: 1px solid var(--line); border-radius: 6px; overflow: hidden; background: white; }
    .model3d-metric { padding: 9px 11px; border-right: 1px solid var(--line); }
    .model3d-metric:last-child { border-right: 0; }
    .model3d-metric strong, .model3d-metric span { display: block; }
    .model3d-metric strong { font-size: 16px; }
    .model3d-metric span { margin-top: 3px; color: var(--muted); font-size: 11px; }
    .model3d-blockers { display: grid; gap: 7px; margin: 13px 0 0; padding: 0; list-style: none; }
    .model3d-blocker { display: grid; grid-template-columns: minmax(190px, .55fr) minmax(0, 1.45fr); gap: 12px; padding-top: 7px; border-top: 1px solid #eddada; font-size: 12px; line-height: 1.55; }
    .model3d-blocker code { color: var(--red); font-weight: 800; overflow-wrap: anywhere; }
    .model3d-blocker span { color: #435a6f; }
    .model3d-blocker small { display: block; color: var(--muted); font-size: 11px; }
    .model3d-note { margin: 11px 0 0; color: var(--muted); font-size: 11px; }
    .workspace { display: grid; grid-template-columns: minmax(480px, 1.55fr) minmax(310px, .9fr); margin-top: 12px; border: 1px solid var(--line); border-radius: var(--radius); overflow: hidden; height: 390px; }
    .plan-panel { min-width: 0; min-height: 0; border-right: 1px solid var(--line); display: grid; grid-template-rows: 46px minmax(0, 1fr); }
    .panel-toolbar { display: flex; align-items: center; gap: 8px; padding: 0 12px; border-bottom: 1px solid var(--line); }
    .panel-toolbar h2 { margin: 0 auto 0 0; font-size: 16px; }
    .tool { width: 32px; min-height: 32px; border: 1px solid transparent; border-radius: 5px; background: transparent; color: var(--muted); cursor: pointer; }
    .tool:hover, .tool.active { background: #e8f2ff; border-color: #bdd6f5; color: #194e90; }
    .zoom { color: var(--muted); font-size: 12px; }
    .plan-stage { position: relative; min-height: 0; overflow: hidden; background-color: #fbfcfd; background-image: radial-gradient(#dbe4ec .75px, transparent .75px); background-size: 14px 14px; }
    #planCanvas { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
    .plan-empty { position: absolute; inset: 0; display: none; place-items: center; text-align: center; color: var(--muted); padding: 40px; background: rgba(251,252,253,.92); }
    .plan-room { fill: rgba(230,237,243,.78); stroke: #28465f; stroke-width: 18; vector-effect: non-scaling-stroke; }
    .plan-room[data-category="bedroom"] { fill: #eef2ff; }
    .plan-room[data-category="bath"] { fill: #eefbfc; }
    .plan-room[data-category="kitchen"] { fill: #eff9f2; }
    .plan-room[data-category="outdoor"] { fill: #f2faf4; stroke-dasharray: 7 5; }
    .plan-label { font-family: var(--font); font-size: 180px; font-weight: 700; fill: #27445c; text-anchor: middle; dominant-baseline: middle; pointer-events: none; }
    .finding-marker { cursor: pointer; stroke: white; stroke-width: 3; vector-effect: non-scaling-stroke; }
    .inspector { padding: 0 17px 16px; overflow: auto; }
    .inspector-header { height: 46px; display: flex; align-items: center; border-bottom: 1px solid var(--line); margin: 0 -17px 15px; padding: 0 17px; }
    .inspector-header h2 { margin: 0; font-size: 16px; }
    .finding-title { display: grid; grid-template-columns: 25px 1fr; gap: 10px; align-items: start; margin-bottom: 17px; }
    .finding-title h3 { font-size: 16px; line-height: 1.45; margin: 0; }
    .status-dot { width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; color: white; font-size: 12px; font-weight: 800; margin-top: 1px; }
    .status-dot.fail { background: var(--red); } .status-dot.warning { background: var(--amber); }
    .status-dot.pass { background: var(--green); } .status-dot.unknown { background: var(--gray); }
    .status-dot.professional_review { background: var(--blue); } .status-dot.not_applicable { background: var(--gray); }
    .detail-grid { display: grid; grid-template-columns: 94px 1fr; gap: 10px 12px; margin: 0; font-size: 13px; line-height: 1.6; }
    .detail-grid dt { color: var(--muted); font-weight: 700; }
    .detail-grid dd { margin: 0; overflow-wrap: anywhere; }
    .status-text { font-weight: 800; }
    .status-text.fail { color: var(--red); } .status-text.warning { color: var(--amber); }
    .status-text.pass { color: var(--green); } .status-text.unknown { color: var(--gray); }
    .status-text.professional_review { color: var(--blue); }
    .next-action { border-top: 1px solid var(--line); margin-top: 17px; padding-top: 16px; }
    .next-action h4 { font-size: 14px; margin: 0 0 7px; }
    .next-action p { margin: 0; font-size: 13px; line-height: 1.65; }
    .table-panel, .comparison-panel { border: 1px solid var(--line); border-radius: var(--radius); margin-top: 12px; overflow: hidden; }
    .section-header { min-height: 42px; padding: 0 12px; display: flex; align-items: center; gap: 12px; border-bottom: 1px solid var(--line); }
    .section-header h2 { margin: 0 auto 0 0; font-size: 15px; }
    .section-header select { border: 1px solid var(--line-strong); border-radius: 5px; min-height: 30px; padding: 0 28px 0 9px; background: white; font-size: 12px; }
    .table-wrap { overflow: auto; max-height: 175px; }
    table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
    th, td { text-align: left; padding: 9px 12px; border-bottom: 1px solid #e4ebf0; vertical-align: top; }
    th { position: sticky; top: 0; background: var(--surface); color: #435a6f; font-size: 12px; z-index: 2; }
    tbody tr { cursor: pointer; }
    tbody tr:hover, tbody tr.selected { background: #eff7fb; }
    .table-status { display: inline-flex; align-items: center; gap: 7px; white-space: nowrap; font-weight: 700; }
    .table-status .status-dot { width: 16px; height: 16px; font-size: 9px; }
    .comparison-body { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); min-height: 120px; }
    .change { padding: 15px; border-right: 1px solid var(--line); }
    .change:last-child { border-right: 0; }
    .change strong { display: block; font-size: 13px; margin-bottom: 8px; }
    .change p { margin: 0; color: var(--muted); font-size: 12px; line-height: 1.55; }
    .change-index { display: inline-grid; place-items: center; width: 19px; height: 19px; background: var(--blue); color: white; border-radius: 50%; margin-right: 7px; font-size: 11px; }
    .empty-row { color: var(--muted); padding: 22px; text-align: center; grid-column: 1 / -1; }
    .dialog-backdrop { position: fixed; inset: 0; z-index: 40; background: rgba(16,42,67,.35); display: none; place-items: center; padding: 20px; }
    .dialog-backdrop.open { display: grid; }
    .dialog { width: min(620px, 100%); background: white; border: 1px solid var(--line-strong); border-radius: var(--radius); padding: 22px; box-shadow: 0 20px 60px rgba(16,42,67,.18); }
    .dialog h2 { margin: 0 0 8px; font-size: 20px; }
    .dialog p { color: var(--muted); line-height: 1.6; }
    .dialog code { display: block; background: var(--surface); border: 1px solid var(--line); padding: 12px; border-radius: 5px; white-space: pre-wrap; overflow-wrap: anywhere; color: #23425d; }
    .dialog-actions { display: flex; justify-content: flex-end; margin-top: 18px; }
    @media (max-width: 1080px) {
      .app-header { grid-template-columns: 1fr auto; height: auto; min-height: 68px; padding-block: 10px; }
      .revision-picker { grid-column: 1 / -1; grid-row: 2; justify-self: stretch; width: 100%; }
      .app-shell { grid-template-columns: 190px minmax(0, 1fr); }
      .model3d-readiness { scroll-margin-top: 128px; }
      .readiness { grid-template-columns: 1fr; }
      .predesign-readiness { grid-template-columns: 1fr; }
      .phase-list { grid-template-columns: repeat(3, 1fr); }
      .model3d-metrics { grid-template-columns: repeat(2, 1fr); }
      .model3d-metric:nth-child(2) { border-right: 0; }
      .model3d-metric:nth-child(n+3) { border-top: 1px solid var(--line); }
      .fact-list { grid-template-columns: repeat(3, 1fr); }
      .fact:nth-child(3) { border-right: 0; }
      .fact:nth-child(n+4) { border-top: 1px solid var(--line); }
      .workspace { grid-template-columns: 1fr; height: auto; }
      .plan-panel { border-right: 0; border-bottom: 1px solid var(--line); }
      .plan-stage { min-height: 410px; }
    }
    @media (max-width: 760px) {
      .app-header { grid-template-columns: 1fr; gap: 8px; }
      .brand { font-size: 19px; }
      .header-actions { grid-row: 3; }
      .app-shell { display: block; }
      .model3d-readiness { scroll-margin-top: 164px; }
      .sidebar { border-right: 0; border-bottom: 1px solid var(--line); max-height: 280px; }
      main { padding: 10px; }
      .fact-list { grid-template-columns: 1fr; }
      .phase-list { grid-template-columns: repeat(2, 1fr); }
      .model3d-metrics { grid-template-columns: 1fr; }
      .model3d-metric, .model3d-metric:nth-child(2) { border-right: 0; border-top: 1px solid var(--line); }
      .model3d-metric:first-child { border-top: 0; }
      .model3d-blocker { grid-template-columns: 1fr; gap: 3px; }
      .fact, .fact:nth-child(3) { border-right: 0; border-top: 1px solid var(--line); }
      .fact:first-child { border-top: 0; }
      .workspace { display: block; }
      .plan-panel { grid-template-rows: 46px 330px; }
      .plan-stage { min-height: 330px; }
      .comparison-body { grid-template-columns: 1fr; }
      .change { border-right: 0; border-bottom: 1px solid var(--line); }
      th:nth-child(4), td:nth-child(4) { display: none; }
    }
    @media print {
      .app-header { position: static; }
      .header-actions, .nav, .tool, .section-header select { display: none !important; }
      .app-shell { grid-template-columns: 150px 1fr; }
      .sidebar { background: white; }
      .table-wrap { max-height: none; overflow: visible; }
      .workspace, .table-panel, .comparison-panel, .readiness { break-inside: avoid; }
    }
  </style>
</head>
<body>
  <header class="app-header">
    <div class="brand"><span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i></span>住宅設計檢核中心</div>
    <select class="revision-picker" id="revisionPicker" aria-label="目前圖面版次"></select>
    <div class="header-actions">
      <button class="button primary" id="importButton" type="button">↑ 匯入新版圖面</button>
      <button class="button" id="printButton" type="button">▤ 匯出會議報告</button>
    </div>
  </header>
  <div class="app-shell">
    <aside class="sidebar">
      <nav class="nav" aria-label="主要功能">
        <button class="active" type="button"><span class="nav-icon">⌂</span>專案總覽</button>
        <button type="button" data-domain="requirements"><span class="nav-icon">≡</span>需求確認</button>
        <button type="button" data-domain="drawing_import"><span class="nav-icon">✓</span>圖面檢核</button>
        <button type="button" data-jump="model3d"><span class="nav-icon">3D</span>現行 3D</button>
        <button type="button" data-jump="comparison"><span class="nav-icon">↔</span>版次比較</button>
        <button type="button" data-domain="rule_governance"><span class="nav-icon">▤</span>決策紀錄</button>
      </nav>
      <div class="location-tree" id="locationTree" aria-label="棟別與樓層"></div>
    </aside>
    <main>
      <section class="readiness" aria-labelledby="readinessHeading">
        <div>
          <h1 id="readinessHeading">基地資料完成度</h1>
          <div class="readiness-value"><span id="readinessPercent">0</span><small>%</small></div>
          <div class="readiness-caption">灰色代表未知，不計為通過</div>
        </div>
        <div class="fact-list" id="factList"></div>
      </section>

      <section class="predesign-readiness" id="predesignReadiness" aria-labelledby="predesignHeading">
        <div class="predesign-summary">
          <h2 id="predesignHeading">前期階段閘門</h2>
          <strong><span id="predesignPercent">0</span>% 完成</strong>
          <span id="predesignBlockers">尚未載入</span>
        </div>
        <div class="phase-list" id="phaseList"></div>
      </section>

      <section class="model3d-readiness" id="model3dReadiness" aria-labelledby="model3dHeading">
        <div class="model3d-header">
          <h2 id="model3dHeading">現行 revision 3D</h2>
          <span class="model3d-status" id="model3dStatus">檢查中</span>
        </div>
        <p class="model3d-summary" id="model3dSummary"></p>
        <div class="model3d-metrics" id="model3dMetrics"></div>
        <ul class="model3d-blockers" id="model3dBlockers"></ul>
        <p class="model3d-note" id="model3dNote"></p>
      </section>

      <section class="workspace" aria-label="圖面與檢核詳情">
        <div class="plan-panel">
          <div class="panel-toolbar">
            <h2 id="planTitle">A棟 1F 平面圖</h2>
            <button class="tool active" type="button" aria-label="選取工具">⌖</button>
            <button class="tool" type="button" aria-label="圖層">▱</button>
            <span class="zoom">100%</span>
          </div>
          <div class="plan-stage">
            <svg id="planCanvas" role="img" aria-labelledby="planTitle"></svg>
            <div class="plan-empty" id="planEmpty">這個樓層尚無可追溯幾何。<br>請匯入 IFC，或以 mapping 對應 DXF 圖層。</div>
          </div>
        </div>
        <aside class="inspector" aria-live="polite">
          <div class="inspector-header"><h2>檢核事項詳情</h2></div>
          <div id="inspectorContent"></div>
        </aside>
      </section>

      <section class="table-panel" aria-labelledby="findingsHeading">
        <div class="section-header">
          <h2 id="findingsHeading">跨棟檢核事項總表</h2>
          <select id="statusFilter" aria-label="篩選檢核狀態">
            <option value="all">顯示全部</option>
            <option value="fail">失敗</option><option value="warning">警告</option>
            <option value="unknown">未知</option><option value="professional_review">專業確認</option>
            <option value="pass">通過</option>
          </select>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>狀態</th><th>棟別／樓層</th><th>問題</th><th>來源</th><th>負責角色</th></tr></thead>
            <tbody id="findingsBody"></tbody>
          </table>
        </div>
      </section>

      <section class="comparison-panel" id="comparison" aria-labelledby="comparisonHeading">
        <div class="section-header"><h2 id="comparisonHeading">版次比較</h2></div>
        <div class="comparison-body" id="comparisonBody"></div>
      </section>
    </main>
  </div>

  <div class="dialog-backdrop" id="importDialog" role="dialog" aria-modal="true" aria-labelledby="importHeading">
    <div class="dialog">
      <h2 id="importHeading">匯入新版圖面</h2>
      <p>版次是不可變資料。請使用新的 revision id，並優先提供 PDF＋IFC；只有 2D CAD 時提供 DXF 與圖層 mapping。</p>
      <code id="importCommand"></code>
      <div class="dialog-actions"><button class="button primary" id="closeDialog" type="button">知道了</button></div>
    </div>
  </div>

  <script id="reportData" type="application/json">__REPORT_JSON__</script>
  <script>
    const report = JSON.parse(document.getElementById('reportData').textContent);
    const statusGlyph = {fail:'×', warning:'!', pass:'✓', unknown:'?', professional_review:'i', not_applicable:'–'};
    const statusColor = {fail:'#c93737', warning:'#c87912', pass:'#23834a', unknown:'#8795a1', professional_review:'#2d6cdf', not_applicable:'#8795a1'};
    const floorsOrder = {'floor-1':1,'1F':1,'floor-2':2,'2F':2,'floor-3':3,'3F':3,'floor-rf':4,'RF':4};
    let selectedFinding = report.findings[0] || null;
    let selectedLocation = null;

    const revisionPicker = document.getElementById('revisionPicker');
    const revision = report.revision || {};
    revisionPicker.innerHTML = `<option>${escapeHtml(revision.revision_id || '未命名')} ${escapeHtml(revision.label || '')}</option>`;
    revisionPicker.disabled = true;
    document.getElementById('readinessPercent').textContent = report.readiness?.percent ?? 0;

    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
    }
    function locationText(applies = {}) {
      const building = applies.building_id || (Array.isArray(applies.parcel_ids) ? applies.parcel_ids.join(',') : applies.parcel_id);
      return [building ? `${building}棟` : '', applies.floor_id || ''].filter(Boolean).join('／') || '全專案';
    }
    function evidenceText(evidence = []) {
      const first = evidence[0] || {};
      if (first.path) return first.field ? `${first.path} · ${first.field}` : first.path;
      if (first.revision_id) return first.revision_id;
      if (first.entity_id) return first.entity_id;
      return first.kind || '專案檢核規則';
    }

    function renderFacts() {
      const host = document.getElementById('factList');
      host.innerHTML = (report.readiness?.facts || []).map(fact => `
        <div class="fact ${fact.known ? 'known' : ''}">
          <span class="fact-symbol">${fact.known ? '✓' : '–'}</span>
          <div><strong>${escapeHtml(fact.label)}</strong><span>${fact.known ? '已完成' : `缺 ${fact.total_count - fact.known_count} 筆基地資料`}</span></div>
        </div>`).join('');
    }

    function renderPredesign() {
      const predesign = report.predesign;
      const section = document.getElementById('predesignReadiness');
      if (!predesign) { section.style.display = 'none'; return; }
      const readiness = predesign.readiness || {};
      document.getElementById('predesignPercent').textContent = readiness.percent ?? 0;
      const blockers = predesign.gate?.active_blockers ?? 0;
      document.getElementById('predesignBlockers').textContent = blockers ? `${blockers} 個硬阻擋，不能進入下一階段` : '目前硬閘門已完成';
      const labels = {owner_brief:'家庭任務書',finance:'財務',site_search:'選地',site_due_diligence:'購地查核',design:'設計',tender:'發包',construction:'施工',handover:'交屋'};
      document.getElementById('phaseList').innerHTML = Object.entries(readiness.by_phase || {}).map(([phase,value]) => `
        <div class="phase-card ${phase === predesign.current_phase ? 'current' : ''}">
          <strong>${escapeHtml(labels[phase] || phase)}</strong>
          <span>${value.completed}/${value.total}${phase === predesign.current_phase ? ' · 目前' : ''}</span>
        </div>`).join('');
    }

    function renderModel3dReadiness() {
      const readiness = report.model3d_readiness;
      const section = document.getElementById('model3dReadiness');
      if (!readiness) { section.style.display = 'none'; return; }
      const eligible = Boolean(readiness.eligible);
      const counts = readiness.counts || {};
      section.classList.add(eligible ? 'ready' : 'blocked');
      document.getElementById('model3dStatus').textContent = eligible ? '可進入產圖' : '已阻擋';
      document.getElementById('model3dSummary').textContent = eligible
        ? '這個版次的輸入已具備可追溯 3D 幾何條件；仍須把產圖結果視為圖面閱讀工具，不等同合規放行。'
        : `這個版次有 ${readiness.blockers?.length || 0} 項輸入阻擋，不會建立或連結為現行 3D。`;
      const coordinateStatus = readiness.coordinate_system?.status || 'unknown';
      const metrics = [
        [`${counts.authoritative_renderable_spaces || 0}/${counts.total_spaces || 0}`, '權威且可渲染空間'],
        [`${counts.spaces_with_geometry || 0}/${counts.total_spaces || 0}`, '具有平面幾何'],
        [`${counts.elevated_storeys || 0}/${counts.total_storeys || 0}`, '具有樓層標高'],
        [coordinateStatus, '座標系統狀態'],
      ];
      document.getElementById('model3dMetrics').innerHTML = metrics.map(([value,label]) => `
        <div class="model3d-metric"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span></div>`).join('');
      const blockers = readiness.blockers || [];
      document.getElementById('model3dBlockers').innerHTML = blockers.map(blocker => `
        <li class="model3d-blocker">
          <code>${escapeHtml(blocker.code)}</code>
          <span>${escapeHtml(blocker.message)}<small>下一步：${escapeHtml(blocker.next_action)}</small></span>
        </li>`).join('');
      document.getElementById('model3dNote').textContent = eligible
        ? readiness.policy
        : '歷史 walkthrough 仍可供概念回顧，但不會冒充這個 revision 的現行 3D。';
    }

    function allLocations() {
      const spaces = report.model?.entities?.spaces || [];
      const seen = new Set();
      const values = [];
      spaces.forEach(space => {
        if (!space.building_id || !space.floor_id) return;
        const key = `${space.building_id}|${space.floor_id}`;
        if (!seen.has(key)) { seen.add(key); values.push({building_id:space.building_id, floor_id:space.floor_id}); }
      });
      if (!values.length) ['A','B','C'].forEach(building_id => ['floor-1','floor-2','floor-3','floor-rf'].forEach(floor_id => values.push({building_id,floor_id})));
      return values.sort((a,b) => a.building_id.localeCompare(b.building_id) || (floorsOrder[a.floor_id] ?? 99) - (floorsOrder[b.floor_id] ?? 99));
    }
    function floorLabel(floor) {
      return ({'floor-1':'1F','floor-2':'2F','floor-3':'3F','floor-rf':'RF'})[floor] || floor;
    }
    function renderTree() {
      const locations = allLocations();
      if (!selectedLocation) selectedLocation = locations.find(item => item.building_id === 'A' && item.floor_id === 'floor-1') || locations[0];
      const groups = {};
      locations.forEach(item => (groups[item.building_id] ||= []).push(item.floor_id));
      document.getElementById('locationTree').innerHTML = Object.entries(groups).map(([building, floors]) => `
        <section class="building"><button class="building-title" type="button">▥ ${escapeHtml(building)}棟</button>
        <div class="floor-list">${floors.map(floor => `<button class="floor-button ${selectedLocation?.building_id === building && selectedLocation?.floor_id === floor ? 'selected' : ''}" type="button" data-building="${escapeHtml(building)}" data-floor="${escapeHtml(floor)}">${escapeHtml(floorLabel(floor))}</button>`).join('')}</div></section>`).join('');
      document.querySelectorAll('.floor-button').forEach(button => button.addEventListener('click', () => {
        selectedLocation = {building_id:button.dataset.building, floor_id:button.dataset.floor};
        renderTree(); renderPlan();
      }));
    }

    function renderPlan() {
      const svg = document.getElementById('planCanvas');
      const empty = document.getElementById('planEmpty');
      const spaces = (report.model?.entities?.spaces || []).filter(space => space.building_id === selectedLocation?.building_id && space.floor_id === selectedLocation?.floor_id && Array.isArray(space.bbox_mm));
      document.getElementById('planTitle').textContent = `${selectedLocation?.building_id || '—'}棟 ${floorLabel(selectedLocation?.floor_id || '')} 平面圖`;
      svg.replaceChildren();
      if (!spaces.length) { empty.style.display = 'grid'; return; }
      empty.style.display = 'none';
      const bounds = spaces.reduce((box, room) => [Math.min(box[0],room.bbox_mm[0]),Math.min(box[1],room.bbox_mm[1]),Math.max(box[2],room.bbox_mm[2]),Math.max(box[3],room.bbox_mm[3])],[Infinity,Infinity,-Infinity,-Infinity]);
      const padding = Math.max((bounds[2]-bounds[0])*.08, 500);
      svg.setAttribute('viewBox', `${bounds[0]-padding} ${bounds[1]-padding} ${bounds[2]-bounds[0]+padding*2} ${bounds[3]-bounds[1]+padding*2}`);
      const ns = 'http://www.w3.org/2000/svg';
      spaces.forEach(room => {
        const [x0,y0,x1,y1] = room.bbox_mm;
        const rect = document.createElementNS(ns,'rect');
        rect.setAttribute('x',x0); rect.setAttribute('y',y0); rect.setAttribute('width',Math.max(1,x1-x0)); rect.setAttribute('height',Math.max(1,y1-y0));
        rect.setAttribute('class','plan-room'); rect.dataset.category = room.category || '';
        const title = document.createElementNS(ns,'title'); title.textContent = `${room.name || room.id} ${room.area_sqm ? `${room.area_sqm} m²` : ''}`; rect.appendChild(title); svg.appendChild(rect);
        if ((x1-x0) > 900 && (y1-y0) > 650) {
          const label = document.createElementNS(ns,'text'); label.setAttribute('x',(x0+x1)/2); label.setAttribute('y',(y0+y1)/2); label.setAttribute('class','plan-label'); label.textContent = String(room.name || '').slice(0,10); svg.appendChild(label);
        }
      });
      const localFindings = report.findings.filter(item => item.applies_to?.building_id === selectedLocation.building_id && item.applies_to?.floor_id === selectedLocation.floor_id);
      localFindings.slice(0,12).forEach((finding,index) => {
        const room = spaces.find(space => space.requirement_id && space.requirement_id === finding.applies_to?.requirement_id) || spaces[index % spaces.length];
        const [x0,y0,x1,y1] = room.bbox_mm;
        const marker = document.createElementNS(ns,'circle'); marker.setAttribute('cx',x0+(x1-x0)*(.25 + (index%3)*.22)); marker.setAttribute('cy',y0+(y1-y0)*(.25 + (index%2)*.4)); marker.setAttribute('r',170); marker.setAttribute('fill',statusColor[finding.status]); marker.setAttribute('class','finding-marker'); marker.setAttribute('tabindex','0'); marker.setAttribute('aria-label',finding.title);
        marker.addEventListener('click',() => selectFinding(finding)); marker.addEventListener('keydown',event => { if (event.key === 'Enter' || event.key === ' ') selectFinding(finding); }); svg.appendChild(marker);
        const number = document.createElementNS(ns,'text'); number.setAttribute('x',marker.getAttribute('cx')); number.setAttribute('y',Number(marker.getAttribute('cy'))+7); number.setAttribute('text-anchor','middle'); number.setAttribute('font-size','180'); number.setAttribute('font-weight','800'); number.setAttribute('fill','white'); number.setAttribute('pointer-events','none'); number.textContent=String(index+1); svg.appendChild(number);
      });
    }

    function renderInspector() {
      const host = document.getElementById('inspectorContent');
      if (!selectedFinding) { host.innerHTML = '<div class="empty-row">尚無檢核事項</div>'; return; }
      host.innerHTML = `
        <div class="finding-title"><span class="status-dot ${selectedFinding.status}">${statusGlyph[selectedFinding.status]}</span><h3>${escapeHtml(selectedFinding.finding_id)} ${escapeHtml(selectedFinding.title)}</h3></div>
        <dl class="detail-grid">
          <dt>狀態</dt><dd class="status-text ${selectedFinding.status}">${escapeHtml(selectedFinding.status_label)}</dd>
          <dt>類別</dt><dd>${escapeHtml(selectedFinding.domain)}</dd>
          <dt>說明</dt><dd>${escapeHtml(selectedFinding.message)}</dd>
          <dt>證據</dt><dd>${escapeHtml(evidenceText(selectedFinding.evidence))}</dd>
          <dt>負責角色</dt><dd>${escapeHtml(selectedFinding.responsible_role)}</dd>
        </dl>
        <div class="next-action"><h4>下一步行動</h4><p>${escapeHtml(selectedFinding.next_action)}</p></div>`;
    }

    function selectFinding(finding) {
      selectedFinding = finding; renderInspector(); renderFindings();
      if (finding.applies_to?.building_id && finding.applies_to?.floor_id) { selectedLocation = {building_id:finding.applies_to.building_id,floor_id:finding.applies_to.floor_id}; renderTree(); renderPlan(); }
    }
    function renderFindings(domain = null) {
      const filter = document.getElementById('statusFilter').value;
      const values = report.findings.filter(item => (filter === 'all' || item.status === filter) && (!domain || item.domain === domain));
      const body = document.getElementById('findingsBody');
      body.innerHTML = values.length ? values.map(item => `
        <tr tabindex="0" data-id="${escapeHtml(item.finding_id)}" class="${selectedFinding?.finding_id === item.finding_id ? 'selected' : ''}">
          <td><span class="table-status"><span class="status-dot ${item.status}">${statusGlyph[item.status]}</span>${escapeHtml(item.status_label)}</span></td>
          <td>${escapeHtml(locationText(item.applies_to))}</td><td>${escapeHtml(item.title)}</td>
          <td>${escapeHtml(evidenceText(item.evidence))}</td><td>${escapeHtml(item.responsible_role)}</td>
        </tr>`).join('') : '<tr><td colspan="5" class="empty-row">目前篩選沒有檢核事項</td></tr>';
      body.querySelectorAll('tr[data-id]').forEach(row => {
        const activate = () => selectFinding(report.findings.find(item => item.finding_id === row.dataset.id));
        row.addEventListener('click',activate); row.addEventListener('keydown',event => { if(event.key === 'Enter' || event.key === ' ') activate(); });
      });
    }

    function renderComparison() {
      const comparison = report.comparison;
      const host = document.getElementById('comparisonBody');
      if (!comparison) { document.getElementById('comparisonHeading').textContent = '版次比較 · 尚未指定上一版'; host.innerHTML = '<div class="empty-row">下次執行 review run 時加上 --previous R000，即可看到可追溯差異。</div>'; return; }
      document.getElementById('comparisonHeading').textContent = `版次比較：${comparison.from.revision_id} ${comparison.from.label || ''} → ${comparison.to.revision_id} ${comparison.to.label || ''}`;
      const changes = comparison.changes.slice(0,3);
      host.innerHTML = changes.length ? changes.map((change,index) => {
        const field = change.fields?.[0];
        const detail = field ? `${field.field}: ${JSON.stringify(field.before)} → ${JSON.stringify(field.after)}` : change.change;
        return `<article class="change"><strong><span class="change-index">${index+1}</span>${escapeHtml(change.name || change.entity_id)}</strong><p>${escapeHtml(detail)}</p></article>`;
      }).join('') : '<div class="empty-row">兩版正規化模型沒有偵測到空間、門窗或設備變更。</div>';
    }

    renderFacts(); renderPredesign(); renderModel3dReadiness(); renderTree(); renderPlan(); renderInspector(); renderFindings(); renderComparison();
    document.getElementById('statusFilter').addEventListener('change',() => renderFindings());
    document.querySelectorAll('.nav button[data-domain]').forEach(button => button.addEventListener('click',() => { document.getElementById('statusFilter').value='all'; renderFindings(button.dataset.domain); document.querySelector('.table-panel').scrollIntoView({behavior:'smooth'}); }));
    document.querySelectorAll('[data-jump]').forEach(button => button.addEventListener('click',() => document.getElementById(button.dataset.jump === 'model3d' ? 'model3dReadiness' : button.dataset.jump)?.scrollIntoView({behavior:'smooth'})));
    document.getElementById('printButton').addEventListener('click',() => window.print());
    const dialog = document.getElementById('importDialog');
    document.getElementById('importCommand').textContent = 'python -m house_design drawings import --revision R001 --label "初步設計" --pdf path/to/drawings.pdf --ifc path/to/model.ifc';
    document.getElementById('importButton').addEventListener('click',() => { dialog.classList.add('open'); document.getElementById('closeDialog').focus(); });
    document.getElementById('closeDialog').addEventListener('click',() => { dialog.classList.remove('open'); document.getElementById('importButton').focus(); });
    dialog.addEventListener('click',event => { if(event.target === dialog) dialog.classList.remove('open'); });
  </script>
</body>
</html>'''
    return document.replace("__TITLE__", title).replace("__REPORT_JSON__", payload)


def write_dashboard(report: dict[str, Any], directory: Path) -> Path:
    path = directory / "index.html"
    path.write_text(dashboard_html(report), encoding="utf-8", newline="\n")
    return path
