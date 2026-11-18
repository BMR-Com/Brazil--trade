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

## Coffee → KC spread model on the "Certified stocks & structure" tab (2026-11-18)
- `models/kc_spread_model.py` → `data/coffee/spread_model.json`, rendered by `smBlock()` / `smCharts()` in `assets/coffee.js` on `#kc-certs` (replaces the old monthly certs-vs-spread scatter; `structure.fair` in coffee.json is no longer drawn). Runs in `coffee.yml` after the certs profile and in `ice_inbox.yml` after ICE uploads; a missing input or too-short history exits non-zero. Registered in `pipelines/data_status.py`.
- Inputs: ICE certs (month-end by port, daily, aging, grading, daily detail pending), `kc_spreads_history.csv`, CFTC `data/cot/KC_fut.csv`, MDIC `data/exports_*.csv`, `certs_profile.json` (pool value), `data/contracts/KC.csv`, `data/options/roll.json`.
- `python models/kc_spread_model.py --lab PATH` also writes the regime tests and out-of-sample statistics to PATH (keep it outside the repo; they belong in the private Lab only). The page shows outputs and the variables list only.

## Coffee → "Certs profile & delivery economics" tab (2026-11-17)
- `models/coffee_certs_profile.py` → `data/coffee/certs_profile.json`, rendered by `cprof()` in `assets/coffee.js` (tab `#kc-cprof`). Runs in `ice_inbox.yml` after new ICE files and in `coffee.yml` (weekdays) after the coffee build; any missing input or failed check exits non-zero and fails the run. Registered in `pipelines/data_status.py`.
- Rule parameters by version: `data/coffee/ref/kc_rule_params.json`; dated rule timeline with sources: `data/coffee/ref/rule_changes.csv` (both edited by hand when ICE amends Chapter 8). Physical comparison uses `coffee/data/ico_groups_monthly.csv` and the Brazil ladder in `coffee/data/coffee.json` (no manual file needed).
- Exchange vs ICO is shown only relative to its own history: the model also writes `data/coffee/ico_groups_history.csv` (ICO group prices by market since 2000 with the computed ICE 2nd/3rd average) and a per-delivery gap history (`gap` in the JSON).
- The method write-up is in the private Lab artifact only; the page shows outputs and variables used.
- The existing certs tab note now describes "transition" bags as EUDR transition stock (Appendix VIII), not an earlier grading rule.

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

## Coffee → "KC contract: old vs new" tab (2026-11-17)
- Tab `#kc-newc` (`kcnew()` in `assets/coffee.js`), data in `data/coffee/certs_profile.json` → `contract_compare`, written by `models/coffee_certs_profile.py` (same runs as the certs profile).
- "New contract" = Coffee "C" Metric (AC, ICE rulebook Ch. 14, Submission 25-157): 10 t, $/t, FIBCs, no Barcelona, first expiry May 2028; KC's last expiry is Mar 2028. AC parameters: `data/coffee/ref/ac_rule_params.json`.
- Correction: the +10¢ Colombia/Costa Rica/Kenya and +5¢ Guatemala premiums apply from the **March 2026** contract (ICE notice 16 Jan 2024; rulebook amendment note 20 Dec 2023; ICE product spec page). The rulebook's "Effective with …" lines sit between schedules; May 2027 adds only Vietnam. `kc_rule_params.json` and `rule_changes.csv` fixed; certs-profile values for Dec 2026 changed for Kenya/Colombia/Guatemala lots.
- AC prices: `pipelines/contracts.py AC` → `data/contracts/AC.csv` (seeded by hand with ACK2028 bars 3–16 Nov 2026; the softs-contracts workflow refreshes it). Same workflow backfills `KC_pre2006` / `CC_pre2006` (1996–2005 contracts) into separate files so the main KC/CC files keep their length.

## Cocoa → "Certs profile & delivery value" tab; KC/CC spread history (2026-11-17)
- `models/cocoa_certs_profile.py` → `data/cocoa/certs_profile.json`, rendered by `certs()` in `assets/cocoa.js` (tab `#cc-certs`). Runs in `ice_inbox.yml` (after the coffee profile; failures fail the run) and in `softs_contracts.yml`. Registered in `pipelines/data_status.py`.
- Rules: `data/cocoa/ref/cc_rule_params.json` (Ch. 9 Cocoa: group premiums A +160 / B +80 / C par, count classes, slate, waste, certificate life, weight) and `data/cocoa/ref/rule_changes.csv` (2010–2026, sources). No port differential and no EUDR rule in ICE US cocoa.
- Delivery value per origin × port = growth-group premium (daily report class) − weight discount (count + waste, 12-month grading average × front futures) + slate discount. Age since first grading is an estimate (newest first-time gradings fill the stock). Physical diffs: no public dated series found → only the $400 LID reference is shown (confidence low).
- Long cocoa cert-stock history is not in the desk: ICE report centre is captcha-protected; Ma to drop the historical file into the ICE inbox.
- `models/softs_spreads_history.py` → `data/coffee/kc_spreads_history.csv`, `data/cocoa/cc_spreads_history.csv` (daily front/second/third, s12, s23, pair names, business days to first notice; front rolls at first notice with an ICE-holiday calendar). Uses `data/contracts/{KC,CC}.csv` (2004 on) plus `*_pre2006.csv` once the softs-contracts workflow has backfilled 1996–2005. Spread-vs-history charts with rule markers on both certs tabs.
- (later 2026-11-17) Cocoa grade validity added: each lot's latest grading date (first grading or regrade) estimated newest-first from the grading file and daily passes; Rule 9.18(d)(ii)(1) gives "grade valid through" (delivery period = delivery month, an assumption). Lots needing regrade before the next delivery, recent regrade return rate (lapsing tonnage that comes back as regrades, median of the last 8 delivery periods) and lots at risk are in `economics.validity`. Delivery value now includes the Rule 9.23(b)(ii)(B) loss-of-weight allowance (0.25% per 30 days from the first grading date to mid delivery month; re-weighing avoids it — `value_before_allow` kept) and the expected discount change on regrade.
