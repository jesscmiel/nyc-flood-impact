#!/usr/bin/env python3
"""Build the upgraded product map (Tracks 1–3 + validation panel)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from nyc_flash_flood_case_study.config import FIGURES_DIR, PROJECT_ROOT
from nyc_flash_flood_case_study.extents import EVENTS, EXTENTS, bounds_list
from nyc_flash_flood_case_study.pluvial import build_pluvial_screening
from nyc_flash_flood_case_study.validation_product import build_validation_product

ASSETS = FIGURES_DIR / "product_assets"
IDA_ASSETS = FIGURES_DIR / "ida_v0_assets"


def _stage_assets() -> dict:
    ASSETS.mkdir(parents=True, exist_ok=True)
    if IDA_ASSETS.exists():
        for path in IDA_ASSETS.iterdir():
            if path.is_file():
                shutil.copy2(path, ASSETS / path.name)
    manifest = json.loads((ASSETS / "manifest.json").read_text()) if (ASSETS / "manifest.json").exists() else {}
    return manifest


def write_product_html(manifest: dict, pluvial: dict, validation: dict) -> Path:
    events_json = json.dumps(EVENTS)
    extents_json = json.dumps(EXTENTS)
    precip = manifest.get("precip", {})
    mrms = manifest.get("mrms_qpe")
    frames = precip.get("frames", [])
    n = max(len(frames), 1)
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NYC Flood Impact · product map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css">
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css">
<style>
:root {{ --ink:#15202b; --muted:#5c6b7a; --panel:#f3f6f8; --line:#d7dee5; --accent:#0f6e8c; --warn:#9a3412; --bg:#e7eef2; }}
* {{ box-sizing:border-box; }}
html,body {{ margin:0; height:100%; font-family:"IBM Plex Sans",system-ui,sans-serif; color:var(--ink); background:var(--bg); }}
body {{ display:grid; grid-template-columns:minmax(280px,340px) 1fr; }}
@media (max-width:900px) {{
  body {{ grid-template-columns:1fr; grid-template-rows:auto 1fr; }}
  aside {{ max-height:46vh; border-right:0; border-bottom:1px solid var(--line); }}
}}
aside {{ background:var(--panel); border-right:1px solid var(--line); padding:14px 14px 24px; overflow:auto; }}
h1 {{ font-size:1.2rem; margin:0 0 6px; }}
.eyebrow {{ text-transform:uppercase; letter-spacing:.08em; font-size:.68rem; color:var(--muted); margin:0 0 6px; }}
.sub {{ color:var(--muted); font-size:.84rem; line-height:1.4; margin:0 0 10px; }}
.disclaimer-bar {{ position:sticky; top:0; z-index:2; background:#fff7ed; border:1px solid #fdba74; color:var(--warn); padding:8px 10px; border-radius:8px; font-size:.78rem; line-height:1.35; margin-bottom:12px; }}
section {{ margin:14px 0; padding-top:10px; border-top:1px solid var(--line); }}
section h2 {{ font-size:.9rem; margin:0 0 8px; }}
label.row, .field {{ display:flex; justify-content:space-between; align-items:center; gap:8px; margin:6px 0; font-size:.84rem; }}
select, button, input[type=range] {{ width:100%; }}
select, button {{ padding:8px 10px; border-radius:8px; border:1px solid var(--line); background:#fff; font:inherit; }}
button.active {{ border-color:var(--accent); background:#e7f4f8; color:var(--accent); font-weight:600; }}
.readout {{ font-variant-numeric:tabular-nums; font-weight:600; color:var(--accent); }}
.metric {{ display:flex; justify-content:space-between; gap:8px; font-size:.8rem; margin:4px 0; }}
.swatch {{ display:inline-block; width:11px; height:11px; border-radius:2px; margin-right:6px; vertical-align:middle; }}
.map-stage {{ position:relative; min-height:0; height:100%; display:grid; }}
.map-stage.single {{ grid-template-columns:1fr; }}
.map-stage.compare {{ grid-template-columns:1fr 1fr; }}
.map-pane {{ position:relative; height:100%; min-height:0; overflow:hidden; border-left:1px solid var(--line); }}
.map-pane:first-child {{ border-left:0; }}
.map-pane[hidden] {{ display:none !important; }}
.map-el {{ position:absolute; inset:0; }}
.pane-label {{ position:absolute; z-index:1000; top:10px; left:48px; background:rgba(255,255,255,.93); border:1px solid var(--line); padding:4px 8px; font-size:.74rem; font-weight:600; }}
.footer-note {{ position:absolute; z-index:1000; left:10px; bottom:10px; max-width:min(420px,90%); background:rgba(255,255,255,.94); border:1px solid var(--line); padding:7px 9px; font-size:.72rem; color:var(--muted); }}
.validation {{ background:#fff; border:1px solid var(--line); border-radius:8px; padding:8px 10px; font-size:.78rem; line-height:1.4; }}
.validation b {{ font-variant-numeric:tabular-nums; }}
.coarse {{ background:#eef2ff; color:#3730a3; border-radius:6px; padding:6px 8px; font-size:.75rem; margin-top:6px; }}
</style>
</head>
<body>
<aside>
  <p class="eyebrow">NYC flood impact · product</p>
  <h1>Event replay map</h1>
  <p class="sub">Earth2 precip + pluvial screening + observed QPE/311. Earth2Studio is a dependency only.</p>
  <div class="disclaimer-bar" id="alwaysDisclaimer">
    <b>Not inundation depth. Not a flood warning. Not emergency guidance.</b>
    Screening and AI precip are exploratory research products on a coarse native grid (~0.25°).
  </div>

  <section>
    <h2>Event</h2>
    <select id="eventSelect" aria-label="Event"></select>
  </section>

  <section>
    <h2>Extent</h2>
    <select id="extentSelect" aria-label="Map extent"></select>
  </section>

  <section>
    <h2>Valid time</h2>
    <input id="leadSlider" type="range" min="0" max="{n - 1}" value="{min(1, n - 1)}" step="1">
    <div class="metric"><span>Clock (UTC)</span><span class="readout" id="clockReadout">—</span></div>
    <div class="metric"><span>Lead</span><span class="readout" id="leadReadout">—</span></div>
    <div class="metric"><span>Earth2 6h max</span><span class="readout" id="e2Readout">—</span></div>
    <div class="metric"><span>MRMS QPE 6h max</span><span class="readout" id="mrmsReadout">—</span></div>
  </section>

  <section>
    <h2>View</h2>
    <button type="button" class="active" id="modeSingle">Single map</button>
    <button type="button" id="modeCompare" style="margin-top:6px">Side-by-side Earth2 | MRMS</button>
    <div class="field" style="margin-top:8px"><span>Precip display</span>
      <select id="resampleSelect" style="width:auto;min-width:120px">
        <option value="bilinear" selected>Bilinear (smooth)</option>
        <option value="nearest">Nearest (blocky / honest)</option>
      </select>
    </div>
    <div class="coarse" id="gridNote">Native Earth2 grid ~0.25°. Smoothing is display-only — not physical downscaling. StormCast/CorrDiff hooks: see README.</div>
  </section>

  <section>
    <h2>Layers</h2>
    <label class="row"><span><span class="swatch" style="background:#3b82f6"></span>Earth2 6h precip</span><input id="lyE2" type="checkbox" checked></label>
    <label class="row"><span><span class="swatch" style="background:#0f766e"></span>MRMS QPE 6h</span><input id="lyMrms" type="checkbox"></label>
    <label class="row"><span><span class="swatch" style="background:#c2410c"></span>Pluvial screening</span><input id="lyPluvial" type="checkbox" checked></label>
    <label class="row"><span><span class="swatch" style="background:#475569"></span>Built-surface proxy (roads)</span><input id="lyBuilt" type="checkbox"></label>
    <label class="row"><span><span class="swatch" style="background:#7c3aed"></span>Earth2 storm total</span><input id="lyE2Tot" type="checkbox"></label>
    <label class="row"><span><span class="swatch" style="background:#b45309"></span>Diff E2−MRMS</span><input id="lyDiff" type="checkbox"></label>
    <label class="row"><span><span class="swatch" style="background:#dc2626"></span>Hotspot / roads</span><input id="lyHot" type="checkbox" checked></label>
    <label class="row"><span><span class="swatch" style="background:#64748b"></span>Roads</span><input id="lyRoads" type="checkbox"></label>
    <label class="row"><span><span class="swatch" style="background:#0f766e"></span>Stations</span><input id="lySta" type="checkbox" checked></label>
    <label class="row"><span><span class="swatch" style="background:#e11d48"></span>311 reports</span><input id="ly311" type="checkbox" checked></label>
    <label class="row"><span><span class="swatch" style="background:#6366f1"></span>Ensemble band (if present)</span><input id="lyEns" type="checkbox" disabled></label>
    <label class="row"><span><span class="swatch" style="background:#1d4ed8"></span>FEMA NFHL zones (static)</span><input id="lyFema" type="checkbox"></label>
    <label class="row"><span><span class="swatch" style="background:#0ea5e9"></span>NWM high-flow reaches (context)</span><input id="lyNwm" type="checkbox"></label>
    <label class="row"><span><span class="swatch" style="background:#0369a1"></span>AHPS river gauges (context)</span><input id="lyGauges" type="checkbox"></label>
  </section>

  <section>
    <h2>Validation snapshot</h2>
    <div class="validation" id="validationPanel">Loading…</div>
  </section>

  <section>
    <details open>
      <summary><b>What this is / isn’t</b></summary>
      <p style="font-size:.78rem;color:var(--muted);line-height:1.4">
        <b>Earth2 precip</b> = FCN + PrecipitationAFNO 6h accumulations.<br>
        <b>Pluvial screening</b> = USGS ~10&nbsp;m terrain + built-surface proxy — not depth.<br>
        <b>Impervious</b> = NLCD 2021 percent impervious (~30&nbsp;m) when available.<br>
        <b>FEMA NFHL</b> = static regulatory flood-hazard zones — not event inundation.<br>
        <b>NWM / AHPS</b> = channel high-flow / river-gauge context — not street flooding.<br>
        <b>MRMS QPE</b> = observed rainfall estimate (~1&nbsp;km; not BREF).<br>
        <b>311</b> = complaints, not surveyed floods.<br>
        No SWMM depths without a calibrated NYC sewer INP (scaffold only).
      </p>
    </details>
  </section>
</aside>

<div id="mapStage" class="map-stage single">
  <div class="map-pane"><div class="pane-label" id="leftLabel">Earth2</div><div id="mapLeft" class="map-el"></div></div>
  <div class="map-pane" id="rightPane" hidden><div class="pane-label">MRMS QPE</div><div id="mapRight" class="map-el"></div></div>
  <div class="footer-note">Shareable URL updates as you change lead/layers/mode/extent. Prototype only.</div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script>
const EVENTS = {events_json};
const EXTENTS = {extents_json};
const manifest = {json.dumps(manifest)};
const pluvial = {json.dumps(pluvial)};
const validation = {json.dumps(validation)};
const assets = "product_assets/";
const hasMrms = Boolean(manifest.mrms_qpe);
const frames = manifest.precip?.frames || [];
const ens = manifest.ensemble || null;

const mapLeft = L.map("mapLeft", {{ zoomControl: true }});
L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{ maxZoom: 19, attribution: "&copy; OpenStreetMap" }}).addTo(mapLeft);
let mapRight = null, syncing = false, compareMode = false;

function sync(a,b) {{
  if (!b || syncing) return;
  syncing = true;
  try {{ b.setView(a.getCenter(), a.getZoom(), {{ animate:false }}); }} finally {{ syncing = false; }}
}}
function ensureRight() {{
  if (!hasMrms || mapRight) return mapRight;
  mapRight = L.map("mapRight", {{ zoomControl: true }});
  L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{ maxZoom: 19, attribution: "&copy; OpenStreetMap" }}).addTo(mapRight);
  mapLeft.on("moveend", () => sync(mapLeft, mapRight));
  mapRight.on("moveend", () => sync(mapRight, mapLeft));
  return mapRight;
}}

// Populate selectors before any currentBounds() call.
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
extentSel.value = "south_queens";

function currentBounds() {{
  const id = document.getElementById("extentSelect").value || "south_queens";
  const b = (EXTENTS[id] || EXTENTS.south_queens).bounds;
  return [[b.ymin, b.xmin],[b.ymax, b.xmax]];
}}

const e2Layers = frames.map(f => L.imageOverlay(assets + f.png, currentBounds(), {{ opacity: 0.72, interactive:false, className: "precip-bilinear" }}));
const mrmsLayers = hasMrms ? manifest.mrms_qpe.frames.map(f => L.imageOverlay(assets + f.png, currentBounds(), {{ opacity: 0.72 }})) : [];
const diffLayers = hasMrms ? manifest.mrms_qpe.diff_frames.map(f => L.imageOverlay(assets + f.png, currentBounds(), {{ opacity: 0.7 }})) : [];
let activeE2 = e2Layers[Math.min(1, e2Layers.length-1)];
let activeMrms = mrmsLayers[Math.min(1, Math.max(mrmsLayers.length-1,0))] || null;
let activeDiff = null;
const e2Total = manifest.precip?.storm_total_png ? L.imageOverlay(assets + manifest.precip.storm_total_png, currentBounds(), {{ opacity: 0.65 }}) : null;
const pluvialLayer = pluvial?.png ? L.imageOverlay(assets + pluvial.png, currentBounds(), {{ opacity: 0.55 }}) : null;
const builtLayer = pluvial?.built_surface_png ? L.imageOverlay(assets + pluvial.built_surface_png, currentBounds(), {{ opacity: 0.5 }}) : null;
const hotspot = manifest.disruption?.hotspot_png ? L.imageOverlay(assets + manifest.disruption.hotspot_png, currentBounds(), {{ opacity: 0.5 }}) : null;
const ensLayer = (ens && ens.available && ens.png) ? L.imageOverlay(assets + ens.png, currentBounds(), {{ opacity: 0.55 }}) : null;
let roadsLayer=null, disruptLayer=null, stationsLayer=null;
const reports = L.markerClusterGroup({{ showCoverageOnHover:false }});
if (pluvialLayer) pluvialLayer.addTo(mapLeft);
if (hotspot) hotspot.addTo(mapLeft);
if (activeE2) activeE2.addTo(mapLeft);

function fitExtent() {{
  const b = currentBounds();
  mapLeft.fitBounds(b);
  [...e2Layers, ...mrmsLayers, ...diffLayers, e2Total, pluvialLayer, builtLayer, hotspot, ensLayer].forEach(layer => {{
    if (layer) layer.setBounds(b);
  }});
  if (mapRight) mapRight.fitBounds(b);
  writeUrl();
}}

function setLead(i) {{
  if (!frames.length) return;
  const f = frames[i];
  if (activeE2 && mapLeft.hasLayer(activeE2)) mapLeft.removeLayer(activeE2);
  activeE2 = e2Layers[i];
  if (document.getElementById("lyE2").checked) activeE2.addTo(mapLeft);
  if (hasMrms) {{
    if (activeMrms) {{ mapLeft.hasLayer(activeMrms) && mapLeft.removeLayer(activeMrms); mapRight && mapRight.hasLayer(activeMrms) && mapRight.removeLayer(activeMrms); }}
    activeMrms = mrmsLayers[i];
    if (compareMode && mapRight) activeMrms.addTo(mapRight);
    else if (document.getElementById("lyMrms").checked) activeMrms.addTo(mapLeft);
    if (activeDiff && mapLeft.hasLayer(activeDiff)) mapLeft.removeLayer(activeDiff);
    activeDiff = diffLayers[i];
    if (document.getElementById("lyDiff").checked && !compareMode) activeDiff.addTo(mapLeft);
    document.getElementById("mrmsReadout").textContent = manifest.mrms_qpe.frames[i].max_mm.toFixed(1) + " mm";
  }} else document.getElementById("mrmsReadout").textContent = "n/a";
  document.getElementById("clockReadout").textContent = f.valid_time.replace("T", " ");
  document.getElementById("leadReadout").textContent = "+" + f.lead_hours + " h";
  document.getElementById("e2Readout").textContent = f.max_mm.toFixed(1) + " mm";
  document.getElementById("leftLabel").textContent = compareMode ? ("Earth2 · " + f.valid_time.replace("T"," ")) : "Earth2";
  writeUrl();
}}

function setCompare(on) {{
  compareMode = on && hasMrms;
  const stage = document.getElementById("mapStage");
  document.getElementById("modeSingle").classList.toggle("active", !compareMode);
  document.getElementById("modeCompare").classList.toggle("active", compareMode);
  if (compareMode) {{
    stage.classList.add("compare"); stage.classList.remove("single");
    document.getElementById("rightPane").hidden = false;
    setTimeout(() => {{
      const r = ensureRight();
      mapLeft.invalidateSize(); r.invalidateSize();
      r.setView(mapLeft.getCenter(), mapLeft.getZoom(), {{ animate:false }});
      setLead(+document.getElementById("leadSlider").value);
    }}, 120);
  }} else {{
    stage.classList.add("single"); stage.classList.remove("compare");
    document.getElementById("rightPane").hidden = true;
    if (mapRight && activeMrms && mapRight.hasLayer(activeMrms)) mapRight.removeLayer(activeMrms);
    setTimeout(() => mapLeft.invalidateSize(), 50);
    setLead(+document.getElementById("leadSlider").value);
  }}
  writeUrl();
}}

function writeUrl() {{
  const params = new URLSearchParams({{
    event: document.getElementById("eventSelect").value,
    extent: document.getElementById("extentSelect").value,
    lead: document.getElementById("leadSlider").value,
    mode: compareMode ? "compare" : "single",
    resample: document.getElementById("resampleSelect").value,
    layers: ["lyE2","lyMrms","lyPluvial","lyBuilt","lyE2Tot","lyDiff","lyHot","lyRoads","lySta","ly311","lyEns","lyFema","lyNwm","lyGauges"].filter(id => document.getElementById(id).checked).join(",")
  }});
  history.replaceState(null, "", "#" + params.toString());
}}

function readUrl() {{
  const raw = location.hash.replace(/^#/, "");
  if (!raw) return;
  const p = new URLSearchParams(raw);
  if (p.get("event")) document.getElementById("eventSelect").value = p.get("event");
  if (p.get("extent")) document.getElementById("extentSelect").value = p.get("extent");
  if (p.get("lead") != null) document.getElementById("leadSlider").value = p.get("lead");
  if (p.get("resample")) document.getElementById("resampleSelect").value = p.get("resample");
  const layers = (p.get("layers") || "").split(",");
  if (layers[0]) ["lyE2","lyMrms","lyPluvial","lyBuilt","lyE2Tot","lyDiff","lyHot","lyRoads","lySta","ly311","lyEns","lyFema","lyNwm","lyGauges"].forEach(id => {{
    const el = document.getElementById(id); if (el) el.checked = layers.includes(id);
  }});
  if (p.get("mode") === "compare") setCompare(true);
}}

// validation panel
(function() {{
  const v = validation || {{}};
  const e2 = v.earth2_storm_total || {{}};
  const m = v.mrms_qpe_storm_total || {{}};
  const c = v.comparison || {{}};
  const r = v.reports_311 || {{}};
  document.getElementById("validationPanel").innerHTML = `
    <div class="metric"><span>Earth2 storm max</span><b>${{e2.max_mm != null ? e2.max_mm.toFixed(1)+" mm" : "n/a"}}</b></div>
    <div class="metric"><span>MRMS QPE storm max</span><b>${{m.max_mm != null ? m.max_mm.toFixed(1)+" mm" : "n/a"}}</b></div>
    <div class="metric"><span>Max Δ (E2−MRMS)</span><b>${{c.max_mm_earth2_minus_mrms != null ? c.max_mm_earth2_minus_mrms.toFixed(1)+" mm" : "n/a"}}</b></div>
    <div class="metric"><span>311 reports</span><b>${{r.n_reports ?? "n/a"}}</b></div>
    <div class="metric"><span>311 above E2 P75</span><b>${{r.fraction_reports_above_earth2_p75 != null ? (100*r.fraction_reports_above_earth2_p75).toFixed(0)+"%" : "n/a"}}</b></div>
    <div style="margin-top:6px;color:var(--muted)">Exploratory only — not certified skill / not flood warnings.</div>`;
}})();

if (ens && ens.available) {{
  document.getElementById("lyEns").disabled = false;
  document.getElementById("gridNote").textContent += " Ensemble members available: " + ens.n_members + " (spread layer = storm-total std).";
}} else {{
  document.getElementById("gridNote").textContent += " Ensemble band: not loaded (run multi-member forecast to enable).";
}}

document.getElementById("leadSlider").addEventListener("input", e => setLead(+e.target.value));
document.getElementById("modeSingle").onclick = () => setCompare(false);
document.getElementById("modeCompare").onclick = () => setCompare(true);
document.getElementById("extentSelect").onchange = fitExtent;
document.getElementById("eventSelect").onchange = () => {{
  const ev = EVENTS[eventSel.value];
  if (!ev.available) alert("Event placeholder only — Ida is currently loaded.");
  writeUrl();
}};
document.getElementById("resampleSelect").onchange = () => {{
  const nearest = document.getElementById("resampleSelect").value === "nearest";
  document.querySelectorAll(".leaflet-image-layer").forEach(el => {{
    el.style.imageRendering = nearest ? "pixelated" : "auto";
  }});
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
bind("lyPluvial", pluvialLayer);
bind("lyBuilt", builtLayer);
bind("lyE2Tot", e2Total);
bind("lyHot", hotspot);
bind("lyEns", ensLayer);

let femaLayer=null, nwmLayer=null, gaugesLayer=null;
fetch(assets + "fema_nfhl.geojson").then(r => r.ok ? r.json() : null).then(geo => {{
  if (!geo) return;
  femaLayer = L.geoJSON(geo, {{
    style: f => {{
      const z = (f.properties && f.properties.FLD_ZONE) || "";
      const sfha = (f.properties && f.properties.SFHA_TF) === "T";
      return {{
        color: sfha ? "#1d4ed8" : "#93c5fd",
        weight: 1,
        fillColor: sfha ? "#3b82f6" : "#bfdbfe",
        fillOpacity: sfha ? 0.28 : 0.12,
      }};
    }},
    onEachFeature: (f,l) => l.bindTooltip(
      "FEMA " + ((f.properties&&f.properties.FLD_ZONE)||"?") +
      " · static NFHL context (not event inundation)"
    )
  }});
  bind("lyFema", femaLayer);
  if (document.getElementById("lyFema").checked) femaLayer.addTo(mapLeft);
}}).catch(() => {{}});
fetch(assets + "nwm_high_flow.geojson").then(r => r.ok ? r.json() : null).then(geo => {{
  if (!geo) return;
  nwmLayer = L.geoJSON(geo, {{
    style: {{ color:"#0ea5e9", weight:3, opacity:0.85 }},
    onEachFeature: (f,l) => l.bindTooltip("NWM high-flow reach · context only (not street flood)")
  }});
  bind("lyNwm", nwmLayer);
  if (document.getElementById("lyNwm").checked) nwmLayer.addTo(mapLeft);
}}).catch(() => {{}});
fetch(assets + "nwm_ahps_gauges.geojson").then(r => r.ok ? r.json() : null).then(geo => {{
  if (!geo) return;
  gaugesLayer = L.geoJSON(geo, {{
    pointToLayer: (f,ll) => L.circleMarker(ll, {{ radius:5, color:"#0369a1", fillColor:"#38bdf8", fillOpacity:0.9, weight:1 }}),
    onEachFeature: (f,l) => {{
      const p = f.properties || {{}};
      l.bindTooltip((p.location || p.gaugelid || "AHPS gauge") + " · river context (not street flood)");
    }}
  }});
  bind("lyGauges", gaugesLayer);
  if (document.getElementById("lyGauges").checked) gaugesLayer.addTo(mapLeft);
}}).catch(() => {{}});

document.getElementById("lyE2").onchange = e => {{ if (e.target.checked) activeE2.addTo(mapLeft); else mapLeft.removeLayer(activeE2); writeUrl(); }};
document.getElementById("lyMrms").onchange = e => {{
  if (compareMode) return;
  if (!activeMrms) return;
  if (e.target.checked) activeMrms.addTo(mapLeft); else mapLeft.removeLayer(activeMrms);
  writeUrl();
}};
document.getElementById("lyDiff").onchange = e => {{
  if (compareMode || !activeDiff) return;
  if (e.target.checked) activeDiff.addTo(mapLeft); else mapLeft.removeLayer(activeDiff);
  writeUrl();
}};

fetch(assets + (manifest.infra?.roads_geojson || "roads.geojson")).then(r=>r.json()).then(geo => {{
  roadsLayer = L.geoJSON(geo, {{ style: {{ color:"#64748b", weight:1, opacity:.5 }} }});
  bind("lyRoads", roadsLayer);
  if (document.getElementById("lyRoads").checked) roadsLayer.addTo(mapLeft);
}});
fetch(assets + (manifest.disruption?.disrupted_geojson || "roads_potential_disruption.geojson")).then(r=>r.json()).then(geo => {{
  disruptLayer = L.geoJSON(geo, {{ style: {{ color:"#b91c1c", weight:3, opacity:.9 }} }});
  if (document.getElementById("lyHot").checked) disruptLayer.addTo(mapLeft);
}});
fetch(assets + (manifest.infra?.stations_geojson || "subway_stations.geojson")).then(r=>r.json()).then(geo => {{
  stationsLayer = L.geoJSON(geo, {{ pointToLayer: (f,ll) => L.circleMarker(ll, {{ radius:4, color:"#0f766e", fillColor:"#14b8a6", fillOpacity:.9, weight:1 }}) }});
  bind("lySta", stationsLayer);
  if (document.getElementById("lySta").checked) stationsLayer.addTo(mapLeft);
}});
fetch(assets + (manifest.reports?.geojson || "observed_311.geojson")).then(r=>r.json()).then(geo => {{
  L.geoJSON(geo, {{
    pointToLayer: (f,ll) => L.circleMarker(ll, {{ radius:4, color:"#9f1239", fillColor:"#e11d48", fillOpacity:.85, weight:1 }}),
    onEachFeature: (f,l) => l.bindTooltip((f.properties.descriptor||"311") + " · " + (f.properties.created_date||""))
  }}).eachLayer(l => reports.addLayer(l));
  bind("ly311", reports);
  if (document.getElementById("ly311").checked) reports.addTo(mapLeft);
}});

readUrl();
fitExtent();
setLead(+document.getElementById("leadSlider").value);
</script>
</body>
</html>
"""
    out = FIGURES_DIR / "product_map.html"
    out.write_text(html)
    return out


