"""Catch-up job: every report on the desk should be in the data soon after its publisher releases it.

For each report in data/release_calendar.json it compares the latest data date with the newest release that should be in by
now (release time + late_after_hours; rules of type 'age' use the data-status limit), and checks the last run of the workflow
that collects it. A late report or a failed last run gets its workflow re-dispatched (once per cooldown) when that workflow
lives in the repo running this job; reports collected by another BMR-Com repo are rerun by that repo's own catch-up job
(the same script with --repo), because a cross-repo dispatch needs a token the repos do not have. With --wait it waits for
the reruns, rechecks and exits 1 (red run) if anything collected automatically is still late or a rerun failed.
Reports that need an upload or manual entry by Ma are listed but never fail the run.

  desk:   python pipelines/watchdog.py [--wait] [--strict]            (reads data/status.json; writes data/watchdog.json)
  source: python watchdog.py --repo BMR-Com/<repo> --calendar release_calendar.json --root . [--wait] [--strict]
Standard library only. Needs GITHUB_TOKEN (actions: write) to dispatch; e-mail only when SMTP_HOST/SMTP_USER/SMTP_PASS/EMAIL_FROM/EMAIL_TO are set.
"""
import argparse, json, os, smtplib, subprocess, sys, time
import urllib.request, urllib.error
from datetime import date, datetime, timedelta, timezone
from email.mime.text import MIMEText
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import release_rules as R

DESK = "BMR-Com/Brazil--trade"
API = "https://api.github.com"


def gh(method, path, body=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Accept", "application/vnd.github+json")
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            t = r.read()
            return r.status, (json.loads(t) if t else None)
    except urllib.error.HTTPError as e:
        return e.code, {"message": e.read()[:300].decode(errors="replace")}
    except Exception as e:
        return 0, {"message": str(e)[:300]}


def runs(wf, n=10):
    code, J = gh("GET", f"/repos/{wf['repo']}/actions/workflows/{wf['file']}/runs?per_page={n}")
    return (J or {}).get("workflow_runs", []) if code == 200 else None


def dig(J, key):
    for k in key:
        J = J[k]
    return J


def bd_age(d, today, cal):
    n, x = 0, d
    while x < today:
        x += timedelta(days=1)
        if cal.is_bd(x):
            n += 1
    return n


def assess(e, latest, status_state, cal, now):
    """Return a reason string if the report is late, else None."""
    exp = R.expected(e, cal, now)
    if exp:
        if not latest or latest < exp["data_date"]:
            return f"data {latest or 'missing'}; release of {exp['release'][:16].replace('T', ' ')} ET (data {exp['data_date']}) should be in since {exp['late_since'][:16].replace('T', ' ')} ET", exp
        return None, exp
    if status_state is not None:
        return (None if status_state == "ok" else f"data {latest or 'missing'} is older than the {e['age_limit']} {e['age_unit']} limit"), None
    if not latest:
        return "data missing", None
    today = now.date()
    a = bd_age(date.fromisoformat(latest), today, cal) if e["age_unit"] == "business days" else (today - date.fromisoformat(latest)).days
    return (f"data {latest} is {a} {e['age_unit']} old (limit {e['age_limit']})" if a > e["age_limit"] else None), None


def latest_dates(entries, args, root):
    """{id: (latest, status_state)} from data/status.json (desk) or from each entry's probe in the checked-out repo."""
    out = {}
    if args.repo == DESK:
        S = json.loads((root / "data" / "status.json").read_text())
        by = {r["source"]: r for r in S["sources"]}
        for e in entries:
            r = by.get(e["status_source"])
            out[e["id"]] = ((r or {}).get("latest"), (r or {}).get("state"))
    else:
        for e in entries:
            p = e.get("probe")
            try:
                v = str(dig(json.loads((root / p["path"]).read_text()), p["key"]))[:10] if p else None
            except Exception as ex:
                print("probe failed:", e["id"], repr(ex)[:120]); v = None
            out[e["id"]] = (v, None)
    return out


def check(entries, args, root, cal, now, prev):
    L = latest_dates(entries, args, root)
    items, wf_state = [], {}
    for e in entries:
        latest, st = L[e["id"]]
        reason, exp = assess(e, latest, st, cal, now)
        wf = e.get("workflow")
        key = f"{wf['repo']}/{wf['file']}" if wf else None
        if wf and key not in wf_state:
            rs = runs(wf)
            done = [r for r in (rs or []) if r["status"] == "completed"]
            wf_state[key] = {"reachable": rs is not None, "last": done[0] if done else None, "runs": rs or []}
        ws = wf_state.get(key)
        failed = bool(ws and ws["last"] and ws["last"]["conclusion"] in ("failure", "timed_out", "startup_failure"))
        no_run = False
        if reason and exp and ws and ws["reachable"]:
            rel = datetime.fromisoformat(exp["release"]).astimezone(timezone.utc)
            no_run = not any(datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) >= rel for r in ws["runs"])
        if reason or failed:
            items.append({"id": e["id"], "report": e["status_source"] if e["report"] == "Desk build" else e["report"], "tab": e["tab"], "latest": latest,
                          "expected": exp["data_date"] if exp else None, "late": bool(reason),
                          "reason": "; ".join(x for x in [reason, f"last run of {wf['file']} {ws['last']['conclusion']} ({ws['last']['html_url']})" if failed else None,
                                                          f"no run of {wf['file']} since the release" if no_run else None] if x),
                          "workflow": key, "manual": e.get("manual", False),
                          "owner": "Ma (upload / manual entry)" if e.get("manual") else (wf["repo"] if wf else "Ma")})
    return items, wf_state


