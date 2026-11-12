#!/usr/bin/env python3
"""Asset Decision Desk — Ida research replay map HTML.

Demo-locked defaults: assets first, MRMS awareness locked, screening collapsed.
Storm (MRMS) is background awareness. NOT NWS / NOT decision-grade.
"""

from __future__ import annotations

import json
from pathlib import Path

from nyc_flash_flood_case_study.config import FIGURES_DIR
from nyc_flash_flood_case_study.extents import DEFAULT_MAP_EXTENT, EVENTS, EXTENTS

# Curated ≥8 cm named click targets for the 60s demo (facility story is thin; tunnel substitutes).
DEMO_SHORTLIST_IDS = (
    "road:37394898",  # Myrtle Avenue · 10.7 cm
    "stations:146:36th Street",  # 36th Street · 10.2 cm
    "road:5681925",  # Brooklyn–Battery Tunnel · 9.8 cm
)


def write_product_html(manifest: dict, pluvial: dict, validation: dict) -> Path:
    precip = manifest.get("precip", {})
    frames = precip.get("frames", [])
    n = max(len(frames), 1)
    demo_ids_json = json.dumps(list(DEMO_SHORTLIST_IDS))
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Asset Decision Desk · Ida research replay</title>
<meta name="description" content="Research Asset Decision Desk for Hurricane Ida. Ranked wet assets from metro pysheds × MRMS. NOT official NWS. NOT decision-grade.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@500;600;700&family=IBM+Plex+Mono:wght@500&family=Source+Sans+3:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
:root {{
  --ink:#071018; --ink-soft:#152433; --muted:#6a7f90; --paper:#f3f7f9;
  --panel:rgba(255,255,255,.94); --line:#c5d3de; --line-soft:#dde6ed;
  --accent:#0a8a96; --accent-deep:#056068; --accent-soft:#d4eef1;
  --sea:#083b48; --sea-2:#0c6170; --warn:#8d3d14; --warn-bg:#fff3e6; --warn-line:#efc49a;
  --band-3:#a16207; --band-8:#c2410c; --band-15:#b91c1c;
  --shadow:0 18px 50px rgba(7,16,24,.16); --radius:14px;
}}
* {{ box-sizing:border-box; }}
html,body {{ margin:0; height:100%; font-family:"Source Sans 3",sans-serif; color:var(--ink);
  background:
    radial-gradient(900px 520px at 8% -10%, rgba(12,97,112,.18), transparent 55%),
    radial-gradient(800px 480px at 100% 0%, rgba(8,59,72,.10), transparent 45%),
    linear-gradient(165deg, #eef4f7 0%, #d9e5ec 100%); }}
body {{ display:grid; grid-template-columns:minmax(340px,420px) 1fr; min-height:100%; }}
@media (max-width:980px) {{ body {{ grid-template-columns:1fr; grid-template-rows:auto 1fr; }} aside {{ max-height:55vh; border-right:0; border-bottom:1px solid var(--line); }} }}
aside {{
  position:relative; overflow:auto; padding:16px 14px 28px;
  background: linear-gradient(180deg, rgba(255,255,255,.86), rgba(243,247,249,.94));
  border-right:1px solid var(--line); backdrop-filter: blur(10px);
}}
.brand {{
  position:relative; overflow:hidden; margin:0 0 12px; padding:16px 14px 14px; border-radius:18px;
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
.brand-mark {{ font-family:Sora,sans-serif; font-weight:700; font-size:1.4rem; letter-spacing:-.04em; line-height:1.05; }}
.brand-tag {{ margin-top:8px; font-size:.78rem; line-height:1.4; max-width:34ch; opacity:.9; }}
.disclaimer-bar {{
  position:sticky; top:0; z-index:4; margin:0 0 12px; padding:10px 11px; border-radius:var(--radius);
  background:var(--warn-bg); border:1px solid var(--warn-line); color:var(--warn); font-size:.74rem; line-height:1.4;
}}
.panel {{
  background:var(--panel); border:1px solid var(--line-soft); border-radius:16px; padding:12px;
  margin:0 0 10px; box-shadow:0 1px 0 rgba(255,255,255,.85) inset, 0 8px 24px rgba(7,16,24,.03);
}}
.panel h2 {{
  font-family:Sora,sans-serif; font-size:.68rem; font-weight:600; margin:0 0 8px;
  text-transform:uppercase; letter-spacing:.1em; color:var(--muted);
}}
.panel.core {{ border-color:#9ec9d0; box-shadow:0 0 0 1px rgba(10,138,150,.12), 0 10px 28px rgba(7,16,24,.05); }}
.honesty {{ margin-top:8px; padding:8px 9px; border-radius:11px; font-size:.72rem; line-height:1.4; color:#3d5563; background:#f2f6f8; border:1px dashed #b7c7d2; }}
.metric {{ display:flex; justify-content:space-between; gap:8px; font-size:.78rem; padding:7px 9px; border-radius:10px; background:linear-gradient(180deg,#f7fafc,#eef3f6); margin-bottom:5px; }}
.metric b, .readout {{ font:600 .8rem "IBM Plex Mono",monospace; color:#045963; }}
label.caption {{ display:block; font-size:.72rem; color:var(--muted); font-weight:600; margin-bottom:4px; }}
select, input[type=search] {{ width:100%; appearance:none; padding:9px 11px; border-radius:11px; border:1px solid var(--line); background:#fff; font:500 .88rem "Source Sans 3",sans-serif; color:var(--ink); }}
.filters {{ display:grid; grid-template-columns:1fr 1fr; gap:6px; margin:8px 0; }}
.chip-row {{ display:flex; flex-wrap:wrap; gap:5px; margin:6px 0 8px; }}
.chip {{ border:1px solid var(--line); background:#fff; border-radius:999px; padding:5px 10px; font:600 .7rem Sora,sans-serif; color:var(--muted); cursor:pointer; }}
.chip.active {{ background:#d4eef1; border-color:var(--accent); color:#045963; }}
.asset-list {{ display:flex; flex-direction:column; gap:6px; max-height:min(52vh,520px); overflow:auto; padding-right:2px; }}
.asset-row {{
  text-align:left; width:100%; border:1px solid var(--line-soft); background:#fff; border-radius:12px;
  padding:9px 10px; cursor:pointer; transition:border-color .12s, transform .12s, background .12s;
}}
.asset-row:hover {{ transform:translateY(-1px); border-color:#9db4c2; }}
.asset-row.selected {{ border-color:var(--accent); background:linear-gradient(180deg,#f5fcfd,#d9eef1); }}
.asset-row .top {{ display:flex; justify-content:space-between; gap:8px; align-items:baseline; }}
.asset-row .name {{ font:600 .84rem Sora,sans-serif; letter-spacing:-.02em; }}
.asset-row .depth {{ font:600 .78rem "IBM Plex Mono",monospace; color:#045963; white-space:nowrap; }}
.asset-row .meta {{ margin-top:4px; display:flex; flex-wrap:wrap; gap:5px; font-size:.7rem; color:var(--muted); }}
.band {{ display:inline-flex; align-items:center; padding:2px 7px; border-radius:999px; font:600 .66rem Sora,sans-serif; }}
.band.ponding {{ background:#fef3c7; color:var(--band-3); }}
.band.deep_ponding {{ background:#ffedd5; color:var(--band-8); }}
.band.hazard {{ background:#fee2e2; color:var(--band-15); }}
.type-pill {{ display:inline-flex; padding:2px 7px; border-radius:999px; background:#eef3f6; font-weight:600; }}
.legend-swatch {{ height:8px; border-radius:999px; margin:4px 0 8px; }}
.legend-swatch.precip {{ background:linear-gradient(90deg,#30123b,#4662d8,#1ae4b6,#a2fc3c,#f9ba38,#e8332b); }}
.legend-swatch.susc {{ background:linear-gradient(90deg,#fff7bc,#fec44f,#d95f0e,#7f2704); }}
.legend-swatch.depth {{ background:linear-gradient(90deg,#f7fbff,#c6dbef,#6baed6,#2171b5,#08306b); }}
.opacity-row {{ display:grid; grid-template-columns:92px 1fr 40px; gap:8px; align-items:center; font-size:.76rem; margin:6px 0; }}
.layer-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:6px; }}
.group-label {{ grid-column:1 / -1; margin:4px 0 0; font-size:.66rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:#7d91a1; }}
.layer-btn {{ position:relative; display:flex; align-items:center; gap:7px; min-height:38px; padding:7px 9px 7px 30px; border-radius:11px; border:1px solid var(--line); background:#fff; cursor:pointer; font-size:.74rem; font-weight:600; }}
.layer-btn input {{ position:absolute; left:9px; top:50%; transform:translateY(-50%); margin:0; accent-color:var(--accent); }}
.layer-btn:has(input:checked) {{ background:linear-gradient(180deg,#f5fcfd,#d9eef1); border-color:var(--accent); color:#045963; }}
details.advanced {{ font-size:.76rem; color:var(--muted); }}
details.advanced > summary {{ cursor:pointer; font:700 .72rem Sora,sans-serif; letter-spacing:.06em; text-transform:uppercase; color:var(--ink-soft); margin-bottom:8px; list-style:none; }}
details.advanced > summary::-webkit-details-marker {{ display:none; }}
details.about {{ font-size:.74rem; color:var(--muted); line-height:1.45; }}
details.about summary {{ cursor:pointer; font-weight:700; color:var(--ink-soft); margin-bottom:6px; }}
.map-stage {{ position:relative; min-height:0; height:100%; }}
.map-el {{ position:absolute; inset:0; }}
.pane-label {{
  position:absolute; z-index:1000; top:14px; left:54px; padding:6px 12px; border-radius:999px;
  background:rgba(7,20,28,.82); color:#e8f4f6; border:1px solid rgba(255,255,255,.1);
  font:600 .72rem Sora,sans-serif; backdrop-filter:blur(8px);
}}
.footer-note {{
  position:absolute; z-index:1000; left:14px; bottom:98px; max-width:min(420px,88%);
  background:rgba(255,255,255,.92); border:1px solid var(--line); padding:8px 10px;
  font-size:.7rem; color:var(--muted); border-radius:11px;
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
}}
.radar-hud .clock {{ font:700 1rem Sora,sans-serif; letter-spacing:-.02em; }}
.radar-hud .sub {{ font-size:.72rem; opacity:.78; margin-top:2px; }}
.radar-hud .legend {{ display:flex; flex-direction:column; gap:5px; align-items:flex-end; font-size:.68rem; opacity:.92; }}
.radar-hud .bar {{ width:128px; height:8px; border-radius:999px; background:linear-gradient(90deg,#30123b,#4662d8,#1ae4b6,#a2fc3c,#f9ba38,#e8332b); }}
.radar-hud .bar.susc {{ background:linear-gradient(90deg,#fff7bc,#fec44f,#d95f0e,#7f2704); }}
.selected-card {{
  position:absolute; z-index:1050; top:56px; right:14px; width:min(320px,calc(100% - 28px));
  background:rgba(255,255,255,.95); border:1px solid var(--line); border-radius:14px; padding:12px;
  box-shadow:var(--shadow); display:none;
}}
.selected-card.on {{ display:block; }}
.selected-card h3 {{ margin:0 0 6px; font:700 .95rem Sora,sans-serif; }}
.selected-card p {{ margin:0; font-size:.78rem; color:var(--muted); line-height:1.4; }}
.empty {{ padding:14px; text-align:center; color:var(--muted); font-size:.8rem; }}
/* Soft radar-style overlays — continuous metro, no hard crop box */
.leaflet-image-layer.precip-radar,
.leaflet-image-layer.depth-radar,
.leaflet-image-layer.susc-radar {{
  -webkit-mask-image: radial-gradient(ellipse 92% 88% at 50% 50%, #000 58%, transparent 100%);
  mask-image: radial-gradient(ellipse 92% 88% at 50% 50%, #000 58%, transparent 100%);
  image-rendering: auto;
  filter: saturate(1.08) contrast(1.04);
}}
.leaflet-image-layer.precip-radar {{ mix-blend-mode: screen; }}
</style>
</head>
<body>
<aside>
  <div class="brand">
    <div class="brand-kicker">Flood risk · research prototype</div>
    <div class="brand-mark">Asset Decision Desk</div>
    <div class="brand-tag">Which roads / stations get wet under Ida — ranked assets first. Research case study only.</div>
  </div>
  <div class="disclaimer-bar">
    <b>NOT decision-grade. NOT an official NWS flood warning. NOT emergency guidance.</b>
    Research depths are cm-scale HAND heuristics — not Ida street depths; sewer = open capacity proxy, not DEP.
  </div>
  <div id="assetBanner" class="disclaimer-bar" style="display:none;background:#3b0d0d;border-color:#7f1d1d;color:#fecaca"></div>

  <div class="panel core">
    <h2>Affected assets</h2>
    <div class="honesty" style="margin-top:0">Ranked wet assets from <b>metro pysheds × spatial MRMS QPE</b>. Demo shortlist first — click a row to fly to it.</div>
    <div id="deskSummary" class="metric"><span>Loading…</span><b>—</b></div>
    <div class="chip-row" id="listModeChips" role="group" aria-label="List mode" style="margin-bottom:2px">
      <button type="button" class="chip active" data-mode="shortlist">Demo shortlist</button>
      <button type="button" class="chip" data-mode="all">Show all</button>
    </div>
    <div class="chip-row" id="typeChips" role="group" aria-label="Asset type">
      <button type="button" class="chip active" data-type="all">All</button>
      <button type="button" class="chip" data-type="road">Roads</button>
      <button type="button" class="chip" data-type="station">Stations</button>
      <button type="button" class="chip" data-type="facility">Facilities</button>
    </div>
    <div class="filters">
      <div>
        <label class="caption" for="bandFilter">Research depth band</label>
        <select id="bandFilter">
          <option value="all">All wet (≥3 cm)</option>
          <option value="ponding">≥3 cm ponding</option>
          <option value="deep_ponding" selected>≥8 cm deep ponding</option>
          <option value="hazard">≥15 cm hazard</option>
        </select>
      </div>
      <div>
        <label class="caption" for="assetSearch">Search</label>
        <input id="assetSearch" type="search" placeholder="Name / id…" autocomplete="off">
      </div>
    </div>
    <div class="asset-list" id="assetList" aria-label="Ranked wet assets"><div class="empty">Loading ranked assets…</div></div>
  </div>

  <div class="panel">
    <h2>Storm + primary depth</h2>
    <div class="honesty" style="margin-top:0">Primary: <b>pysheds metro</b> · Alt: SFINCS (Advanced). Storm path locked to <b>MRMS QPE Ida</b>.</div>
    <div class="metric"><span>Storm path</span><b style="font-size:.68rem">MRMS QPE Ida (~1 km)</b></div>
    <div class="metric" id="timeWindowMetric"><span>Time window</span><b style="font-size:.62rem" id="timeWindowVal">+6…+24h</b></div>
    <label class="layer-btn"><input id="lyDepthTot" type="checkbox" checked>Primary research depth (evolves w/ loop)</label>
    <label class="layer-btn"><input id="lyE2" type="checkbox" checked>MRMS precip loop (soft metro)</label>
    <div class="opacity-row"><span>Precip</span><input id="opPrecip" type="range" min="10" max="85" value="34"><span id="opPrecipVal">34%</span></div>
    <div class="opacity-row"><span>Est. depth</span><input id="opDepth" type="range" min="15" max="90" value="68"><span id="opDepthVal">68%</span></div>
    <div class="legend-swatch precip"></div>
    <div class="legend-swatch depth"></div>
    <div class="honesty" id="depthTimelineNote">Depth follows nearest cum lead (0…36h / 3h steps) — buildup then post-peak recession. HAND puddles are heuristic, not street-truth.</div>
    <div class="honesty" id="pathHonesty" style="display:none">Primary Ida awareness: MRMS QPE (~1 km).</div>
  </div>

  <div class="panel">
    <details class="advanced" id="screeningDetails">
      <summary>Screening (optional)</summary>
      <div class="honesty" style="margin-top:0">Uncalibrated screening — weather factor evolves with precip; landscape/infra are mostly static. Not flood probability / not depth.</div>
      <div class="opacity-row"><span>Susceptibility</span><input id="opSusc" type="range" min="10" max="90" value="48"><span id="opSuscVal">48%</span></div>
      <div class="legend-swatch susc"></div>
      <label class="layer-btn" style="margin-top:4px"><input id="lySusc" type="checkbox">Show susceptibility screening</label>
    </details>
  </div>

  <div class="panel">
    <details class="advanced">
      <summary>Advanced / context layers</summary>
      <div class="honesty" style="margin-top:0;margin-bottom:8px">Research chrome only — Earth2 scenarios, SFINCS, FEMA/NWM/gauges, validation. Keep closed for demos.</div>
      <div class="filters" style="grid-template-columns:1fr 1fr">
        <div><label class="caption" for="extentSelect">Extent</label><select id="extentSelect"></select></div>
        <div><label class="caption" for="eventSelect">Event</label><select id="eventSelect"></select></div>
      </div>
      <label class="caption" for="stormPathSelect" style="margin-top:8px">Scenario path (Advanced)</label>
      <select id="stormPathSelect" aria-label="Scenario path"></select>
      <div class="layer-grid" style="margin-top:8px">
        <div class="group-label">Alternate hydro / scenario</div>
        <label class="layer-btn"><input id="lySfincs" type="checkbox">Queens SFINCS (labeled alternate)</label>
        <label class="layer-btn"><input id="lyE2Tot" type="checkbox">Storm-total precip</label>
        <div class="group-label">Exposure / obs</div>
        <label class="layer-btn"><input id="lySta" type="checkbox">All stations</label>
        <label class="layer-btn"><input id="lyRoads" type="checkbox">All roads</label>
        <label class="layer-btn"><input id="lyFac" type="checkbox">All facilities</label>
        <label class="layer-btn"><input id="ly311" type="checkbox">311 reports</label>
        <label class="layer-btn"><input id="lyFloodNet" type="checkbox">FloodNet Ida posts (hotspot cal)</label>
        <div class="group-label">Reference context</div>
        <label class="layer-btn"><input id="lyFema" type="checkbox">FEMA NFHL</label>
        <label class="layer-btn"><input id="lyNwm" type="checkbox">NWM reaches</label>
        <label class="layer-btn"><input id="lyGauges" type="checkbox">AHPS gauges</label>
        <label class="layer-btn"><input id="lyBuilt" type="checkbox">Built surface</label>
      </div>
      <div id="validationPanel" class="honesty" style="margin-top:8px">Limitations-first: exploratory collocation only — not certified skill; do not lead with hit-rate.</div>
    </details>
  </div>

  <div class="panel">
    <details class="about">
      <summary>Science notes</summary>
      <p>
        <b>Product</b> = Asset Decision Desk for infrastructure/response <i>research</i> screening.<br>
        <b>Primary depth</b> = unified pysheds HAND/bathtub on metro DEM × spatial MRMS QPE Ida after open drainage capacity proxy (NLCD + metro open catch-basin / inlet density + literature mm/hr sink with surcharge; soft land mask). NOT DEP sewer model / NOT SWMM — cells without inlet credit use NLCD base only.<br>
        <b>FloodNet Ida reproduction</b> = separate transparent hotspot hydro (runoff × excess precip + fitted scale/bias at the sparse 2021 posts). Does <i>not</i> rescale citywide HAND. First-step peak OOM at sensors only — residual error documented; not citywide perfection.<br>
        <b>Map + data domain</b> = metro continuous soft-edge overlays (no hard citywide crop); SFINCS Queens remains alternate hydro track under Advanced (shared excess-rate sink when rebuilt; not a peer depth toggle).<br>
        <b>Time window</b> = Ida MRMS native hourly +0h…+36h from 2021-09-01T12:00 UTC (valid 12:00 Sep 1 → 00:00 Sep 3). Depth cum every 3h with buildup + recession.<br>
        <b>Bands</b> = research ≥3 / ≥8 / ≥15 cm — not NWS watch/warning language. 10&nbsp;m HAND nest is a documented experiment only — product default stays ~30&nbsp;m metro HAND.<br>
        <b>Cannot claim</b> = official NWS warning, calibrated DEP sewer / SWMM, decision-grade guidance, Enterprise/HENS.
      </p>
    </details>
  </div>
</aside>

<div class="map-stage" id="mapStage">
  <div class="pane-label" id="leftLabel">Asset Decision Desk · Ida research</div>
  <div id="mapLeft" class="map-el"></div>
  <div class="selected-card" id="selectedCard">
    <h3 id="selName">—</h3>
    <p id="selBody">—</p>
  </div>
  <div class="footer-note">Research prototype — NOT NWS / NOT decision-grade. Metro pysheds × MRMS primary; SFINCS only under Advanced.</div>
  <div class="radar-hud">
    <button type="button" class="play" id="hudPlay">▶</button>
    <div>
      <div class="clock" id="hudClock">—</div>
      <div class="sub" id="hudSub">MRMS soft metro · +0…+36h native · not NEXRAD</div>
    </div>
    <div class="legend">
      <span id="hudLegendLabel">Precip (mm) · context</span>
      <div class="bar" id="hudLegendBar"></div>
    </div>
  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const EVENTS = {json.dumps(EVENTS)};
const EXTENTS = {json.dumps(EXTENTS)};
const manifest = {json.dumps(manifest)};
const pluvial = {json.dumps(pluvial)};
const validation = {json.dumps(validation)};

function resolveAssetBase() {{
  const here = window.location.href;
  if (here.startsWith("file:")) {{
    const b = document.getElementById("assetBanner");
    if (b) {{
      b.style.display = "block";
      b.innerHTML = "<b>Open via local HTTP</b> — from repo: <code>python scripts/serve_product.py</code> then open the printed URL.";
    }}
  }}
  try {{ return new URL("product_assets/", here).href; }}
  catch (e) {{ return "product_assets/"; }}
}}
const assets = resolveAssetBase();

const mapLeft = L.map("mapLeft", {{ zoomControl: true }});
window.mapLeft = mapLeft;
mapLeft.createPane("rasterPane"); mapLeft.getPane("rasterPane").style.zIndex = 350;
mapLeft.createPane("depthPane"); mapLeft.getPane("depthPane").style.zIndex = 400;
mapLeft.createPane("vectorPane"); mapLeft.getPane("vectorPane").style.zIndex = 650;
mapLeft.createPane("pointPane"); mapLeft.getPane("pointPane").style.zIndex = 670;
mapLeft.createPane("selectPane"); mapLeft.getPane("selectPane").style.zIndex = 700;
L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}", {{
  maxZoom: 19, attribution: "Tiles © Esri"
}}).addTo(mapLeft);

const DEMO_SHORTLIST = {demo_ids_json};
const eventSel = document.getElementById("eventSelect");
Object.values(EVENTS).forEach(ev => {{
  if (!ev.available) return; // hide placeholder-future during demos
  const opt = document.createElement("option");
  opt.value = ev.id; opt.textContent = ev.label;
  eventSel.appendChild(opt);
}});
eventSel.value = "ida-2021";
const extentSel = document.getElementById("extentSelect");
Object.values(EXTENTS).forEach(ex => {{
  const opt = document.createElement("option"); opt.value = ex.id; opt.textContent = ex.label; extentSel.appendChild(opt);
}});
extentSel.value = (manifest.layer_bounds && manifest.layer_bounds.map_extent_default) || "{DEFAULT_MAP_EXTENT}";

const stormPaths = manifest.storm_paths || [{{
  id: "mrms_qpe_ida", label: "MRMS QPE Ida", primary: true,
  precip: manifest.precip, susceptibility: manifest.susceptibility
}}];
const pathSel = document.getElementById("stormPathSelect");
stormPaths.forEach(p => {{
  const opt = document.createElement("option");
  const isMrms = p.id === "mrms_qpe_ida" || p.ida_primary_viz;
  opt.value = p.id;
  opt.textContent = p.label + (isMrms ? " · locked primary" : " · AI scenario");
  pathSel.appendChild(opt);
}});
// Demo-locked default: MRMS; Earth2 only via Advanced scenario path
pathSel.value = "mrms_qpe_ida";

function currentBounds() {{
  const b = (EXTENTS[extentSel.value] || EXTENTS.metro || EXTENTS.citywide).bounds;
  return [[b.ymin, b.xmin],[b.ymax, b.xmax]];
}}
/** Native georef for data overlays — metro after DEM/MRMS rebuild; soft land mask (no painted box). */
function dataDomainBounds() {{
  const fromMeta = (manifest.inundation && manifest.inundation.bounds)
    || (manifest.inundation_citywide && manifest.inundation_citywide.bounds)
    || (manifest.layer_bounds && manifest.layer_bounds.data_domain_bounds);
  if (fromMeta) return fromMeta;
  const b = (EXTENTS.metro || EXTENTS.citywide).bounds;
  return [[b.ymin, b.xmin],[b.ymax, b.xmax]];
}}
function fitMapFrame() {{
  mapLeft.fitBounds(currentBounds(), {{ padding: [28, 28], maxZoom: 11, animate: false }});
}}
function precipOpacity() {{ return (+document.getElementById("opPrecip").value) / 100; }}
function suscOpacity() {{ return (+document.getElementById("opSusc").value) / 100; }}
function depthOpacity() {{ return (+document.getElementById("opDepth").value) / 100; }}

let activePath = stormPaths.find(p => p.id === pathSel.value) || stormPaths[0];
let frames = [], suscFrames = [], depthCumFrames = [], e2Layers = [], suscLayers = [], depthLayers = [];
let activeE2 = null, activeSusc = null, activeDepth = null, e2Total = null, depthTotal = null, sfincsLayer = null;
let playing = false, playTimer = null;
let desk = null, wetLayer = null, selectedLayer = null, selectedId = null;
let typeFilter = "all";
let listMode = "shortlist";

function depthSetForPath(pathId) {{
  const inundation = manifest.inundation || null;
  if (!inundation) return null;
  const by = inundation.by_path || {{}};
  if (pathId && by[pathId]) return by[pathId];
  if (pathId && String(pathId).startsWith("earth2") && by.earth2_control) return by.earth2_control;
  if (by[inundation.default_depth_path]) return by[inundation.default_depth_path];
  return inundation;
}}

function overlayBoundsPreferMetro(explicit) {{
  if (explicit) return explicit;
  return dataDomainBounds();
}}

function nearestDepthIndex(leadHours) {{
  if (!depthCumFrames.length) return -1;
  let best = 0, bestAbs = Infinity;
  depthCumFrames.forEach((fr, idx) => {{
    const d = Math.abs((fr.lead_hours || 0) - leadHours);
    if (d < bestAbs) {{ bestAbs = d; best = idx; }}
  }});
  return best;
}}

function syncTimeWindowLabel() {{
  const tw = (activePath.precip && activePath.precip.time_window)
    || manifest.time_window
    || null;
  const el = document.getElementById("timeWindowVal");
  if (!el) return;
  if (tw && tw.first_valid_time_utc && tw.last_valid_time_utc) {{
    el.textContent = "+" + tw.lead_hours_min + "…" + tw.lead_hours_max + "h · " +
      String(tw.first_valid_time_utc).replace("T"," ") + "→" + String(tw.last_valid_time_utc).slice(11);
  }} else if (frames.length) {{
    el.textContent = "+" + frames[0].lead_hours + "…" + frames[frames.length-1].lead_hours + "h";
  }} else {{
    el.textContent = "+6…+24h";
  }}
}}

function rebuildPathLayers() {{
  e2Layers.forEach(l => mapLeft.removeLayer(l));
  suscLayers.forEach(l => mapLeft.removeLayer(l));
  depthLayers.forEach(l => mapLeft.removeLayer(l));
  if (e2Total) mapLeft.removeLayer(e2Total);
  if (depthTotal && mapLeft.hasLayer(depthTotal)) mapLeft.removeLayer(depthTotal);
  frames = activePath.precip?.frames || [];
  suscFrames = activePath.susceptibility?.frames || [];
  const precipBounds = overlayBoundsPreferMetro(activePath.precip && activePath.precip.bounds);
  const suscBounds = overlayBoundsPreferMetro((activePath.susceptibility && activePath.susceptibility.bounds) || precipBounds);
  e2Layers = frames.map(f => L.imageOverlay(assets + f.png, precipBounds, {{
    opacity: precipOpacity(), interactive:false, pane:"rasterPane", className:"precip-radar"
  }}));
  suscLayers = suscFrames.map(f => L.imageOverlay(assets + f.png, suscBounds, {{
    opacity: suscOpacity(), interactive:false, pane:"rasterPane", className:"susc-radar"
  }}));
  e2Total = activePath.precip?.storm_total_png
    ? L.imageOverlay(assets + activePath.precip.storm_total_png, precipBounds, {{
        opacity: precipOpacity(), pane:"rasterPane", interactive:false, className:"precip-radar"
      }})
    : null;
  const ds = depthSetForPath(activePath.id);
  const depthBounds = overlayBoundsPreferMetro((ds && ds.bounds) || precipBounds);
  depthCumFrames = (ds && ds.cumulative_frames) ? ds.cumulative_frames.slice() : [];
  depthLayers = depthCumFrames.map(fr => L.imageOverlay(assets + fr.png, depthBounds, {{
    opacity: depthOpacity(), interactive:false, pane:"depthPane", className:"depth-radar"
  }}));
  depthTotal = (ds && ds.storm_total && ds.storm_total.png)
    ? L.imageOverlay(assets + ds.storm_total.png, depthBounds, {{
        opacity: depthOpacity(), interactive:false, pane:"depthPane", className:"depth-radar"
      }})
    : (manifest.inundation_citywide && manifest.inundation_citywide.png)
      ? L.imageOverlay(assets + manifest.inundation_citywide.png, dataDomainBounds(), {{
          opacity: depthOpacity(), interactive:false, pane:"depthPane", className:"depth-radar"
        }})
      : null;
  if (manifest.inundation_sfincs && manifest.inundation_sfincs.png) {{
    const b = EXTENTS.south_queens?.bounds || EXTENTS.citywide.bounds;
    sfincsLayer = L.imageOverlay(assets + manifest.inundation_sfincs.png, [[b.ymin,b.xmin],[b.ymax,b.xmax]], {{
      opacity: Math.min(depthOpacity(), 0.55), interactive:false, pane:"depthPane"
    }});
  }}
  document.getElementById("pathHonesty").textContent = activePath.primary || activePath.ida_primary_viz
    ? "Primary Ida awareness: soft-edge metro MRMS MultiSensor QPE (~1 km), native hourly 0–36h — not NEXRAD tiles."
    : (activePath.honesty || "Labeled AI / alternate scenario — coarse cells; not the decision surface.");
  const note = document.getElementById("depthTimelineNote");
  if (note) {{
    note.textContent = depthCumFrames.length
      ? ("Depth follows nearest cum lead (" + depthCumFrames.map(f => "+" + f.lead_hours + "h").join("/") +
         ") — buildup then post-peak recession. HAND puddles are heuristic, not street-truth.")
      : "Depth is storm-total only on this path (no cum frames) — label as static if it does not change with the loop.";
  }}
  syncTimeWindowLabel();
  // Prefer bilinear-ish for MRMS awareness; keep Earth2 pixelated if selected
  const nearest = !(activePath.ida_primary_viz || activePath.id === "mrms_qpe_ida");
  document.querySelectorAll(".leaflet-image-layer").forEach(el => {{
    el.style.imageRendering = nearest ? "pixelated" : "auto";
  }});
}}

function setLead(i) {{
  if (!frames.length) return;
  i = Math.max(0, Math.min(frames.length - 1, i));
  const f = frames[i];
  if (activeE2 && mapLeft.hasLayer(activeE2)) mapLeft.removeLayer(activeE2);
  activeE2 = e2Layers[i];
  if (document.getElementById("lyE2").checked && activeE2) {{
    activeE2.setOpacity(precipOpacity()); activeE2.addTo(mapLeft);
  }}
  if (activeSusc && mapLeft.hasLayer(activeSusc)) mapLeft.removeLayer(activeSusc);
  if (suscLayers[i]) {{
    activeSusc = suscLayers[i];
    if (document.getElementById("lySusc").checked) {{
      activeSusc.setOpacity(suscOpacity()); activeSusc.addTo(mapLeft);
    }}
  }}
  if (activeDepth && mapLeft.hasLayer(activeDepth)) mapLeft.removeLayer(activeDepth);
  if (depthTotal && mapLeft.hasLayer(depthTotal)) mapLeft.removeLayer(depthTotal);
  const di = nearestDepthIndex(f.lead_hours);
  activeDepth = (di >= 0 && depthLayers[di]) ? depthLayers[di] : depthTotal;
  if (document.getElementById("lyDepthTot").checked && activeDepth) {{
    activeDepth.setOpacity(depthOpacity());
    activeDepth.addTo(mapLeft);
  }}
  if (document.getElementById("lySfincs").checked && sfincsLayer) {{
    if (!mapLeft.hasLayer(sfincsLayer)) sfincsLayer.addTo(mapLeft);
  }}
  if (document.getElementById("lyE2Tot").checked && e2Total) {{
    e2Total.setOpacity(precipOpacity());
    if (!mapLeft.hasLayer(e2Total)) e2Total.addTo(mapLeft);
  }}
  const clock = (f.valid_time || "").replace("T", " ");
  document.getElementById("hudClock").textContent = clock + " UTC";
  const depthLead = (di >= 0 && depthCumFrames[di]) ? depthCumFrames[di].lead_hours : null;
  const depthBit = depthLead != null
    ? (" · depth cum +" + depthLead + "h")
    : (depthTotal ? " · depth storm-total (static)" : "");
  document.getElementById("hudSub").textContent =
    activePath.label + " · +" + f.lead_hours + "h · " + (f.temporal_blend ? "blend" : "native") +
    depthBit + " · awareness only";
  document.getElementById("leftLabel").textContent = "Asset Decision Desk · " + (activePath.label || "Ida");
}}

function setPlaying(on) {{
  playing = on;
  document.getElementById("hudPlay").textContent = on ? "❚❚" : "▶";
  if (playTimer) {{ clearInterval(playTimer); playTimer = null; }}
  if (!on || !frames.length) return;
  let i = 0;
  playTimer = setInterval(() => {{
    i = (i + 1) % frames.length;
    setLead(i);
  }}, 450);
}}

function bandClass(band) {{ return band || "ponding"; }}
function leadLabel(a) {{
  if (a.first_exceedance_lead_h != null) return "band @ +" + a.first_exceedance_lead_h + "h";
  if (a.first_exceedance_note) return "storm-total / late";
  return "lead n/a";
}}
function typeLabel(t) {{
  if (t === "road") return "Road";
  if (t === "station") return "Station";
  if (t === "facility") return "Facility";
  return t;
}}
function filteredAssets() {{
  if (!desk || !desk.assets) return [];
  const q = (document.getElementById("assetSearch").value || "").trim().toLowerCase();
  const band = document.getElementById("bandFilter").value;
  let rows = desk.assets.filter(a => {{
    if (typeFilter !== "all" && a.asset_type !== typeFilter) return false;
    if (band !== "all" && a.band !== band) return false;
    if (q && !(String(a.name).toLowerCase().includes(q) || String(a.id).toLowerCase().includes(q))) return false;
    return true;
  }});
  if (listMode === "shortlist" && !q) {{
    const byId = Object.fromEntries(rows.map(a => [a.id, a]));
    const curated = DEMO_SHORTLIST.map(id => byId[id] || (desk.assets || []).find(a => a.id === id)).filter(Boolean);
    if (curated.length) return curated;
  }}
  return rows;
}}
function renderAssetList() {{
  const list = document.getElementById("assetList");
  const rows = filteredAssets().slice(0, listMode === "shortlist" ? 12 : 120);
  if (!rows.length) {{
    list.innerHTML = '<div class="empty">No wet assets match these filters.</div>';
    return;
  }}
  list.innerHTML = rows.map(a => `
    <button type="button" class="asset-row${{selectedId === a.id ? " selected" : ""}}" data-id="${{a.id}}">
      <div class="top">
        <span class="name">#${{a.rank}} · ${{a.name}}</span>
        <span class="depth">${{a.max_depth_cm.toFixed(1)}} cm</span>
      </div>
      <div class="meta">
        <span class="type-pill">${{typeLabel(a.asset_type)}}</span>
        <span class="band ${{bandClass(a.band)}}">${{a.band_label}}</span>
        <span>${{leadLabel(a)}}</span>
      </div>
    </button>`).join("");
  list.querySelectorAll(".asset-row").forEach(btn => {{
    btn.addEventListener("click", () => selectAsset(btn.dataset.id));
  }});
}}
function selectAsset(id) {{
  selectedId = id;
  const a = (desk.assets || []).find(x => x.id === id);
  if (!a) return;
  renderAssetList();
  if (selectedLayer) {{ mapLeft.removeLayer(selectedLayer); selectedLayer = null; }}
  const ll = [a.lat, a.lon];
  mapLeft.flyTo(ll, Math.max(mapLeft.getZoom(), 14), {{ duration: 0.7 }});
  // Prefer geometry from wet layer if present
  let geomLayer = null;
  if (wetLayer) {{
    wetLayer.eachLayer(l => {{
      if (l.feature && l.feature.properties && l.feature.properties.id === id) geomLayer = l;
    }});
  }}
  if (geomLayer && geomLayer.feature && geomLayer.feature.geometry && geomLayer.feature.geometry.type !== "Point") {{
    selectedLayer = L.geoJSON(geomLayer.feature, {{
      pane: "selectPane",
      style: {{ color:"#045963", weight:7, opacity:1 }}
    }}).addTo(mapLeft);
  }} else {{
    selectedLayer = L.circleMarker(ll, {{
      pane: "selectPane", radius: 11, color:"#042227", weight:3,
      fillColor:"#1bc0cd", fillOpacity:0.95
    }}).addTo(mapLeft);
  }}
  const card = document.getElementById("selectedCard");
  document.getElementById("selName").textContent = a.name;
  document.getElementById("selBody").innerHTML =
    typeLabel(a.asset_type) + " · max <b>" + a.max_depth_cm.toFixed(1) + " cm</b> · research band <b>" + a.band_label + "</b><br>" +
    leadLabel(a) + (a.first_exceedance_note ? " — " + a.first_exceedance_note : "") + "<br>" +
    "<span style='color:#8d3d14'>" + (a.action_hint || "Research only — not an SOP trigger.") + "</span>";
  card.classList.add("on");
}}

function loadDecisionDesk() {{
  const name = (manifest.asset_decision_desk && manifest.asset_decision_desk.assets_json) || "decision_desk_assets.json";
  const geoName = (manifest.asset_decision_desk && manifest.asset_decision_desk.assets_geojson) || "decision_desk_assets.geojson";
  Promise.all([
    fetch(assets + name, {{ cache:"no-cache" }}).then(r => r.ok ? r.json() : null),
    fetch(assets + geoName, {{ cache:"no-cache" }}).then(r => r.ok ? r.json() : null),
  ]).then(([json, geo]) => {{
    if (!json) {{
      document.getElementById("assetList").innerHTML = '<div class="empty">decision_desk_assets.json missing — run scripts/build_decision_desk_assets.py</div>';
      return;
    }}
    desk = json;
    const c = json.counts || {{}};
    document.getElementById("deskSummary").innerHTML =
      `<span>Wet assets (metro · MRMS)</span><b>${{c.wet_total||0}} · R ${{c.roads||0}} / S ${{c.stations||0}} / F ${{c.facilities||0}}</b>`;
    renderAssetList();
    if (geo && geo.features) {{
      wetLayer = L.geoJSON(geo, {{
        pane: "vectorPane",
        style: f => {{
          const band = f.properties && f.properties.band;
          const color = band === "hazard" ? "#b91c1c" : band === "deep_ponding" ? "#c2410c" : "#a16207";
          return {{ color, weight: 3.5, opacity: 0.85 }};
        }},
        pointToLayer: (f, ll) => {{
          const band = f.properties && f.properties.band;
          const color = band === "hazard" ? "#b91c1c" : band === "deep_ponding" ? "#c2410c" : "#a16207";
          return L.circleMarker(ll, {{ radius:5, color:"#fff", weight:1, fillColor:color, fillOpacity:0.9, pane:"pointPane" }});
        }},
        onEachFeature: (f, layer) => {{
          layer.on("click", () => selectAsset(f.properties.id));
          layer.bindTooltip((f.properties.name || "") + " · " + (f.properties.band_label || ""));
        }}
      }}).addTo(mapLeft);
    }}
  }}).catch(err => {{
    document.getElementById("assetList").innerHTML = '<div class="empty">Failed to load desk assets.</div>';
    const b = document.getElementById("assetBanner");
    if (b) {{ b.style.display="block"; b.textContent = String(err); }}
  }});
}}

async function fetchGeoJSON(path) {{
  const r = await fetch(assets + path, {{ cache:"no-cache" }});
  if (!r.ok) throw new Error(path + " HTTP " + r.status);
  return r.json();
}}
function bindToggle(id, layer) {{
  const el = document.getElementById(id);
  if (!el || !layer) return;
  const sync = () => {{
    if (el.checked) layer.addTo(mapLeft); else if (mapLeft.hasLayer(layer)) mapLeft.removeLayer(layer);
  }};
  el.addEventListener("change", sync);
  if (el.checked) sync();
}}
function loadOptionalLayers() {{
  const built = pluvial?.built_surface_png
    ? L.imageOverlay(assets + pluvial.built_surface_png, currentBounds(), {{ opacity:0.45, pane:"rasterPane", interactive:false }})
    : null;
  bindToggle("lyBuilt", built);

  fetchGeoJSON(manifest.infra?.roads_geojson || "roads.geojson").then(geo => {{
    bindToggle("lyRoads", L.geoJSON(geo, {{ pane:"vectorPane", style: {{ color:"#ff6b00", weight:2.5, opacity:0.7 }} }}));
  }}).catch(()=>{{}});
  fetchGeoJSON(manifest.infra?.stations_geojson || "subway_stations.geojson").then(geo => {{
    bindToggle("lySta", L.geoJSON(geo, {{
      pointToLayer: (f,ll) => L.circleMarker(ll, {{ radius:5, fillColor:"#00e5a8", color:"#004d40", weight:1, fillOpacity:0.9, pane:"pointPane" }})
    }}));
  }}).catch(()=>{{}});
  fetchGeoJSON("critical_facilities.geojson").then(geo => {{
    bindToggle("lyFac", L.geoJSON(geo, {{
      pointToLayer: (f,ll) => L.circleMarker(ll, {{ radius:6, fillColor:"#a855f7", color:"#5b21b6", weight:1, fillOpacity:0.95, pane:"pointPane" }})
    }}));
  }}).catch(()=>{{}});
  fetchGeoJSON(manifest.reports?.geojson || "observed_311.geojson").then(geo => {{
    bindToggle("ly311", L.geoJSON(geo, {{
      pointToLayer: (f,ll) => L.circleMarker(ll, {{ radius:4, fillColor:"#ff3b5c", color:"#7f0020", weight:1, fillOpacity:0.85, pane:"pointPane" }})
    }}));
  }}).catch(()=>{{}});
  fetchGeoJSON("fema_nfhl.geojson").then(geo => {{
    bindToggle("lyFema", L.geoJSON(geo, {{ style: {{ color:"#1d4ed8", weight:1, fillOpacity:0.15 }} }}));
  }}).catch(()=>{{}});
  fetchGeoJSON("nwm_high_flow.geojson").then(geo => {{
    bindToggle("lyNwm", L.geoJSON(geo, {{ style: {{ color:"#00c2ff", weight:3, opacity:0.8 }} }}));
  }}).catch(()=>{{}});
  fetchGeoJSON("nwm_ahps_gauges.geojson").then(geo => {{
    bindToggle("lyGauges", L.geoJSON(geo, {{
      pointToLayer: (f,ll) => L.circleMarker(ll, {{ radius:6, fillColor:"#37d6ff", color:"#003d5c", weight:2, fillOpacity:1, pane:"pointPane" }})
    }}));
  }}).catch(()=>{{}});

  const fnName = (manifest.validation_dashboard && manifest.validation_dashboard.floodnet)
    || (manifest.validation_floodnet && manifest.validation_floodnet.scores)
    || "floodnet_validation.json";
  const reproName = (manifest.validation_dashboard && manifest.validation_dashboard.ida_reproduction)
    || (manifest.ida_event_reproduction && manifest.ida_event_reproduction.scores)
    || "ida_floodnet_reproduction.json";
  const hotspotGeo = (manifest.ida_event_reproduction && manifest.ida_event_reproduction.stations_geojson)
    || "floodnet_ida_hotspot_stations.geojson";
  const scoresName = (manifest.validation_dashboard && manifest.validation_dashboard.scores) || "validation_scores.json";
  fetchGeoJSON(hotspotGeo).then(geo => {{
    bindToggle("lyFloodNet", L.geoJSON(geo, {{
      pointToLayer: (f, ll) => {{
        const p = f.properties || {{}};
        const ok = !!p.oom_ok;
        return L.circleMarker(ll, {{
          radius: 7,
          fillColor: ok ? "#0a8a96" : "#8d3d14",
          color: "#071018",
          weight: 1.5,
          fillOpacity: 0.92,
          pane: "pointPane",
        }});
      }},
      onEachFeature: (f, layer) => {{
        const p = f.properties || {{}};
        const fmt = (x) => (x == null || Number.isNaN(Number(x))) ? "—" : Number(x).toFixed(3);
        layer.bindPopup(
          `<b>${{p.sensor_name || p.sensor_id || "FloodNet"}}</b><br>` +
          `obs peak ${{fmt(p.obs_peak_m)}} m · hotspot cal ${{fmt(p.hotspot_cal_m)}} m<br>` +
          `residual ${{fmt(p.residual_m)}} m · HAND@post ${{fmt(p.primary_hand_m)}} m<br>` +
          `<span style="opacity:.8">Ida reproduction only — not primary depth</span>`
        );
      }},
    }}));
  }}).catch(()=>{{}});
  Promise.all([
    fetch(assets + fnName, {{ cache:"no-cache" }}).then(r => r.ok ? r.json() : null).catch(() => null),
    fetch(assets + reproName, {{ cache:"no-cache" }}).then(r => r.ok ? r.json() : null).catch(() => null),
    fetch(assets + scoresName, {{ cache:"no-cache" }}).then(r => r.ok ? r.json() : null).catch(() => null),
  ]).then(([fn, repro, scores]) => {{
    const el = document.getElementById("validationPanel");
    if (!el) return;
    const fmt = (x) => (x == null || Number.isNaN(x)) ? "—" : Number(x).toFixed(3);
    if (repro && repro.summary && repro.summary.hotspot_calibrated) {{
      const h = repro.summary.hotspot_calibrated;
      const hand = repro.summary.primary_hand || {{}};
      const cal = repro.calibration || {{}};
      const loo = repro.leave_one_out || {{}};
      el.innerHTML =
        `<b>Ida @ FloodNet posts</b> — hotspot cal RMSE ${{fmt(h.rmse_m)}} m · bias ${{fmt(h.bias_m)}} m · OOM ${{h.oom_ok_n || 0}}/${{h.n || 0}}` +
        ` (scale ${{fmt(cal.scale)}}, bias ${{fmt(cal.bias_m)}} m; LOO RMSE ${{fmt(loo.rmse_m)}} m).` +
        ` Primary HAND still dry/cm-scale (RMSE ${{fmt(hand.rmse_m)}} m) — not rescaled citywide. Research only; never lead with 311.`;
      return;
    }}
    if (fn && fn.summary) {{
      const rmse = fn.summary.peak_rmse_m;
      const bias = fn.summary.peak_bias_m && fn.summary.peak_bias_m.mean;
      const n = fn.summary.n_sensors;
      el.innerHTML = `<b>FloodNet vs primary HAND</b> — n=${{n}} sensors · peak RMSE ${{fmt(rmse)}} m · bias ${{fmt(bias)}} m (model−obs). Research only; cm-scale HAND ≪ street peaks. Never lead with 311 hit-rate.`;
      return;
    }}
    const conf = scores && scores.confidence ? scores.confidence.level : "low";
    const note = (scores && scores.confidence && scores.confidence.note) || "Exploratory collocation only.";
    el.innerHTML = `<b>Limitations-first</b> — exploratory collocation (${{conf}}); ${{note}} Never lead with 311 hit-rate.`;
  }});
}}

document.getElementById("listModeChips").addEventListener("click", e => {{
  const btn = e.target.closest(".chip");
  if (!btn) return;
  listMode = btn.dataset.mode || "shortlist";
  document.querySelectorAll("#listModeChips .chip").forEach(c => c.classList.toggle("active", c === btn));
  renderAssetList();
}});
document.getElementById("typeChips").addEventListener("click", e => {{
  const btn = e.target.closest(".chip");
  if (!btn) return;
  typeFilter = btn.dataset.type;
  document.querySelectorAll("#typeChips .chip").forEach(c => c.classList.toggle("active", c === btn));
  renderAssetList();
}});
document.getElementById("bandFilter").onchange = renderAssetList;
document.getElementById("assetSearch").oninput = () => {{
  if ((document.getElementById("assetSearch").value || "").trim()) {{
    listMode = "all";
    document.querySelectorAll("#listModeChips .chip").forEach(c => c.classList.toggle("active", c.dataset.mode === "all"));
  }}
  renderAssetList();
}};
document.getElementById("hudPlay").onclick = () => setPlaying(!playing);
document.getElementById("extentSelect").onchange = () => fitMapFrame();
document.getElementById("eventSelect").onchange = () => {{ if (!EVENTS[eventSel.value].available) alert("Only Ida is loaded."); }};
document.getElementById("stormPathSelect").onchange = () => {{
  activePath = stormPaths.find(p => p.id === pathSel.value) || stormPaths[0];
  rebuildPathLayers();
  setLead(0);
}};
document.getElementById("opPrecip").oninput = () => {{
  document.getElementById("opPrecipVal").textContent = document.getElementById("opPrecip").value + "%";
  if (activeE2) activeE2.setOpacity(precipOpacity());
  if (e2Total) e2Total.setOpacity(precipOpacity());
}};
document.getElementById("opSusc").oninput = () => {{
  document.getElementById("opSuscVal").textContent = document.getElementById("opSusc").value + "%";
  if (activeSusc) activeSusc.setOpacity(suscOpacity());
}};
document.getElementById("opDepth").oninput = () => {{
  document.getElementById("opDepthVal").textContent = document.getElementById("opDepth").value + "%";
  if (activeDepth) activeDepth.setOpacity(depthOpacity());
  else if (depthTotal) depthTotal.setOpacity(depthOpacity());
}};
document.getElementById("lyE2").onchange = () => setLead(0);
document.getElementById("lySusc").onchange = () => setLead(0);
document.getElementById("lyDepthTot").onchange = () => {{
  if (activeDepth && mapLeft.hasLayer(activeDepth)) mapLeft.removeLayer(activeDepth);
  if (depthTotal && mapLeft.hasLayer(depthTotal)) mapLeft.removeLayer(depthTotal);
  if (document.getElementById("lyDepthTot").checked) setLead(0);
}};
document.getElementById("lySfincs").onchange = () => {{
  if (!sfincsLayer) return;
  if (document.getElementById("lySfincs").checked) {{
    sfincsLayer.addTo(mapLeft);
    const b = document.getElementById("assetBanner");
    if (b) {{
      b.style.display = "block";
      b.innerHTML = "<b>SFINCS Queens is an alternate hydro track</b> — not peer-authoritative with primary pysheds metro ranking. Magnitudes are not comparable.";
    }}
  }} else {{
    mapLeft.removeLayer(sfincsLayer);
  }}
}};
document.getElementById("lyE2Tot").onchange = () => {{
  if (!e2Total) return;
  if (document.getElementById("lyE2Tot").checked) {{ e2Total.setOpacity(precipOpacity()); e2Total.addTo(mapLeft); }}
  else mapLeft.removeLayer(e2Total);
}};

rebuildPathLayers();
fitMapFrame();
setLead(0);
loadDecisionDesk();
loadOptionalLayers();
setPlaying(true);
</script>
</body>
</html>
"""
    out = FIGURES_DIR / "product_map.html"
    out.write_text(html)
    return out
