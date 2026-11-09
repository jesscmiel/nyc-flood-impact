#!/usr/bin/env python3
"""Earth2-only product map HTML (radar loop + separate susceptibility)."""

from __future__ import annotations

import json
from pathlib import Path

from nyc_flash_flood_case_study.config import FIGURES_DIR
from nyc_flash_flood_case_study.extents import EVENTS, EXTENTS


def write_product_html(manifest: dict, pluvial: dict, validation: dict) -> Path:
    precip = manifest.get("precip", {})
    frames = precip.get("frames", [])
    n = max(len(frames), 1)
    susc = manifest.get("susceptibility") or {}
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NYC Flood Impact · Earth2</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@500;600;700&family=Source+Sans+3:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css">
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css">
<style>
:root {{
  --ink:#0b1620; --ink-soft:#1a2b38; --muted:#5f7384; --panel:#f2f6f8; --panel-2:#fff;
  --line:#c9d5de; --line-soft:#e2eaf0; --accent:#0b7f8a; --accent-deep:#065a63;
  --accent-soft:#d7eef0; --warn:#8a3b12; --warn-bg:#fff4e8; --warn-line:#f0c49a;
  --sea:#0a4f5c; --chip:#e8eef2; --shadow:0 10px 30px rgba(11,22,32,.08); --radius:12px;
}}
* {{ box-sizing:border-box; }}
html,body {{ margin:0; height:100%; font-family:"Source Sans 3",sans-serif; color:var(--ink);
  background: radial-gradient(1200px 600px at 0% 0%, #d9ecee 0%, transparent 55%),
  radial-gradient(900px 500px at 100% 100%, #e7edf2 0%, transparent 50%),
  linear-gradient(160deg, #eef3f6 0%, #dfe8ee 100%); }}
body {{ display:grid; grid-template-columns:minmax(300px,380px) 1fr; }}
@media (max-width:980px) {{ body {{ grid-template-columns:1fr; grid-template-rows:auto 1fr; }} aside {{ max-height:48vh; border-right:0; border-bottom:1px solid var(--line); }} }}
aside {{ position:relative; overflow:auto; padding:18px 16px 28px;
  background: linear-gradient(180deg, rgba(255,255,255,.78), rgba(242,246,248,.92)),
  repeating-linear-gradient(135deg, rgba(11,127,138,.035) 0 2px, transparent 2px 10px);
  border-right:1px solid var(--line); }}
.brand {{ display:flex; flex-direction:column; gap:4px; margin-bottom:12px; padding:14px;
  border-radius:16px; background:linear-gradient(145deg, var(--sea), #0d6d78 48%, #12818d); color:#f4fbfd; box-shadow:var(--shadow); }}
.brand-mark {{ font-family:Sora,sans-serif; font-weight:700; font-size:1.35rem; letter-spacing:-.03em; }}
.brand-tag {{ font-size:.78rem; opacity:.88; line-height:1.35; max-width:30ch; }}
.disclaimer-bar {{ position:sticky; top:0; z-index:3; margin:0 0 14px; background:var(--warn-bg); border:1px solid var(--warn-line);
  color:var(--warn); padding:10px 12px; border-radius:var(--radius); font-size:.78rem; line-height:1.4; }}
.panel {{ background:var(--panel-2); border:1px solid var(--line-soft); border-radius:14px; padding:12px; margin:0 0 12px; }}
.panel h2 {{ font-family:Sora,sans-serif; font-size:.72rem; font-weight:600; margin:0 0 10px; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); }}
.stack {{ display:grid; gap:8px; }}
.seg {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:6px; padding:4px; border-radius:14px; background:var(--chip); border:1px solid var(--line-soft); }}
.seg button {{ border:0; background:transparent; border-radius:10px; padding:10px 6px; font:600 .72rem Sora,sans-serif; color:var(--muted); cursor:pointer; }}
.seg button.active {{ background:#fff; color:var(--accent-deep); box-shadow:0 1px 3px rgba(11,22,32,.12); }}
label.caption {{ font-size:.76rem; color:var(--muted); font-weight:600; }}
select {{ width:100%; appearance:none; padding:10px 12px; border-radius:10px; border:1px solid var(--line); background:#fff; font:500 .9rem "Source Sans 3",sans-serif; }}
.metrics {{ display:grid; gap:6px; margin-top:8px; }}
.metric {{ display:flex; justify-content:space-between; gap:8px; font-size:.82rem; padding:7px 9px; border-radius:9px; background:var(--panel); }}
.readout {{ font-variant-numeric:tabular-nums; font-weight:700; color:var(--accent-deep); font-family:Sora,sans-serif; font-size:.84rem; }}
input[type=range] {{ width:100%; accent-color:var(--accent); }}
.btn-row {{ display:flex; flex-wrap:wrap; gap:6px; }}
.btn {{ border:1px solid var(--line); background:#fff; color:var(--ink-soft); border-radius:999px; padding:8px 12px; font:600 .78rem Sora,sans-serif; cursor:pointer; }}
.btn:hover {{ border-color:var(--accent); color:var(--accent-deep); }}
.layer-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:7px; }}
.layer-btn {{ position:relative; display:flex; align-items:center; gap:8px; min-height:42px; padding:8px 10px; border-radius:11px; border:1px solid var(--line); background:#fff; cursor:pointer; font-size:.8rem; font-weight:600; }}
.layer-btn input {{ position:absolute; opacity:0; pointer-events:none; }}
.layer-btn .dot {{ width:9px; height:9px; border-radius:50%; flex:0 0 auto; }}
.layer-btn:has(input:checked) {{ background:linear-gradient(180deg, #f7fcfd, var(--accent-soft)); border-color:var(--accent); color:var(--accent-deep); }}
.group-label {{ grid-column:1 / -1; margin:4px 0 0; font-size:.7rem; font-weight:700; letter-spacing:.06em; text-transform:uppercase; color:#7a8d9c; }}
.note,.honesty {{ margin-top:8px; padding:9px 10px; border-radius:10px; font-size:.74rem; line-height:1.4; background:#eef6f7; color:#335560; border:1px solid #cfe3e6; }}
.honesty {{ background:#f4f7f9; border-style:dashed; }}
.chain {{ display:grid; grid-template-columns:1fr auto 1fr auto 1fr; gap:4px; align-items:center; margin-top:8px; font-size:.72rem; font-weight:700; color:var(--accent-deep); }}
.chain span.step {{ text-align:center; padding:8px 4px; border-radius:10px; background:var(--accent-soft); border:1px solid #b7dce0; }}
.chain span.step.dim {{ opacity:.45; background:var(--chip); border-color:var(--line-soft); color:var(--muted); }}
.transport {{ display:grid; grid-template-columns:auto 1fr auto; gap:8px; align-items:center; }}
.btn-icon {{ width:42px; height:42px; border-radius:12px; border:1px solid var(--line); background:#fff; font:700 1rem Sora,sans-serif; cursor:pointer; color:var(--accent-deep); }}
.btn-icon.playing {{ background:var(--accent-soft); border-color:var(--accent); }}
.tick-row {{ display:flex; justify-content:space-between; margin-top:4px; font-size:.65rem; color:var(--muted); font-variant-numeric:tabular-nums; }}
.opacity-row {{ display:grid; grid-template-columns:72px 1fr 36px; gap:8px; align-items:center; font-size:.78rem; margin:6px 0; }}
.legend-swatch {{ height:10px; border-radius:999px; margin-top:6px; }}
.legend-swatch.precip {{ background:linear-gradient(90deg,#30123b,#4662d8,#1ae4b6,#a2fc3c,#f9ba38,#e8332b); }}
.legend-swatch.susc {{ background:linear-gradient(90deg,#fff7bc,#fec44f,#d95f0e,#7f2704); }}
.map-stage {{ position:relative; min-height:0; height:100%; display:grid; grid-template-columns:1fr; }}
.map-pane {{ position:relative; height:100%; min-height:0; overflow:hidden; }}
.map-el {{ position:absolute; inset:0; }}
.pane-label {{ position:absolute; z-index:1000; top:12px; left:52px; background:rgba(255,255,255,.94); border:1px solid var(--line); padding:5px 10px; font:600 .74rem Sora,sans-serif; border-radius:999px; }}
.footer-note {{ position:absolute; z-index:1000; left:12px; bottom:92px; max-width:min(440px,90%); background:rgba(255,255,255,.94); border:1px solid var(--line); padding:8px 10px; font-size:.72rem; color:var(--muted); border-radius:10px; }}
.radar-hud {{ position:absolute; z-index:1100; left:50%; bottom:14px; transform:translateX(-50%); width:min(720px, calc(100% - 24px));
  display:grid; grid-template-columns:auto 1fr auto; gap:12px; align-items:center; padding:10px 14px; border-radius:16px;
  background:rgba(11,22,32,.88); color:#e8f2f5; border:1px solid rgba(255,255,255,.08); }}
.radar-hud .play {{ width:44px; height:44px; border-radius:12px; border:0; cursor:pointer; background:#12a3b0; color:#042227; font:700 .95rem Sora,sans-serif; }}
.radar-hud .clock {{ font:700 .95rem Sora,sans-serif; }}
.radar-hud .sub {{ font-size:.72rem; opacity:.78; }}
.radar-hud .legend {{ display:flex; flex-direction:column; gap:4px; align-items:flex-end; font-size:.68rem; }}
.radar-hud .bar {{ width:120px; height:8px; border-radius:999px; background:linear-gradient(90deg,#30123b,#4662d8,#1ae4b6,#a2fc3c,#f9ba38,#e8332b); }}
.radar-hud .bar.susc {{ background:linear-gradient(90deg,#fff7bc,#fec44f,#d95f0e,#7f2704); }}
.mode-hint {{ font-size:.76rem; color:var(--muted); margin-top:8px; line-height:1.35; }}
.validation {{ display:grid; gap:6px; }}
.validation b {{ font-variant-numeric:tabular-nums; font-family:Sora,sans-serif; }}
details.about {{ font-size:.78rem; color:var(--muted); line-height:1.45; }}
details.about summary {{ cursor:pointer; font-weight:700; color:var(--ink-soft); }}
.blend-tag {{ display:inline-block; margin-left:6px; padding:1px 6px; border-radius:999px; background:#e8f0f2; color:#4a6573; font-size:.65rem; font-weight:700; }}
</style>
</head>
<body>
<aside>
  <div class="brand">
    <div class="brand-mark">NYC Flood Impact</div>
    <div class="brand-tag">Earth2-only storm replay — radar-style loop coupled to flood susceptibility.</div>
  </div>
  <div class="disclaimer-bar">
    <b>Not inundation depth. Not a flood warning. Not emergency guidance.</b>
    Product policy: <b>Earth2 precip only</b> (no MRMS/NEXRAD/other weather sources). AI 6h accumulations on ~0.25° — <b>not radar reflectivity</b>. Mid-frames may be temporal blends for a smoother loop.
  </div>

  <div class="panel">
    <h2>Product mode</h2>
    <div class="seg" role="group" aria-label="Product mode">
      <button type="button" class="active" id="productStorm" data-mode="storm">Storm</button>
      <button type="button" id="productSusc" data-mode="susceptibility">Susceptibility</button>
      <button type="button" id="productCoupled" data-mode="coupled">Coupled</button>
    </div>
    <div class="chain" aria-hidden="true">
      <span class="step" id="chainPrecip">Precip</span><span>→</span>
      <span class="step dim" id="chainSusc">Susceptibility</span><span>→</span>
      <span class="step dim" id="chainInfra">Infra</span>
    </div>
    <p class="mode-hint" id="modeHint">Storm mode: animate Earth2 precip. Susceptibility stays off until you switch modes.</p>
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
        <option value="1400">Slow</option>
        <option value="900" selected>Med</option>
        <option value="550">Fast</option>
      </select>
    </div>
    <div class="metrics">
      <div class="metric"><span>Clock (UTC)</span><span class="readout" id="clockReadout">—</span></div>
      <div class="metric"><span>Lead</span><span class="readout" id="leadReadout">—</span></div>
      <div class="metric"><span>Earth2 max</span><span class="readout" id="e2Readout">—</span></div>
      <div class="metric"><span>Frame type</span><span class="readout" id="frameTypeReadout">—</span></div>
    </div>
    <div class="honesty">Loop = native Earth2 6h frames + mid-interval <b>temporal blends</b> (not extra model output, not NEXRAD).</div>
  </div>

  <div class="panel">
    <h2>Opacity</h2>
    <div class="opacity-row"><span>Precip</span><input id="opPrecip" type="range" min="15" max="95" value="75"><span id="opPrecipVal">75%</span></div>
    <div class="legend-swatch precip" title="Earth2 precip colorbar"></div>
    <div class="opacity-row"><span>Susceptibility</span><input id="opSusc" type="range" min="15" max="95" value="65"><span id="opSuscVal">65%</span></div>
    <div class="legend-swatch susc" title="Susceptibility colorbar"></div>
    <div class="select-wrap" style="margin-top:10px">
      <label class="caption" for="resampleSelect">Precip display</label>
      <select id="resampleSelect">
        <option value="nearest" selected>Nearest (blocky / honest)</option>
        <option value="bilinear">Bilinear (smooth CSS only)</option>
      </select>
    </div>
    <div class="note" id="gridNote">Native Earth2 ~0.25° cells. CSS smoothing is display-only. Overlays are land-masked.</div>
  </div>

  <div class="panel">
    <h2>Layers</h2>
    <div class="layer-grid">
      <div class="group-label">Storm (Earth2)</div>
      <label class="layer-btn"><input id="lyE2" type="checkbox" checked><span class="dot" style="background:#4662d8"></span>Earth2 precip</label>
      <label class="layer-btn"><input id="lyE2Tot" type="checkbox"><span class="dot" style="background:#30123b"></span>Storm total</label>
      <label class="layer-btn"><input id="lyEns" type="checkbox" disabled><span class="dot" style="background:#64748b"></span>Ensemble</label>

      <div class="group-label">Susceptibility (separate)</div>
      <label class="layer-btn"><input id="lySusc" type="checkbox"><span class="dot" style="background:#d95f0e"></span>Heatmap (time-varying)</label>
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
    <h2>Validation snapshot</h2>
    <div class="validation" id="validationPanel">Loading…</div>
  </div>

  <div class="panel">
    <details class="about" open>
      <summary>What this is / isn’t</summary>
      <p>
        <b>Earth2-only product</b> — no MRMS or other precip sources in this map.<br>
        <b>Storm loop</b> = FCN + PrecipitationAFNO frames (+ temporal blends).<br>
        <b>Susceptibility</b> = terrain/NLCD base × frame precip — screening, not depth.<br>
        <b>Infra sync</b> = roads highlighted where precip × susceptibility is elevated.<br>
        <b>311 / FEMA / NWM</b> = context only.
      </p>
    </details>
  </div>
</aside>

<div id="mapStage" class="map-stage">
  <div class="map-pane"><div class="pane-label" id="leftLabel">Storm · Earth2</div><div id="mapLeft" class="map-el"></div></div>
  <div class="footer-note">Earth2-only prototype. AI precip loop ≠ live radar. Susceptibility is screening, not flood depth.</div>
  <div class="radar-hud">
    <button type="button" class="play" id="hudPlay">▶</button>
    <div>
      <div class="clock" id="hudClock">—</div>
      <div class="sub" id="hudSub">Earth2 frame · land-masked · nearest ~0.25°</div>
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
const frames = manifest.precip?.frames || [];
const suscFrames = manifest.susceptibility?.frames || [];
const infraFrames = manifest.infra_highlights?.frames || [];
const ens = manifest.ensemble || null;

const mapLeft = L.map("mapLeft", {{ zoomControl: true }});
window.mapLeft = mapLeft;
L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{ maxZoom: 19, attribution: "&copy; OpenStreetMap" }}).addTo(mapLeft);

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

function currentBounds() {{
  const id = extentSel.value || "citywide";
  const b = (EXTENTS[id] || EXTENTS.citywide).bounds;
  return [[b.ymin, b.xmin],[b.ymax, b.xmax]];
}}
const precipBounds = (manifest.precip && manifest.precip.bounds) || currentBounds();
const suscBounds = (manifest.susceptibility && manifest.susceptibility.bounds) || precipBounds;
const hotspotBounds = (manifest.terrain && manifest.terrain.terrain_bounds) || precipBounds;

const e2Layers = frames.map(f => L.imageOverlay(assets + f.png, precipBounds, {{ opacity: 0.75, interactive:false, className: "precip-nearest" }}));
const suscLayers = suscFrames.map(f => L.imageOverlay(assets + f.png, suscBounds, {{ opacity: 0.65, interactive:false }}));
let activeE2 = e2Layers[0] || null;
let activeSusc = suscLayers[0] || null;
let activeInfra = null;
const e2Total = manifest.precip?.storm_total_png ? L.imageOverlay(assets + manifest.precip.storm_total_png, precipBounds, {{ opacity: 0.65 }}) : null;
const builtLayer = pluvial?.built_surface_png ? L.imageOverlay(assets + pluvial.built_surface_png, suscBounds, {{ opacity: 0.5 }}) : null;
const hotspot = manifest.disruption?.hotspot_png ? L.imageOverlay(assets + manifest.disruption.hotspot_png, hotspotBounds, {{ opacity: 0.5 }}) : null;
const ensLayer = (ens && ens.available && ens.png) ? L.imageOverlay(assets + ens.png, precipBounds, {{ opacity: 0.55 }}) : null;
let roadsLayer=null, disruptLayer=null, stationsLayer=null, drainNodes=null, drainEdges=null, femaLayer=null, nwmLayer=null, gaugesLayer=null;
const reports = L.markerClusterGroup({{ showCoverageOnHover:false }});
let productMode = "storm", playing = false, playTimer = null;
if (activeE2) activeE2.addTo(mapLeft);

document.getElementById("tickRow").innerHTML = frames.map(f => `<span>+${{Number(f.lead_hours)}}h</span>`).join("");

function precipOpacity() {{ return (+document.getElementById("opPrecip").value) / 100; }}
function suscOpacity() {{ return (+document.getElementById("opSusc").value) / 100; }}

function setLead(i) {{
  if (!frames.length) return;
  i = Math.max(0, Math.min(frames.length - 1, i));
  document.getElementById("leadSlider").value = String(i);
  const f = frames[i];
  if (activeE2 && mapLeft.hasLayer(activeE2)) mapLeft.removeLayer(activeE2);
  activeE2 = e2Layers[i];
  if (document.getElementById("lyE2").checked) {{
    activeE2.setOpacity(precipOpacity());
    activeE2.addTo(mapLeft);
  }}
  if (activeSusc && mapLeft.hasLayer(activeSusc)) mapLeft.removeLayer(activeSusc);
  if (suscLayers[i]) {{
    activeSusc = suscLayers[i];
    if (document.getElementById("lySusc").checked) {{
      activeSusc.setOpacity(suscOpacity());
      activeSusc.addTo(mapLeft);
    }}
  }}
  // Infra sync
  if (activeInfra) {{ mapLeft.removeLayer(activeInfra); activeInfra = null; }}
  const infraMeta = infraFrames[i];
  if (infraMeta && infraMeta.geojson && document.getElementById("lyInfra").checked) {{
    fetch(assets + infraMeta.geojson).then(r => r.ok ? r.json() : null).then(geo => {{
      if (!geo || +document.getElementById("leadSlider").value !== i) return;
      activeInfra = L.geoJSON(geo, {{
        style: {{ color:"#b91c1c", weight:3, opacity:0.9 }},
        onEachFeature: (ft, layer) => layer.bindTooltip("Storm-synced highlight · precip × susceptibility (demo)")
      }}).addTo(mapLeft);
    }}).catch(() => {{}});
  }}
  const clock = (f.valid_time || "").replace("T", " ");
  document.getElementById("clockReadout").textContent = clock;
  document.getElementById("leadReadout").textContent = "+" + f.lead_hours + " h";
  document.getElementById("e2Readout").textContent = (f.max_mm != null ? f.max_mm.toFixed(1) : "—") + " mm";
  document.getElementById("frameTypeReadout").textContent = f.temporal_blend ? "temporal blend" : "native Earth2";
  document.getElementById("hudClock").textContent = clock + " UTC";
  document.getElementById("hudSub").textContent = productMode === "susceptibility"
    ? ("Susceptibility · lead +" + f.lead_hours + "h · screening only")
    : ("Lead +" + f.lead_hours + "h · max " + (f.max_mm!=null?f.max_mm.toFixed(1):"—") + " mm · " + (f.temporal_blend ? "blend" : "native") + " · not NEXRAD");
  const labelBase = productMode === "susceptibility" ? "Susceptibility" : (productMode === "coupled" ? "Coupled" : "Storm");
  document.getElementById("leftLabel").textContent = labelBase + " · Earth2";
  writeUrl();
}}

function setPlaying(on) {{
  playing = on;
  document.getElementById("playBtn").textContent = on ? "❚❚" : "▶";
  document.getElementById("hudPlay").textContent = on ? "❚❚" : "▶";
  document.getElementById("playBtn").classList.toggle("playing", on);
  if (playTimer) {{ clearInterval(playTimer); playTimer = null; }}
  if (!on) return;
  const ms = +document.getElementById("playSpeed").value || 900;
  playTimer = setInterval(() => {{
    const cur = +document.getElementById("leadSlider").value;
    setLead((cur + 1) % frames.length);
  }}, ms);
}}

const LAYER_IDS = ["lyE2","lyE2Tot","lyEns","lySusc","lyBuilt","lyInfra","lyHot","ly311","lySta","lyRoads","lyFema","lyNwm","lyGauges","lyDrainE","lyDrainN"];
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
    document.getElementById("modeHint").textContent = "Susceptibility mode: time-varying heatmap f(terrain/NLCD × Earth2 precip). Not depth.";
    setLayerChecks(["lySusc"]); setPlaying(false);
  }} else if (mode === "coupled") {{
    bar.classList.remove("susc"); legend.textContent = "Earth2 precip (mm)";
    document.getElementById("modeHint").textContent = "Coupled: precip → susceptibility → storm-synced infrastructure.";
    setLayerChecks(["lyE2","lySusc","lyInfra","lySta"]);
  }} else {{
    bar.classList.remove("susc"); legend.textContent = "Earth2 precip (mm)";
    document.getElementById("modeHint").textContent = "Storm mode: Earth2-only radar-style loop. Susceptibility off by default.";
    setLayerChecks(["lyE2"]);
  }}
  setLead(+document.getElementById("leadSlider").value);
}}

function fitExtent() {{
  mapLeft.fitBounds(currentBounds());
  writeUrl();
}}
function writeUrl() {{
  const params = new URLSearchParams({{
    event: eventSel.value, extent: extentSel.value, lead: document.getElementById("leadSlider").value,
    product: productMode, playing: playing ? "1" : "0",
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
    <div style="margin-top:6px;color:var(--muted)">Earth2-only exploratory validation — not certified skill / not flood warnings.</div>`;
}})();
if (ens && ens.available) document.getElementById("lyEns").disabled = false;

document.getElementById("leadSlider").addEventListener("input", e => {{ setPlaying(false); setLead(+e.target.value); }});
document.getElementById("playBtn").onclick = () => setPlaying(!playing);
document.getElementById("hudPlay").onclick = () => setPlaying(!playing);
document.getElementById("playSpeed").onchange = () => {{ if (playing) setPlaying(true); }};
document.getElementById("productStorm").onclick = () => applyProductMode("storm");
document.getElementById("productSusc").onclick = () => applyProductMode("susceptibility");
document.getElementById("productCoupled").onclick = () => applyProductMode("coupled");
document.getElementById("extentSelect").onchange = fitExtent;
document.getElementById("eventSelect").onchange = () => {{ if (!EVENTS[eventSel.value].available) alert("Only Ida is loaded."); writeUrl(); }};
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

function bind(id, layer) {{
  const el = document.getElementById(id);
  el.addEventListener("change", () => {{
    if (!layer) return;
    if (el.checked) layer.addTo(mapLeft); else mapLeft.removeLayer(layer);
    writeUrl();
  }});
}}
document.getElementById("lyE2").onchange = e => {{
  if (e.target.checked) {{ activeE2.setOpacity(precipOpacity()); activeE2.addTo(mapLeft); }}
  else mapLeft.removeLayer(activeE2);
  writeUrl();
}};
document.getElementById("lySusc").onchange = e => {{
  if (!activeSusc) return;
  if (e.target.checked) {{ activeSusc.setOpacity(suscOpacity()); activeSusc.addTo(mapLeft); }}
  else mapLeft.removeLayer(activeSusc);
  writeUrl();
}};
document.getElementById("lyInfra").onchange = () => setLead(+document.getElementById("leadSlider").value);
bind("lyE2Tot", e2Total);
bind("lyBuilt", builtLayer);
bind("lyHot", hotspot);
bind("lyEns", ensLayer);

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
  document.getElementById("lyHot").addEventListener("change", () => {{
    if (document.getElementById("lyHot").checked) disruptLayer.addTo(mapLeft); else mapLeft.removeLayer(disruptLayer);
    writeUrl();
  }});
}});
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
document.getElementById("opPrecipVal").textContent = document.getElementById("opPrecip").value + "%";
document.getElementById("opSuscVal").textContent = document.getElementById("opSusc").value + "%";
fitExtent();
if (urlState.product && ["storm","susceptibility","coupled"].includes(urlState.product) && urlState.hasLayers) {{
  productMode = urlState.product;
  ["productStorm","productSusc","productCoupled"].forEach(id => {{
    const el = document.getElementById(id); el.classList.toggle("active", el.dataset.mode === productMode);
  }});
  setLead(+document.getElementById("leadSlider").value);
}} else {{
  applyProductMode(urlState.product || "storm");
}}
if (urlState.playing) setPlaying(true);
document.querySelectorAll(".leaflet-image-layer").forEach(el => {{
  el.style.imageRendering = (document.getElementById("resampleSelect").value === "nearest") ? "pixelated" : "auto";
}});
</script>
</body>
</html>
"""
    out = FIGURES_DIR / "product_map.html"
    out.write_text(html)
    return out
