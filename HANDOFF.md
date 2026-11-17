# Softs desk (Brazil--trade) — handoff notes

## Cotton → Australia tab, synced from the US desk (2026-11-11)
- `assets/australia.js` copied unchanged from BMR-Com/US-commodity-desk; `assets/cotton.js` gets `['ct-aus', 'Australia']` after India in TABS and the same isolated `'ct-aus'` handler as US desk commit 79e3dbdc; `index.html` loads `australia.js?v=20261111a` after india.js (cotton.js bumped).
- Data is not collected here. `.github/workflows/australia_sync.yml` (daily 22:47 UTC + dispatch) sparse-clones US-commodity-desk and copies `data/australia/australia.json` and `data/australia/raw/forecasts_manual.json`, committing only if something changed (pattern of the US desk's `cotton_certs_sync.yml`, which copies the other way). Seeded once by hand on 2026-11-11.

## WASDE fetched and stored by the desk itself (2026-11-11; same as US desk commit 918ec4de)
- `pipelines/wasde.py`, `models/wasde_store.py`, `models/wasde_cotton_brief.py` copied from the US desk. `data/wasde/raw/*.csv.gz` seeded from the US desk's store (196 reports, through WASDE #677); `data/wasde/json/` is built on each run and ignored by git; the cotton brief goes to `data/wasde/brief/`.
- 918ec4de's loader changes applied to `models/grains_wasde.py`, `grains_wasde_brief.py`, `grains_esr_brief.py`, `dairy_sd.py`: the local store first, BMR-Com/wasde-analytics as the fallback.
- `.github/workflows/wasde.yml` replaced with the US desk's: fetch USDA's CSV (`--wait 35`), then wasde_store, wasde_cotton_brief, grains_wasde, grains_esr_brief, grains_wasde_brief, balance_sheets, summary, outlook_brief (grains_pack and validate are not in this repo; dairy_sd dropped: no dairy data here and the softs desk covers exchange-traded softs only), commit data. No clock workflow here, so the US desk's report-day times (12:05, 12:20, 16:30 ET, weekdays, days 8–14) are UTC crons for EST and EDT; a first step skips the twin that is an hour off.
- Verified: `python models/wasde_store.py && python -W ignore models/wasde_cotton_brief.py && python -W ignore models/grains_wasde_brief.py` gives a cotton block in `data/grains/derived/wasde_brief/2026-11.json` identical to the US desk's except the build date.

## ICE drop box: combined histories for coffee/cocoa certs, aging, grading (2026-11-17)
- `pipelines/ice_history.py` (called by `pipelines/ice_inbox.py`) recognises by content and appends to one combined CSV each; a re-upload replaces that date's / month's rows. History was built by running the same code over Ma's local ICE folder (~400 files).
  - `data/coffee/ice_aging_history.csv` (date, delivery, age bucket, port, bags; non-zero cells) from 2016-01; `data/coffee/ice_certs_eom_by_port.csv` (month-end bags by port, 1996-11 on; ICE's file has no June 1999 row and its Mar-2017 total is 2,000 above the ports); `data/coffee/ice_certs_daily_detail.csv` (every section of the daily report incl. rebagging and pass rate; from 2026-10-01); `data/coffee/ice_grading_monthly.csv` (month and year-to-date tables, original/appeal, by origin and by criterion; five 2022-23 PDFs are images and are read by OCR, accepted only when the table checks pass); `data/cocoa/ice_certs_daily.csv`; `data/cocoa/ice_grading_monthly.csv` (chop-level ICE file summarised per month, port, origin, class, initial/regrade); `data/coffee/ref/{licensed_warehouses,warehouse_rates}.csv` (no contact details kept).
  - Cotton: new type `four_months_older_YYYY-MM-DD.csv` (in `latest.json` with history); the strength classifier now accepts ICE's "GPT Range" headers.
  - Newest original per kind in `data/ice_raw/latest/` (not the PDFs/xls that print contact e-mails).
- Known: `pipelines/coffee_certs.py` counts "Flagged for Rebagging" bags as pending (no section break), so `ice_certs.csv` pending = true pending + rebagging; the daily detail file has them apart. Not changed here.
- No desk panels read the new files yet.

## Sugar tab: public-data panels and weekly input pack (2026-11-17)
- New tabs in `assets/sugar.js` (rendered by `assets/sugar_world.js`): "Brazil cane weather & season range" (rain and estimated harvest-stoppage days by state vs 2011–2025, ECMWF ENS/GEFS 15-day forecast with run history, MAPA fortnight scorecard vs last year and 5-yr avg, season range under wet/normal/dry cases with a kg/t grid, Brazil fuel-policy log), "India detail", "Europe", "Deliveries & revisions".
- Data: `models/sugar_world.py` → `data/sugar/world.json`; `models/sugar_weekly.py` → `data/sugar/weekly_inputs.json` (every input for the weekly note, with date and source); `pipelines/sugar_wx.py` → `data/sugar/wx/` (per-member ensemble rain for 7 cane points, EU beet-region ERA5 history + recent, extra cane point Piracicaba/Jaú). Workflow `.github/workflows/sugar_world.yml`: after each "Sugar — data refresh" run, Fridays 22:40 UTC, weekdays 11:20 UTC, and on demand.
- Manual-entry files (edit by hand from dated public releases; each row has source and URL): `data/sugar/manual/{india,agency_revisions,deliveries,fuel_policy,eu_price}.csv`. They show their date on the page and are on the Data status tab.
- The stoppage-day rule and the season-range method live in `models/sugar_world.py` only; the page shows results and the inputs used.

## Sugar weekly report (BMR-Com Sugar Research)
Written every Friday after the ICE close for the week Friday to Friday; published as a post on the "BMR-Com Sugar Research" artifact (same framework as BMR-Com Cotton Research: SNAPSHOT strip + POSTS array, each post = slug, date, readTime, title, dek, tags, cover data-URI, coverAlt, HTML body).

**Commands (in this repo, in order)**
1. `git pull --rebase`, then check the latest runs of "Sugar — data refresh and model build" and "Sugar — public panels and weekly inputs" finished (gh api repos/BMR-Com/Brazil--trade/actions/runs). Do not re-fetch data the workflows already collect.
2. `python models/sugar_world.py && python models/sugar_weekly.py` (rebuilds from the committed data; safe to rerun).
3. `python models/sugar_weekly_charts.py <out_dir>` writes c1_parity, c2_white, c3_rain, c4_stoppage, c5_range, c6_cot (PNG, light background). Embed as data URIs; use c1 (or the week's key chart) as the cover.
4. Read `data/sugar/weekly_inputs.json` → `status` (input / date / source) and list every input's date in the report's "Data used" table; mark anything older than the week.

**Where the numbers are** (`data/sugar/weekly_inputs.json` → `inputs`)
- `prices`, `spreads` (incl. white premiums), `macro` (USD/BRL, USD/INR, EUR/USD, Brent, DXY, RBOB): Friday vs previous Friday.
- `parity` (Friday hydrous parity and sugar minus parity), `pump` (ANP São Paulo), `white_curve`.
- `cot` (managed money, producers; Tuesday positions).
- `crush_scorecard` (MAPA fortnight and season to date vs last year and 5-yr avg; corn-adjusted mix; UNICA last published), `crush_states`.
- `cane_weather` (rain and estimated stoppage days by state and CS, month to date and since 1 April vs normal; ensemble forecast with previous run), `season_range` (wet / normal / dry cases, kg/t grid, cross-checks vs the desk pace projection and Conab).
- `exports` (SECEX weekly pace, desk forecast), `india` (ISMA, policy, quota, ex-mill prices, import parity), `europe` (EC revisions, EU price vs No. 5, beet-region weather), `deliveries`, `revisions`, `fuel_policy` (+ sugar-equivalent value of the hydrous subsidy), `psd`, `industry_reading` (Czapp digest date).
- Manual files to refresh before writing if a release came out: `data/sugar/manual/{india,agency_revisions,deliveries,fuel_policy,eu_price}.csv` (one row per release with date, source and URL). Add each new expiry delivery (No. 11 and No. 5) to `deliveries.csv`.

**Post structure (sections in this order)**
Key takeaways box (6-8 bullets: what changed and why it matters for price and spreads) → cover chart → Data used in this report (table of inputs and dates) → Prices and spreads (settlement table, raw spreads, white premium, BRL/Brent; expiry deliveries) → Centre-South Brazil: the fortnight (scorecard), Cane weather (rain/stoppage days, forecast), What the public data imply for the season (cases + kg/t grid + cross-checks, read for price incl. Jan-Mar cane), Ethanol parity and fuel policy, Exports → India (production, policy/quota, import-parity table) → Europe (EC revisions, EU price vs No. 5, beet weather) → other origins if material → Positioning (COT) → What the agencies changed (revisions table) → Our read (direction as a read of the evidence, reference levels from public inputs, what would change it, supportive/negative table) → What to watch next week (dated) → Abbreviations → Sources (linked) → disclaimer. Plain short sentences, trader vocabulary, every number dated and sourced.

**Standing rules**
- Public data only. Paid balance sheets and trade-flow sheets are not used; never name a paid vendor (say "industry estimates" if a paid view must be referenced at all, and prefer not to).
- Agencies (USDA, ISO, EC, Conab, ISMA): report changes from their previous release, not levels.
- Merchant names at exchange deliveries are allowed: delivery reports are public.
- No fair-value range unless built transparently from public inputs and labelled (the ethanol-parity floor and India import parity are reference levels).
- Method detail (stoppage-day rule, range method, calibration) stays out of the report and the page: show results and the variables used.
- Czapp (Czarnikow) free articles may be cited by name; summarise in our own words.
- Brazil focus for basis and premiums.
