"""
Brazil Trade Scraper — Incremental Updater
==========================================
Fetches only new/incomplete years from MDIC/SECEX and merges into
the existing data/exports.csv that was bootstrapped by the Colab notebook.

Usage:
  python scraper.py                    # fetch only missing/incomplete years
  python scraper.py --years 2025 2026  # force specific years
"""

import io, time, logging, argparse
import requests, urllib3, pandas as pd
from pathlib import Path
from datetime import date

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger(__name__)

BASE_DIR    = Path(__file__).parent
DATA_DIR    = BASE_DIR / "data"
EXPORT_CSV  = DATA_DIR / "exports.csv"
COUNTRY_CSV = DATA_DIR / "countries.csv"
DATA_DIR.mkdir(exist_ok=True)

BASE_URL = "https://balanca.economia.gov.br/balanca/bd/comexstat-bd/ncm"
BALE_KG  = 217.724

NCM_MAP = {
    "09011100": {"commodity":"coffee",   "subtype":"arabica_green",    "desc":"Green arabica (not roasted, not decaff)"},
    "09011200": {"commodity":"coffee",   "subtype":"arabica_green",    "desc":"Green arabica (not roasted, decaff)"},
    "09011900": {"commodity":"coffee",   "subtype":"conillon_robusta", "desc":"Conillon / Robusta (not roasted, other)"},
    "09012100": {"commodity":"coffee",   "subtype":"arabica_green",    "desc":"Roasted arabica (not decaff)"},
    "09012200": {"commodity":"coffee",   "subtype":"arabica_green",    "desc":"Roasted arabica (decaff)"},
    "09019000": {"commodity":"coffee",   "subtype":"arabica_green",    "desc":"Coffee husks and substitutes"},
    "21011110": {"commodity":"coffee",   "subtype":"soluble",          "desc":"Soluble/instant coffee extract (not decaff)"},
    "21011190": {"commodity":"coffee",   "subtype":"soluble",          "desc":"Soluble/instant coffee extract (other)"},
    "21011200": {"commodity":"coffee",   "subtype":"soluble",          "desc":"Preparations based on coffee extract"},
    "52010010": {"commodity":"cotton",   "subtype":"raw_cotton",       "desc":"Raw cotton not carded, staple <28.5mm"},
    "52010090": {"commodity":"cotton",   "subtype":"raw_cotton",       "desc":"Raw cotton not carded, other"},
    "52030000": {"commodity":"cotton",   "subtype":"raw_cotton",       "desc":"Cotton carded or combed"},
    "17011310": {"commodity":"sugar",    "subtype":"raw_cane",         "desc":"Raw cane sugar for refining"},
    "17011390": {"commodity":"sugar",    "subtype":"raw_cane",         "desc":"Raw cane sugar other"},
    "17011410": {"commodity":"sugar",    "subtype":"raw_beet",         "desc":"Raw beet sugar for refining"},
    "17011490": {"commodity":"sugar",    "subtype":"raw_beet",         "desc":"Raw beet sugar other"},
    "17019910": {"commodity":"sugar",    "subtype":"refined",          "desc":"Refined white cane sugar"},
    "17019990": {"commodity":"sugar",    "subtype":"refined",          "desc":"Refined white sugar other"},
    "12010090": {"commodity":"soybeans", "subtype":"raw_soybeans",     "desc":"Raw soybeans not for sowing"},
    "12010010": {"commodity":"soybeans", "subtype":"raw_soybeans",     "desc":"Soybeans for sowing"},
    "23040010": {"commodity":"soybeans", "subtype":"soybean_meal",     "desc":"Soybean oilcake / meal pellets"},
    "23040090": {"commodity":"soybeans", "subtype":"soybean_meal",     "desc":"Soybean oilcake residues other"},
    "15071000": {"commodity":"soybeans", "subtype":"soybean_oil",      "desc":"Crude soybean oil"},
    "15079011": {"commodity":"soybeans", "subtype":"soybean_oil",      "desc":"Refined soybean oil (edible)"},
    "15079019": {"commodity":"soybeans", "subtype":"soybean_oil",      "desc":"Refined soybean oil (other)"},
    "10059010": {"commodity":"corn",     "subtype":"yellow_corn",      "desc":"Yellow dent corn"},
    "10059090": {"commodity":"corn",     "subtype":"yellow_corn",      "desc":"Other corn not seed"},
    "10051000": {"commodity":"corn",     "subtype":"seed_corn",        "desc":"Corn seed"},
}
TARGET_NCMS = set(NCM_MAP.keys())