def dispatch(items, args, prev, now, cooldown_h):
    done, seen = [], {}
    last = {d["workflow"]: d["at"] for d in (prev.get("dispatch_log") or [])}
    for it in items:
        k = it["workflow"]
        if it["manual"] or not k:
            continue
        if k in seen:
            it["action"] = seen[k]
            continue
        repo, file = k.rsplit("/", 1)
        if repo != args.repo:
            it["action"] = f"rerun by {repo}'s own catch-up job"
            continue
        if k in last and now - datetime.fromisoformat(last[k]) < timedelta(hours=cooldown_h):
            it["action"] = seen[k] = f"already rerun at {last[k][:16]} UTC (cooldown {cooldown_h} h)"
            continue
        if args.dry_run:
            code = 204; print("DRY RUN: would dispatch", k)
        else:
            code, J = gh("POST", f"/repos/{repo}/actions/workflows/{file}/dispatches", {"ref": "main"})
        ok = code == 204
        it["action"] = seen[k] = "rerun dispatched" if ok else f"dispatch failed (HTTP {code})"
        done.append({"workflow": k, "file": file, "repo": repo, "at": now.isoformat(timespec="minutes"), "ok": ok, "for": it["id"]})
        print(("dispatched " if ok else f"DISPATCH FAILED {code} ") + k + " for " + it["id"])
    return done


def wait_for(done, minutes):
    """Wait until each dispatched workflow has a run created after the dispatch that completed; record its conclusion."""
    end = time.time() + minutes * 60
    pending = [d for d in done if d["ok"]]
    while pending and time.time() < end:
        time.sleep(60)
        for d in list(pending):
            rs = runs({"repo": d["repo"], "file": d["file"]}, 5) or []
            t0 = datetime.fromisoformat(d["at"]) - timedelta(minutes=1)
            mine = [r for r in rs if datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) >= t0]
            if mine and mine[0]["status"] == "completed":
                d["result"] = mine[0]["conclusion"]; d["run"] = mine[0]["html_url"]; pending.remove(d)
                print("rerun finished:", d["workflow"], d["result"])
    for d in pending:
        d["result"] = "still running after wait"


