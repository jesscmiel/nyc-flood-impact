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

# Curated named NYC click targets — all ≥8 cm deep ponding on current desk.
DEMO_SHORTLIST_IDS = (
    "stations:194:Smith–9th Streets",  # 11.1 cm — iconic Ida station
    "road:25430129",  # Van Wyck Expressway 9.4 cm
    "facilities:40:Staten Island University Hospital",  # 8.7 cm
    "road:37394898",  # Myrtle Avenue 8.2 cm
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
.asset-row.top-hit {{ background:rgba(13,143,156,.09); }}
.asset-row.top-hit::before {{ background:var(--accent); }}
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
.selected-card .sel-chips {{ display:flex; flex-wrap:wrap; gap:5px; margin:8px 0 6px; }}
.selected-card .sel-chip {{
  font:600 .62rem "IBM Plex Mono",monospace; padding:3px 7px; border-radius:6px;
  border:1px solid var(--line); background:rgba(8,40,52,.04); color:var(--ink-soft);
}}
.selected-card .sel-chip.access-open {{ border-color:rgba(13,143,156,.35); color:var(--accent-deep); }}
.selected-card .sel-chip.access-watch {{ border-color:rgba(154,74,18,.35); color:var(--warn); background:var(--warn-bg); }}
.selected-card .sel-chip.access-limited {{ border-color:rgba(185,28,28,.4); color:#9f1239; background:rgba(185,28,28,.08); }}
.selected-card .sel-hint {{
  margin-top:6px; padding-top:6px; border-top:1px solid var(--line-soft);
  font-size:.72rem; color:var(--ink-soft); line-height:1.4; font-weight:600;
}}
.selected-card .sel-access-note {{ margin-top:4px; font-size:.66rem; color:var(--muted); line-height:1.35; }}
.asset-row .meta .access-pill {{
  font:600 .58rem "IBM Plex Mono",monospace; padding:1px 5px; border-radius:4px;
  border:1px solid var(--line-soft); color:var(--muted);
}}
.asset-row .meta .access-pill.limited {{ color:#9f1239; border-color:rgba(185,28,28,.35); }}
.asset-row .meta .access-pill.watch {{ color:var(--warn); border-color:rgba(154,74,18,.3); }}
.empty {{ padding:16px 8px; text-align:center; color:var(--muted); font-size:.78rem; }}
.leaflet-image-layer.precip-radar,
.leaflet-image-layer.depth-radar,
.leaflet-image-layer.susc-radar {{
  -webkit-mask-image: radial-gradient(ellipse 96% 92% at 50% 50%, #000 62%, transparent 100%);
  mask-image: radial-gradient(ellipse 96% 92% at 50% 50%, #000 62%, transparent 100%);
  image-rendering: auto;
  filter: saturate(1.28) contrast(1.14) brightness(1.04);
  transition:opacity .22s ease;
}}
.leaflet-image-layer.precip-radar {{
  mix-blend-mode: screen;
  filter: saturate(1.45) contrast(1.22) brightness(1.08);
}}
.leaflet-image-layer.depth-radar {{
  mix-blend-mode: soft-light;
  filter: saturate(1.2) contrast(1.18);
}}
.leaflet-image-layer.susc-radar {{ mix-blend-mode: multiply; filter: saturate(1.35) contrast(1.18); }}
.sparkline-wrap {{
  margin-top:8px; padding-top:8px; border-top:1px solid rgba(255,255,255,.12);
}}
.sparkline-wrap .spark-cap {{
  font:700 .58rem Syne,sans-serif; letter-spacing:.1em; text-transform:uppercase;
  color:#9fd7de; margin-bottom:4px;
}}
.sparkline-wrap svg {{ display:block; width:100%; height:44px; }}
.sparkline-wrap .spark-readout {{
  margin-top:2px; font:600 .66rem "IBM Plex Mono",monospace; color:#cfe8ec;
}}
.shortlist-actions {{
  display:flex; flex-wrap:wrap; gap:6px; margin:8px 0 0;
}}
.shortlist-actions button {{
  border:1px solid var(--line); background:#fff; color:var(--ink-soft);
  border-radius:8px; padding:6px 9px; font:600 .68rem Figtree,sans-serif; cursor:pointer;
}}
.shortlist-actions button:hover {{ border-color:var(--accent); color:var(--accent-deep); }}
.shortlist-actions .status {{
  flex:1 1 100%; font-size:.64rem; color:var(--muted); min-height:1em;
}}
.drawer .drawer {{
  margin:8px 0 0; border:1px solid var(--line-soft); border-radius:10px; padding:0 8px 6px;
  background:rgba(8,40,52,.03);
}}
.drawer .drawer > summary {{
  font:700 .62rem Syne,sans-serif; letter-spacing:.08em; text-transform:uppercase;
  color:#7d91a1; padding:8px 2px;
}}
@media print {{
  body {{ display:block; background:#fff; }}
  aside {{ max-height:none !important; border:0 !important; }}
  .map-stage, .radar-hud, .map-key-float, .honesty-line, .brand::before, .brand::after {{ display:none !important; }}
  .print-snapshot {{ display:block !important; }}
}}
.print-snapshot {{ display:none; padding:16px; font:500 .85rem Figtree,sans-serif; }}
.print-snapshot h1 {{ font:800 1.2rem Syne,sans-serif; margin:0 0 8px; }}
.print-snapshot pre {{ white-space:pre-wrap; background:#f4f8fa; padding:12px; border-radius:8px; }}
.leaflet-control-zoom a {{ border-radius:8px !important; }}
.marker-key {{
  margin:8px 0 0; padding:10px 11px; border-radius:12px; font-size:.68rem; line-height:1.35;
  color:var(--muted); background:rgba(8,40,52,.04); border:1px solid var(--line-soft);
}}
.marker-key > b {{ display:block; color:var(--ink-soft); font:700 .62rem Syne,sans-serif;
  letter-spacing:.1em; text-transform:uppercase; margin-bottom:8px; }}
.map-dot-toggles {{ display:grid; grid-template-columns:1fr 1fr; gap:5px; margin:0 0 10px; }}
.map-dot-toggles .layer-btn {{ font-size:.7rem; padding:7px 8px 7px 26px; }}
.map-legend-rows {{ display:flex; flex-direction:column; gap:6px; }}
.map-legend-row {{ display:flex; align-items:center; gap:8px; color:var(--ink-soft); font-size:.7rem; }}
.map-legend-row span {{ color:var(--muted); }}
.leg-sw {{ flex:0 0 auto; width:18px; height:18px; position:relative; }}
.leg-sw svg {{ display:block; width:18px; height:18px; }}
.access-legend {{
  margin-top:8px; padding-top:8px; border-top:1px dashed var(--line-soft);
  display:flex; flex-direction:column; gap:5px;
}}
.access-legend .cap {{
  font:700 .58rem Syne,sans-serif; letter-spacing:.1em; text-transform:uppercase; color:#7d91a1;
}}
.map-key-float {{
  position:absolute; z-index:650; left:12px; bottom:86px; max-width:min(280px, calc(100% - 24px));
  padding:10px 12px; border-radius:12px; background:rgba(7,24,32,.88); color:#d7eef2;
  border:1px solid rgba(255,255,255,.12); box-shadow:0 10px 28px rgba(0,0,0,.28);
  font-size:.68rem; line-height:1.35; backdrop-filter:blur(10px);
  animation:riseIn .4s var(--ease);
}}
.map-key-float.collapsed .map-key-float-body {{ display:none; }}
.map-key-float-head {{
  display:flex; align-items:center; justify-content:space-between; gap:8px;
  font:700 .62rem Syne,sans-serif; letter-spacing:.1em; text-transform:uppercase; color:#9fd7de;
}}
.map-key-float-head button {{
  border:0; background:rgba(255,255,255,.08); color:#cfe8ec; border-radius:6px;
  width:22px; height:22px; cursor:pointer; font:700 .75rem Figtree,sans-serif;
}}
.map-key-float-head button:hover {{ background:rgba(255,255,255,.16); }}
.map-key-float-body {{ margin-top:8px; display:flex; flex-direction:column; gap:6px; }}
.map-key-float .map-legend-row {{ color:#e8f7f9; }}
.map-key-float .map-legend-row span {{ color:#9eb8c0; }}
.leaflet-div-icon.access-div {{
  background:transparent; border:0; width:24px !important; height:24px !important;
}}
.access-marker {{
  width:22px; height:22px; display:flex; align-items:center; justify-content:center;
  font:700 .48rem Syne,sans-serif; letter-spacing:.04em; color:#fff;
  border:2px solid; box-shadow:0 1px 4px rgba(0,0,0,.35); line-height:1;
}}
.access-marker.dot {{ border-radius:4px; background:rgba(180,83,9,.94); border-color:#7c2d12; border-style:dashed; }}
.access-marker.dot.limited {{ background:rgba(159,18,57,.94); border-color:#7f1d1d; }}
.access-marker.ev511 {{
  clip-path:polygon(50% 6%, 94% 88%, 6% 88%); border:0; border-radius:0;
  background:#b45309; box-shadow:none; font-size:.4rem; padding-top:7px;
}}
.access-marker.ev511.limited {{ background:#9f1239; }}
.access-marker.mta {{ border-radius:50%; background:rgba(13,143,156,.94); border-color:#045963; border-style:solid; }}
.access-marker.mta.limited {{ background:rgba(159,18,57,.94); border-color:#7f1d1d; border-style:dashed; }}
.access-marker.mta.watch {{ border-style:dashed; border-color:#b45309; background:rgba(180,83,9,.9); }}
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
    <div class="shortlist-actions" role="group" aria-label="Shortlist snapshot">
      <button type="button" id="btnShareSnapshot">Copy snapshot</button>
      <button type="button" id="btnPrintSnapshot">Print / share</button>
      <div class="status" id="snapshotStatus" aria-live="polite"></div>
    </div>
    <div class="marker-key" id="markerKey">
      <b>Map layers</b>
      <div class="map-dot-toggles" role="group" aria-label="Map dot toggles">
        <label class="layer-btn"><input id="lyWet" type="checkbox" checked>Wet assets</label>
        <label class="layer-btn"><input id="lyTopHits" type="checkbox" checked>Top hits</label>
        <label class="layer-btn"><input id="lyFloodNet" type="checkbox" checked>FloodNet</label>
        <label class="layer-btn"><input id="lyAccess" type="checkbox" checked>DOT / access</label>
      </div>
      <div class="map-legend-rows" aria-label="Teal selection key">
        <div class="map-legend-row">
          <span class="leg-sw" aria-hidden="true"><svg viewBox="0 0 18 18"><circle cx="9" cy="9" r="6.5" fill="rgba(27,192,205,.15)" stroke="#0d8f9c" stroke-width="1.6" stroke-dasharray="3.2 2.4"/></svg></span>
          <span><b style="color:var(--ink-soft)">Dashed teal</b> — top shortlist hit</span>
        </div>
        <div class="map-legend-row">
          <span class="leg-sw" aria-hidden="true"><svg viewBox="0 0 18 18"><circle cx="9" cy="9" r="5.5" fill="#1bc0cd" stroke="#042227" stroke-width="2"/></svg></span>
          <span><b style="color:var(--ink-soft)">Filled teal</b> — selected asset</span>
        </div>
        <div class="map-legend-row">
          <span class="leg-sw" aria-hidden="true"><svg viewBox="0 0 18 18"><line x1="2" y1="9" x2="16" y2="9" stroke="#045963" stroke-width="3.5" stroke-linecap="round"/><line x1="3" y1="3" x2="15" y2="15" stroke="#0d8f9c" stroke-width="1.4" opacity=".85"/></svg></span>
          <span><b style="color:var(--ink-soft)">Teal line-through</b> — selected road</span>
        </div>
      </div>
      <div class="access-legend">
        <div class="cap">DOT / access overlay</div>
        <div class="map-legend-row">
          <span class="leg-sw" aria-hidden="true"><svg viewBox="0 0 18 18"><rect x="3" y="3" width="12" height="12" rx="2" fill="#b45309" stroke="#7c2d12" stroke-width="1.4" stroke-dasharray="2.5 2"/><text x="9" y="12" text-anchor="middle" fill="#fff" font-size="5.5" font-family="Syne,sans-serif" font-weight="700">DOT</text></svg></span>
          <span>Square — NYC DOT speed (watch / limited)</span>
        </div>
        <div class="map-legend-row">
          <span class="leg-sw" aria-hidden="true"><svg viewBox="0 0 18 18"><path d="M9 2.5 L15.5 14.5 H2.5 Z" fill="#9f1239" stroke="#7f1d1d" stroke-width="1"/><text x="9" y="13" text-anchor="middle" fill="#fff" font-size="4.2" font-family="Syne,sans-serif" font-weight="700">511</text></svg></span>
          <span>Triangle — 511-style closure / event</span>
        </div>
        <div class="map-legend-row">
          <span class="leg-sw" aria-hidden="true"><svg viewBox="0 0 18 18"><circle cx="9" cy="9" r="6" fill="#0d8f9c" stroke="#045963" stroke-width="1.5"/><text x="9" y="11.2" text-anchor="middle" fill="#fff" font-size="4.5" font-family="Syne,sans-serif" font-weight="700">MTA</text></svg></span>
          <span>Circle — MTA alert on wet station</span>
        </div>
      </div>
      <p class="drawer-note" style="margin-top:8px">Amber/red wet dots = depth band (≥3 / ≥8 / ≥15). Inventory Stations/Facilities stay under Advanced.</p>
    </div>
  </section>

  <section class="section" id="floodnetPeaksPanel">
    <details class="drawer" open>
      <summary>FloodNet peaks · all 5 Ida posts</summary>
      <p class="drawer-note">Post-level Ida OOM check — does not rescale citywide HAND. All five 2021 posts listed.</p>
      <div id="floodnetSummary" class="metric"><span>Loading…</span><b>—</b></div>
      <div id="floodnetMeta" class="metric" style="display:none"><span>Primary HAND @ posts</span><b>—</b></div>
      <p class="drawer-note">Map toggle lives under <b>Map layers</b> above (FloodNet).</p>
      <div class="floodnet-list" id="floodnetList" aria-label="FloodNet Ida peak comparison"><div class="empty">Loading sensor peaks…</div></div>
      <details class="drawer" id="floodnetLaterDrawer">
        <summary>Later FloodNet events</summary>
        <p class="drawer-note">Post-Ida Open Data archive (optional map layer). Research only.</p>
        <div id="floodnetLaterSummary" class="metric"><span>Loading…</span><b>—</b></div>
        <label class="layer-btn"><input id="lyFloodNetLater" type="checkbox">Show later FloodNet peaks</label>
      </details>
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
      <div class="opacity-row"><span>Precip</span><input id="opPrecip" type="range" min="10" max="92" value="52"><span id="opPrecipVal">52%</span></div>
      <div class="opacity-row"><span>Depth</span><input id="opDepth" type="range" min="15" max="92" value="74"><span id="opDepthVal">74%</span></div>
      <div class="legend-swatch precip" title="Precip"></div>
      <div class="legend-swatch depth" title="Depth"></div>
      <span id="depthTimelineNote" hidden></span>
      <span id="pathHonesty" hidden></span>
    </details>
  </section>

  <section class="section">
    <details class="drawer" id="screeningDetails">
      <summary>Screening</summary>
      <p class="drawer-note">Real MRMS×terrain susceptibility frames (37). Uncalibrated — not probability or depth. Draws above Depth when on. Demo default: closed / off.</p>
      <div class="opacity-row"><span>Susc.</span><input id="opSusc" type="range" min="10" max="90" value="62"><span id="opSuscVal">62%</span></div>
      <div class="legend-swatch susc"></div>
      <label class="layer-btn"><input id="lySusc" type="checkbox">Show screening</label>
    </details>
  </section>

  <section class="section">
    <details class="drawer">
      <summary>Advanced · research only</summary>
      <p class="drawer-note">Collapsed by design — demo stays shortlist + FloodNet + scrubber.</p>
      <details class="drawer">
        <summary>Event / path</summary>
        <div class="filters" style="grid-template-columns:1fr 1fr">
          <div><label class="caption" for="extentSelect">Extent</label><select id="extentSelect"></select></div>
          <div><label class="caption" for="eventSelect">Event</label><select id="eventSelect"></select></div>
        </div>
        <label class="caption" for="stormPathSelect" style="margin-top:6px">Scenario path</label>
        <select id="stormPathSelect" aria-label="Scenario path"></select>
      </details>
      <details class="drawer">
        <summary>Alternate hydro</summary>
        <div class="layer-grid">
          <label class="layer-btn"><input id="lySfincs" type="checkbox">SFINCS Queens</label>
          <label class="layer-btn"><input id="lyE2Tot" type="checkbox">Storm-total</label>
        </div>
      </details>
      <details class="drawer">
        <summary>Access feeds</summary>
        <p class="drawer-note">DOT / 511 / MTA overlay defaults <b>on</b> — use <b>Map layers → DOT / access</b> to hide.</p>
        <label class="layer-btn"><input id="lyAccessLive" type="checkbox">Prefer live DOT / 511 / MTA feeds</label>
        <div id="accessFeedStatus" class="drawer-note" style="margin-top:4px">Fixture default · Ida replay</div>
      </details>
      <details class="drawer">
        <summary>Archived open layers</summary>
        <p class="drawer-note">Optional Open Data samples — off by default. Not sewer performance / not official closures.</p>
        <label class="layer-btn"><input id="lyArchive511" type="checkbox">Archived 511-style</label>
        <label class="layer-btn"><input id="lyDepBasins" type="checkbox">DEP catch basins (sample)</label>
        <label class="layer-btn"><input id="lyBuildings" type="checkbox">Building footprints (sample)</label>
        <div id="archiveLayersStatus" class="drawer-note" style="margin-top:4px">Load on toggle…</div>
      </details>
      <details class="drawer">
        <summary>Exposure inventory</summary>
        <div class="layer-grid">
          <label class="layer-btn"><input id="lySta" type="checkbox">Stations</label>
          <label class="layer-btn"><input id="lyRoads" type="checkbox">Roads</label>
          <label class="layer-btn"><input id="lyFac" type="checkbox">Facilities</label>
          <label class="layer-btn"><input id="ly311" type="checkbox">311</label>
        </div>
      </details>
      <details class="drawer">
        <summary>Context GIS</summary>
        <div class="layer-grid">
          <label class="layer-btn"><input id="lyFema" type="checkbox">FEMA NFHL</label>
          <label class="layer-btn"><input id="lyNwm" type="checkbox">NWM</label>
          <label class="layer-btn"><input id="lyGauges" type="checkbox">AHPS</label>
          <label class="layer-btn"><input id="lyBuilt" type="checkbox">Built</label>
        </div>
      </details>
      <div id="validationPanel" class="drawer-note" style="margin-top:8px">Limitations-first · exploratory only.</div>
    </details>
  </section>
  <div class="print-snapshot" id="printSnapshot" aria-hidden="true">
    <h1>Asset Decision Desk · shortlist snapshot</h1>
    <pre id="printSnapshotBody"></pre>
  </div>
</aside>

<div class="map-stage" id="mapStage">
  <div class="pane-label" id="leftLabel">Decision Desk · Ida</div>
  <div id="mapLeft" class="map-el"></div>
  <div class="selected-card" id="selectedCard">
    <button type="button" class="sel-close" id="selClose" aria-label="Close">×</button>
    <div class="sel-kicker" id="selKicker">Selected asset</div>
    <h3 id="selName">—</h3>
    <p id="selBody">—</p>
    <div class="sel-chips" id="selChips"></div>
    <div class="sparkline-wrap" id="selSparkWrap" hidden>
      <div class="spark-cap">Depth vs lead (HAND cm)</div>
      <svg id="selSpark" viewBox="0 0 220 44" role="img" aria-label="Asset depth sparkline synced to scrubber"></svg>
      <div class="spark-readout" id="selSparkReadout">—</div>
    </div>
    <div class="sel-hint" id="selHint"></div>
    <div class="sel-access-note" id="selAccessNote"></div>
  </div>
  <div class="map-key-float" id="mapKeyFloat">
    <div class="map-key-float-head">
      <span>Map key</span>
      <button type="button" id="mapKeyFloatToggle" aria-label="Collapse map key" aria-expanded="true">–</button>
    </div>
    <div class="map-key-float-body">
      <div class="map-legend-row">
        <span class="leg-sw" aria-hidden="true"><svg viewBox="0 0 18 18"><circle cx="9" cy="9" r="6.5" fill="rgba(27,192,205,.15)" stroke="#1bc0cd" stroke-width="1.6" stroke-dasharray="3.2 2.4"/></svg></span>
        <span>Dashed = top hit</span>
      </div>
      <div class="map-legend-row">
        <span class="leg-sw" aria-hidden="true"><svg viewBox="0 0 18 18"><circle cx="9" cy="9" r="5.5" fill="#1bc0cd" stroke="#042227" stroke-width="2"/></svg></span>
        <span>Filled = selected</span>
      </div>
      <div class="map-legend-row">
        <span class="leg-sw" aria-hidden="true"><svg viewBox="0 0 18 18"><line x1="2" y1="9" x2="16" y2="9" stroke="#7dd3de" stroke-width="3.2" stroke-linecap="round"/><line x1="3" y1="3" x2="15" y2="15" stroke="#1bc0cd" stroke-width="1.3"/></svg></span>
        <span>Line-through = selected road</span>
      </div>
      <div class="map-legend-row">
        <span class="leg-sw" aria-hidden="true"><svg viewBox="0 0 18 18"><rect x="3.5" y="3.5" width="11" height="11" rx="2" fill="#b45309" stroke="#fff" stroke-width="1" stroke-dasharray="2 1.5"/></svg></span>
        <span>DOT square · 511 △ · MTA ○</span>
      </div>
    </div>
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
// Screening above depth so "Show screening" is actually visible (was buried under Depth).
mapLeft.createPane("suscPane"); mapLeft.getPane("suscPane").style.zIndex = 450;
mapLeft.createPane("vectorPane"); mapLeft.getPane("vectorPane").style.zIndex = 650;
mapLeft.createPane("pointPane"); mapLeft.getPane("pointPane").style.zIndex = 670;
mapLeft.createPane("selectPane"); mapLeft.getPane("selectPane").style.zIndex = 700;
L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}", {{
  maxZoom: 19, attribution: "Tiles © Esri"
}}).addTo(mapLeft);

const DEMO_SHORTLIST = {demo_ids_json};
const AUTO_HIGHLIGHT_N = (manifest.asset_decision_desk && manifest.asset_decision_desk.auto_highlight_top_n) || 3;
const secondStorm = manifest.second_storm || {{}};
if (secondStorm.available && EVENTS["henri-2021"]) EVENTS["henri-2021"].available = true;
const eventSel = document.getElementById("eventSelect");
Object.values(EVENTS).forEach(ev => {{
  if (!ev.available) return; // hide placeholders during demos
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
let fadeE2 = null, fadeDepth = null, fadeSusc = null, fadeTimer = null;
let playing = false, playTimer = null, leadIndex = 0;
let desk = null, wetLayer = null, selectedLayer = null, selectedId = null;
let highlightLayer = null, highlightIds = [];
let floodnetLayer = null, floodnetStations = [], selectedFloodnetId = null;
let floodnetLaterLayer = null;
let accessFixture = null, accessLayer = null, accessFeedMode = "fixture";
let archive511Layer = null, depBasinsLayer = null, buildingsLayer = null;
let typeFilter = "all";
let listMode = "shortlist";
let activeEventId = "ida-2021";
const PLAY_MS = 380;
const FADE_MS = 220;

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
  [activeE2, fadeE2, activeSusc, fadeSusc, activeDepth, fadeDepth].forEach(l => {{
    if (l && mapLeft.hasLayer(l)) mapLeft.removeLayer(l);
  }});
  activeE2 = fadeE2 = activeSusc = fadeSusc = activeDepth = fadeDepth = null;
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
    opacity: 0, interactive:false, pane:"rasterPane", className:"precip-radar"
  }}));
  suscLayers = suscFrames.map(f => L.imageOverlay(assets + f.png, suscBounds, {{
    opacity: 0, interactive:false, pane:"suscPane", className:"susc-radar"
  }}));
  // Prefetch a few radar frames so crossfades are less stuttery.
  frames.slice(0, 8).forEach(f => {{ const im = new Image(); im.src = assets + f.png; }});
  suscFrames.slice(0, 4).forEach(f => {{ const im = new Image(); im.src = assets + f.png; }});
  e2Total = activePath.precip?.storm_total_png
    ? L.imageOverlay(assets + activePath.precip.storm_total_png, precipBounds, {{
        opacity: precipOpacity(), pane:"rasterPane", interactive:false, className:"precip-radar"
      }})
    : null;
  const ds = depthSetForPath(activePath.id);
  const depthBounds = overlayBoundsPreferMetro((ds && ds.bounds) || precipBounds);
  depthCumFrames = (ds && ds.cumulative_frames) ? ds.cumulative_frames.slice() : [];
  depthLayers = depthCumFrames.map(fr => L.imageOverlay(assets + fr.png, depthBounds, {{
    opacity: 0, interactive:false, pane:"depthPane", className:"depth-radar"
  }}));
  depthTotal = (ds && ds.storm_total && ds.storm_total.png)
    ? L.imageOverlay(assets + ds.storm_total.png, depthBounds, {{
        opacity: 0, interactive:false, pane:"depthPane", className:"depth-radar"
      }})
    : (manifest.inundation_citywide && manifest.inundation_citywide.png)
      ? L.imageOverlay(assets + manifest.inundation_citywide.png, dataDomainBounds(), {{
          opacity: 0, interactive:false, pane:"depthPane", className:"depth-radar"
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

function screeningOn() {{ return !!document.getElementById("lySusc").checked; }}
function effectiveDepthOpacity() {{
  const base = depthOpacity();
  return screeningOn() ? Math.min(base, 0.32) : base;
}}
function swapOverlay(prev, next, getOpacity, onDone) {{
  if (!next) {{
    if (prev && mapLeft.hasLayer(prev)) mapLeft.removeLayer(prev);
    onDone(null, null);
    return;
  }}
  if (prev === next) {{
    next.setOpacity(getOpacity());
    if (!mapLeft.hasLayer(next)) next.addTo(mapLeft);
    onDone(next, null);
    return;
  }}
  next.setOpacity(0);
  next.addTo(mapLeft);
  requestAnimationFrame(() => {{
    next.setOpacity(getOpacity());
    if (prev && mapLeft.hasLayer(prev)) prev.setOpacity(0);
  }});
  setTimeout(() => {{
    if (prev && mapLeft.hasLayer(prev) && prev !== next) mapLeft.removeLayer(prev);
  }}, FADE_MS);
  onDone(next, prev);
}}

function setLead(i) {{
  if (!frames.length) return;
  i = Math.max(0, Math.min(frames.length - 1, i));
  const f = frames[i];
  [i + 1, i + 2].forEach(j => {{
    const fr = frames[j % frames.length];
    if (fr) {{ const im = new Image(); im.src = assets + fr.png; }}
  }});

  const wantPrecip = document.getElementById("lyE2").checked;
  swapOverlay(activeE2, wantPrecip ? e2Layers[i] : null, precipOpacity, (a, fprev) => {{
    activeE2 = a; fadeE2 = fprev;
  }});

  const wantSusc = screeningOn() && !!suscLayers[i];
  swapOverlay(activeSusc, wantSusc ? suscLayers[i] : null, suscOpacity, (a, fprev) => {{
    activeSusc = a; fadeSusc = fprev;
  }});

  const di = nearestDepthIndex(f.lead_hours);
  const nextDepth = (di >= 0 && depthLayers[di]) ? depthLayers[di] : depthTotal;
  const wantDepth = document.getElementById("lyDepthTot").checked;
  swapOverlay(activeDepth, wantDepth ? nextDepth : null, effectiveDepthOpacity, (a, fprev) => {{
    activeDepth = a; fadeDepth = fprev;
  }});

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
  const suscBit = wantSusc ? " · screening on" : "";
  document.getElementById("hudSub").textContent =
    "+" + f.lead_hours + "h · " + (f.temporal_blend ? "blend" : "native") + depthBit + suscBit + " · dense awareness";
  document.getElementById("leftLabel").textContent = "Decision Desk · " + (activePath.label || "Ida");
  syncSparklineToScrubber();
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
  }}, PLAY_MS);
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
function accessStatus(a) {{
  return (a && a.access_status) ? a.access_status : "open";
}}
function accessChipLabel(status) {{
  if (status === "limited") return "access: limited (research)";
  if (status === "watch") return "access: watch (research)";
  return "access: open (research)";
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
    const byId = Object.fromEntries((desk.assets || []).map(a => [a.id, a]));
    const curated = DEMO_SHORTLIST.map(id => byId[id]).filter(Boolean);
    // Shortlist ignores band filter so demo rows always appear; numbers still honest.
    if (curated.length) return curated;
  }}
  // All mode already uses demoted ranks from desk JSON (NJ Turnpike pushed down).
  return rows;
}}
function renderAssetList() {{
  const list = document.getElementById("assetList");
  const rows = filteredAssets().slice(0, listMode === "shortlist" ? 12 : 120);
  if (!rows.length) {{
    list.innerHTML = '<div class="empty">No wet assets match these filters.</div>';
    return;
  }}
  list.innerHTML = rows.map(a => {{
    const acc = accessStatus(a);
    const accPill = (acc === "limited" || acc === "watch")
      ? `<span class="access-pill ${{acc}}">${{acc}}</span>` : "";
    const topHit = highlightIds.includes(a.id) ? " top-hit" : "";
    return `
    <button type="button" class="asset-row${{selectedId === a.id ? " selected" : ""}}${{topHit}}" data-id="${{a.id}}">
      <div class="top">
        <span class="name">#${{a.rank}} · ${{a.name}}</span>
        <span class="depth">${{a.max_depth_cm.toFixed(1)}} cm</span>
      </div>
      <div class="meta">
        <span class="type-pill">${{typeLabel(a.asset_type)}}</span>
        <span class="band ${{bandClass(a.band)}}">${{a.band_label}}</span>
        <span>${{leadLabel(a)}}</span>
        ${{accPill}}
      </div>
    </button>`;
  }}).join("");
  list.querySelectorAll(".asset-row").forEach(btn => {{
    btn.addEventListener("click", () => selectAsset(btn.dataset.id));
  }});
}}
function depthSeriesForAsset(a) {{
  if (!a) return {{ leads: [], vals: [] }};
  const leads = (a.depth_series_leads_h && a.depth_series_leads_h.length)
    ? a.depth_series_leads_h.slice()
    : ((desk && desk.lead_frames_h) || []).slice();
  const vals = (a.depth_series_cm && a.depth_series_cm.length)
    ? a.depth_series_cm.slice()
    : [];
  return {{ leads, vals }};
}}
function nearestSeriesIndex(leads, leadHours) {{
  if (!leads.length) return -1;
  let best = 0, bestAbs = Infinity;
  leads.forEach((h, idx) => {{
    const d = Math.abs((h || 0) - leadHours);
    if (d < bestAbs) {{ bestAbs = d; best = idx; }}
  }});
  return best;
}}
function renderSparkline(a) {{
  const wrap = document.getElementById("selSparkWrap");
  const svg = document.getElementById("selSpark");
  const readout = document.getElementById("selSparkReadout");
  if (!wrap || !svg || !readout) return;
  const {{ leads, vals }} = depthSeriesForAsset(a);
  if (!leads.length || vals.length !== leads.length) {{
    wrap.hidden = true;
    svg.innerHTML = "";
    readout.textContent = "—";
    return;
  }}
  wrap.hidden = false;
  const w = 220, h = 44, pad = 4;
  const maxV = Math.max(1, ...vals, a.max_depth_cm || 0);
  const xs = leads.map((_, i) => pad + (i / Math.max(leads.length - 1, 1)) * (w - pad * 2));
  const ys = vals.map(v => h - pad - (v / maxV) * (h - pad * 2));
  const poly = xs.map((x, i) => x.toFixed(1) + "," + ys[i].toFixed(1)).join(" ");
  // Band thresholds as faint guides (3 / 8 / 15 cm)
  const guides = [3, 8, 15].filter(t => t < maxV).map(t => {{
    const y = h - pad - (t / maxV) * (h - pad * 2);
    return `<line x1="${{pad}}" y1="${{y.toFixed(1)}}" x2="${{w - pad}}" y2="${{y.toFixed(1)}}" stroke="rgba(255,255,255,.14)" stroke-width="1"/>`;
  }}).join("");
  svg.innerHTML = guides +
    `<polyline fill="none" stroke="#1ae4b6" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round" points="${{poly}}"/>` +
    `<circle id="sparkCursor" cx="${{xs[0]}}" cy="${{ys[0]}}" r="3.6" fill="#f9ba38" stroke="#042227" stroke-width="1.4"/>`;
  syncSparklineToScrubber();
}}
function syncSparklineToScrubber() {{
  const a = selectedId && desk ? (desk.assets || []).find(x => x.id === selectedId) : null;
  const svg = document.getElementById("selSpark");
  const readout = document.getElementById("selSparkReadout");
  const cursor = document.getElementById("sparkCursor");
  if (!a || !svg || !readout || !cursor) return;
  const {{ leads, vals }} = depthSeriesForAsset(a);
  if (!leads.length || vals.length !== leads.length) return;
  const leadHours = (frames[leadIndex] && frames[leadIndex].lead_hours != null)
    ? frames[leadIndex].lead_hours
    : 0;
  const idx = nearestSeriesIndex(leads, leadHours);
  if (idx < 0) return;
  const w = 220, h = 44, pad = 4;
  const maxV = Math.max(1, ...vals, a.max_depth_cm || 0);
  const x = pad + (idx / Math.max(leads.length - 1, 1)) * (w - pad * 2);
  const y = h - pad - (vals[idx] / maxV) * (h - pad * 2);
  cursor.setAttribute("cx", x.toFixed(1));
  cursor.setAttribute("cy", y.toFixed(1));
  readout.textContent = "+" + leads[idx] + "h · " + Number(vals[idx]).toFixed(1) + " cm (scrubber)";
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
    // Teal "line-through" selection: bright corridor stroke + darker underlay.
    selectedLayer = L.layerGroup([
      L.geoJSON(geomLayer.feature, {{
        pane: "selectPane",
        style: {{ color:"#042227", weight:11, opacity:0.55, lineCap:"round", lineJoin:"round" }}
      }}),
      L.geoJSON(geomLayer.feature, {{
        pane: "selectPane",
        style: {{ color:"#1bc0cd", weight:5.5, opacity:1, lineCap:"round", lineJoin:"round", dashArray:"10 6" }}
      }}),
    ]).addTo(mapLeft);
  }} else {{
    selectedLayer = L.circleMarker(ll, {{
      pane: "selectPane", radius: 11, color:"#042227", weight:3,
      fillColor:"#1bc0cd", fillOpacity:0.95
    }}).addTo(mapLeft);
  }}
  const card = document.getElementById("selectedCard");
  const acc = accessStatus(a);
  document.getElementById("selKicker").textContent = typeLabel(a.asset_type) + " · #" + a.rank;
  document.getElementById("selName").textContent = a.name;
  document.getElementById("selBody").innerHTML =
    "<b>" + a.max_depth_cm.toFixed(1) + " cm</b> · " + a.band_label + " · " + leadLabel(a);
  document.getElementById("selChips").innerHTML =
    `<span class="sel-chip access-${{acc}}">${{accessChipLabel(acc)}}</span>` +
    `<span class="sel-chip">${{a.band_label}}</span>`;
  document.getElementById("selHint").textContent = a.action_hint ||
    "Research depth only — not an SOP trigger.";
  const sigs = (a.access_signals || []).map(s => s.label || s.source).filter(Boolean);
  document.getElementById("selAccessNote").textContent = sigs.length
    ? ("Signals: " + sigs.slice(0, 2).join(" · ") + " — not official closures.")
    : "Open DOT/MTA signals + research depth — not official closures.";
  renderSparkline(a);
  card.classList.remove("on");
  void card.offsetWidth;
  card.classList.add("on");
}}

function clearSelection() {{
  selectedId = null;
  if (selectedLayer) {{ mapLeft.removeLayer(selectedLayer); selectedLayer = null; }}
  document.getElementById("selectedCard").classList.remove("on");
  const wrap = document.getElementById("selSparkWrap");
  if (wrap) wrap.hidden = true;
  renderAssetList();
}}

function buildShortlistSnapshotText() {{
  const rows = filteredAssets().slice(0, listMode === "shortlist" ? 12 : 12);
  const f = frames[leadIndex] || {{}};
  const lead = f.lead_hours != null ? f.lead_hours : "—";
  const clock = (f.valid_time || "").replace("T", " ") || "—";
  const sel = selectedId && desk ? (desk.assets || []).find(x => x.id === selectedId) : null;
  const lines = [
    "Asset Decision Desk · shortlist snapshot",
    "Research only · NOT NWS · NOT decision-grade",
    "Event: " + activeEventId + " · scrubber +" + lead + "h · " + clock + " UTC",
    "",
    "Shortlist (" + rows.length + "):",
  ];
  rows.forEach(a => {{
    lines.push(
      "#" + a.rank + " · " + a.name + " · " + a.max_depth_cm.toFixed(1) + " cm · " +
      a.band_label + " · " + leadLabel(a) + " · access " + accessStatus(a)
    );
  }});
  if (sel) {{
    const {{ leads, vals }} = depthSeriesForAsset(sel);
    const idx = nearestSeriesIndex(leads, Number(lead) || 0);
    const at = (idx >= 0 && vals[idx] != null) ? (Number(vals[idx]).toFixed(1) + " cm @" + leads[idx] + "h") : "n/a";
    lines.push("");
    lines.push("Selected: " + sel.name + " · storm-total " + sel.max_depth_cm.toFixed(1) + " cm · at scrubber " + at);
    lines.push("Hint: " + (sel.action_hint || "research only"));
  }}
  lines.push("");
  lines.push("FloodNet Ida posts: " + (floodnetStations.length || 0) + " surfaced in panel.");
  return lines.join("\\n");
}}
function setSnapshotStatus(msg) {{
  const el = document.getElementById("snapshotStatus");
  if (el) el.textContent = msg || "";
}}
async function copyShortlistSnapshot() {{
  const text = buildShortlistSnapshotText();
  try {{
    await navigator.clipboard.writeText(text);
    setSnapshotStatus("Snapshot copied.");
  }} catch (err) {{
    setSnapshotStatus("Copy blocked — use Print / share.");
  }}
  const body = document.getElementById("printSnapshotBody");
  if (body) body.textContent = text;
}}
function printShortlistSnapshot() {{
  const text = buildShortlistSnapshotText();
  const body = document.getElementById("printSnapshotBody");
  if (body) body.textContent = text;
  window.print();
}}

function deskPathsForEvent(eventId) {{
  const deskCfg = manifest.asset_decision_desk || {{}};
  const events = deskCfg.events || {{}};
  if (eventId && events[eventId]) return events[eventId];
  if (eventId === "henri-2021" && secondStorm && secondStorm.desk) {{
    return {{
      assets_json: secondStorm.desk.assets_json || "decision_desk_assets_henri.json",
      assets_geojson: secondStorm.desk.assets_geojson || "decision_desk_assets_henri.geojson",
    }};
  }}
  return {{
    assets_json: deskCfg.assets_json || "decision_desk_assets.json",
    assets_geojson: deskCfg.assets_geojson || "decision_desk_assets.geojson",
  }};
}}

function topHighlightTargets() {{
  const byId = Object.fromEntries((desk.assets || []).map(a => [a.id, a]));
  const curated = DEMO_SHORTLIST.map(id => byId[id]).filter(Boolean);
  if (curated.length) return curated.slice(0, AUTO_HIGHLIGHT_N);
  // Henri / non-Ida: deepest NYC-preferred wet assets
  return (desk.assets || []).filter(a => a.nyc_demo_geography !== false).slice(0, AUTO_HIGHLIGHT_N);
}}

function topHitsEnabled() {{
  const el = document.getElementById("lyTopHits");
  return !el || el.checked;
}}
function wetAssetsEnabled() {{
  const el = document.getElementById("lyWet");
  return !el || el.checked;
}}
function syncWetLayerVisibility() {{
  if (!wetLayer) return;
  if (wetAssetsEnabled()) {{
    if (!mapLeft.hasLayer(wetLayer)) wetLayer.addTo(mapLeft);
  }} else if (mapLeft.hasLayer(wetLayer)) {{
    mapLeft.removeLayer(wetLayer);
  }}
}}
function applyAutoHighlight(selectFirst) {{
  if (highlightLayer) {{ mapLeft.removeLayer(highlightLayer); highlightLayer = null; }}
  const tops = topHighlightTargets();
  highlightIds = tops.map(a => a.id);
  if (!tops.length) {{
    renderAssetList();
    return;
  }}
  const feats = tops.map(a => ({{
    type: "Feature",
    properties: {{ id: a.id, name: a.name, band: a.band }},
    geometry: {{ type: "Point", coordinates: [a.lon, a.lat] }}
  }}));
  highlightLayer = L.geoJSON({{ type: "FeatureCollection", features: feats }}, {{
    pane: "selectPane",
    pointToLayer: (f, ll) => L.circleMarker(ll, {{
      radius: 14, color: "#0d8f9c", weight: 2.5, dashArray: "5 4",
      fillColor: "#1bc0cd", fillOpacity: 0.12, pane: "selectPane"
    }}),
    onEachFeature: (f, layer) => {{
      layer.bindTooltip("Top hit · " + (f.properties.name || ""));
      layer.on("click", () => selectAsset(f.properties.id));
    }}
  }});
  if (topHitsEnabled()) highlightLayer.addTo(mapLeft);
  renderAssetList();
  if (selectFirst) selectAsset(tops[0].id);
}}

function loadDecisionDesk() {{
  const paths = deskPathsForEvent(activeEventId);
  const name = paths.assets_json;
  const geoName = paths.assets_geojson;
  if (wetLayer) {{ mapLeft.removeLayer(wetLayer); wetLayer = null; }}
  if (highlightLayer) {{ mapLeft.removeLayer(highlightLayer); highlightLayer = null; }}
  highlightIds = [];
  clearSelection();
  Promise.all([
    fetch(assets + name, {{ cache:"no-cache" }}).then(r => r.ok ? r.json() : null),
    fetch(assets + geoName, {{ cache:"no-cache" }}).then(r => r.ok ? r.json() : null),
  ]).then(([json, geo]) => {{
    if (!json) {{
      document.getElementById("assetList").innerHTML = '<div class="empty">Desk assets missing for ' + activeEventId + ' — run build scripts.</div>';
      return;
    }}
    desk = json;
    const c = json.counts || {{}};
    const label = activeEventId === "henri-2021" ? "Wet · Henri HAND" : "Wet · metro HAND";
    document.getElementById("deskSummary").innerHTML =
      `<span>${{label}}</span><b>${{c.wet_total||0}} · R${{c.roads||0}} S${{c.stations||0}} F${{c.facilities||0}}</b>`;
    const leftLabel = document.getElementById("leftLabel");
    if (leftLabel) leftLabel.textContent = activeEventId === "henri-2021"
      ? "Decision Desk · Henri" : "Decision Desk · Ida";
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
      }});
      syncWetLayerVisibility();
    }}
    applyAutoHighlight(true);
    rebuildAccessOverlay();
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
function accessKindClass(kind) {{
  if (kind === "limited" || kind === "closure") return "limited";
  if (kind === "watch" || kind === "slow") return "watch";
  return "open";
}}
function accessSourceLabel(source) {{
  if (source === "nyc_dot_speeds") return "NYC DOT speed";
  if (source === "nysdot_511_events" || source === "nyc_street_closures") return "511-style event";
  if (source === "mta_alerts") return "MTA alert";
  return source || "Access signal";
}}
function accessDivIcon(source, kind) {{
  const k = accessKindClass(kind);
  let cls = "access-marker ";
  let label = "";
  if (source === "nyc_dot_speeds") {{
    cls += "dot" + (k === "limited" ? " limited" : "");
    label = "DOT";
  }} else if (source === "nysdot_511_events" || source === "nyc_street_closures") {{
    cls += "ev511" + (k === "limited" ? " limited" : "");
    label = "511";
  }} else {{
    cls += "mta" + (k === "limited" ? " limited" : k === "watch" ? " watch" : "");
    label = "MTA";
  }}
  return L.divIcon({{
    className: "access-div",
    html: `<div class="${{cls}}" title="${{accessSourceLabel(source)}}">${{label}}</div>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  }});
}}
function rebuildAccessOverlay() {{
  if (accessLayer) {{ mapLeft.removeLayer(accessLayer); accessLayer = null; }}
  const on = document.getElementById("lyAccess") && document.getElementById("lyAccess").checked;
  if (!on || !accessFixture) return;
  const feats = [];
  (accessFixture.dot_speeds || []).forEach(sp => {{
    if (sp.lon == null || sp.lat == null) return;
    const limited = sp.speed_ratio != null && Number(sp.speed_ratio) < 0.35;
    const ratio = sp.speed_ratio != null ? (" · " + Math.round(Number(sp.speed_ratio) * 100) + "% free-flow") : "";
    feats.push({{
      type: "Feature",
      properties: {{
        kind: limited ? "limited" : "watch",
        label: (sp.label || "DOT speed") + ratio,
        source: "nyc_dot_speeds",
      }},
      geometry: {{ type: "Point", coordinates: [sp.lon, sp.lat] }}
    }});
  }});
  (accessFixture.events_511 || []).forEach(ev => {{
    if (ev.lon == null || ev.lat == null) return;
    feats.push({{
      type: "Feature",
      properties: {{
        kind: ev.closure ? "limited" : "watch",
        label: ev.label || "511 event",
        source: ev.source || "nysdot_511_events",
      }},
      geometry: {{ type: "Point", coordinates: [ev.lon, ev.lat] }}
    }});
  }});
  (accessFixture.mta_alerts || []).forEach(al => {{
    const ids = al.asset_ids || [];
    ids.forEach(aid => {{
      const a = (desk && desk.assets || []).find(x => x.id === aid);
      if (!a) return;
      feats.push({{
        type: "Feature",
        properties: {{ kind: al.access || "watch", label: al.label || "MTA alert", source: "mta_alerts" }},
        geometry: {{ type: "Point", coordinates: [a.lon, a.lat] }}
      }});
    }});
  }});
  if (!feats.length) return;
  accessLayer = L.geoJSON({{ type: "FeatureCollection", features: feats }}, {{
    pane: "selectPane",
    pointToLayer: (f, ll) => L.marker(ll, {{
      icon: accessDivIcon(f.properties.source, f.properties.kind),
      pane: "selectPane",
      keyboard: false,
    }}),
    onEachFeature: (f, layer) => {{
      const src = accessSourceLabel(f.properties.source);
      const kind = accessKindClass(f.properties.kind);
      layer.bindTooltip(src + " · " + kind + " · " + (f.properties.label || ""));
    }}
  }}).addTo(mapLeft);
}}
function setAccessFeedStatus(text) {{
  const el = document.getElementById("accessFeedStatus");
  if (el) el.textContent = text;
}}
function loadAccessSignals() {{
  const deskCfg = manifest.asset_decision_desk || {{}};
  const fixtureName = deskCfg.access_signals_fixture || "access_signals_ida_fixture.json";
  const liveName = deskCfg.access_signals_live || "access_signals_live.json";
  const preferLive = document.getElementById("lyAccessLive") && document.getElementById("lyAccessLive").checked;
  const primary = preferLive ? liveName : fixtureName;
  const fallback = preferLive ? fixtureName : null;
  fetch(assets + primary, {{ cache: "no-cache" }}).then(r => r.ok ? r.json() : null).then(fx => {{
    if (fx) {{
      accessFixture = fx;
      accessFeedMode = preferLive ? ((fx.live_status && fx.live_status.mode) || fx.mode || "live") : "fixture";
      const nDot = (fx.dot_speeds || []).length;
      const n511 = (fx.events_511 || []).length;
      const nMta = (fx.mta_alerts || []).length;
      if (preferLive) {{
        setAccessFeedStatus(
          accessFeedMode === "fixture_fallback"
            ? "Live failed · fixture fallback"
            : ("Live · " + nDot + " speeds · " + n511 + " closures · " + nMta + " alerts")
        );
      }} else {{
        setAccessFeedStatus(
          "Fixture · Ida · " + nDot + " DOT · " + n511 + " closures · " + nMta + " MTA (shapes on map)"
        );
      }}
      rebuildAccessOverlay();
      return;
    }}
    if (!fallback) {{ accessFixture = null; setAccessFeedStatus("No access fixture"); return; }}
    return fetch(assets + fallback, {{ cache: "no-cache" }}).then(r => r.ok ? r.json() : null).then(fb => {{
      accessFixture = fb;
      accessFeedMode = "fixture_fallback";
      setAccessFeedStatus("Live missing · fixture fallback");
      rebuildAccessOverlay();
    }});
  }}).catch(() => {{
    if (!fallback) {{ accessFixture = null; return; }}
    fetch(assets + fallback, {{ cache: "no-cache" }}).then(r => r.ok ? r.json() : null).then(fb => {{
      accessFixture = fb;
      accessFeedMode = "fixture_fallback";
      setAccessFeedStatus("Live error · fixture fallback");
      rebuildAccessOverlay();
    }});
  }});
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

function loadFloodNetLaterEvents() {{
  const laterSummary = document.getElementById("floodnetLaterSummary");
  fetchGeoJSON("floodnet_later_events.geojson").then(geo => {{
    const nSens = (geo.properties && geo.properties.n_sensors) || (geo.features || []).length;
    const nEv = (geo.properties && geo.properties.n_events) || 0;
    if (laterSummary) {{
      laterSummary.innerHTML = `<span>Post-Ida archive</span><b>${{nSens}} sensors · ${{nEv}} events</b>`;
    }}
    if (!geo.features || !geo.features.length) return;
    floodnetLaterLayer = L.geoJSON(geo, {{
      pointToLayer: (f, ll) => L.circleMarker(ll, {{
        radius: 5,
        fillColor: "#5b8def",
        color: "#0b1d2a",
        weight: 1.5,
        fillOpacity: 0.75,
        pane: "pointPane",
      }}),
      onEachFeature: (f, layer) => {{
        const p = f.properties || {{}};
        const cm = p.max_depth_m != null ? (Number(p.max_depth_m) * 100).toFixed(1) : "—";
        layer.bindPopup(
          `<b>${{p.sensor_name || p.sensor_id || "FloodNet"}}</b><br>` +
          `later peak ~${{cm}} cm · n=${{p.n_events_post_ida || "—"}}<br>` +
          `<span style="opacity:.75">Post-Ida archive · research only</span>`
        );
        layer.bindTooltip((p.sensor_name || "FloodNet") + " · later " + cm + " cm");
      }},
    }});
    bindToggle("lyFloodNetLater", floodnetLaterLayer);
  }}).catch(() => {{
    if (laterSummary) laterSummary.innerHTML = `<span>Later FloodNet</span><b>unavailable</b>`;
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
      if (summaryEl && floodnetStations.length) {{
        // Keep a posts count visible even before repro summary lands.
        if (!summaryEl.dataset.locked) {{
          summaryEl.innerHTML = `<span>Ida posts surfaced</span><b>${{floodnetStations.length}}/5</b>`;
        }}
      }}
    }} else {{
      document.getElementById("floodnetList").innerHTML = '<div class="empty">floodnet_ida_hotspot_stations.geojson missing — run scripts/calibrate_ida_floodnet_hotspot.py</div>';
    }}

    if (repro && repro.summary && repro.summary.hotspot_calibrated) {{
      const h = repro.summary.hotspot_calibrated;
      const cal = repro.calibration || {{}};
      const loo = repro.leave_one_out || {{}};
      if (summaryEl) {{
        summaryEl.dataset.locked = "1";
        summaryEl.innerHTML =
          `<span>Hotspot cal · ${{floodnetStations.length || h.n || 0}}/5 posts</span>` +
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
      loadFloodNetLaterEvents();
      return;
    }}

    if (fn && fn.summary) {{
      const rmse = fn.summary.peak_rmse_m;
      const bias = fn.summary.peak_bias_m && fn.summary.peak_bias_m.mean;
      const n = fn.summary.n_sensors;
      if (summaryEl) {{
        summaryEl.dataset.locked = "1";
        summaryEl.innerHTML = `<span>FloodNet vs primary HAND</span><b>RMSE ${{fmtM(rmse)}} m · n=${{n}}</b>`;
      }}
      if (advEl) {{
        advEl.dataset.floodnetWired = "1";
        advEl.innerHTML = `FloodNet vs HAND · n=${{n}} · RMSE ${{fmtM(rmse)}} m · bias ${{fmtM(bias)}} m.`;
      }}
      loadFloodNetLaterEvents();
      return;
    }}

    if (summaryEl) {{
      summaryEl.innerHTML = `<span>FloodNet reproduction</span><b>unavailable</b>`;
    }}
    loadFloodNetLaterEvents();
  }}).catch(err => {{
    const summaryEl = document.getElementById("floodnetSummary");
    if (summaryEl) summaryEl.innerHTML = `<span>FloodNet load failed</span><b>—</b>`;
    document.getElementById("floodnetList").innerHTML = '<div class="empty">Failed to load FloodNet reproduction assets.</div>';
    console.warn(err);
  }});
}}

function setArchiveStatus(msg) {{
  const el = document.getElementById("archiveLayersStatus");
  if (el) el.textContent = msg;
}}
function loadArchiveOpenLayers() {{
  const statusBits = [];
  fetchGeoJSON("archived_511_events.geojson").then(geo => {{
    archive511Layer = L.geoJSON(geo, {{
      pointToLayer: (f, ll) => {{
        const kind = f.properties && (f.properties.closure || f.properties.kind === "limited") ? "limited" : "watch";
        return L.marker(ll, {{ icon: accessDivIcon("nysdot_511_events", kind), pane: "pointPane" }});
      }},
      onEachFeature: (f, layer) => {{
        const p = f.properties || {{}};
        layer.bindPopup(`<b>${{p.label || "Archived 511-style"}}</b><br>Research archive · not official closures`);
      }},
    }});
    bindToggle("lyArchive511", archive511Layer);
    statusBits.push("511×" + ((geo.features || []).length));
    setArchiveStatus(statusBits.join(" · ") + " ready");
  }}).catch(() => statusBits.push("511 missing"));

  fetchGeoJSON("dep_catch_basins_sample.geojson").then(geo => {{
    depBasinsLayer = L.geoJSON(geo, {{
      pointToLayer: (f, ll) => L.circleMarker(ll, {{
        radius: 2.5, fillColor: "#6b7280", color: "#111827", weight: 0.8, fillOpacity: 0.7, pane: "pointPane"
      }}),
      onEachFeature: (f, layer) => {{
        const p = f.properties || {{}};
        layer.bindTooltip((p.unitid || p.node_id || "DEP basin") + " · open inventory");
      }},
    }});
    bindToggle("lyDepBasins", depBasinsLayer);
    statusBits.push("DEP×" + ((geo.features || []).length));
    setArchiveStatus(statusBits.join(" · ") + " ready");
  }}).catch(() => {{
    statusBits.push("DEP missing");
    setArchiveStatus(statusBits.join(" · "));
  }});

  fetchGeoJSON("building_footprints_sample.geojson").then(geo => {{
    buildingsLayer = L.geoJSON(geo, {{
      style: {{ color: "#334155", weight: 1, fillColor: "#94a3b8", fillOpacity: 0.25 }},
      onEachFeature: (f, layer) => {{
        const p = f.properties || {{}};
        const h = p.height_roof != null ? (Number(p.height_roof).toFixed(0) + " ft roof") : "footprint";
        layer.bindTooltip(h + " · open sample");
      }},
    }});
    bindToggle("lyBuildings", buildingsLayer);
    statusBits.push("bldgs×" + ((geo.features || []).length));
    setArchiveStatus(statusBits.join(" · ") + " ready");
  }}).catch(() => {{
    statusBits.push("buildings missing");
    setArchiveStatus(statusBits.join(" · "));
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
  // Stations/facilities are sparse at ≥8 cm — open All wet + full list so the chip is usable.
  if (typeFilter === "station" || typeFilter === "facility") {{
    listMode = "all";
    document.querySelectorAll("#listModeChips .chip").forEach(c => c.classList.toggle("active", c.dataset.mode === "all"));
    const band = document.getElementById("bandFilter");
    if (band && band.value === "deep_ponding") {{
      band.value = "all";
    }}
  }}
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
document.getElementById("eventSelect").onchange = () => {{
  const ev = EVENTS[eventSel.value];
  if (!ev || !ev.available) {{
    alert("That event is not loaded yet.");
    eventSel.value = activeEventId;
    return;
  }}
  activeEventId = ev.id;
  // Henri desk swaps asset JSON; Ida keeps MRMS awareness loop (Henri radar frames not wired yet).
  if (activeEventId === "henri-2021") {{
    listMode = "all";
    document.querySelectorAll("#listModeChips .chip").forEach(c => c.classList.toggle("active", c.dataset.mode === "all"));
    const band = document.getElementById("bandFilter");
    if (band) band.value = "all";
  }} else {{
    listMode = "shortlist";
    document.querySelectorAll("#listModeChips .chip").forEach(c => c.classList.toggle("active", c.dataset.mode === "shortlist"));
  }}
  loadDecisionDesk();
}};
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
  if (activeDepth) activeDepth.setOpacity(effectiveDepthOpacity());
  else if (depthTotal) depthTotal.setOpacity(effectiveDepthOpacity());
}};
document.getElementById("lyE2").onchange = () => setLead(leadIndex);
document.getElementById("lySusc").onchange = () => {{
  // Dim depth under screening so the amber index reads; keep current lead.
  setLead(leadIndex);
}};
document.getElementById("lyDepthTot").onchange = () => {{
  if (activeDepth && mapLeft.hasLayer(activeDepth)) mapLeft.removeLayer(activeDepth);
  if (depthTotal && mapLeft.hasLayer(depthTotal)) mapLeft.removeLayer(depthTotal);
  activeDepth = null;
  if (document.getElementById("lyDepthTot").checked) setLead(leadIndex);
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
document.getElementById("lyAccess").onchange = () => rebuildAccessOverlay();
document.getElementById("lyWet").onchange = () => syncWetLayerVisibility();
document.getElementById("lyTopHits").onchange = () => {{
  if (!highlightLayer) return;
  if (topHitsEnabled()) {{
    if (!mapLeft.hasLayer(highlightLayer)) highlightLayer.addTo(mapLeft);
  }} else if (mapLeft.hasLayer(highlightLayer)) {{
    mapLeft.removeLayer(highlightLayer);
  }}
}};
document.getElementById("lyAccessLive").onchange = () => {{
  loadAccessSignals();
  // Live overlay does not rebuild desk ranks in-browser; run fetch_live_access_feeds.py --apply-desk for joined chips.
}};
const btnShare = document.getElementById("btnShareSnapshot");
const btnPrint = document.getElementById("btnPrintSnapshot");
if (btnShare) btnShare.onclick = () => copyShortlistSnapshot();
if (btnPrint) btnPrint.onclick = () => printShortlistSnapshot();
(function wireMapKeyFloat() {{
  const box = document.getElementById("mapKeyFloat");
  const btn = document.getElementById("mapKeyFloatToggle");
  if (!box || !btn) return;
  btn.addEventListener("click", () => {{
    const collapsed = box.classList.toggle("collapsed");
    btn.textContent = collapsed ? "+" : "–";
    btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
    btn.setAttribute("aria-label", collapsed ? "Expand map key" : "Collapse map key");
  }});
}})();

rebuildPathLayers();
fitMapFrame();
setLead(0);
loadDecisionDesk();
loadAccessSignals();
loadFloodNetProduct();
loadOptionalLayers();
loadArchiveOpenLayers();
setPlaying(true);
</script>
</body>
</html>
"""
    out = FIGURES_DIR / "product_map.html"
    out.write_text(html)
    return out
