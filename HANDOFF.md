# Softs desk (Brazil--trade) — handoff notes

## Cotton → Australia tab, synced from the US desk (2026-11-11)
- `assets/australia.js` copied unchanged from BMR-Com/US-commodity-desk; `assets/cotton.js` gets `['ct-aus', 'Australia']` after India in TABS and the same isolated `'ct-aus'` handler as US desk commit 79e3dbdc; `index.html` loads `australia.js?v=20261111a` after india.js (cotton.js bumped).
- Data is not collected here. `.github/workflows/australia_sync.yml` (daily 22:47 UTC + dispatch) sparse-clones US-commodity-desk and copies `data/australia/australia.json` and `data/australia/raw/forecasts_manual.json`, committing only if something changed (pattern of the US desk's `cotton_certs_sync.yml`, which copies the other way). Seeded once by hand on 2026-11-11.

## WASDE fetched and stored by the desk itself (2026-11-11; same as US desk commit 918ec4de)
- `pipelines/wasde.py`, `models/wasde_store.py`, `models/wasde_cotton_brief.py` copied from the US desk. `data/wasde/raw/*.csv.gz` seeded from the US desk's store (196 reports, through WASDE #677); `data/wasde/json/` is built on each run and ignored by git; the cotton brief goes to `data/wasde/brief/`.
- 918ec4de's loader changes applied to `models/grains_wasde.py`, `grains_wasde_brief.py`, `grains_esr_brief.py`, `dairy_sd.py`: the local store first, BMR-Com/wasde-analytics as the fallback.
- `.github/workflows/wasde.yml` replaced with the US desk's: fetch USDA's CSV (`--wait 35`), then wasde_store, wasde_cotton_brief, grains_wasde, grains_esr_brief, grains_wasde_brief, balance_sheets, summary, outlook_brief (grains_pack and validate are not in this repo; dairy_sd dropped: no dairy data here and the softs desk covers exchange-traded softs only), commit data. No clock workflow here, so the US desk's report-day times (12:05, 12:20, 16:30 ET, weekdays, days 8–14) are UTC crons for EST and EDT; a first step skips the twin that is an hour off.
- Verified: `python models/wasde_store.py && python -W ignore models/wasde_cotton_brief.py && python -W ignore models/grains_wasde_brief.py` gives a cotton block in `data/grains/derived/wasde_brief/2026-11.json` identical to the US desk's except the build date.
