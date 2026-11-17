"""Which UNICA Centre-South reports are published: reads the UNICA report listing, opens the newest few PDFs and records
their 'Posição até' date. Writes data/sugar/unica_check.json (used for the 'UNICA last published' label and data status)."""
import io, json, re
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sugar" / "unica_check.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; BMR-Com research desk)"}


def main():
    res = {"checked": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "listing": "https://unicadata.com.br/listagem.php?idMn=63", "reports": []}
    try:
        t = requests.get(res["listing"], headers=UA, timeout=90).text
        links = list(dict.fromkeys(re.findall(r"https://unicadata\.com\.br/arquivos/pdfs/[^'\"\s]+\.pdf", t)))
        res["n_links"] = len(links)
        import pdfplumber
        for u in links[:4]:
            try:
                b = requests.get(u, headers=UA, timeout=120).content
                with pdfplumber.open(io.BytesIO(b)) as pdf:
                    txt = (pdf.pages[0].extract_text() or "")
                m = re.search(r"Posição até\s*(\d{2})/(\d{2})/(\d{4})", txt)
                res["reports"].append({"url": u, "position": f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None, "title": txt.strip().splitlines()[0][:120] if txt.strip() else ""})
            except Exception as e:
                res["reports"].append({"url": u, "error": str(e)[:120]})
    except Exception as e:
        res["error"] = str(e)[:200]
    pos = [r["position"] for r in res["reports"] if r.get("position")]
    res["latest_position"] = max(pos) if pos else None
    OUT.write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(json.dumps(res, ensure_ascii=False)[:1500])


if __name__ == "__main__":
    main()
