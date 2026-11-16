# Asset Decision Desk — 60s demo talk track

**Entrypoint:** `python scripts/serve_product.py` → `product_map.html` only.  
**Shortlist SSOT:** `config/demo_shortlist.yaml`  
**Offline:** vendored Leaflet/fonts under `figures/vendor/`; paper basemap always on; uncheck Online streets if offline.  
**Defaults locked:** assets first · demo shortlist · FloodNet closed · access overlay off · MRMS locked · Screening closed/off · Advanced closed.  
**Optional (not 60s):** Advanced → Event → Henri research replay (radar + shortlist + Ida↔Henri compare strip).

---

## Three bullets (say these)

1. **Job:** For Ida, we show **which named roads / stations / facilities get wet**, research depth bands, a rough lead, and **what that means for access / staging** — research, not agency guidance.
2. **Surface:** Ranked wet assets from **metro pysheds × spatial MRMS QPE** — research bands ≥3 / ≥8 / ≥15 cm (not NWS watch/warning). Access chips join a **labeled synthetic Ida replay pack**.
3. **Honesty:** Depths are **cm-scale HAND heuristics**, not Ida street-truth (FloodNet peaks up to ~0.9 m, n=5); sewer = open capacity proxy, **not DEP**. Access = research join — **not** official closures. Not decision-grade.

---

## Four click targets (all ≥8 cm deep ponding · live desk)

| # | Asset | Type | Depth | Access | ID | Lead chip |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | **Smith-9 Sts** | Station (Viaduct) | 11.1 cm | limited (research) | `stations:gtfs:F22` | band @ +15h |
| 2 | **Van Wyck Expressway** | Road | 9.4 cm | limited (research) | `road:25430129` | band @ +15h |
| 3 | **Brooklyn Hospital Downtown** | Facility | 8.5 cm | watch (research) | `facilities:uid:a464e8e63eb8b2c92ab1995735cfd284` | band @ +18h |
| 4 | **Myrtle Avenue** | Road | 8.2 cm | watch (research) | `road:37394898` | band @ +18h |

**UI:** leave **Shortlist** selected (loads light bundle first); click each row → map fly-to + highlight + typed `action_hint` + access chip + engine agree/disagree chip (non-peer). Optional: Map layers → DOT / access. All-mode / search lazy-loads the full desk.

**Do not** open All-mode for the 60s beat — decision-class filter helps, but shortlist is the story.

---

## Beat sheet (~60s)

| Beat | ~time | Do / say |
| --- | --- | --- |
| Frame | 0–5s | Brand + sticky honesty + magnitude chip (HAND cm ≠ FloodNet ~0.9 m) |
| Where | 5–15s | Primary depth on; MRMS precip loop low opacity — no screening |
| What | 15–40s | Click Smith-9 → Van Wyck → Brooklyn Hospital → Myrtle; point at access chip, SOP hint, and disagreement chip on Smith-9 / Brooklyn Hospital |
| When | 40–50s | Lead chip (“band @ +15h / +18h · 3h cum screening frames”); read one hint aloud |
| Close | 50–60s | Repeat honesty (research access, not official closures); do **not** open Advanced / SFINCS |

**Pass:** viewer can name 2–3 assets + bands + “research HAND / research access, not street-truth.”  
**Fail:** presenter opens Advanced or sells Earth2 / SFINCS / FEMA / official closures / SIUH (retired shortlist).