def email(subject, body):
    env = {k: os.environ.get(k, "") for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "EMAIL_FROM", "EMAIL_TO")}
    if not all(env[k] for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS", "EMAIL_FROM", "EMAIL_TO")):
        print("e-mail secrets not set: no e-mail"); return False
    m = MIMEText(body); m["Subject"] = subject; m["From"] = env["EMAIL_FROM"]; m["To"] = env["EMAIL_TO"]
    try:
        with smtplib.SMTP(env["SMTP_HOST"], int(env["SMTP_PORT"] or 587), timeout=30) as s:
            s.starttls(); s.login(env["SMTP_USER"], env["SMTP_PASS"])
            s.sendmail(env["EMAIL_FROM"], [x.strip() for x in env["EMAIL_TO"].split(",") if x.strip()], m.as_string())
        print("e-mail sent"); return True
    except Exception as ex:
        print("e-mail failed:", repr(ex)[:200]); return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=DESK)
    ap.add_argument("--calendar", default=str(R.CAL_PATH))
    ap.add_argument("--root", default=str(HERE.parent))
    ap.add_argument("--out", default=None, help="log file (desk: data/watchdog.json)")
    ap.add_argument("--wait", action="store_true", help="wait for reruns, then recheck")
    ap.add_argument("--strict", action="store_true", help="exit 1 if anything automatic is still late or a rerun failed")
    ap.add_argument("--no-dispatch", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--now", default=None, help="ISO time (testing)")
    args = ap.parse_args()
    root = Path(args.root)
    calj = R.load_calendar(args.calendar); cal = R.Cal(calj)
    now = datetime.fromisoformat(args.now).astimezone(timezone.utc) if args.now else datetime.now(timezone.utc)
    nowET = now.astimezone(R.ET)
    out = Path(args.out) if args.out else (root / "data" / "watchdog.json" if args.repo == DESK else None)
    prev = {}
    if out and out.exists():
        try:
            prev = json.loads(out.read_text())
        except Exception:
            prev = {}
    entries = [e for e in calj["reports"] if args.repo == DESK or (e.get("workflow") or {}).get("repo") == args.repo]
    cooldown = calj.get("catch_up", {}).get("rerun_cooldown_hours", 6)
    items, _ = check(entries, args, root, cal, nowET, prev)
    print(f"{len(items)} item(s) late or failed of {len(entries)}")
    for it in items:
        print(f"  {'MANUAL ' if it['manual'] else ''}{it['id']}: {it['reason']}")
    done = [] if args.no_dispatch else dispatch(items, args, prev, now, cooldown)
    after = items
    if args.wait and any(d["ok"] for d in done):
        wait_for(done, calj.get("catch_up", {}).get("wait_minutes", 40))
        subprocess.run(["git", "-C", str(root), "pull", "-q", "--rebase", "--autostash"], check=False)
        if args.repo == DESK:
            subprocess.run([sys.executable, str(root / "pipelines" / "data_status.py")], check=False)
        after, _ = check(entries, args, root, cal, datetime.now(timezone.utc).astimezone(R.ET), prev)
        acts = {i["id"]: i.get("action") for i in items}
        for i in after:
            i.setdefault("action", acts.get(i["id"]))
    still = [i for i in after if not i["manual"] and i["late"]]
    failed_now = [i for i in after if not i["manual"] and not i["late"]]   # data fine but last run failed
    bad_reruns = [d for d in done if d.get("result") not in (None, "success")]
    needs_ma = [i for i in after if i["manual"]]
    red = bool(still or bad_reruns or failed_now)
    log = (prev.get("dispatch_log") or [])
    log = [d for d in log if now - datetime.fromisoformat(d["at"]) < timedelta(days=7)] + done
    J = {"checked": now.strftime("%Y-%m-%d %H:%M UTC"), "repo": args.repo, "mode": "wait+recheck" if args.wait else "check",
         "late_or_failed_at_start": items, "reruns": done, "still_late": still, "last_run_failed": failed_now,
         "needs_ma": needs_ma, "result": "red" if red else "green", "dispatch_log": log,
         "last_email": prev.get("last_email")}
    if args.strict and red and J["last_email"] != now.date().isoformat():
        lines = [f"- {i['report']} ({i['tab']}): {i['reason']}. {i.get('action') or ''}" for i in still + failed_now]
        lines += [f"- rerun of {d['workflow']}: {d.get('result')}" for d in bad_reruns]
        if email(f"Softs desk catch-up: {len(still) + len(failed_now) + len(bad_reruns)} item(s) still late or failing ({args.repo})",
                 "Checked " + J["checked"] + "\n\n" + "\n".join(lines) + "\n\nDetails: https://github.com/" + args.repo + "/actions"):
            J["last_email"] = now.date().isoformat()
    if out:
        out.write_text(json.dumps(J, indent=1, ensure_ascii=False))
    for i in still + failed_now:
        print(f"::error::{i['report']}: {i['reason']}{'; ' + i['action'] if i.get('action') else ''}")
    for d in bad_reruns:
        print(f"::error::rerun of {d['workflow']}: {d.get('result')}")
    for i in needs_ma:
        print(f"::warning::needs Ma: {i['report']}: {i['reason']}")
    print("RESULT:", J["result"])
    if args.strict and red:
        sys.exit(1)


if __name__ == "__main__":
    main()