def main() -> None:
    print("Staging Ida v0 assets into product_assets…")
    manifest = _stage_assets()
    if not manifest.get("precip"):
        raise SystemExit("Missing ida_v0 manifest/precip assets. Run scripts/build_ida_v0_map.py first.")

    # Track 1 honesty metadata (+ optional ensemble spread asset)
    ens_meta_path = ASSETS / "ensemble_meta.json"
    if ens_meta_path.exists():
        manifest["ensemble"] = json.loads(ens_meta_path.read_text())
    else:
        manifest["ensemble"] = {
            "available": False,
            "n_members": 1,
            "note": "Single-member deterministic run. Multi-member NetCDF enables uncertainty band.",
        }
    for clipped in (
        PROJECT_ROOT / "data" / "forecasts" / "nyc_precip_ida_ens2.nc",
        PROJECT_ROOT / "data" / "forecasts" / "nyc_precip_ida_20210901T12.nc",
    ):
        if not clipped.exists():
            continue
        try:
            import xarray as xr

            with xr.open_dataset(clipped) as ds:
                if "ensemble" in ds.dims and ds.sizes["ensemble"] > 1:
                    manifest["ensemble"]["available"] = True
                    manifest["ensemble"]["n_members"] = int(ds.sizes["ensemble"])
                    manifest["ensemble"]["note"] = (
                        manifest["ensemble"].get("note")
                        or "Ensemble members present in clipped forecast NetCDF."
                    )
                    break
        except Exception as exc:  # noqa: BLE001
            print(f"  ensemble probe skipped: {exc}")

    print("Building pluvial screening…")
    pluvial = build_pluvial_screening(extent_id="south_queens", assets_dir=ASSETS)
    print(f"  mean={pluvial['mean']:.2f} p90={pluvial['p90']:.2f}")

    print("Building validation product…")
    e2_tif = PROJECT_ROOT / "data" / "processed" / "earth2_precip" / "precip_storm_total.tif"
    mrms_tif = PROJECT_ROOT / "data" / "processed" / "mrms_qpe" / "mrms_qpe_storm_total.tif"
    validation = build_validation_product(e2_tif, mrms_tif if mrms_tif.exists() else None, ASSETS)
    print(f"  wrote outputs/validation_product.json")

    # SWMM scaffold note in manifest
    manifest["swmm"] = {
        "integrated": False,
        "missing": "Calibrated NYC sewer/drainage INP + rain-gage mapping. See docs in README Track 2.",
    }
    manifest["downscaling_hooks"] = {
        "stormcast": "earth2studio.models.px.StormCast / StormCastConus — not run in this pass (weights/runtime).",
        "corrdiff": "earth2studio.models.dx.CorrDiff* — not run in this pass; wire as diagnostic after FCN.",
        "policy": "No fake downscaling; bilinear display is visual only.",
    }

    (ASSETS / "product_manifest.json").write_text(json.dumps(manifest, indent=2))
    html = write_product_html(manifest, pluvial, validation)
    print(f"Wrote {html}")


if __name__ == "__main__":
    main()
