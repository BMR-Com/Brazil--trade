"""Temporary probe 3: open ICE report 4 (Certified Stock Reports - Cotton) in a browser, record file links and network calls."""
import json, os, re, asyncio
from playwright.async_api import async_playwright
os.makedirs("data/probe", exist_ok=True); out = {"requests": [], "links": [], "downloads": []}
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); ctx = await b.new_context(accept_downloads=True, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36")
        pg = await ctx.new_page()
        pg.on("request", lambda r: out["requests"].append(r.url) if "ice.com" in r.url and not re.search(r"\.(css|png|svg|woff2?|gif|jpg)(\?|$)", r.url) else None)
        resp = {}
        async def on_resp(r):
            if ("api" in r.url or "report" in r.url) and "json" in (r.headers.get("content-type") or ""):
                try: resp[r.url] = (await r.text())[:20000]
                except Exception: pass
        pg.on("response", on_resp)
        await pg.goto("https://www.ice.com/report/4", wait_until="networkidle", timeout=90000)
        await pg.wait_for_timeout(5000)
        out["title"] = await pg.title()
        out["text"] = (await pg.inner_text("body"))[:6000]
        out["links"] = await pg.eval_on_selector_all("a", "els => els.map(e => [e.innerText.trim().slice(0,80), e.href]).filter(x => x[1])")
        out["json"] = resp
        for sel in ["text=/xls/i", "text=/Download/i", "a[href*='.xls']", "a[href*='publicdocs']"]:
            try:
                async with pg.expect_download(timeout=15000) as dl:
                    await pg.click(sel, timeout=5000)
                d = await dl.value; path = "data/probe/" + d.suggested_filename; await d.save_as(path); out["downloads"].append([sel, d.url, path]); break
            except Exception as e: out["downloads"].append([sel, str(e)[:120]])
        await pg.screenshot(path="data/probe/ice_report4.png", full_page=True)
        await b.close()
asyncio.run(main())
json.dump(out, open("data/probe/ct_probe3.json", "w"), indent=1)
