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
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=Figtree:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
:root {{
  --ink:#06131a; --ink-soft:#17303c; --muted:#5f7584; --paper:#e8f0f3;
  --rail:#f4f8fa; --line:rgba(8,40,52,.12); --line-soft:rgba(8,40,52,.07);
  --accent:#0d8f9c; --accent-deep:#066470; --accent-glow:rgba(13,143,156,.22);
  --sea:#052833; --sea-2:#0a5460; --sea-3:#117988;
  --warn:#9a4a12; --warn-bg:rgba(154,74,18,.08); --warn-line:rgba(154,74,18,.28);
  --band-3:#a16207; --band-8:#c2410c; --band-15:#b91c1c;
  --hud:#071820ee; --ease:cubic-bezier(.22,.8,.28,1);
}}
* {{ box-sizing:border-box; }}
html,body {{ margin:0; height:100%; font-family:Figtree,system-ui,sans-serif; color:var(--ink);
  background:
    radial-gradient(1100px 640px at -8% -20%, rgba(17,121,136,.22), transparent 58%),
    radial-gradient(900px 520px at 108% 8%, rgba(5,40,51,.16), transparent 50%),
    linear-gradient(160deg, #edf4f7 0%, #d5e4ea 48%, #c9dbe3 100%);
}}
body {{ display:grid; grid-template-columns:minmax(300px,360px) 1fr; min-height:100%; }}
@media (max-width:980px) {{
  body {{ grid-template-columns:1fr; grid-template-rows:auto minmax(52vh,1fr); }}
  aside {{ max-height:48vh; border-right:0 !important; border-bottom:1px solid var(--line); }}
}}
aside {{
  position:relative; overflow:auto; padding:0 0 20px;
  background:
    linear-gradient(180deg, rgba(255,255,255,.72), rgba(244,248,250,.92)),
    repeating-linear-gradient(-18deg, transparent, transparent 11px, rgba(8,59,72,.015) 11px, rgba(8,59,72,.015) 12px);
  border-right:1px solid var(--line); backdrop-filter:blur(14px);
}}
.brand {{
  position:relative; overflow:hidden; margin:0; padding:22px 18px 18px;
  background:
    radial-gradient(520px 220px at 88% 120%, rgba(255,255,255,.14), transparent 55%),
    linear-gradient(145deg, var(--sea) 0%, var(--sea-2) 52%, var(--sea-3) 100%);
  color:#e8f7f9;
}}
.brand::before {{
  content:""; position:absolute; inset:0;
  background:linear-gradient(105deg, transparent 40%, rgba(255,255,255,.05) 50%, transparent 60%);
  animation: sweep 7.5s var(--ease) infinite; pointer-events:none;
}}
.brand::after {{
  content:""; position:absolute; width:180px; height:180px; right:-36px; bottom:-70px;
  border-radius:50%; border:1px solid rgba(255,255,255,.12);
  box-shadow:0 0 0 18px rgba(255,255,255,.04); pointer-events:none;
  animation: pulseRing 5.5s ease-in-out infinite;
}}
@keyframes sweep {{ 0%,100% {{ transform:translateX(-12%); opacity:.35; }} 50% {{ transform:translateX(8%); opacity:.7; }} }}
@keyframes pulseRing {{ 0%,100% {{ transform:scale(1); opacity:.55; }} 50% {{ transform:scale(1.08); opacity:.9; }} }}
@keyframes riseIn {{ from {{ opacity:0; transform:translateY(8px); }} to {{ opacity:1; transform:none; }} }}
@keyframes selectPulse {{ 0% {{ box-shadow:0 0 0 0 var(--accent-glow); }} 100% {{ box-shadow:0 0 0 14px transparent; }} }}
@keyframes playGlow {{ 0%,100% {{ box-shadow:0 0 0 0 rgba(27,192,205,.35); }} 50% {{ box-shadow:0 0 0 10px transparent; }} }}
.brand-kicker {{ position:relative; font:700 .62rem Syne,sans-serif; letter-spacing:.16em; text-transform:uppercase; opacity:.7; margin-bottom:8px; }}
.brand-mark {{ position:relative; font:800 clamp(1.55rem,3.4vw,1.9rem)/1.02 Syne,sans-serif; letter-spacing:-.045em; }}
.brand-tag {{ position:relative; margin-top:8px; font-size:.8rem; line-height:1.35; max-width:28ch; opacity:.88; font-weight:500; }}
.honesty-line {{
  position:sticky; top:0; z-index:5; margin:0; padding:9px 16px;
  background:linear-gradient(180deg, rgba(255,246,236,.96), rgba(255,243,230,.9));
  border-bottom:1px solid var(--warn-line); color:var(--warn);
  font:600 .72rem/1.35 Figtree,sans-serif; backdrop-filter:blur(8px);
}}
#assetBanner {{
  margin:8px 14px 0; padding:9px 11px; border-radius:10px; display:none;
  background:#3b0d0d; border:1px solid #7f1d1d; color:#fecaca; font-size:.74rem;
}}
.section {{ padding:14px 16px 6px; animation:riseIn .45s var(--ease) both; }}
.section + .section {{ border-top:1px solid var(--line-soft); }}
.section h2 {{
  display:flex; align-items:baseline; justify-content:space-between; gap:8px;
  font:700 .66rem Syne,sans-serif; margin:0 0 10px;
  text-transform:uppercase; letter-spacing:.12em; color:var(--muted);
}}
.section h2 .hint {{ font:600 .66rem Figtree,sans-serif; letter-spacing:0; text-transform:none; color:#8aa0ad; }}
.metric {{
  display:flex; justify-content:space-between; align-items:baseline; gap:10px;
  font-size:.78rem; padding:0 0 10px; margin:0 0 8px; border-bottom:1px solid var(--line-soft);
}}
.metric b, .readout {{ font:600 .8rem "IBM Plex Mono",monospace; color:var(--accent-deep); }}
label.caption {{ display:block; font-size:.68rem; color:var(--muted); font-weight:600; margin-bottom:4px; letter-spacing:.02em; }}
select, input[type=search] {{
  width:100%; appearance:none; padding:8px 10px; border-radius:8px;
  border:1px solid var(--line); background:rgba(255,255,255,.78);
  font:500 .84rem Figtree,sans-serif; color:var(--ink);
  transition:border-color .15s, box-shadow .15s, background .15s;
}}
select:focus, input[type=search]:focus {{ outline:none; border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-glow); background:#fff; }}
.filters {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; margin:0 0 10px; }}
.chip-row {{ display:flex; flex-wrap:wrap; gap:5px; margin:0 0 8px; }}
.chip {{
  border:1px solid var(--line); background:rgba(255,255,255,.55); border-radius:8px;
  padding:5px 9px; font:650 .68rem Syne,sans-serif; color:var(--muted); cursor:pointer;
  transition:transform .14s var(--ease), background .14s, border-color .14s, color .14s;
}}
.chip:hover {{ transform:translateY(-1px); color:var(--ink-soft); border-color:#9db4c2; }}
.chip.active {{ background:rgba(13,143,156,.14); border-color:var(--accent); color:var(--accent-deep); }}
.asset-list, .floodnet-list {{ display:flex; flex-direction:column; gap:4px; overflow:auto; padding-right:2px; }}
.asset-list {{ max-height:min(46vh,460px); }}
.floodnet-list {{ max-height:min(28vh,240px); margin-top:8px; }}
.asset-row {{
  position:relative; text-align:left; width:100%; border:0; border-radius:10px;
  background:transparent; padding:9px 10px 9px 12px; cursor:pointer;
  transition:background .16s var(--ease), transform .16s var(--ease);
}}
.asset-row::before {{
  content:""; position:absolute; left:0; top:10px; bottom:10px; width:2px; border-radius:2px;
  background:transparent; transition:background .16s, transform .16s var(--ease);
}}
.asset-row:hover {{ background:rgba(13,143,156,.07); transform:translateX(2px); }}
.asset-row:hover::before {{ background:#9db4c2; }}
.asset-row.selected {{ background:linear-gradient(90deg, rgba(13,143,156,.16), rgba(13,143,156,.04)); }}
.asset-row.selected::before {{ background:var(--accent); transform:scaleY(1.15); }}
.asset-row .top {{ display:flex; justify-content:space-between; gap:8px; align-items:baseline; }}
.asset-row .name {{ font:700 .84rem Syne,sans-serif; letter-spacing:-.02em; }}
.asset-row .depth {{ font:600 .78rem "IBM Plex Mono",monospace; color:var(--accent-deep); white-space:nowrap; }}
.asset-row .meta {{ margin-top:3px; display:flex; flex-wrap:wrap; gap:5px; font-size:.68rem; color:var(--muted); }}
.band {{ display:inline-flex; align-items:center; padding:1px 6px; border-radius:5px; font:700 .62rem Syne,sans-serif; }}
.band.ponding {{ background:#fef3c7; color:var(--band-3); }}
.band.deep_ponding {{ background:#ffedd5; color:var(--band-8); }}
.band.hazard {{ background:#fee2e2; color:var(--band-15); }}
.band.oom-ok {{ background:rgba(13,143,156,.16); color:var(--accent-deep); }}
.band.oom-miss {{ background:#ffedd5; color:var(--band-8); }}
.type-pill {{ display:inline-flex; padding:1px 6px; border-radius:5px; background:rgba(8,40,52,.06); font-weight:650; }}
.legend-swatch {{ height:6px; border-radius:999px; margin:2px 0 8px; opacity:.9; }}
.legend-swatch.precip {{ background:linear-gradient(90deg,#0b1d2a,#1a6f7a,#1ae4b6,#a2fc3c,#f9ba38,#e8332b); }}
.legend-swatch.susc {{ background:linear-gradient(90deg,#fff7bc,#fec44f,#d95f0e,#7f2704); }}
.legend-swatch.depth {{ background:linear-gradient(90deg,#f7fbff,#9ecae1,#4292c6,#08519c,#08306b); }}
.opacity-row {{ display:grid; grid-template-columns:72px 1fr 36px; gap:8px; align-items:center; font-size:.72rem; margin:4px 0; color:var(--muted); }}
.opacity-row input[type=range] {{ width:100%; accent-color:var(--accent); }}
.layer-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:6px; }}
.group-label {{ grid-column:1 / -1; margin:6px 0 0; font:700 .62rem Syne,sans-serif; letter-spacing:.1em; text-transform:uppercase; color:#7d91a1; }}
.layer-btn {{
  position:relative; display:flex; align-items:center; gap:7px; min-height:34px;
  padding:6px 8px 6px 28px; border-radius:8px; border:1px solid transparent;
  background:rgba(255,255,255,.35); cursor:pointer; font-size:.72rem; font-weight:600;
  transition:background .14s, border-color .14s, color .14s;
}}
.layer-btn input {{ position:absolute; left:8px; top:50%; transform:translateY(-50%); margin:0; accent-color:var(--accent); }}
.layer-btn:hover {{ background:rgba(255,255,255,.7); }}
.layer-btn:has(input:checked) {{ background:rgba(13,143,156,.12); border-color:rgba(13,143,156,.35); color:var(--accent-deep); }}
.storm-toggles {{ display:grid; grid-template-columns:1fr 1fr; gap:6px; margin:0 0 6px; }}
details.drawer {{ font-size:.76rem; color:var(--muted); }}
details.drawer > summary {{
  cursor:pointer; list-style:none; font:700 .66rem Syne,sans-serif; letter-spacing:.1em;
  text-transform:uppercase; color:var(--ink-soft); padding:2px 0 8px;
  display:flex; align-items:center; justify-content:space-between;
}}
details.drawer > summary::-webkit-details-marker {{ display:none; }}
details.drawer > summary::after {{ content:"+"; font:700 .9rem "IBM Plex Mono",monospace; color:var(--accent); transition:transform .2s var(--ease); }}
details.drawer[open] > summary::after {{ content:"–"; }}
.drawer-note {{ margin:0 0 8px; font-size:.72rem; line-height:1.35; color:var(--muted); }}
.map-stage {{
  position:relative; min-height:0; height:100%;
  background:
    radial-gradient(ellipse 80% 60% at 50% 40%, rgba(8,59,72,.08), transparent 70%),
    #0a1a22;
}}
.map-el {{ position:absolute; inset:0; }}
.pane-label {{
  position:absolute; z-index:1000; top:14px; left:54px; padding:7px 12px; border-radius:8px;
  background:rgba(7,20,28,.78); color:#dff2f4; border:1px solid rgba(255,255,255,.08);
  font:700 .7rem Syne,sans-serif; letter-spacing:.02em; backdrop-filter:blur(10px);
  animation:riseIn .5s var(--ease) .1s both;
}}
.radar-hud {{
  position:absolute; z-index:1100; left:50%; bottom:14px; transform:translateX(-50%);
  width:min(820px, calc(100% - 20px));
  display:grid; grid-template-columns:auto 1fr auto; gap:12px 16px; align-items:center;
  padding:12px 14px 10px; border-radius:16px;
  background:linear-gradient(180deg, rgba(8,28,36,.94), rgba(5,16,22,.92));
  color:#e7f3f5; border:1px solid rgba(255,255,255,.08); box-shadow:0 22px 56px rgba(0,0,0,.35);
  backdrop-filter:blur(16px); animation:riseIn .55s var(--ease) .15s both;
}}
.radar-hud .play {{
  width:46px; height:46px; border-radius:12px; border:0; cursor:pointer;
  background:linear-gradient(180deg,#22c9d4,#0e8f9c); color:#042227; font:700 .95rem Syne,sans-serif;
  transition:transform .15s var(--ease), filter .15s;
}}
.radar-hud .play:hover {{ transform:scale(1.04); filter:brightness(1.05); }}
.radar-hud.playing .play {{ animation:playGlow 1.6s ease-out infinite; }}
.radar-hud .clock {{ font:750 .98rem Syne,sans-serif; letter-spacing:-.02em; }}
.radar-hud .sub {{ font-size:.7rem; opacity:.72; margin-top:2px; font-weight:500; }}
.radar-hud .legend {{ display:flex; flex-direction:column; gap:4px; align-items:flex-end; font-size:.66rem; opacity:.9; }}
.radar-hud .bar {{ width:120px; height:7px; border-radius:999px; background:linear-gradient(90deg,#0b1d2a,#1a6f7a,#1ae4b6,#a2fc3c,#f9ba38,#e8332b); }}
.radar-hud .bar.susc {{ background:linear-gradient(90deg,#fff7bc,#fec44f,#d95f0e,#7f2704); }}
.radar-hud .scrub {{
  grid-column:1 / -1; width:100%; accent-color:#1bc0cd; height:18px; cursor:pointer; margin:0;
}}
.selected-card {{
  position:absolute; z-index:1050; top:54px; right:14px; width:min(300px,calc(100% - 28px));
  background:rgba(255,255,255,.94); border:1px solid rgba(8,40,52,.1); border-radius:12px;
  padding:12px 14px; box-shadow:0 16px 40px rgba(5,20,28,.22); display:none;
  backdrop-filter:blur(12px); transform-origin:top right;
}}
.selected-card.on {{ display:block; animation:riseIn .28s var(--ease), selectPulse .7s ease-out; }}
.selected-card .sel-kicker {{ font:700 .6rem Syne,sans-serif; letter-spacing:.12em; text-transform:uppercase; color:var(--muted); margin-bottom:4px; }}
.selected-card h3 {{ margin:0 0 4px; font:750 .95rem Syne,sans-serif; letter-spacing:-.02em; }}
.selected-card p {{ margin:0; font-size:.76rem; color:var(--muted); line-height:1.4; }}
.selected-card .sel-close {{
  position:absolute; top:8px; right:8px; width:26px; height:26px; border:0; border-radius:7px;
  background:rgba(8,40,52,.06); color:var(--ink-soft); cursor:pointer; font:700 .8rem Figtree,sans-serif;
}}
.selected-card .sel-close:hover {{ background:rgba(8,40,52,.12); }}
.empty {{ padding:16px 8px; text-align:center; color:var(--muted); font-size:.78rem; }}
.leaflet-image-layer.precip-radar,
.leaflet-image-layer.depth-radar,
.leaflet-image-layer.susc-radar {{
  -webkit-mask-image: radial-gradient(ellipse 92% 88% at 50% 50%, #000 58%, transparent 100%);
  mask-image: radial-gradient(ellipse 92% 88% at 50% 50%, #000 58%, transparent 100%);
  image-rendering: auto;
  filter: saturate(1.1) contrast(1.05);
  transition:opacity .25s ease;
}}
.leaflet-image-layer.precip-radar {{ mix-blend-mode: screen; }}
.leaflet-control-zoom a {{ border-radius:8px !important; }}
</style>
</head>
<body>
<aside>
  <div class="brand">
    <div class="brand-kicker">Ida research replay</div>
    <div class="brand-mark">Asset Decision Desk</div>
    <div class="brand-tag">Ranked wet roads &amp; stations — click to inspect.</div>
  </div>
  <p class="honesty-line">Research only · NOT NWS · cm-scale HAND ranking, not street-truth depths.</p>
  <div id="assetBanner"></div>

  <section class="section">
    <h2>Affected assets <span class="hint">click → fly</span></h2>
    <div id="deskSummary" class="metric"><span>Loading…</span><b>—</b></div>
    <div class="chip-row" id="listModeChips" role="group" aria-label="List mode">
      <button type="button" class="chip active" data-mode="shortlist">Shortlist</button>
      <button type="button" class="chip" data-mode="all">All</button>
    </div>
    <div class="chip-row" id="typeChips" role="group" aria-label="Asset type">
      <button type="button" class="chip active" data-type="all">All</button>
      <button type="button" class="chip" data-type="road">Roads</button>
      <button type="button" class="chip" data-type="station">Stations</button>
      <button type="button" class="chip" data-type="facility">Facilities</button>
    </div>
    <div class="filters">
      <div>
        <label class="caption" for="bandFilter">Depth band</label>
        <select id="bandFilter">
          <option value="all">All wet (≥3 cm)</option>
          <option value="ponding">≥3 cm</option>
          <option value="deep_ponding" selected>≥8 cm</option>
          <option value="hazard">≥15 cm</option>
        </select>
      </div>
      <div>
        <label class="caption" for="assetSearch">Search</label>
        <input id="assetSearch" type="search" placeholder="Name / id…" autocomplete="off">
      </div>
    </div>
    <div class="asset-list" id="assetList" aria-label="Ranked wet assets"><div class="empty">Loading ranked assets…</div></div>
  </section>

  <section class="section" id="floodnetPeaksPanel">
    <details class="drawer">
      <summary>FloodNet peaks</summary>
      <p class="drawer-note">Post-level Ida OOM check — does not rescale citywide HAND.</p>
      <div id="floodnetSummary" class="metric"><span>Loading…</span><b>—</b></div>
      <div id="floodnetMeta" class="metric" style="display:none"><span>Primary HAND @ posts</span><b>—</b></div>
      <label class="layer-btn"><input id="lyFloodNet" type="checkbox" checked>FloodNet posts on map</label>
      <div class="floodnet-list" id="floodnetList" aria-label="FloodNet Ida peak comparison"><div class="empty">Loading sensor peaks…</div></div>
    </details>
  </section>

  <section class="section">
    <details class="drawer">
      <summary>Storm layers</summary>
      <div class="metric"><span>Path</span><b style="font-size:.68rem">MRMS QPE Ida</b></div>
      <div class="metric" id="timeWindowMetric"><span>Window</span><b style="font-size:.62rem" id="timeWindowVal">+0…+36h</b></div>
      <div class="storm-toggles">
        <label class="layer-btn"><input id="lyDepthTot" type="checkbox" checked>Depth</label>
        <label class="layer-btn"><input id="lyE2" type="checkbox" checked>Precip</label>
      </div>
      <div class="opacity-row"><span>Precip</span><input id="opPrecip" type="range" min="10" max="85" value="34"><span id="opPrecipVal">34%</span></div>
      <div class="opacity-row"><span>Depth</span><input id="opDepth" type="range" min="15" max="90" value="68"><span id="opDepthVal">68%</span></div>
      <div class="legend-swatch precip" title="Precip"></div>
      <div class="legend-swatch depth" title="Depth"></div>
      <span id="depthTimelineNote" hidden></span>
      <span id="pathHonesty" hidden></span>
    </details>
  </section>

  <section class="section">
    <details class="drawer" id="screeningDetails">
      <summary>Screening</summary>
      <p class="drawer-note">Uncalibrated index — not probability or depth.</p>
      <div class="opacity-row"><span>Susc.</span><input id="opSusc" type="range" min="10" max="90" value="48"><span id="opSuscVal">48%</span></div>
      <div class="legend-swatch susc"></div>
      <label class="layer-btn"><input id="lySusc" type="checkbox">Show screening</label>
    </details>
  </section>

  <section class="section">
    <details class="drawer">
      <summary>Advanced</summary>
      <div class="filters" style="grid-template-columns:1fr 1fr">
        <div><label class="caption" for="extentSelect">Extent</label><select id="extentSelect"></select></div>
        <div><label class="caption" for="eventSelect">Event</label><select id="eventSelect"></select></div>
      </div>
      <label class="caption" for="stormPathSelect" style="margin-top:6px">Scenario path</label>
      <select id="stormPathSelect" aria-label="Scenario path"></select>
      <div class="layer-grid" style="margin-top:8px">
        <div class="group-label">Alternate</div>
        <label class="layer-btn"><input id="lySfincs" type="checkbox">SFINCS Queens</label>
        <label class="layer-btn"><input id="lyE2Tot" type="checkbox">Storm-total</label>
        <div class="group-label">Exposure</div>
        <label class="layer-btn"><input id="lySta" type="checkbox">Stations</label>
        <label class="layer-btn"><input id="lyRoads" type="checkbox">Roads</label>
        <label class="layer-btn"><input id="lyFac" type="checkbox">Facilities</label>
        <label class="layer-btn"><input id="ly311" type="checkbox">311</label>
        <div class="group-label">Context</div>
        <label class="layer-btn"><input id="lyFema" type="checkbox">FEMA NFHL</label>
        <label class="layer-btn"><input id="lyNwm" type="checkbox">NWM</label>
        <label class="layer-btn"><input id="lyGauges" type="checkbox">AHPS</label>
        <label class="layer-btn"><input id="lyBuilt" type="checkbox">Built</label>
      </div>
      <div id="validationPanel" class="drawer-note" style="margin-top:8px">Limitations-first · exploratory only.</div>
    </details>
  </section>
</aside>

<div class="map-stage" id="mapStage">
  <div class="pane-label" id="leftLabel">Decision Desk · Ida</div>
  <div id="mapLeft" class="map-el"></div>
  <div class="selected-card" id="selectedCard">
    <button type="button" class="sel-close" id="selClose" aria-label="Close">×</button>
    <div class="sel-kicker" id="selKicker">Selected asset</div>
    <h3 id="selName">—</h3>
    <p id="selBody">—</p>
  </div>
  <div class="radar-hud" id="radarHud">
    <button type="button" class="play" id="hudPlay" aria-label="Play or pause storm loop">▶</button>
    <div>
      <div class="clock" id="hudClock">—</div>
      <div class="sub" id="hudSub">MRMS soft metro · +0…+36h · not NEXRAD</div>
    </div>
    <div class="legend">
      <span id="hudLegendLabel">Precip · context</span>
      <div class="bar" id="hudLegendBar"></div>
    </div>
    <input class="scrub" id="hudScrub" type="range" min="0" max="{n - 1}" value="0" aria-label="Storm lead scrubber">
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
let playing = false, playTimer = null, leadIndex = 0;
let desk = null, wetLayer = null, selectedLayer = null, selectedId = null;
let floodnetLayer = null, floodnetStations = [], selectedFloodnetId = null;
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
  leadIndex = i;
  const scrub = document.getElementById("hudScrub");
  if (scrub) {{ scrub.max = Math.max(frames.length - 1, 0); scrub.value = String(i); }}
  const clock = (f.valid_time || "").replace("T", " ");
  document.getElementById("hudClock").textContent = clock + " UTC";
  const depthLead = (di >= 0 && depthCumFrames[di]) ? depthCumFrames[di].lead_hours : null;
  const depthBit = depthLead != null ? (" · depth +" + depthLead + "h") : "";
  document.getElementById("hudSub").textContent =
    "+" + f.lead_hours + "h · " + (f.temporal_blend ? "blend" : "native") + depthBit + " · awareness";
  document.getElementById("leftLabel").textContent = "Decision Desk · " + (activePath.label || "Ida");
}}

function setPlaying(on) {{
  playing = on;
  document.getElementById("hudPlay").textContent = on ? "❚❚" : "▶";
  document.getElementById("radarHud").classList.toggle("playing", !!on);
  if (playTimer) {{ clearInterval(playTimer); playTimer = null; }}
  if (!on || !frames.length) return;
  playTimer = setInterval(() => {{
    leadIndex = (leadIndex + 1) % frames.length;
    setLead(leadIndex);
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
  document.getElementById("selKicker").textContent = typeLabel(a.asset_type) + " · #" + a.rank;
  document.getElementById("selName").textContent = a.name;
  document.getElementById("selBody").innerHTML =
    "<b>" + a.max_depth_cm.toFixed(1) + " cm</b> · " + a.band_label + " · " + leadLabel(a) +
    "<br><span style='color:#9a4a12'>Research only — not an SOP trigger.</span>";
  card.classList.remove("on");
  void card.offsetWidth;
  card.classList.add("on");
}}

function clearSelection() {{
  selectedId = null;
  if (selectedLayer) {{ mapLeft.removeLayer(selectedLayer); selectedLayer = null; }}
  document.getElementById("selectedCard").classList.remove("on");
  renderAssetList();
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
      `<span>Wet · metro HAND</span><b>${{c.wet_total||0}} · R${{c.roads||0}} S${{c.stations||0}} F${{c.facilities||0}}</b>`;
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
      pointToLayer: (f,ll) => L.circleMarker(ll, {{ radius:6, fillColor:"#c45c26", color:"#7c2d12", weight:1, fillOpacity:0.95, pane:"pointPane" }})
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

  const scoresName = (manifest.validation_dashboard && manifest.validation_dashboard.scores) || "validation_scores.json";
  fetch(assets + scoresName, {{ cache:"no-cache" }}).then(r => r.ok ? r.json() : null).catch(() => null).then(scores => {{
    const el = document.getElementById("validationPanel");
    if (!el || !scores) return;
    // Desk FloodNet panel owns the primary reproduction story; Advanced keeps limitations-only fallback.
    if (el.dataset.floodnetWired === "1") return;
    const conf = scores.confidence ? scores.confidence.level : "low";
    const note = (scores.confidence && scores.confidence.note) || "Exploratory collocation only.";
    el.innerHTML = `Exploratory (${{conf}}) · ${{note}}`;
  }});
}}

function fmtM(x) {{
  return (x == null || Number.isNaN(Number(x))) ? "—" : Number(x).toFixed(3);
}}

function floodnetPopupHtml(p) {{
  return `<b>${{p.sensor_name || p.sensor_id || "FloodNet"}}</b><br>` +
    `obs ${{fmtM(p.obs_peak_m)}} m · cal ${{fmtM(p.hotspot_cal_m)}} m · resid ${{fmtM(p.residual_m)}} m` +
    `<br><span style="opacity:.75">Post OOM check · not citywide HAND</span>`;
}}

function selectFloodnetStation(sensorId) {{
  selectedFloodnetId = sensorId;
  document.querySelectorAll("#floodnetList .asset-row").forEach(btn => {{
    btn.classList.toggle("selected", btn.dataset.id === sensorId);
  }});
  if (!floodnetLayer) return;
  floodnetLayer.eachLayer(layer => {{
    const p = layer.feature && layer.feature.properties;
    if (!p || p.sensor_id !== sensorId) return;
    const ll = layer.getLatLng();
    mapLeft.flyTo(ll, Math.max(mapLeft.getZoom(), 14), {{ duration: 0.65 }});
    layer.openPopup();
  }});
}}

function renderFloodnetList(stations) {{
  const list = document.getElementById("floodnetList");
  if (!list) return;
  if (!stations.length) {{
    list.innerHTML = '<div class="empty">No FloodNet Ida peaks loaded.</div>';
    return;
  }}
  const ranked = stations.slice().sort((a, b) => (b.obs_peak_m || 0) - (a.obs_peak_m || 0));
  list.innerHTML = ranked.map(p => {{
    const ok = !!p.oom_ok;
    const obsCm = p.obs_peak_m == null ? "—" : (Number(p.obs_peak_m) * 100).toFixed(1);
    const calCm = p.hotspot_cal_m == null ? "—" : (Number(p.hotspot_cal_m) * 100).toFixed(1);
    const resCm = p.residual_m == null ? "—" : ((Number(p.residual_m) >= 0 ? "+" : "") + (Number(p.residual_m) * 100).toFixed(1));
    return `<button type="button" class="asset-row${{selectedFloodnetId === p.sensor_id ? " selected" : ""}}" data-id="${{p.sensor_id}}">` +
      `<div class="top"><span class="name">${{p.sensor_name || p.sensor_id}}</span>` +
      `<span class="depth">${{obsCm}} cm</span></div>` +
      `<div class="meta"><span class="type-pill">${{p.borough || "NYC"}}</span>` +
      `<span class="band ${{ok ? "oom-ok" : "oom-miss"}}">${{ok ? "OOM" : "miss"}}</span>` +
      `<span>cal ${{calCm}}</span><span>${{resCm}}</span></div></button>`;
  }}).join("");
  list.querySelectorAll(".asset-row").forEach(btn => {{
    btn.onclick = () => selectFloodnetStation(btn.dataset.id);
  }});
}}

function loadFloodNetProduct() {{
  const fnName = (manifest.validation_dashboard && manifest.validation_dashboard.floodnet)
    || (manifest.validation_floodnet && manifest.validation_floodnet.scores)
    || "floodnet_validation.json";
  const reproName = (manifest.validation_dashboard && manifest.validation_dashboard.ida_reproduction)
    || (manifest.ida_event_reproduction && manifest.ida_event_reproduction.scores)
    || "ida_floodnet_reproduction.json";
  const hotspotGeo = (manifest.ida_event_reproduction && manifest.ida_event_reproduction.stations_geojson)
    || "floodnet_ida_hotspot_stations.geojson";

  Promise.all([
    fetchGeoJSON(hotspotGeo).catch(() => null),
    fetch(assets + reproName, {{ cache:"no-cache" }}).then(r => r.ok ? r.json() : null).catch(() => null),
    fetch(assets + fnName, {{ cache:"no-cache" }}).then(r => r.ok ? r.json() : null).catch(() => null),
  ]).then(([geo, repro, fn]) => {{
    const summaryEl = document.getElementById("floodnetSummary");
    const metaEl = document.getElementById("floodnetMeta");
    const advEl = document.getElementById("validationPanel");

    if (geo && geo.features) {{
      floodnetStations = geo.features.map(f => Object.assign({{}}, f.properties || {{}}, {{
        lon: f.geometry && f.geometry.coordinates ? f.geometry.coordinates[0] : null,
        lat: f.geometry && f.geometry.coordinates ? f.geometry.coordinates[1] : null,
      }}));
      floodnetLayer = L.geoJSON(geo, {{
        pointToLayer: (f, ll) => {{
          const p = f.properties || {{}};
          const ok = !!p.oom_ok;
          return L.circleMarker(ll, {{
            radius: 8,
            fillColor: ok ? "#0a8a96" : "#8d3d14",
            color: "#071018",
            weight: 2,
            fillOpacity: 0.95,
            pane: "pointPane",
          }});
        }},
        onEachFeature: (f, layer) => {{
          const p = f.properties || {{}};
          layer.bindPopup(floodnetPopupHtml(p));
          layer.bindTooltip((p.sensor_name || p.sensor_id || "FloodNet") + " · obs " + fmtM(p.obs_peak_m) + " m");
          layer.on("click", () => {{ selectedFloodnetId = p.sensor_id; renderFloodnetList(floodnetStations); }});
        }},
      }});
      bindToggle("lyFloodNet", floodnetLayer);
      renderFloodnetList(floodnetStations);
    }} else {{
      document.getElementById("floodnetList").innerHTML = '<div class="empty">floodnet_ida_hotspot_stations.geojson missing — run scripts/calibrate_ida_floodnet_hotspot.py</div>';
    }}

    if (repro && repro.summary && repro.summary.hotspot_calibrated) {{
      const h = repro.summary.hotspot_calibrated;
      const hand = repro.summary.primary_hand || {{}};
      const cal = repro.calibration || {{}};
      const loo = repro.leave_one_out || {{}};
      if (summaryEl) {{
        summaryEl.innerHTML =
          `<span>Hotspot cal @ posts</span>` +
          `<b>RMSE ${{fmtM(h.rmse_m)}} m · OOM ${{h.oom_ok_n || 0}}/${{h.n || 0}}</b>`;
      }}
      if (metaEl) {{
        metaEl.style.display = "flex";
        metaEl.innerHTML =
          `<span>HAND dry/cm · LOO ${{fmtM(loo.rmse_m)}} m</span>` +
          `<b>bias ${{fmtM(h.bias_m)}} · scale ${{fmtM(cal.scale)}}</b>`;
      }}
      if (advEl) {{
        advEl.dataset.floodnetWired = "1";
        advEl.innerHTML =
          `FloodNet hotspot RMSE ${{fmtM(h.rmse_m)}} m · OOM ${{h.oom_ok_n || 0}}/${{h.n || 0}} · LOO ${{fmtM(loo.rmse_m)}} m · HAND unchanged.`;
      }}
      if ((!geo || !geo.features) && Array.isArray(repro.stations)) {{
        floodnetStations = repro.stations;
        renderFloodnetList(floodnetStations);
      }}
      return;
    }}

    if (fn && fn.summary) {{
      const rmse = fn.summary.peak_rmse_m;
      const bias = fn.summary.peak_bias_m && fn.summary.peak_bias_m.mean;
      const n = fn.summary.n_sensors;
      if (summaryEl) {{
        summaryEl.innerHTML = `<span>FloodNet vs primary HAND</span><b>RMSE ${{fmtM(rmse)}} m · n=${{n}}</b>`;
      }}
      if (advEl) {{
        advEl.dataset.floodnetWired = "1";
        advEl.innerHTML = `FloodNet vs HAND · n=${{n}} · RMSE ${{fmtM(rmse)}} m · bias ${{fmtM(bias)}} m.`;
      }}
      return;
    }}

    if (summaryEl) {{
      summaryEl.innerHTML = `<span>FloodNet reproduction</span><b>unavailable</b>`;
    }}
  }}).catch(err => {{
    const summaryEl = document.getElementById("floodnetSummary");
    if (summaryEl) summaryEl.innerHTML = `<span>FloodNet load failed</span><b>—</b>`;
    document.getElementById("floodnetList").innerHTML = '<div class="empty">Failed to load FloodNet reproduction assets.</div>';
    console.warn(err);
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
document.getElementById("hudScrub").oninput = (e) => {{
  setPlaying(false);
  setLead(+e.target.value);
}};
document.getElementById("selClose").onclick = clearSelection;
document.addEventListener("keydown", (e) => {{
  if (e.key === "Escape") clearSelection();
  if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "SELECT" || e.target.tagName === "TEXTAREA")) return;
  if (e.key === "ArrowRight" || e.key === "ArrowLeft") {{
    e.preventDefault();
    setPlaying(false);
    const step = e.key === "ArrowRight" ? 1 : -1;
    if (!frames.length) return;
    setLead((leadIndex + step + frames.length) % frames.length);
  }}
  if (e.key === " " && e.target === document.body) {{
    e.preventDefault();
    setPlaying(!playing);
  }}
}});
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
      b.innerHTML = "<b>SFINCS Queens</b> — alternate hydro track; magnitudes not comparable to primary HAND.";
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
loadFloodNetProduct();
loadOptionalLayers();
setPlaying(true);
</script>
</body>
</html>
"""
    out = FIGURES_DIR / "product_map.html"
    out.write_text(html)
    return out