# Fallback country lookup if countries.csv is missing
COUNTRIES_EMBEDDED = {
    "013":"Afghanistan","017":"South Africa","023":"Albania","025":"Germany",
    "027":"Andorra","031":"Angola","037":"Antigua And Barbuda","040":"Saudi Arabia",
    "041":"Algeria","043":"Argentina","047":"Armenia","048":"Aruba","050":"Australia",
    "053":"Austria","055":"Azerbaijan","058":"Bahamas","059":"Bahrain","063":"Bangladesh",
    "064":"Barbados","068":"Belarus","069":"Belgium","072":"Belize","073":"Benin",
    "076":"Bolivia","077":"Bosnia And Herzegovina","080":"Botswana","085":"Brunei",
    "087":"Bulgaria","090":"Burkina Faso","094":"Burundi","099":"Cabo Verde",
    "102":"Cameroon","103":"Cambodia","105":"Canada","107":"Chile","111":"China",
    "115":"Colombia","116":"Comoros","119":"Congo","123":"North Korea","124":"South Korea",
    "127":"Costa Rica","131":"Croatia","132":"Cuba","139":"Denmark","141":"Djibouti",
    "145":"Dominica","147":"Dominican Republic","149":"Ecuador","153":"Egypt",
    "157":"El Salvador","160":"United Arab Emirates","163":"Eritrea","164":"Slovakia",
    "166":"Slovenia","169":"Spain","170":"United States","172":"Estonia","175":"Ethiopia",
    "179":"Fiji","182":"Philippines","183":"Finland","184":"France","187":"Gabon",
    "190":"Gambia","193":"Georgia","196":"Ghana","199":"Gibraltar","201":"Greece",
    "202":"Grenada","204":"Guadeloupe","207":"Guatemala","211":"Guinea",
    "213":"Guinea-Bissau","215":"Equatorial Guinea","218":"Guyana","221":"Haiti",
    "225":"Honduras","227":"Hong Kong","229":"Hungary","232":"Yemen","235":"India",
    "238":"Indonesia","239":"Iran","240":"Iraq","243":"Ireland","246":"Iceland",
    "249":"Israel","252":"Italy","253":"Jamaica","255":"Japan","258":"Jordan",
    "261":"Kazakhstan","264":"Kenya","268":"Kuwait","270":"Laos","272":"Lesotho",
    "274":"Latvia","277":"Lebanon","280":"Liberia","283":"Libya","285":"Liechtenstein",
    "287":"Lithuania","290":"Luxembourg","291":"Macao","292":"North Macedonia",
    "295":"Madagascar","298":"Malawi","300":"Malaysia","303":"Maldives","305":"Mali",
    "308":"Malta","310":"Morocco","313":"Martinique","316":"Mauritius","319":"Mauritania",
    "322":"Mexico","325":"Mozambique","328":"Moldova","331":"Monaco","334":"Mongolia",
    "337":"Montenegro","343":"Myanmar","346":"Namibia","349":"Nepal","353":"Nicaragua",
    "355":"Niger","356":"Nigeria","358":"Norway","361":"New Zealand","364":"Oman",
    "366":"Netherlands","369":"Pakistan","372":"Panama","375":"Papua New Guinea",
    "378":"Paraguay","380":"Peru","381":"Poland","384":"Portugal","386":"Puerto Rico",
    "389":"Qatar","393":"United Kingdom","396":"Czech Republic","399":"Romania",
    "400":"Russia","403":"Rwanda","406":"Saint Kitts And Nevis","409":"Saint Lucia",
    "412":"Samoa","414":"Saint Vincent And The Grenadines","418":"San Marino",
    "420":"Sao Tome And Principe","422":"Senegal","425":"Sierra Leone","428":"Somalia",
    "431":"Sri Lanka","434":"Sudan","437":"Sweden","438":"Switzerland","440":"Suriname",
    "443":"Eswatini","446":"Syria","449":"Tajikistan","452":"Tanzania","455":"Taiwan",
    "458":"Thailand","460":"Timor-Leste","462":"Togo","465":"Trinidad And Tobago",
    "467":"Tunisia","470":"Turkmenistan","472":"Turkey","474":"Ukraine","477":"Uganda",
    "479":"Uruguay","481":"Uzbekistan","484":"Vanuatu","487":"Venezuela","489":"Vietnam",
    "492":"Zambia","495":"Zimbabwe","499":"Serbia","501":"South Sudan","532":"Palestine",
    "605":"Faroe Islands","608":"French Guiana","610":"French Polynesia","614":"Greenland",
    "628":"New Caledonia","708":"Central African Republic","711":"Chad","714":"DR Congo",
    "717":"Ivory Coast","720":"Cyprus","729":"Eswatini",
}

OUT_COLS = [
    "year","month","ncm","commodity","subtype","description",
    "country_code","country_name",
    "qt_estat","kg_net","mt","bales_480lb","fob_usd",
]


