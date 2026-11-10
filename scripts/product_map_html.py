#!/usr/bin/env python3
"""Earth2-primary product map — radar loop, multi-factor susceptibility, alt storm paths."""

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
<title>NYC Flood Impact</title>
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
  --accent:#0a8a96; --accent-deep:#056 dig 068; --accent-soft:#d4eef1;
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
.layer-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:7px; }}
.group-label {{ grid-column:1 / -1; margin:6px 0 0; font-size:.68rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:#7d91a1; }}
.layer-btn {{ position:relative; display:flex; align-items:center; gap:8px; min-height:42px; padding:8px 10px; border-radius:12px; border:1px solid var(--line); background:#fff; cursor:pointer; font-size:.78rem; font-weight:600; transition:border-color .15s, background .15s, transform .12s; }}
.layer-btn:hover {{ transform:translateY(-1px); border-color:#9db4c2; }}
.layer-btn input {{ position:absolute; opacity:0; pointer-events:none; }}
.layer-btn .dot {{ width:9px; height:9px; border-radius:50%; flex:0 0 auto; box-shadow:0 0 0 2px #fff; }}
.layer-btn:has(input:checked) {{ background:linear-gradient(180deg,#f5fcfd,#d9eef1); border-color:var(--accent); color:#045963; }}
.layer-btn:has(input:disabled) {{ opacity:.4; cursor:not-allowed; transform:none; }}
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
.path-pill {{
  display:inline-flex; align-items:center; gap:6px; margin-top:8px; padding:5px 10px; border-radius:999px;
  background:#e7f5f7; color:#045963; font:600 .7rem Sora,sans-serif; border:1px solid #b7dde2;
}}
</style>
</head>
<body>
<aside>
  <div class="brand">
    <div class="brand-kicker">NYC · Earth2 primary</div>
    <div class="brand-mark">Flood Impact</div>
    <div class="brand-tag">Radar-style storm replay with multi-factor flood susceptibility screening.</div>
  </div>
  <div class="disclaimer-bar">
    <b>Not inundation depth. Not a flood warning. Not emergency guidance.</b>
    Primary path is <b>Earth2</b>. Alternate Earth2 ensemble tracks are scenario paths — not MRMS/NEXRAD. AI precip ≠ radar reflectivity.
  </div>

  <div class="panel">
    <h2>Product mode</h2>
    <div class="seg" role="group" aria-label="Product mode">
      <button type="button" class="active" id="productStorm" data-mode="storm">Storm</button>
      <button type="button" id="productSusc" data-mode="susceptibility">Susceptibility</button>
      <button type="button" id="productCoupled" data-mode="coupled">Coupled</button>
    </div>
    <div class="chain" aria-hidden="true">
      <span class="step" id="chainPrecip">Weather</span><span>→</span>
      <span class="step dim" id="chainSusc">Landscape×Infra</span><span>→</span>
      <span class="step dim" id="chainInfra">Exposure</span>
    </div>
    <p class="mode-hint" id="modeHint">Storm mode: animate Earth2 precip. Susceptibility stays off until you switch modes.</p>
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
    <div><label class="caption" for="resampleSelect">Precip display</label>
      <select id="resampleSelect">
        <option value="nearest" selected>Nearest (blocky / honest)</option>
        <option value="bilinear">Bilinear (CSS only)</option>
      </select>
    </div>
  </div>

  <div class="panel">
    <h2>Layers</h2>
    <div class="layer-grid">
      <div class="group-label">Storm</div>
      <label class="layer-btn"><input id="lyE2" type="checkbox" checked><span class="dot" style="background:#4662d8"></span>Earth2 precip</label>
      <label class="layer-btn"><input id="lyE2Tot" type="checkbox"><span class="dot" style="background:#30123b"></span>Storm total</label>

      <div class="group-label">Susceptibility</div>
      <label class="layer-btn"><input id="lySusc" type="checkbox"><span class="dot" style="background:#d95f0e"></span>Multi-factor heatmap</label>
      <label class="layer-btn"><input id="lyBuilt" type="checkbox"><span class="dot" style="background:#475569"></span>Built surface</label>

      <div class="group-label">Infrastructure / obs</div>
      <label class="layer-btn"><input id="lyInfra" type="checkbox"><span class="dot" style="background:#b91c1c"></span>Storm-synced roads</label>
      <label class="layer-btn"><input id="lyHot" type="checkbox"><span class="dot" style="background:#dc2626"></span>Hotspot roads</label>
      <label class="layer-btn"><input id="ly311" type="checkbox"><span class="dot" style="background:#e11d48"></span>311 reports</label>
      <label class="layer-btn"><input id="lySta" type="checkbox"><span class="dot" style="background:#0f766e"></span>Stations</label>
      <label class="layer-btn"><input id="lyRoads" type="checkbox"><span class="dot" style="background:#64748b"></span>Roads</label>

      <div class="group-label">Context</div>
      <label class="layer-btn"><input id="lyFema" type="checkbox"><span class="dot" style="background:#1d4ed8"></span>FEMA NFHL</label>
      <label class="layer-btn"><input id="lyNwm" type="checkbox"><span class="dot" style="background:#0ea5e9"></span>NWM reaches</label>
      <label class="layer-btn"><input id="lyGauges" type="checkbox"><span class="dot" style="background:#0369a1"></span>AHPS gauges</label>
      <label class="layer-btn"><input id="lyDrainE" type="checkbox"><span class="dot" style="background:#a16207"></span>Demo conduits</label>
      <label class="layer-btn"><input id="lyDrainN" type="checkbox"><span class="dot" style="background:#ca8a04"></span>Demo nodes</label>
    </div>
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
        <b>Storm paths</b> = Earth2 primary + optional Earth2 ensemble alt tracks.<br>
        <b>Not included in UI</b> = MRMS/NEXRAD as competing live precip.
      </p>
    </details>
  </div>
</aside>

<div class="map-stage" id="mapStage">
  <div class="map-pane"><div class="pane-label" id="leftLabel">Storm · Earth2</div><div id="mapLeft" class="map-el"></div></div>
  <div class="footer-note">Earth2-primary prototype. Alt paths are scenario tracks. Susceptibility is screening, not depth.</div>
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
const assets = "product_assets/";
const stormPaths = manifest.storm_paths || [{{
  id: "earth2_control", label: "Earth2 (primary)", primary: true, scenario_kind: "earth2_primary",
  precip: manifest.precip, susceptibility: manifest.susceptibility, infra_highlights: manifest.infra_highlights
}}];

const mapLeft = L.map("mapLeft", {{ zoomControl: true }});
window.mapLeft = mapLeft;
L.tileLayer("https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png", {{
  maxZoom: 19, attribution: "&copy; OpenStreetMap &copy; CARTO"
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

let e2Layers = [], suscLayers = [];
let activeE2 = null, activeSusc = null, activeInfra = null;
let e2Total = null;
const builtLayer = pluvial?.built_surface_png ? L.imageOverlay(assets + pluvial.built_surface_png, suscBounds, {{ opacity: 0.5 }}) : null;
const hotspot = manifest.disruption?.hotspot_png ? L.imageOverlay(assets + manifest.disruption.hotspot_png, hotspotBounds, {{ opacity: 0.5 }}) : null;
let roadsLayer=null, disruptLayer=null, stationsLayer=null, drainNodes=null, drainEdges=null, femaLayer=null, nwmLayer=null, gaugesLayer=null;
const reports = L.markerClusterGroup({{ showCoverageOnHover:false }});
let productMode = "storm", playing = false, playTimer = null;

function precipOpacity() {{ return (+document.getElementById("opPrecip").value) / 100; }}
function suscOpacity() {{ return (+document.getElementById("opSusc").value) / 100; }}

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
  e2Layers = frames.map(f => L.imageOverlay(assets + f.png, precipBounds, {{ opacity: precipOpacity(), interactive:false, className:"precip-nearest" }}));
  suscLayers = suscFrames.map(f => L.imageOverlay(assets + f.png, suscBounds, {{ opacity: suscOpacity(), interactive:false }}));
  e2Total = activePath.precip?.storm_total_png ? L.imageOverlay(assets + activePath.precip.storm_total_png, precipBounds, {{ opacity: precipOpacity() }}) : null;
  document.getElementById("leadSlider").max = Math.max(frames.length - 1, 0);
  document.getElementById("tickRow").innerHTML = frames.map(f => `<span>+${{Number(f.lead_hours)}}</span>`).join("");
  document.getElementById("pathPill").textContent = activePath.label;
  document.getElementById("pathHonesty").textContent = activePath.primary
    ? "Primary Earth2 control path. Alternate members are IC-perturbation scenarios, not observations."
    : "Alternate Earth2 storm scenario (ensemble member) — not MRMS/NEXRAD, not a validation split-screen.";
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
        style: {{ color:"#b91c1c", weight:3, opacity:0.9 }},
        onEachFeature: (ft, layer) => layer.bindTooltip("Storm-synced · multi-factor susceptibility (demo)")
      }}).addTo(mapLeft);
    }}).catch(()=>{{}});
  }}
  const clock = (f.valid_time || "").replace("T", " ");
  document.getElementById("clockReadout").textContent = clock;
  document.getElementById("leadReadout").textContent = "+" + f.lead_hours + " h";
  document.getElementById("e2Readout").textContent = (f.max_mm != null ? f.max_mm.toFixed(1) : "—") + " mm";
  document.getElementById("frameTypeReadout").textContent = f.temporal_blend ? "temporal blend" : "native Earth2";
  document.getElementById("hudClock").textContent = clock + " UTC";
  document.getElementById("hudSub").textContent = productMode === "susceptibility"
    ? ("Multi-factor susceptibility · +" + f.lead_hours + "h · screening only")
    : (activePath.label + " · +" + f.lead_hours + "h · " + (f.temporal_blend ? "blend" : "native") + " · not NEXRAD");
  document.getElementById("leftLabel").textContent =
    (productMode === "susceptibility" ? "Susceptibility" : productMode === "coupled" ? "Coupled" : "Storm")
    + " · " + (activePath.primary ? "Earth2" : "Alt path");
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

const LAYER_IDS = ["lyE2","lyE2Tot","lySusc","lyBuilt","lyInfra","lyHot","ly311","lySta","lyRoads","lyFema","lyNwm","lyGauges","lyDrainE","lyDrainN"];
function setLayerChecks(onIds) {{
  LAYER_IDS.forEach(id => {{
    const el = document.getElementById(id);
    if (!el || el.disabled) return;
    const want = onIds.includes(id);
    if (el.checked !== want) {{ el.checked = want; el.dispatchEvent(new Event("change")); }}
  }});
}}

function applyProductMode(mode) {{
  productMode = mode;
  ["productStorm","productSusc","productCoupled"].forEach(id => {{
    const el = document.getElementById(id);
    el.classList.toggle("active", el.dataset.mode === mode);
  }});
  document.getElementById("chainPrecip").classList.toggle("dim", mode === "susceptibility");
  document.getElementById("chainSusc").classList.toggle("dim", mode === "storm");
  document.getElementById("chainInfra").classList.toggle("dim", mode !== "coupled");
  const bar = document.getElementById("hudLegendBar");
  const legend = document.getElementById("hudLegendLabel");
  if (mode === "susceptibility") {{
    bar.classList.add("susc"); legend.textContent = "Susceptibility (screening)";
    document.getElementById("modeHint").textContent = "Susceptibility: weather × landscape × infrastructure — screening, not depth.";
    setLayerChecks(["lySusc"]); setPlaying(false);
  }} else if (mode === "coupled") {{
    bar.classList.remove("susc"); legend.textContent = "Earth2 precip (mm)";
    document.getElementById("modeHint").textContent = "Coupled: precip → multi-factor susceptibility → storm-synced infra.";
    setLayerChecks(["lyE2","lySusc","lyInfra","lySta"]);
  }} else {{
    bar.classList.remove("susc"); legend.textContent = "Earth2 precip (mm)";
    document.getElementById("modeHint").textContent = "Storm mode: Earth2 radar-style loop. Susceptibility off by default.";
    setLayerChecks(["lyE2"]);
  }}
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
document.getElementById("extentSelect").onchange = fitExtent;
document.getElementById("eventSelect").onchange = () => {{ if (!EVENTS[eventSel.value].available) alert("Only Ida is loaded."); writeUrl(); }};
document.getElementById("stormPathSelect").onchange = () => {{
  activePath = stormPaths.find(p => p.id === pathSel.value) || stormPaths[0];
  rebuildPathLayers();
  applyProductMode(productMode);
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

function bind(id, getLayer) {{
  document.getElementById(id).addEventListener("change", () => {{
    const layer = typeof getLayer === "function" ? getLayer() : getLayer;
    if (!layer) return;
    if (document.getElementById(id).checked) layer.addTo(mapLeft); else mapLeft.removeLayer(layer);
    writeUrl();
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
document.getElementById("lyInfra").onchange = () => setLead(+document.getElementById("leadSlider").value);
document.getElementById("lyE2Tot").onchange = () => {{
  if (!e2Total) return;
  if (document.getElementById("lyE2Tot").checked) {{ e2Total.setOpacity(precipOpacity()); e2Total.addTo(mapLeft); }}
  else mapLeft.removeLayer(e2Total);
  writeUrl();
}};
bind("lyBuilt", builtLayer);
bind("lyHot", () => disruptLayer);

fetch(assets + "fema_nfhl.geojson").then(r => r.ok ? r.json() : null).then(geo => {{
  if (!geo) return;
  femaLayer = L.geoJSON(geo, {{ style: f => {{ const sfha=(f.properties&&f.properties.SFHA_TF)==="T"; return {{ color: sfha?"#1d4ed8":"#93c5fd", weight:1, fillColor: sfha?"#3b82f6":"#bfdbfe", fillOpacity: sfha?0.28:0.12 }}; }} }});
  bind("lyFema", femaLayer);
}}).catch(()=>{{}});
fetch(assets + "nwm_high_flow.geojson").then(r => r.ok ? r.json() : null).then(geo => {{
  if (!geo) return;
  nwmLayer = L.geoJSON(geo, {{ style: {{ color:"#0ea5e9", weight:3, opacity:0.85 }} }});
  bind("lyNwm", nwmLayer);
}}).catch(()=>{{}});
fetch(assets + "nwm_ahps_gauges.geojson").then(r => r.ok ? r.json() : null).then(geo => {{
  if (!geo) return;
  gaugesLayer = L.geoJSON(geo, {{ pointToLayer: (f,ll) => L.circleMarker(ll, {{ radius:5, color:"#0369a1", fillColor:"#38bdf8", fillOpacity:0.9, weight:1 }}) }});
  bind("lyGauges", gaugesLayer);
}}).catch(()=>{{}});
fetch(assets + "drainage_conduits.geojson").then(r => r.ok ? r.json() : null).then(geo => {{
  if (!geo) return;
  drainEdges = L.geoJSON(geo, {{ style: {{ color:"#a16207", weight:1.5, opacity:0.55 }} }});
  bind("lyDrainE", drainEdges);
}}).catch(()=>{{}});
fetch(assets + "drainage_nodes.geojson").then(r => r.ok ? r.json() : null).then(geo => {{
  if (!geo) return;
  drainNodes = L.geoJSON(geo, {{ pointToLayer: (f,ll) => L.circleMarker(ll, {{ radius:3, color:"#854d0e", fillColor:"#facc15", fillOpacity:0.85, weight:1 }}) }});
  bind("lyDrainN", drainNodes);
}}).catch(()=>{{}});
fetch(assets + (manifest.infra?.roads_geojson || "roads.geojson")).then(r=>r.json()).then(geo => {{
  roadsLayer = L.geoJSON(geo, {{ style: {{ color:"#64748b", weight:1, opacity:.5 }} }});
  bind("lyRoads", roadsLayer);
}});
fetch(assets + (manifest.disruption?.disrupted_geojson || "roads_potential_disruption.geojson")).then(r=>r.json()).then(geo => {{
  disruptLayer = L.geoJSON(geo, {{ style: {{ color:"#b91c1c", weight:3, opacity:.9 }} }});
}}).catch(()=>{{}});
fetch(assets + (manifest.infra?.stations_geojson || "subway_stations.geojson")).then(r=>r.json()).then(geo => {{
  stationsLayer = L.geoJSON(geo, {{ pointToLayer: (f,ll) => L.circleMarker(ll, {{ radius:4, color:"#0f766e", fillColor:"#14b8a6", fillOpacity:.9, weight:1 }}) }});
  bind("lySta", stationsLayer);
}});
fetch(assets + (manifest.reports?.geojson || "observed_311.geojson")).then(r=>r.json()).then(geo => {{
  L.geoJSON(geo, {{
    pointToLayer: (f,ll) => L.circleMarker(ll, {{ radius:4, color:"#9f1239", fillColor:"#e11d48", fillOpacity:.85, weight:1 }}),
    onEachFeature: (f,l) => l.bindTooltip((f.properties.descriptor||"311") + " · " + (f.properties.created_date||""))
  }}).eachLayer(l => reports.addLayer(l));
  bind("ly311", reports);
}});

const urlState = readUrl() || {{}};
activePath = stormPaths.find(p => p.id === pathSel.value) || stormPaths[0];
rebuildPathLayers();
document.getElementById("opPrecipVal").textContent = document.getElementById("opPrecip").value + "%";
document.getElementById("opSuscVal").textContent = document.getElementById("opSusc").value + "%";
fitExtent();
if (urlState.product && ["storm","susceptibility","coupled"].includes(urlState.product) && urlState.hasLayers) {{
  productMode = urlState.product;
  ["productStorm","productSusc","productCoupled"].forEach(id => {{
    const el = document.getElementById(id); el.classList.toggle("active", el.dataset.mode === productMode);
  }});
  setLead(+document.getElementById("leadSlider").value);
}} else applyProductMode(urlState.product || "storm");
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
