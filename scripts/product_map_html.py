#!/usr/bin/env python3
"""Flood-risk research product map — case-study storm loop + exposure layers.

NYC / Hurricane Ida is a case study only. Not Earth2Studio Enterprise / HENS.
"""

from __future__ import annotations

import json
from pathlib import Path

from nyc_flash_flood_case_study.config import FIGURES_DIR
from nyc_flash_flood_case_study.extents import EVENTS, EXTENTS


def write_product_html(manifest: dict, pluvial: dict, validation: dict) -> Path:
    precip = manifest.get("precip", {})
    frames = precip.get("frames", [])
    n = max(len(frames), 1)
    storm_paths = manifest.get("storm_paths") or []
    formula = (manifest.get("susceptibility") or {}).get("formula") or ""
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Flood Risk · research prototype (Ida case study)</title>
<meta name="description" content="Research flood-risk prototype. NYC Hurricane Ida is a case study only. Not official NWS guidance. No Earth2Studio Enterprise / HENS.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@500;600;700&family=IBM+Plex+Mono:wght@500&family=Source+Sans+3:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css">
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css">
<style>
:root {{
  --ink:#071018; --ink-soft:#152433; --muted:#6a7f90; --paper:#f3f7f9;
  --panel:rgba(255,255,255,.92); --line:#c5d3de; --line-soft:#dde6ed;
  --accent:#0a8a96; --accent-deep:#056068; --accent-soft:#d4eef1;
  --sea:#083b48; --sea-2:#0c6170; --warn:#8d3d14; --warn-bg:#fff3e6; --warn-line:#efc49a;
  --hud:#07141c; --chip:#e7eef3; --shadow:0 18px 50px rgba(7,16,24,.16);
  --radius:14px;
}}
* {{ box-sizing:border-box; }}
html,body {{ margin:0; height:100%; font-family:"Source Sans 3",sans-serif; color:var(--ink);
  background:
    radial-gradient(900px 520px at 8% -10%, rgba(12,97,112,.18), transparent 55%),
    radial-gradient(800px 480px at 100% 0%, rgba(8,59,72,.10), transparent 45%),
    linear-gradient(165deg, #eef4f7 0%, #d9e5ec 100%); }}
body {{ display:grid; grid-template-columns:minmax(320px,400px) 1fr; min-height:100%; }}
@media (max-width:980px) {{ body {{ grid-template-columns:1fr; grid-template-rows:auto 1fr; }} aside {{ max-height:50vh; border-right:0; border-bottom:1px solid var(--line); }} }}
aside {{
  position:relative; overflow:auto; padding:18px 16px 32px;
  background:
    linear-gradient(180deg, rgba(255,255,255,.86), rgba(243,247,249,.94)),
    repeating-linear-gradient(135deg, rgba(10,138,150,.04) 0 1px, transparent 1px 9px);
  border-right:1px solid var(--line); backdrop-filter: blur(10px);
}}
.brand {{
  position:relative; overflow:hidden; margin:0 0 14px; padding:18px 16px 16px; border-radius:18px;
  background: linear-gradient(145deg, var(--sea) 0%, var(--sea-2) 55%, #12818f 100%);
  color:#eef9fb; box-shadow:var(--shadow);
}}
.brand::after {{
  content:""; position:absolute; inset:auto -20% -40% 30%; height:120%;
  background:radial-gradient(circle, rgba(255,255,255,.16), transparent 60%); pointer-events:none;
  animation: drift 10s ease-in-out infinite alternate;
}}
@keyframes drift {{ from {{ transform:translateX(0); }} to {{ transform:translateX(-18px); }} }}
.brand-kicker {{ font:600 .68rem Sora,sans-serif; letter-spacing:.14em; text-transform:uppercase; opacity:.72; margin-bottom:6px; }}
.brand-mark {{ font-family:Sora,sans-serif; font-weight:700; font-size:1.55rem; letter-spacing:-.04em; line-height:1.05; }}
.brand-tag {{ margin-top:8px; font-size:.8rem; line-height:1.4; max-width:32ch; opacity:.9; }}
.disclaimer-bar {{
  position:sticky; top:0; z-index:4; margin:0 0 14px; padding:11px 12px; border-radius:var(--radius);
  background:var(--warn-bg); border:1px solid var(--warn-line); color:var(--warn); font-size:.76rem; line-height:1.4;
  box-shadow:0 1px 0 rgba(255,255,255,.65) inset;
}}
.panel {{
  background:var(--panel); border:1px solid var(--line-soft); border-radius:16px; padding:13px;
  margin:0 0 12px; box-shadow:0 1px 0 rgba(255,255,255,.85) inset, 0 8px 24px rgba(7,16,24,.03);
}}
.panel h2 {{
  font-family:Sora,sans-serif; font-size:.7rem; font-weight:600; margin:0 0 10px;
  text-transform:uppercase; letter-spacing:.1em; color:var(--muted);
}}
.seg {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:5px; padding:4px; border-radius:12px; background:var(--chip); border:1px solid var(--line-soft); }}
.seg button {{ border:0; background:transparent; border-radius:9px; padding:10px 6px; font:600 .72rem Sora,sans-serif; color:var(--muted); cursor:pointer; transition:all .15s; }}
.seg button.active {{ background:#fff; color:#045963; box-shadow:0 2px 8px rgba(7,16,24,.1); }}
.chain {{ display:grid; grid-template-columns:1fr auto 1fr auto 1fr; gap:4px; align-items:center; margin-top:10px; font-size:.7rem; font-weight:700; color:#045963; }}
.chain .step {{ text-align:center; padding:8px 4px; border-radius:10px; background:#d9eef1; border:1px solid #b6dde2; transition:opacity .2s; }}
.chain .step.dim {{ opacity:.4; background:var(--chip); border-color:var(--line-soft); color:var(--muted); }}
.mode-hint {{ font-size:.75rem; color:var(--muted); margin:8px 0 0; line-height:1.4; }}
label.caption {{ display:block; font-size:.74rem; color:var(--muted); font-weight:600; margin-bottom:5px; }}
select {{ width:100%; appearance:none; padding:10px 12px; border-radius:11px; border:1px solid var(--line); background:#fff; font:500 .9rem "Source Sans 3",sans-serif; color:var(--ink); }}
.stack {{ display:grid; gap:9px; }}
.transport {{ display:grid; grid-template-columns:auto 1fr auto; gap:8px; align-items:center; }}
.btn-icon {{ width:44px; height:44px; border-radius:13px; border:1px solid var(--line); background:#fff; font:700 1rem Sora,sans-serif; cursor:pointer; color:#045963; transition:transform .12s, background .15s; }}
.btn-icon:hover {{ transform:translateY(-1px); }}
.btn-icon.playing {{ background:#d4eef1; border-color:var(--accent); }}
input[type=range] {{ width:100%; accent-color:var(--accent); }}
.tick-row {{ display:flex; justify-content:space-between; margin-top:4px; font:500 .62rem "IBM Plex Mono",monospace; color:var(--muted); }}
.metrics {{ display:grid; gap:6px; margin-top:10px; }}
.metric {{ display:flex; justify-content:space-between; gap:8px; font-size:.8rem; padding:8px 10px; border-radius:10px; background:linear-gradient(180deg,#f7fafc,#eef3f6); }}
.readout {{ font:600 .82rem "IBM Plex Mono",monospace; color:#045963; }}
.honesty {{ margin-top:10px; padding:9px 10px; border-radius:11px; font-size:.73rem; line-height:1.4; color:#3d5563; background:#f2f6f8; border:1px dashed #b7c7d2; }}
.opacity-row {{ display:grid; grid-template-columns:88px 1fr 40px; gap:8px; align-items:center; font-size:.78rem; margin:7px 0; }}
.legend-swatch {{ height:9px; border-radius:999px; margin:2px 0 8px; }}
.legend-swatch.precip {{ background:linear-gradient(90deg,#30123b,#4662d8,#1ae4b6,#a2fc3c,#f9ba38,#e8332b); }}
.legend-swatch.susc {{ background:linear-gradient(90deg,#fff7bc,#fec44f,#d95f0e,#7f2704); }}
.legend-swatch.depth {{ background:linear-gradient(90deg,#f7fbff,#c6dbef,#6baed6,#2171b5,#08306b); }}
.layer-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:7px; }}
.group-label {{ grid-column:1 / -1; margin:6px 0 0; font-size:.68rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:#7d91a1; }}
.layer-btn {{ position:relative; display:flex; align-items:center; gap:8px; min-height:42px; padding:8px 10px 8px 34px; border-radius:12px; border:1px solid var(--line); background:#fff; cursor:pointer; font-size:.78rem; font-weight:600; transition:border-color .15s, background .15s, transform .12s; }}
.layer-btn:hover {{ transform:translateY(-1px); border-color:#9db4c2; }}
.layer-btn input {{ position:absolute; left:10px; top:50%; transform:translateY(-50%); width:14px; height:14px; margin:0; accent-color:var(--accent); cursor:pointer; }}
.layer-btn .dot {{ width:9px; height:9px; border-radius:50%; flex:0 0 auto; box-shadow:0 0 0 2px #fff; }}
.layer-btn:has(input:checked) {{ background:linear-gradient(180deg,#f5fcfd,#d9eef1); border-color:var(--accent); color:#045963; }}
.layer-btn:has(input:disabled) {{ opacity:.4; cursor:not-allowed; transform:none; }}
.layer-btn .count {{ margin-left:auto; font:600 .68rem "IBM Plex Mono",monospace; color:#7d91a1; }}
.layer-btn:has(input:checked) .count {{ color:#045963; }}
.layer-status {{ margin-top:8px; padding:8px 10px; border-radius:10px; background:#07141c; color:#e8f4f6; font-size:.74rem; line-height:1.35; display:none; }}
.layer-status.on {{ display:block; }}
.validation {{ display:grid; gap:6px; }}
.validation b {{ font:600 .82rem "IBM Plex Mono",monospace; }}
details.about {{ font-size:.76rem; color:var(--muted); line-height:1.45; }}
details.about summary {{ cursor:pointer; font-weight:700; color:var(--ink-soft); margin-bottom:6px; }}
.map-stage {{ position:relative; min-height:0; height:100%; }}
.map-pane {{ position:absolute; inset:0; }}
.map-el {{ position:absolute; inset:0; }}
.pane-label {{
  position:absolute; z-index:1000; top:14px; left:54px; padding:6px 12px; border-radius:999px;
  background:rgba(7,20,28,.82); color:#e8f4f6; border:1px solid rgba(255,255,255,.1);
  font:600 .72rem Sora,sans-serif; backdrop-filter:blur(8px);
}}
.footer-note {{
  position:absolute; z-index:1000; left:14px; bottom:98px; max-width:min(420px,88%);
  background:rgba(255,255,255,.92); border:1px solid var(--line); padding:8px 10px;
  font-size:.71rem; color:var(--muted); border-radius:11px;
}}
.radar-hud {{
  position:absolute; z-index:1100; left:50%; bottom:16px; transform:translateX(-50%);
  width:min(760px, calc(100% - 24px));
  display:grid; grid-template-columns:auto 1fr auto; gap:14px; align-items:center;
  padding:12px 16px; border-radius:18px;
  background:linear-gradient(180deg, rgba(10,28,36,.94), rgba(7,16,24,.92));
  color:#e7f3f5; border:1px solid rgba(255,255,255,.08); box-shadow:0 20px 50px rgba(0,0,0,.28);
  backdrop-filter: blur(14px);
}}
.radar-hud .play {{
  width:48px; height:48px; border-radius:14px; border:0; cursor:pointer;
  background:linear-gradient(180deg,#1bc0cd,#0e8f9c); color:#042227; font:700 1rem Sora,sans-serif;
  box-shadow:0 6px 16px rgba(14,143,156,.35);
}}
.radar-hud .clock {{ font:700 1rem Sora,sans-serif; letter-spacing:-.02em; }}
.radar-hud .sub {{ font-size:.72rem; opacity:.78; margin-top:2px; }}
.radar-hud .legend {{ display:flex; flex-direction:column; gap:5px; align-items:flex-end; font-size:.68rem; opacity:.92; }}
.radar-hud .bar {{ width:128px; height:8px; border-radius:999px; background:linear-gradient(90deg,#30123b,#4662d8,#1ae4b6,#a2fc3c,#f9ba38,#e8332b); }}
.radar-hud .bar.susc {{ background:linear-gradient(90deg,#fff7bc,#fec44f,#d95f0e,#7f2704); }}
.radar-hud .bar.depth {{ background:linear-gradient(90deg,#f7fbff,#c6dbef,#6baed6,#2171b5,#08306b); }}
.path-pill {{
  display:inline-flex; align-items:center; gap:6px; margin-top:8px; padding:5px 10px; border-radius:999px;
  background:#e7f5f7; color:#045963; font:600 .7rem Sora,sans-serif; border:1px solid #b7dde2;
}}
</style>
</head>
<body>
<aside>
  <div class="brand">
    <div class="brand-kicker">Flood risk · research prototype</div>
    <div class="brand-mark">Flood Risk</div>
    <div class="brand-tag">Infrastructure / response–informing risk screening. NYC Hurricane Ida is a case study only — not the product scope.</div>
  </div>
  <div class="disclaimer-bar">
    <b>NOT decision-grade. NOT an official NWS flood warning. NOT emergency guidance.</b>
    Open-stack research prototype (no Earth2Studio Enterprise / HENS). Case study forcing: MRMS QPE + open Earth2-class scenarios when available.
    Depth/alerts are estimated (pysheds) — not agency-calibrated return-period risk.
  </div>
  <div id="assetBanner" class="disclaimer-bar" style="display:none;background:#3b0d0d;border-color:#7f1d1d;color:#fecaca"></div>

  <div class="panel">
    <h2>Product mode</h2>
    <div class="seg" role="group" aria-label="Product mode" style="grid-template-columns:1fr 1fr 1fr 1fr">
      <button type="button" class="active" id="productStorm" data-mode="storm">Storm</button>
      <button type="button" id="productSusc" data-mode="susceptibility">Susceptibility</button>
      <button type="button" id="productCoupled" data-mode="coupled">Coupled</button>
      <button type="button" id="productDepth" data-mode="depth">Depth</button>
    </div>
    <div class="chain" aria-label="Product chain — always available; modes only change default overlays">
      <span class="step" id="chainPrecip">Weather</span><span>→</span>
      <span class="step" id="chainSusc">Landscape×Infra</span><span>→</span>
      <span class="step" id="chainInfra">Exposure</span>
    </div>
    <p class="mode-hint" id="modeHint">Modes set default overlays only. Roads, 311, FEMA, and all other layer toggles stay available in every mode.</p>
  </div>

  <div class="panel">
    <h2>Storm path</h2>
    <label class="caption" for="stormPathSelect">Scenario track</label>
    <select id="stormPathSelect" aria-label="Storm path"></select>
    <div class="path-pill" id="pathPill">Earth2 (primary)</div>
    <div class="honesty" id="pathHonesty">Primary Earth2 control path. Alternate members are IC-perturbation scenarios, not observations.</div>
  </div>

  <div class="panel">
    <h2>Scene</h2>
    <div class="stack">
      <div><label class="caption" for="eventSelect">Event</label><select id="eventSelect"></select></div>
      <div><label class="caption" for="extentSelect">Map extent</label><select id="extentSelect"></select></div>
    </div>
  </div>

  <div class="panel">
    <h2>Storm clock</h2>
    <div class="transport">
      <button type="button" class="btn-icon" id="playBtn" aria-label="Play">▶</button>
      <div>
        <input id="leadSlider" type="range" min="0" max="{n - 1}" value="0" step="1">
        <div class="tick-row" id="tickRow"></div>
      </div>
      <select id="playSpeed" style="width:auto;min-width:72px;padding:8px" aria-label="Speed">
        <option value="1200">Slow</option>
        <option value="750" selected>Med</option>
        <option value="450">Fast</option>
      </select>
    </div>
    <div class="metrics">
      <div class="metric"><span>Clock (UTC)</span><span class="readout" id="clockReadout">—</span></div>
      <div class="metric"><span>Lead</span><span class="readout" id="leadReadout">—</span></div>
      <div class="metric"><span>Earth2 max</span><span class="readout" id="e2Readout">—</span></div>
      <div class="metric"><span>Frame</span><span class="readout" id="frameTypeReadout">—</span></div>
    </div>
    <div class="honesty">Native Earth2 leads are 6h. Loop densifies with 2h <b>temporal blends</b> (labeled) — not extra model output, not NEXRAD.</div>
  </div>

  <div class="panel">
    <h2>Opacity & legend</h2>
    <div class="opacity-row"><span>Precip</span><input id="opPrecip" type="range" min="15" max="95" value="78"><span id="opPrecipVal">78%</span></div>
    <div class="legend-swatch precip"></div>
    <div class="opacity-row"><span>Susceptibility</span><input id="opSusc" type="range" min="15" max="95" value="64"><span id="opSuscVal">64%</span></div>
    <div class="legend-swatch susc"></div>
    <div class="opacity-row"><span>Est. depth</span><input id="opDepth" type="range" min="15" max="95" value="78"><span id="opDepthVal">78%</span></div>
    <div class="legend-swatch depth"></div>
    <div><label class="caption" for="resampleSelect">Precip display</label>
      <select id="resampleSelect">
        <option value="nearest" selected>Nearest (blocky / honest)</option>
        <option value="bilinear">Bilinear (CSS only)</option>
      </select>
    </div>
  </div>

  <div class="panel">
    <h2>Layers</h2>
    <div class="honesty" style="margin-top:0;margin-bottom:8px">Full checklist usable in every mode. Enabling an infra/context layer dims precip so vectors stay visible at citywide zoom.</div>
    <div class="layer-grid">
      <div class="group-label">Storm</div>
      <label class="layer-btn"><input id="lyE2" type="checkbox" checked><span class="dot" style="background:#4662d8"></span>Precip (active path)</label>
      <label class="layer-btn"><input id="lyE2Tot" type="checkbox"><span class="dot" style="background:#30123b"></span>Storm total</label>

      <div class="group-label">Depth (research · NOT flood warning)</div>
      <label class="layer-btn"><input id="lyDepth" type="checkbox"><span class="dot" style="background:#2171b5"></span>Est. inundation depth</label>
      <label class="layer-btn"><input id="lyDepthTot" type="checkbox"><span class="dot" style="background:#08306b"></span>Storm-total depth</label>
      <div class="honesty" id="depthForceNote" style="grid-column:1/-1;margin-top:4px">Depth forcing follows selected storm path.</div>

      <div class="group-label">Susceptibility</div>
      <label class="layer-btn"><input id="lySusc" type="checkbox"><span class="dot" style="background:#d95f0e"></span>Multi-factor heatmap</label>
      <label class="layer-btn"><input id="lyBuilt" type="checkbox"><span class="dot" style="background:#475569"></span>Built surface</label>

      <div class="group-label">Infrastructure / obs</div>
      <label class="layer-btn"><input id="lyInfra" type="checkbox"><span class="dot" style="background:#b91c1c"></span>Storm-synced roads</label>
      <label class="layer-btn"><input id="lyHot" type="checkbox"><span class="dot" style="background:#ff2d55"></span>Hotspot roads<span class="count" id="cntHot">…</span></label>
      <label class="layer-btn"><input id="ly311" type="checkbox"><span class="dot" style="background:#ff3b5c"></span>311 reports<span class="count" id="cnt311">…</span></label>
      <label class="layer-btn"><input id="lySta" type="checkbox"><span class="dot" style="background:#00e5a8"></span>Stations<span class="count" id="cntSta">…</span></label>
      <label class="layer-btn"><input id="lyRoads" type="checkbox"><span class="dot" style="background:#ff6b00"></span>Roads<span class="count" id="cntRoads">…</span></label>

      <div class="group-label">Context</div>
      <label class="layer-btn"><input id="lyFema" type="checkbox"><span class="dot" style="background:#4f7cff"></span>FEMA NFHL<span class="count" id="cntFema">…</span></label>
      <label class="layer-btn"><input id="lyNwm" type="checkbox"><span class="dot" style="background:#00c2ff"></span>NWM reaches<span class="count" id="cntNwm">…</span></label>
      <label class="layer-btn"><input id="lyGauges" type="checkbox"><span class="dot" style="background:#37d6ff"></span>AHPS gauges<span class="count" id="cntGauges">…</span></label>
      <label class="layer-btn"><input id="lyDrainE" type="checkbox"><span class="dot" style="background:#ffb020"></span>Demo conduits<span class="count" id="cntDrainE">…</span></label>
      <label class="layer-btn"><input id="lyDrainN" type="checkbox"><span class="dot" style="background:#ffd60a"></span>Demo nodes<span class="count" id="cntDrainN">…</span></label>
    </div>
    <div class="layer-status" id="layerStatus">No infra/context layer on.</div>
  </div>

  <div class="panel">
    <h2>Research alerts (prototype)</h2>
    <div class="honesty" style="margin-top:0">Threshold chips from estimated depth — <b>NOT official NWS watches/warnings</b>.</div>
    <div class="validation" id="alertPanel" style="margin-top:8px">Loading…</div>
  </div>

  <div class="panel">
    <h2>Validation</h2>
    <div class="validation" id="validationPanel">Loading…</div>
  </div>

  <div class="panel">
    <details class="about" open>
      <summary>Science notes</summary>
      <p>
        <b>Susceptibility</b> = weather × landscape × infrastructure screening:<br>
        <code style="font-size:.68rem">{formula}</code><br><br>
        <b>Storm paths</b> = Earth2 primary + Earth2 ensemble / labeled MRMS QPE alt scenarios.<br>
        <b>Depth</b> = pysheds HAND + depression bathtub forced by Earth2 precip — research estimate only.<br>
        <b>Cannot claim</b> = official NWS flood warning, calibrated NYC DEP inundation, emergency guidance.
      </p>
    </details>
  </div>
</aside>

<div class="map-stage" id="mapStage">
  <div class="map-pane"><div class="pane-label" id="leftLabel">Flood risk · case study</div><div id="mapLeft" class="map-el"></div></div>
  <div class="footer-note">Flood-risk research prototype (open stack). NYC/Ida is a case study. Not decision-grade. No Enterprise/HENS.</div>
  <div class="radar-hud">
    <button type="button" class="play" id="hudPlay">▶</button>
    <div>
      <div class="clock" id="hudClock">—</div>
      <div class="sub" id="hudSub">Earth2 frame · land-masked · ~0.25°</div>
    </div>
    <div class="legend">
      <span id="hudLegendLabel">Earth2 precip (mm)</span>
      <div class="bar" id="hudLegendBar"></div>
    </div>
  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script>
const EVENTS = {json.dumps(EVENTS)};
const EXTENTS = {json.dumps(EXTENTS)};
const manifest = {json.dumps(manifest)};
const pluvial = {json.dumps(pluvial)};
const validation = {json.dumps(validation)};
// Resolve asset base relative to this HTML file (works under /figures, /docs, nested hosts).
// file:// will fail fetch — banner instructs to use scripts/serve_product.py.
function resolveAssetBase() {{
  const here = window.location.href;
  if (here.startsWith("file:")) {{
    const b = document.getElementById("assetBanner");
    if (b) {{
      b.style.display = "block";
      b.innerHTML = "<b>Open via local HTTP server</b> — file:// cannot fetch GeoJSON. From repo root: <code>python scripts/serve_product.py</code> then open the printed URL.";
    }}
  }}
  try {{ return new URL("product_assets/", here).href; }}
  catch (e) {{ return "product_assets/"; }}
}}
const assets = resolveAssetBase();
window.__productAssetsBase = assets;
const stormPaths = manifest.storm_paths || [{{
  id: "earth2_control", label: "Earth2 open scenario", primary: false, scenario_kind: "earth2_open_scenario",
  precip: manifest.precip, susceptibility: manifest.susceptibility, infra_highlights: manifest.infra_highlights
}}];

const mapLeft = L.map("mapLeft", {{ zoomControl: true }});
window.mapLeft = mapLeft;
mapLeft.createPane("rasterPane");
mapLeft.getPane("rasterPane").style.zIndex = 350;
mapLeft.createPane("depthPane");
mapLeft.getPane("depthPane").style.zIndex = 400;
mapLeft.createPane("vectorPane");
mapLeft.getPane("vectorPane").style.zIndex = 650; // above markerPane (600)
mapLeft.getPane("vectorPane").style.pointerEvents = "none";
mapLeft.createPane("pointPane");
mapLeft.getPane("pointPane").style.zIndex = 670;
mapLeft.getPane("pointPane").style.pointerEvents = "auto";
// Per-layer SVG renderers avoid Leaflet shared-renderer wipe bugs.
function makeVectorRenderer() {{ return L.svg({{ pane: "vectorPane", padding: 0.5 }}); }}
function makePointRenderer() {{ return L.svg({{ pane: "pointPane", padding: 0.5 }}); }}
L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}", {{
  maxZoom: 19,
  attribution: "Tiles &copy; Esri &mdash; Source: Esri, OpenStreetMap"
}}).addTo(mapLeft);

const eventSel = document.getElementById("eventSelect");
Object.values(EVENTS).forEach(ev => {{
  const opt = document.createElement("option");
  opt.value = ev.id; opt.textContent = ev.label + (ev.available ? "" : " (unavailable)");
  opt.disabled = !ev.available; eventSel.appendChild(opt);
}});
eventSel.value = "ida-2021";
const extentSel = document.getElementById("extentSelect");
Object.values(EXTENTS).forEach(ex => {{
  const opt = document.createElement("option"); opt.value = ex.id; opt.textContent = ex.label; extentSel.appendChild(opt);
}});
extentSel.value = (manifest.layer_bounds && manifest.layer_bounds.map_extent_default) || "citywide";

const pathSel = document.getElementById("stormPathSelect");
stormPaths.forEach(p => {{
  const opt = document.createElement("option");
  opt.value = p.id;
  opt.textContent = p.label + (p.primary ? "" : " · alternate scenario");
  pathSel.appendChild(opt);
}});
pathSel.value = manifest.default_storm_path || stormPaths[0].id;

function currentBounds() {{
  const b = (EXTENTS[extentSel.value] || EXTENTS.citywide).bounds;
  return [[b.ymin, b.xmin],[b.ymax, b.xmax]];
}}

let activePath = stormPaths.find(p => p.id === pathSel.value) || stormPaths[0];
let frames = activePath.precip?.frames || [];
let suscFrames = activePath.susceptibility?.frames || [];
let infraFrames = activePath.infra_highlights?.frames || [];
let precipBounds = (activePath.precip && activePath.precip.bounds) || currentBounds();
let suscBounds = (activePath.susceptibility && activePath.susceptibility.bounds) || precipBounds;
const hotspotBounds = precipBounds;

let e2Layers = [], suscLayers = [], depthLayers = [];
let activeE2 = null, activeSusc = null, activeInfra = null, activeDepth = null;
let e2Total = null, depthTotal = null;
const inundation = manifest.inundation || null;
const depthBounds = (inundation && inundation.bounds) || precipBounds;
function depthSetForPath(pathId) {{
  if (!inundation) return null;
  const by = inundation.by_path || {{}};
  if (pathId && by[pathId]) return by[pathId];
  // Earth2 ensemble shares Earth2 depth forcing
  if (pathId && String(pathId).startsWith("earth2") && by.earth2_control) return by.earth2_control;
  if (by[inundation.default_depth_path]) return by[inundation.default_depth_path];
  return inundation; // legacy flat shape
}}
let activeDepthSet = depthSetForPath(activePath && activePath.id);
const builtLayer = pluvial?.built_surface_png ? L.imageOverlay(assets + pluvial.built_surface_png, suscBounds, {{ opacity: 0.5, pane:"rasterPane", interactive:false }}) : null;
const hotspot = (manifest.disruption?.hotspot_png)
  ? L.imageOverlay(assets + manifest.disruption.hotspot_png, hotspotBounds, {{ opacity: 0.55, pane:"rasterPane", interactive:false }})
  : null;
let roadsLayer=null, disruptLayer=null, stationsLayer=null, drainNodes=null, drainEdges=null, femaLayer=null, nwmLayer=null, gaugesLayer=null;
// MarkerCluster uses default marker panes (not custom SVG panes) — more reliable visibility.
const reports = L.markerClusterGroup({{
  showCoverageOnHover: false,
  maxClusterRadius: 50,
  spiderfyOnMaxZoom: true,
  disableClusteringAtZoom: 15
}});
let productMode = "storm", playing = false, playTimer = null;
const vectorLayers = [];
const layerRegistry = {{}}; // id -> {{ layer, n, label }}
const pendingChecked = new Set();
let savedPrecipOpacity = null;

function precipOpacity() {{ return (+document.getElementById("opPrecip").value) / 100; }}
function suscOpacity() {{ return (+document.getElementById("opSusc").value) / 100; }}
function depthOpacity() {{ return (+document.getElementById("opDepth").value) / 100; }}
function raiseVectors() {{
  vectorLayers.forEach(l => {{ if (l && mapLeft.hasLayer(l) && l.bringToFront) l.bringToFront(); }});
  if (activeInfra && mapLeft.hasLayer(activeInfra) && activeInfra.bringToFront) activeInfra.bringToFront();
  if (reports && mapLeft.hasLayer(reports)) reports.bringToFront();
}}
function contextLayerOn() {{
  return ["lyHot","ly311","lySta","lyRoads","lyFema","lyNwm","lyGauges","lyDrainE","lyDrainN","lyInfra"]
    .some(id => document.getElementById(id)?.checked);
}}
function updateLayerStatus() {{
  const el = document.getElementById("layerStatus");
  if (!el) return;
  const on = Object.entries(layerRegistry)
    .filter(([id]) => document.getElementById(id)?.checked)
    .map(([id, meta]) => `${{meta.label}} (${{meta.n}})`);
  if (!on.length) {{
    el.classList.remove("on");
    el.textContent = "No infra/context layer on.";
    return;
  }}
  el.classList.add("on");
  el.textContent = "On map: " + on.join(" · ") + " — precip auto-dimmed for visibility.";
}}
function ensureVectorsVisible() {{
  const op = document.getElementById("opPrecip");
  if (!op) return;
  if (contextLayerOn()) {{
    if (savedPrecipOpacity == null) savedPrecipOpacity = op.value;
    if (+op.value > 35) {{
      op.value = "32";
      document.getElementById("opPrecipVal").textContent = "32%";
      if (activeE2) activeE2.setOpacity(precipOpacity());
      if (e2Total) e2Total.setOpacity(precipOpacity());
    }}
  }} else if (savedPrecipOpacity != null) {{
    op.value = savedPrecipOpacity;
    document.getElementById("opPrecipVal").textContent = savedPrecipOpacity + "%";
    if (activeE2) activeE2.setOpacity(precipOpacity());
    if (e2Total) e2Total.setOpacity(precipOpacity());
    savedPrecipOpacity = null;
  }}
  updateLayerStatus();
}}

function rebuildPathLayers() {{
  e2Layers.forEach(l => mapLeft.removeLayer(l));
  suscLayers.forEach(l => mapLeft.removeLayer(l));
  if (e2Total) mapLeft.removeLayer(e2Total);
  if (activeInfra) {{ mapLeft.removeLayer(activeInfra); activeInfra = null; }}
  frames = activePath.precip?.frames || [];
  suscFrames = activePath.susceptibility?.frames || [];
  infraFrames = activePath.infra_highlights?.frames || [];
  precipBounds = (activePath.precip && activePath.precip.bounds) || currentBounds();
  suscBounds = (activePath.susceptibility && activePath.susceptibility.bounds) || precipBounds;
  e2Layers = frames.map(f => L.imageOverlay(assets + f.png, precipBounds, {{ opacity: precipOpacity(), interactive:false, pane:"rasterPane", className:"precip-nearest" }}));
  suscLayers = suscFrames.map(f => L.imageOverlay(assets + f.png, suscBounds, {{ opacity: suscOpacity(), interactive:false, pane:"rasterPane" }}));
  e2Total = activePath.precip?.storm_total_png ? L.imageOverlay(assets + activePath.precip.storm_total_png, precipBounds, {{ opacity: precipOpacity(), pane:"rasterPane", interactive:false }}) : null;
  // Depth set follows selected storm path forcing (Earth2 vs MRMS QPE Ida alt).
  activeDepthSet = depthSetForPath(activePath.id);
  const depthFrames = (activeDepthSet && activeDepthSet.cumulative_frames) || [];
  depthLayers = depthFrames.map(f => L.imageOverlay(assets + f.png, (activeDepthSet.bounds || depthBounds), {{ opacity: depthOpacity(), interactive:false, pane:"depthPane" }}));
  if (depthTotal && mapLeft.hasLayer(depthTotal)) mapLeft.removeLayer(depthTotal);
  depthTotal = (activeDepthSet && activeDepthSet.storm_total && activeDepthSet.storm_total.png)
    ? L.imageOverlay(assets + activeDepthSet.storm_total.png, (activeDepthSet.bounds || depthBounds), {{ opacity: depthOpacity(), interactive:false, pane:"depthPane" }})
    : null;
  document.getElementById("leadSlider").max = Math.max(frames.length - 1, 0);
  document.getElementById("tickRow").innerHTML = frames.map(f => `<span>+${{Number(f.lead_hours)}}</span>`).join("");
  document.getElementById("pathPill").textContent = activePath.label;
  document.getElementById("pathHonesty").textContent = activePath.primary
    ? "Primary Earth2 control path. Alternate tracks are labeled scenarios (ensemble / higher-res Ida), not a validation split-screen."
    : (activePath.honesty || "Alternate storm scenario — clearly labeled; not a live competing weather product.");
  const depthNote = document.getElementById("depthForceNote");
  if (depthNote) {{
    const ds = activeDepthSet;
    depthNote.textContent = ds
      ? (`Depth forcing: ${{ds.label || ds.id}} · max≈${{ds.storm_total?.max_m != null ? ds.storm_total.max_m.toFixed(2) : "—"}} m · NOT flood warning`)
      : "Depth set unavailable for this path.";
  }}
}}

function setLead(i) {{
  if (!frames.length) return;
  i = Math.max(0, Math.min(frames.length - 1, i));
  document.getElementById("leadSlider").value = String(i);
  const f = frames[i];
  if (activeE2 && mapLeft.hasLayer(activeE2)) mapLeft.removeLayer(activeE2);
  activeE2 = e2Layers[i];
  if (document.getElementById("lyE2").checked && activeE2) {{ activeE2.setOpacity(precipOpacity()); activeE2.addTo(mapLeft); }}
  if (activeSusc && mapLeft.hasLayer(activeSusc)) mapLeft.removeLayer(activeSusc);
  if (suscLayers[i]) {{
    activeSusc = suscLayers[i];
    if (document.getElementById("lySusc").checked) {{ activeSusc.setOpacity(suscOpacity()); activeSusc.addTo(mapLeft); }}
  }}
  if (activeInfra) {{ mapLeft.removeLayer(activeInfra); activeInfra = null; }}
  const infraMeta = infraFrames[i];
  if (infraMeta && infraMeta.geojson && document.getElementById("lyInfra").checked) {{
    fetch(assets + infraMeta.geojson).then(r => r.ok ? r.json() : null).then(geo => {{
      if (!geo || +document.getElementById("leadSlider").value !== i) return;
      activeInfra = L.geoJSON(geo, {{
        pane: "vectorPane", renderer: makeVectorRenderer(),
        style: {{ color:"#ff1744", weight:5, opacity:1 }},
        onEachFeature: (ft, layer) => layer.bindTooltip("Storm-synced · multi-factor susceptibility (demo)")
      }}).addTo(mapLeft);
      raiseVectors();
    }}).catch(()=>{{}});
  }}
  if (activeDepth && mapLeft.hasLayer(activeDepth)) mapLeft.removeLayer(activeDepth);
  activeDepth = null;
  if (depthLayers.length) {{
    const lead = Number(f.lead_hours);
    const depthFrames = (activeDepthSet && activeDepthSet.cumulative_frames) || [];
    let best = 0, bestAbs = Infinity;
    depthFrames.forEach((df, di) => {{
      const d = Math.abs(Number(df.lead_hours) - lead);
      if (d < bestAbs) {{ bestAbs = d; best = di; }}
    }});
    activeDepth = depthLayers[best] || depthLayers[depthLayers.length - 1];
    if (document.getElementById("lyDepth").checked && activeDepth) {{
      activeDepth.setOpacity(depthOpacity()); activeDepth.addTo(mapLeft);
    }}
  }}
  if (document.getElementById("lyDepthTot").checked && depthTotal) {{
    depthTotal.setOpacity(depthOpacity());
    if (!mapLeft.hasLayer(depthTotal)) depthTotal.addTo(mapLeft);
  }}
  const clock = (f.valid_time || "").replace("T", " ");
  document.getElementById("clockReadout").textContent = clock;
  document.getElementById("leadReadout").textContent = "+" + f.lead_hours + " h";
  document.getElementById("e2Readout").textContent = (f.max_mm != null ? f.max_mm.toFixed(1) : "—") + " mm";
  document.getElementById("frameTypeReadout").textContent = f.temporal_blend ? "temporal blend" : (f.resolution_note ? "hi-res alt" : "native");
  document.getElementById("hudClock").textContent = clock + " UTC";
  const depthForce = activeDepthSet ? (activeDepthSet.id === "mrms_qpe_ida" ? "MRMS-forced" : "Earth2-forced") : "";
  document.getElementById("hudSub").textContent = productMode === "susceptibility"
    ? ("Multi-factor susceptibility · +" + f.lead_hours + "h · screening only")
    : productMode === "depth"
      ? ("Est. research inundation · " + depthForce + " · NOT flood warning · +" + f.lead_hours + "h")
      : (activePath.label + " · +" + f.lead_hours + "h · " + (f.temporal_blend ? "blend" : "native") + " · not NEXRAD");
  document.getElementById("leftLabel").textContent =
    (productMode === "susceptibility" ? "Susceptibility" : productMode === "coupled" ? "Coupled" : productMode === "depth" ? ("Depth · " + depthForce) : "Flood risk")
    + " · " + ((activePath && activePath.label) ? activePath.label : "case study");
  raiseVectors();
  writeUrl();
}}

function setPlaying(on) {{
  playing = on;
  document.getElementById("playBtn").textContent = on ? "❚❚" : "▶";
  document.getElementById("hudPlay").textContent = on ? "❚❚" : "▶";
  document.getElementById("playBtn").classList.toggle("playing", on);
  if (playTimer) {{ clearInterval(playTimer); playTimer = null; }}
  if (!on) return;
  const ms = +document.getElementById("playSpeed").value || 750;
  playTimer = setInterval(() => setLead((+document.getElementById("leadSlider").value + 1) % frames.length), ms);
}}

const PRODUCT_LAYER_IDS = ["lyE2","lyE2Tot","lyDepth","lyDepthTot","lySusc","lyBuilt","lyInfra"];
const CONTEXT_LAYER_IDS = ["lyHot","ly311","lySta","lyRoads","lyFema","lyNwm","lyGauges","lyDrainE","lyDrainN"];
const LAYER_IDS = PRODUCT_LAYER_IDS.concat(CONTEXT_LAYER_IDS);
function setLayerChecks(onIds, {{ onlyProduct=true }} = {{}}) {{
  const ids = onlyProduct ? PRODUCT_LAYER_IDS : LAYER_IDS;
  ids.forEach(id => {{
    const el = document.getElementById(id);
    if (!el || el.disabled) return;
    const want = onIds.includes(id);
    if (el.checked !== want) {{ el.checked = want; el.dispatchEvent(new Event("change")); }}
  }});
}}

function applyProductMode(mode) {{
  productMode = mode;
  ["productStorm","productSusc","productCoupled","productDepth"].forEach(id => {{
    const el = document.getElementById(id);
    if (el) el.classList.toggle("active", el.dataset.mode === mode);
  }});
  // Never dim Weather / Landscape×Infra / Exposure — those chips are not locks on the layer checklist.
  ["chainPrecip","chainSusc","chainInfra"].forEach(id => {{
    const el = document.getElementById(id);
    if (el) el.classList.remove("dim");
  }});
  const bar = document.getElementById("hudLegendBar");
  const legend = document.getElementById("hudLegendLabel");
  bar.classList.remove("susc", "depth");
  // Only toggle product rasters/infra-sync — never wipe Roads/311/FEMA/context checkboxes.
  if (mode === "susceptibility") {{
    bar.classList.add("susc"); legend.textContent = "Susceptibility (screening)";
    document.getElementById("modeHint").textContent = "Susceptibility defaults on. Full layer checklist (roads/311/FEMA…) stays usable.";
    setLayerChecks(["lySusc"]); setPlaying(false);
  }} else if (mode === "coupled") {{
    legend.textContent = "Precip (mm)";
    document.getElementById("modeHint").textContent = "Coupled defaults: precip + susceptibility + storm-synced roads. All other layers stay independently toggleable.";
    setLayerChecks(["lyE2","lySusc","lyInfra","lySta"]);
  }} else if (mode === "depth") {{
    bar.classList.add("depth"); legend.textContent = "Est. depth (m) — research prototype";
    document.getElementById("modeHint").textContent = "Depth defaults on (research prototype, NOT NWS). Roads/311/FEMA and all layers stay usable.";
    setLayerChecks(["lyDepth","lyDepthTot"]); setPlaying(false);
  }} else {{
    legend.textContent = (activePath && activePath.precip && activePath.precip.colorbar && activePath.precip.colorbar.label) || "Precip (mm)";
    document.getElementById("modeHint").textContent = "Storm defaults to precip only. Landscape×Infra/Exposure chips stay lit — use the Layers checklist any time.";
    setLayerChecks(["lyE2"]);
  }}
  updateAlerts();
  setLead(+document.getElementById("leadSlider").value);
}}

function fitExtent() {{ mapLeft.fitBounds(currentBounds()); writeUrl(); }}
function writeUrl() {{
  const params = new URLSearchParams({{
    event: eventSel.value, extent: extentSel.value, lead: document.getElementById("leadSlider").value,
    path: activePath.id, product: productMode, playing: playing ? "1" : "0",
    opP: document.getElementById("opPrecip").value, opS: document.getElementById("opSusc").value,
    resample: document.getElementById("resampleSelect").value,
    layers: LAYER_IDS.filter(id => document.getElementById(id).checked).join(",")
  }});
  history.replaceState(null, "", "#" + params.toString());
}}
function readUrl() {{
  const raw = location.hash.replace(/^#/, "");
  if (!raw) return {{}};
  const p = new URLSearchParams(raw);
  if (p.get("event")) eventSel.value = p.get("event");
  if (p.get("extent")) extentSel.value = p.get("extent");
  if (p.get("path") && stormPaths.some(sp => sp.id === p.get("path"))) pathSel.value = p.get("path");
  if (p.get("lead") != null) document.getElementById("leadSlider").value = p.get("lead");
  if (p.get("opP")) document.getElementById("opPrecip").value = p.get("opP");
  if (p.get("opS")) document.getElementById("opSusc").value = p.get("opS");
  if (p.get("resample")) document.getElementById("resampleSelect").value = p.get("resample");
  const layers = (p.get("layers") || "").split(",");
  if (layers[0]) LAYER_IDS.forEach(id => {{ const el = document.getElementById(id); if (el) el.checked = layers.includes(id); }});
  return {{ product: p.get("product"), playing: p.get("playing") === "1", hasLayers: Boolean(layers[0]) }};
}}

(function() {{
  const v = validation || {{}};
  const e2 = v.earth2_storm_total || {{}};
  const r = v.reports_311 || {{}};
  document.getElementById("validationPanel").innerHTML = `
    <div class="metric"><span>Earth2 storm max</span><b>${{e2.max_mm != null ? e2.max_mm.toFixed(1)+" mm" : "n/a"}}</b></div>
    <div class="metric"><span>311 reports</span><b>${{r.n_reports ?? "n/a"}}</b></div>
    <div class="metric"><span>311 above E2 P75</span><b>${{r.fraction_reports_above_earth2_p75 != null ? (100*r.fraction_reports_above_earth2_p75).toFixed(0)+"%" : "n/a"}}</b></div>
    <div style="margin-top:6px;color:var(--muted)">Earth2-primary exploratory validation — not certified skill.</div>`;
}})();

document.getElementById("leadSlider").addEventListener("input", e => {{ setPlaying(false); setLead(+e.target.value); }});
document.getElementById("playBtn").onclick = () => setPlaying(!playing);
document.getElementById("hudPlay").onclick = () => setPlaying(!playing);
document.getElementById("playSpeed").onchange = () => {{ if (playing) setPlaying(true); }};
document.getElementById("productStorm").onclick = () => applyProductMode("storm");
document.getElementById("productSusc").onclick = () => applyProductMode("susceptibility");
document.getElementById("productCoupled").onclick = () => applyProductMode("coupled");
document.getElementById("productDepth").onclick = () => applyProductMode("depth");
document.getElementById("extentSelect").onchange = fitExtent;
document.getElementById("eventSelect").onchange = () => {{ if (!EVENTS[eventSel.value].available) alert("Only Ida is loaded."); writeUrl(); }};
document.getElementById("stormPathSelect").onchange = () => {{
  activePath = stormPaths.find(p => p.id === pathSel.value) || stormPaths[0];
  rebuildPathLayers();
  // Keep current product mode + context toggles; only refresh frames/depth set.
  setLead(+document.getElementById("leadSlider").value);
  updateAlerts();
  writeUrl();
}};
document.getElementById("opPrecip").oninput = () => {{
  document.getElementById("opPrecipVal").textContent = document.getElementById("opPrecip").value + "%";
  if (activeE2) activeE2.setOpacity(precipOpacity());
  if (e2Total) e2Total.setOpacity(precipOpacity());
  writeUrl();
}};
document.getElementById("opSusc").oninput = () => {{
  document.getElementById("opSuscVal").textContent = document.getElementById("opSusc").value + "%";
  if (activeSusc) activeSusc.setOpacity(suscOpacity());
  writeUrl();
}};
document.getElementById("resampleSelect").onchange = () => {{
  const nearest = document.getElementById("resampleSelect").value === "nearest";
  document.querySelectorAll(".leaflet-image-layer").forEach(el => {{ el.style.imageRendering = nearest ? "pixelated" : "auto"; }});
  writeUrl();
}};

function registerVector(layer) {{
  if (layer && !vectorLayers.includes(layer)) vectorLayers.push(layer);
  return layer;
}}
function setCount(id, n, title) {{
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = n != null ? String(n) : "!";
  if (title) el.title = title;
}}
function bindLayer(id, layer, {{ label, n, countId }} = {{}}) {{
  const el = document.getElementById(id);
  if (!el || !layer) return;
  layerRegistry[id] = {{ layer, n: n ?? 0, label: label || id }};
  if (countId) setCount(countId, n, label + " loaded");
  const sync = () => {{
    if (el.checked) {{
      pendingChecked.delete(id);
      layer.addTo(mapLeft);
      if (layer.bringToFront) layer.bringToFront();
    }} else if (mapLeft.hasLayer(layer)) {{
      mapLeft.removeLayer(layer);
    }}
    raiseVectors();
    ensureVectorsVisible();
    writeUrl();
  }};
  if (!el.dataset.bound) {{
    el.dataset.bound = "1";
    el.addEventListener("change", () => {{
      if (el.checked && !layerRegistry[id]) pendingChecked.add(id);
      const meta = layerRegistry[id];
      if (!meta) {{ ensureVectorsVisible(); writeUrl(); return; }}
      sync();
    }});
  }}
  if (el.checked || pendingChecked.has(id)) {{
    el.checked = true;
    sync();
  }}
}}
async function fetchGeoJSON(path) {{
  const bases = [
    assets,
    (() => {{ try {{ return new URL("product_assets/", window.location.href).href; }} catch(e) {{ return null; }} }})(),
    "product_assets/",
    "./product_assets/",
    "../product_assets/",
    "/product_assets/",
  ].filter(Boolean);
  const tried = [];
  let lastErr = null;
  for (const base of bases) {{
    const url = base.endsWith("/") ? base + path : base + "/" + path;
    if (tried.includes(url)) continue;
    tried.push(url);
    try {{
      const r = await fetch(url, {{ cache: "no-cache" }});
      if (!r.ok) {{ lastErr = new Error(url + " → HTTP " + r.status); continue; }}
      const geo = await r.json();
      if (!geo || !Array.isArray(geo.features)) {{ lastErr = new Error(url + " → not a FeatureCollection"); continue; }}
      return {{ geo, url }};
    }} catch (e) {{
      lastErr = e;
    }}
  }}
  throw lastErr || new Error("failed to load " + path + " from " + tried.join(", "));
}}
function loadGeo(path, onOk, countId) {{
  fetchGeoJSON(path).then(({{ geo, url }}) => {{
    try {{
      onOk(geo, url);
    }} catch (e) {{
      console.error("layer build failed", path, e);
      if (countId) setCount(countId, "!", String(e));
      const b = document.getElementById("assetBanner");
      if (b) {{ b.style.display = "block"; b.textContent = "Layer build failed for " + path + ": " + e; }}
    }}
  }}).catch(err => {{
    console.error("layer load failed", path, err);
    if (countId) setCount(countId, "!", String(err));
    const b = document.getElementById("assetBanner");
    if (b) {{
      b.style.display = "block";
      b.innerHTML = "<b>GeoJSON load failed:</b> " + path + " — " + String(err) +
        "<br>Serve <code>figures/</code> over HTTP (repo: <code>python scripts/serve_product.py</code>). Asset base: " + assets;
    }}
  }});
}}

document.getElementById("lyE2").onchange = () => {{
  if (!activeE2) return;
  if (document.getElementById("lyE2").checked) {{ activeE2.setOpacity(precipOpacity()); activeE2.addTo(mapLeft); }}
  else mapLeft.removeLayer(activeE2);
  writeUrl();
}};
document.getElementById("lySusc").onchange = () => {{
  if (!activeSusc) return;
  if (document.getElementById("lySusc").checked) {{ activeSusc.setOpacity(suscOpacity()); activeSusc.addTo(mapLeft); }}
  else mapLeft.removeLayer(activeSusc);
  writeUrl();
}};
document.getElementById("lyInfra").onchange = () => {{ setLead(+document.getElementById("leadSlider").value); ensureVectorsVisible(); }};
document.getElementById("lyE2Tot").onchange = () => {{
  if (!e2Total) return;
  if (document.getElementById("lyE2Tot").checked) {{ e2Total.setOpacity(precipOpacity()); e2Total.addTo(mapLeft); }}
  else mapLeft.removeLayer(e2Total);
  writeUrl();
}};
document.getElementById("lyDepth").onchange = () => {{
  if (!activeDepth) {{ setLead(+document.getElementById("leadSlider").value); return; }}
  if (document.getElementById("lyDepth").checked) {{ activeDepth.setOpacity(depthOpacity()); activeDepth.addTo(mapLeft); }}
  else mapLeft.removeLayer(activeDepth);
  writeUrl();
}};
document.getElementById("lyDepthTot").onchange = () => {{
  if (!depthTotal) return;
  if (document.getElementById("lyDepthTot").checked) {{ depthTotal.setOpacity(depthOpacity()); depthTotal.addTo(mapLeft); }}
  else mapLeft.removeLayer(depthTotal);
  writeUrl();
}};
document.getElementById("opDepth").oninput = () => {{
  document.getElementById("opDepthVal").textContent = document.getElementById("opDepth").value + "%";
  if (activeDepth) activeDepth.setOpacity(depthOpacity());
  if (depthTotal) depthTotal.setOpacity(depthOpacity());
  writeUrl();
}};
bindLayer("lyBuilt", builtLayer, {{ label: "Built", n: builtLayer ? 1 : 0 }});

// High-contrast citywide-visible styles. Canvas for dense roads (SVG can fail/OOM → "err").
loadGeo("fema_nfhl.geojson", geo => {{
  femaLayer = registerVector(L.geoJSON(geo, {{
    pane:"vectorPane", renderer: makeVectorRenderer(),
    style: f => {{
      const sfha=(f.properties&&f.properties.SFHA_TF)==="T";
      return {{ color: sfha?"#1d4ed8":"#93c5fd", weight: sfha?3:2, fillColor: sfha?"#3b82f6":"#bfdbfe", fillOpacity: sfha?0.45:0.2, opacity:1 }};
    }}
  }}));
  bindLayer("lyFema", femaLayer, {{ label:"FEMA", n: geo.features.length, countId:"cntFema" }});
}}, "cntFema");

loadGeo("nwm_high_flow.geojson", geo => {{
  nwmLayer = registerVector(L.geoJSON(geo, {{
    pane:"vectorPane", renderer: makeVectorRenderer(),
    style: {{ color:"#00c2ff", weight:7, opacity:1 }}
  }}));
  bindLayer("lyNwm", nwmLayer, {{ label:"NWM", n: geo.features.length, countId:"cntNwm" }});
}}, "cntNwm");

loadGeo("nwm_ahps_gauges.geojson", geo => {{
  const pr = makePointRenderer();
  gaugesLayer = registerVector(L.geoJSON(geo, {{
    pane:"pointPane", renderer: pr,
    pointToLayer: (f,ll) => L.circleMarker(ll, {{ radius:9, color:"#003d5c", fillColor:"#37d6ff", fillOpacity:1, weight:3, pane:"pointPane", renderer: pr }})
  }}));
  bindLayer("lyGauges", gaugesLayer, {{ label:"Gauges", n: geo.features.length, countId:"cntGauges" }});
}}, "cntGauges");

loadGeo("drainage_conduits.geojson", geo => {{
  drainEdges = registerVector(L.geoJSON(geo, {{
    pane:"vectorPane", renderer: L.canvas({{ pane: "vectorPane", padding: 0.5 }}),
    style: {{ color:"#ffb020", weight:3.5, opacity:1 }}
  }}));
  bindLayer("lyDrainE", drainEdges, {{ label:"Conduits", n: geo.features.length, countId:"cntDrainE" }});
}}, "cntDrainE");

loadGeo("drainage_nodes.geojson", geo => {{
  const pr = makePointRenderer();
  drainNodes = registerVector(L.geoJSON(geo, {{
    pane:"pointPane", renderer: pr,
    pointToLayer: (f,ll) => L.circleMarker(ll, {{ radius:5, color:"#7a4e00", fillColor:"#ffd60a", fillOpacity:1, weight:2, pane:"pointPane", renderer: pr }})
  }}));
  bindLayer("lyDrainN", drainNodes, {{ label:"Nodes", n: geo.features.length, countId:"cntDrainN" }});
}}, "cntDrainN");

loadGeo((manifest.infra?.roads_geojson || "roads.geojson"), geo => {{
  const roadCanvas = L.canvas({{ pane: "vectorPane", padding: 0.5 }});
  roadsLayer = registerVector(L.geoJSON(geo, {{
    pane:"vectorPane", renderer: roadCanvas,
    style: {{ color:"#ff6b00", weight:4, opacity:1, lineCap:"round", lineJoin:"round" }}
  }}));
  bindLayer("lyRoads", roadsLayer, {{ label:"Roads", n: geo.features.length, countId:"cntRoads" }});
}}, "cntRoads");

loadGeo((manifest.disruption?.disrupted_geojson || "roads_potential_disruption.geojson"), geo => {{
  disruptLayer = registerVector(L.geoJSON(geo, {{
    pane:"vectorPane", renderer: makeVectorRenderer(),
    style: {{ color:"#ff2d55", weight:6, opacity:1 }}
  }}));
  bindLayer("lyHot", disruptLayer, {{ label:"Hotspot", n: geo.features.length, countId:"cntHot" }});
}}, "cntHot");

loadGeo((manifest.infra?.stations_geojson || "subway_stations.geojson"), geo => {{
  const pr = makePointRenderer();
  stationsLayer = registerVector(L.geoJSON(geo, {{
    pane:"pointPane", renderer: pr,
    pointToLayer: (f,ll) => L.circleMarker(ll, {{ radius:7, color:"#004d40", fillColor:"#00e5a8", fillOpacity:1, weight:2, pane:"pointPane", renderer: pr }})
  }}));
  bindLayer("lySta", stationsLayer, {{ label:"Stations", n: geo.features.length, countId:"cntSta" }});
}}, "cntSta");

loadGeo((manifest.reports?.geojson || "observed_311.geojson"), geo => {{
  L.geoJSON(geo, {{
    pointToLayer: (f,ll) => L.circleMarker(ll, {{ radius:7, color:"#7f0020", fillColor:"#ff3b5c", fillOpacity:1, weight:2 }}),
    onEachFeature: (f,l) => l.bindTooltip((f.properties.descriptor||"311") + " · " + (f.properties.created_date||""))
  }}).eachLayer(l => reports.addLayer(l));
  registerVector(reports);
  bindLayer("ly311", reports, {{ label:"311", n: geo.features.length, countId:"cnt311" }});
}}, "cnt311");

function updateAlerts() {{
  const panel = document.getElementById("alertPanel");
  if (!panel) return;
  const ds = activeDepthSet || depthSetForPath(activePath && activePath.id);
  const st = ds && ds.storm_total;
  const maxM = st && st.max_m != null ? Number(st.max_m) : null;
  const wet = st && st.wet_fraction != null ? Number(st.wet_fraction) : null;
  const thr = (manifest.flood_warning_prototype && manifest.flood_warning_prototype.thresholds_m) || {{ advisory: 0.03, watch: 0.08, warning: 0.15 }};
  let level = "none", color = "#64748b", label = "No research alert";
  if (maxM != null) {{
    if (maxM >= thr.warning) {{ level = "warning"; color = "#b91c1c"; label = "Research WARNING"; }}
    else if (maxM >= thr.watch) {{ level = "watch"; color = "#c2410c"; label = "Research WATCH"; }}
    else if (maxM >= thr.advisory) {{ level = "advisory"; color = "#a16207"; label = "Research ADVISORY"; }}
  }}
  const force = ds ? (ds.label || ds.id) : "n/a";
  panel.innerHTML = `
    <div class="metric"><span>Prototype level</span><b style="color:${{color}}">${{label}}</b></div>
    <div class="metric"><span>Est. max depth</span><b>${{maxM != null ? maxM.toFixed(3) + " m" : "n/a"}}</b></div>
    <div class="metric"><span>Wet fraction</span><b>${{wet != null ? (100*wet).toFixed(1) + "%" : "n/a"}}</b></div>
    <div class="metric"><span>Depth forcing</span><b style="font-size:.72rem">${{force}}</b></div>
    <div style="margin-top:6px;color:var(--muted);font-size:.72rem;line-height:1.35">
      Thresholds (research): advisory ≥ ${{thr.advisory}} m, watch ≥ ${{thr.watch}} m, warning ≥ ${{thr.warning}} m.
      Derived from bathtub/HAND depth — <b>not NWS criteria</b>, not PySWMM/DEP calibrated sewer response.
    </div>`;
}}

const urlState = readUrl() || {{}};
activePath = stormPaths.find(p => p.id === pathSel.value) || stormPaths[0];
rebuildPathLayers();
document.getElementById("opPrecipVal").textContent = document.getElementById("opPrecip").value + "%";
document.getElementById("opSuscVal").textContent = document.getElementById("opSusc").value + "%";
fitExtent();
if (urlState.product && ["storm","susceptibility","coupled","depth"].includes(urlState.product) && urlState.hasLayers) {{
  productMode = urlState.product;
  ["productStorm","productSusc","productCoupled","productDepth"].forEach(id => {{
    const el = document.getElementById(id); if (el) el.classList.toggle("active", el.dataset.mode === productMode);
  }});
  setLead(+document.getElementById("leadSlider").value);
}} else applyProductMode(urlState.product || "storm");
if (!inundation) {{
  ["lyDepth","lyDepthTot","productDepth"].forEach(id => {{ const el = document.getElementById(id); if (el) el.disabled = true; }});
}}
updateAlerts();
// Default play speed slightly faster for denser loops
const playSpeedEl = document.getElementById("playSpeed");
if (playSpeedEl && (frames.length || 0) >= 12) playSpeedEl.value = "450";
if (urlState.playing) setPlaying(true);
document.querySelectorAll(".leaflet-image-layer").forEach(el => {{
  el.style.imageRendering = (document.getElementById("resampleSelect").value === "nearest") ? "pixelated" : "auto";
}});
</script>
</body>
</html>
"""
    # Fix accidental CSS typo if any
    html = html.replace("--accent-deep:#056 dig 068;", "--accent-deep:#056068;")
    out = FIGURES_DIR / "product_map.html"
    out.write_text(html)
    return out