def load_countries() -> dict:
    if COUNTRY_CSV.exists():
        df = pd.read_csv(COUNTRY_CSV, dtype=str)
        code_col = next((c for c in df.columns if "code" in c.lower()), df.columns[0])
        name_col = next((c for c in df.columns if "name" in c.lower()), df.columns[1])
        df[code_col] = df[code_col].str.strip().str.zfill(3)
        result = dict(zip(df[code_col], df[name_col]))
        log.info("Loaded %d countries from %s", len(result), COUNTRY_CSV)
        return result
    log.warning("countries.csv missing — using embedded lookup")
    pd.DataFrame([{"country_code":k,"country_name":v}
                  for k,v in COUNTRIES_EMBEDDED.items()]).to_csv(COUNTRY_CSV, index=False)
    return COUNTRIES_EMBEDDED


def download_year(year: int) -> pd.DataFrame | None:
    url = f"{BASE_URL}/EXP_{year}.csv"
    log.info("Fetching %s", url)
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=180, verify=False)
            resp.raise_for_status()
            break
        except Exception as e:
            log.warning("  attempt %d: %s", attempt+1, e)
            if attempt == 2:
                log.error("  all retries failed for %d", year)
                return None
            time.sleep(5*(attempt+1))

    chunks = []
    try:
        for chunk in pd.read_csv(io.BytesIO(resp.content), sep=";", dtype=str,
                                  encoding="latin-1", chunksize=300_000):
            chunk.columns = [c.strip().upper() for c in chunk.columns]
            chunk["CO_NCM"] = chunk["CO_NCM"].str.strip().str.zfill(8)
            hit = chunk[chunk["CO_NCM"].isin(TARGET_NCMS)]
            if not hit.empty:
                chunks.append(hit)
    except Exception as e:
        log.error("  parse error for %d: %s", year, e)
        return None

    if not chunks:
        log.info("  no target NCMs in %d", year)
        return None
    df = pd.concat(chunks, ignore_index=True)
    log.info("  %d rows matched for %d", len(df), year)
    return df


def enrich(df: pd.DataFrame, countries: dict) -> pd.DataFrame:
    for col in ("CO_ANO","CO_MES","QT_ESTAT","KG_LIQUIDO","VL_FOB"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df["CO_PAIS"] = df["CO_PAIS"].astype(str).str.strip().str.zfill(3)
    df["commodity"]    = df["CO_NCM"].map(lambda x: NCM_MAP.get(x,{}).get("commodity","unknown"))
    df["subtype"]      = df["CO_NCM"].map(lambda x: NCM_MAP.get(x,{}).get("subtype","unknown"))
    df["description"]  = df["CO_NCM"].map(lambda x: NCM_MAP.get(x,{}).get("desc",""))
    df["mt"]           = (df["KG_LIQUIDO"]/1000).round(4)
    df["bales_480lb"]  = (df["KG_LIQUIDO"]/BALE_KG).round(2)
    df["country_name"] = df["CO_PAIS"].map(countries).fillna("Unknown")
    df = df.rename(columns={"CO_ANO":"year","CO_MES":"month","CO_NCM":"ncm",
                             "CO_PAIS":"country_code","QT_ESTAT":"qt_estat",
                             "KG_LIQUIDO":"kg_net","VL_FOB":"fob_usd"})
    df["year"]  = df["year"].astype(int)
    df["month"] = df["month"].astype(int)
    return df[OUT_COLS]


def load_existing() -> pd.DataFrame:
    if EXPORT_CSV.exists():
        df = pd.read_csv(EXPORT_CSV, dtype={"ncm":str,"country_code":str})
        log.info("Loaded %d existing rows", len(df))
        return df
    log.warning("exports.csv not found — will create fresh")
    return pd.DataFrame(columns=OUT_COLS)


def complete_years(df: pd.DataFrame) -> set:
    if df.empty:
        return set()
    cur = date.today().year
    counts = df.groupby("year")["month"].nunique()
    return {int(y) for y in counts[counts >= 12].index if int(y) < cur}


def save(df: pd.DataFrame):
    df = df.sort_values(["year","month","commodity","country_code"]).reset_index(drop=True)
    df.to_csv(EXPORT_CSV, index=False)
    log.info("Saved %d rows → %s (%.1f MB)",
             len(df), EXPORT_CSV, EXPORT_CSV.stat().st_size/1e6)


def run(years_override=None):
    countries = load_countries()
    existing  = load_existing()
    done      = complete_years(existing)
    cur_year  = date.today().year

    to_fetch = years_override if years_override else [
        y for y in range(1997, cur_year+1) if y not in done
    ]
    if not to_fetch:
        log.info("All years complete — nothing to fetch.")
        return

    log.info("Years to fetch: %s", to_fetch)
    new_frames = []
    for year in to_fetch:
        raw = download_year(year)
        if raw is not None:
            new_frames.append(enrich(raw, countries))

    if not new_frames:
        log.info("No new data retrieved.")
        return

    if not existing.empty:
        existing = existing[~existing["year"].isin(to_fetch)]
    combined = pd.concat([existing]+new_frames, ignore_index=True)
    save(combined)
    log.info("Done. Total rows: %d", len(combined))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs="+", type=int)
    args = ap.parse_args()
    run(years_override=args.years)
