# Live MRMS QPF/QPE path (P2.7)

**Research ops-latency probe** — NOT NWS / NOT decision-grade.

## What is live vs fixture

| Surface | Live? | Notes |
| --- | --- | --- |
| Decision Desk default radar | **Fixture** | Ida MRMS QPE 0–36h replay (`mrms_qpe_ida`) |
| Henri Event switch | **Fixture** | Henri MRMS 0–24h after `make henri-parity` |
| Advanced live probe | **Live when reachable** | Latest NOAA S3 MultiSensor QPE Pass1 hour |

## Reproduce

```bash
make live-mrms
# or
.venv/bin/python scripts/build_live_mrms_path.py
```

Status artifact: `figures/product_assets/live_mrms_status.json`

Last run: live status = `ok` · valid = `2026-11-16T13:00:00+00:00`.

## Honesty

Live fetch does **not** rebuild HAND ranks or swap the default desk loop.
Product QPE product id: `MultiSensor_QPE_01H_Pass1_00.00`.
