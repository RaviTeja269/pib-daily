#!/usr/bin/env python3
"""Fetch new PIB press releases, tag them for exam relevance, write JSON for the site.

Why it opens every release page: PIB's RSS feed carries only a title and a link
(no date, no ministry, no text) and lists roughly the latest 20 releases. So the
feed is used to discover release IDs (PRID), and each new release page is read
for the ministry, the posted time and the text.

Run it often (the GitHub Actions workflow runs it hourly) so releases do not
roll off the feed before they are picked up.

Usage:
    python scripts/fetch_pib.py                    # normal run
    python scripts/fetch_pib.py --allrel today     # also sweep PIB's "All releases" page (best effort)
    python scripts/fetch_pib.py --fixtures tests/fixtures --sample   # offline test run
"""
from __future__ import annotations

import argparse
import html as htmllib
import json
import logging
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify import Classifier  # noqa: E402
import enrich as enrich_mod  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
IST = timezone(timedelta(hours=5, minutes=30))
log = logging.getLogger("pib")

PRID_RE = re.compile(r"PRID=(\d+)", re.I)
POSTED_RE = re.compile(
    r"Posted\s+On:\s*(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\s+(\d{1,2}):(\d{2})\s*([AP]M)(?:\s+by\s+([^\n|]+))?",
    re.I,
)
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
MINISTRY_RE = re.compile(
    r"(Ministry of [^\n]{3,90}|Department of [^\n]{3,90}|Prime Minister['’]s Office|Cabinet Committee[^\n]{0,60}|"
    r"Cabinet|President['’]s Secretariat|Vice[- ]President['’]s Secretariat|Election Commission[^\n]{0,40}|"
    r"NITI Aayog|Lok Sabha Secretariat|Rajya Sabha Secretariat|Special Service and Features)",
)
SIGNOFF_RE = re.compile(r"^[A-Za-z0-9.\-]+(?:\s*/\s*[A-Za-z0-9.\-]+){2,}\s*$")
JUNK_LINES = {"provide suggestions / comments", "provide suggestions", "visitor counter", "***", "*****"}


# ---------------------------------------------------------------- networking
def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": "pib-exam-daily/1.0 (personal study tool; reads public PIB pages)",
            "Accept-Language": "en-IN,en;q=0.9",
        }
    )
    return s


def http_get(session: requests.Session, url: str, retries: int = 3, timeout: int = 30) -> str | None:
    last = None
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=timeout)
            if r.status_code == 200 and r.content.strip():
                return r.content.decode("utf-8-sig", errors="replace")
            last = f"HTTP {r.status_code}"
            if r.status_code in (403, 404):
                break
        except requests.RequestException as e:
            last = str(e)
        time.sleep(2**attempt)
    log.warning("GET failed: %s (%s)", url, last)
    return None


# -------------------------------------------------------------------- parsing
def parse_feed(xml_text: str) -> list[tuple[str, str]]:
    """Return [(prid, title)] from a PIB RSS feed. Regex-based on purpose: tolerant of stray characters."""
    xml_text = xml_text.replace("​", "").lstrip("﻿")
    out: list[tuple[str, str]] = []
    for block in re.findall(r"<item>(.*?)</item>", xml_text, flags=re.S | re.I):
        link = re.search(r"<link>(.*?)</link>", block, flags=re.S | re.I)
        title = re.search(r"<title>(.*?)</title>", block, flags=re.S | re.I)
        if not link:
            continue
        m = PRID_RE.search(htmllib.unescape(link.group(1)))
        if not m:
            continue
        t = htmllib.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", title.group(1))) if title else ""
        out.append((m.group(1), re.sub(r"\s+", " ", t).strip()))
    return out


def parse_release(page_html: str, fallback_title: str = "") -> dict | None:
    """Pull title, ministry, posted time and body text out of a PIB release page."""
    soup = BeautifulSoup(page_html, "html.parser")
    for t in soup(["script", "style", "noscript", "nav", "footer", "form"]):
        t.decompose()

    container = (
        soup.select_one("[class*='content-right-part']")
        or soup.select_one("#PressReleaseDetail")
        or soup.select_one("[class*='ReleaseContent']")
        or soup.body
        or soup
    )
    lines = [ln.strip() for ln in container.get_text("\n", strip=True).split("\n") if ln.strip()]
    flat = "\n".join(lines)

    posted_dt, office = None, None
    m = POSTED_RE.search(soup.get_text("\n", strip=True))
    if m:
        d, mon, y, hh, mm, ap, office = m.groups()
        hour = int(hh) % 12 + (12 if ap.upper() == "PM" else 0)
        try:
            posted_dt = datetime(int(y), MONTHS[mon.lower()], int(d), hour, int(mm), tzinfo=IST)
        except (KeyError, ValueError):
            posted_dt = None
        office = office.strip() if office else None

    title_el = container.find("h2") or soup.find("h2")
    title = title_el.get_text(" ", strip=True) if title_el else ""
    if not title:
        title = fallback_title
    if not title:
        return None

    ministry = None
    min_el = container.select_one("[class*='inistry']")
    if min_el:
        ministry = min_el.get_text(" ", strip=True)
    if not ministry:
        h3 = container.find("h3")
        if h3:
            ministry = h3.get_text(" ", strip=True)
    if not ministry or len(ministry) > 120:
        mm_ = MINISTRY_RE.search(flat[:700])
        ministry = mm_.group(1).strip() if mm_ else "Unknown"

    # Body = everything after the "Posted On" line, minus sign-off and boilerplate lines.
    start = 0
    for i, ln in enumerate(lines):
        if ln.lower().startswith("posted on"):
            start = i + 1
            break
    body_lines = []
    for ln in lines[start:]:
        low = ln.lower()
        if low in JUNK_LINES or low.startswith("release id") or SIGNOFF_RE.match(ln):
            continue
        if ln == title:
            continue
        body_lines.append(ln)
    body = "\n".join(body_lines).strip()

    return {
        "title": title,
        "ministry": ministry,
        "posted_at": posted_dt,
        "office": office,
        "body": body,
    }


def make_excerpt(body: str, limit: int = 560) -> str:
    text = re.sub(r"\s+", " ", body).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    # end on a sentence boundary if one exists in the back half
    p = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    return (cut[: p + 1] if p > limit * 0.5 else cut.rsplit(" ", 1)[0] + "…").strip()


# ------------------------------------------------------------------- storage
def day_file(data_dir: Path, d: str) -> Path:
    return data_dir / f"{d}.json"


def load_day(data_dir: Path, d: str) -> dict:
    p = day_file(data_dir, d)
    if p.exists():
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
            if doc.get("sample"):  # a real run replaces demo data
                return {"date": d, "items": []}
            return doc
        except json.JSONDecodeError:
            log.warning("corrupt %s, starting that day fresh", p)
    return {"date": d, "items": []}


def save_day(data_dir: Path, doc: dict, thresholds: dict, sample: bool) -> None:
    doc["items"].sort(key=lambda it: (-it["score"], it["posted_at"]))
    doc["thresholds"] = thresholds
    doc["updated_at"] = datetime.now(IST).isoformat(timespec="seconds")
    if sample:
        doc["sample"] = True
    else:
        doc.pop("sample", None)
    day_file(data_dir, doc["date"]).write_text(
        json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )


def recent_prids(data_dir: Path, days: int) -> set[str]:
    seen: set[str] = set()
    cutoff = (datetime.now(IST).date() - timedelta(days=days)).isoformat()
    for p in data_dir.glob("????-??-??.json"):
        if p.stem < cutoff:
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if doc.get("sample"):
            continue
        seen.update(str(it["prid"]) for it in doc.get("items", []))
    return seen


def purge_samples(data_dir: Path) -> int:
    n = 0
    for p in data_dir.glob("????-??-??.json"):
        try:
            if json.loads(p.read_text(encoding="utf-8")).get("sample"):
                p.unlink()
                n += 1
        except json.JSONDecodeError:
            pass
    return n


def prune_old(data_dir: Path, keep_days: int) -> None:
    cutoff = (datetime.now(IST).date() - timedelta(days=keep_days)).isoformat()
    for p in data_dir.glob("????-??-??.json"):
        if p.stem < cutoff:
            p.unlink()


def rebuild_index(data_dir: Path) -> None:
    days = []
    for p in sorted(data_dir.glob("????-??-??.json"), reverse=True):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        items = doc.get("items", [])
        counts = {k: sum(1 for i in items if i["priority"] == k) for k in ("must", "good", "skim", "skip")}
        days.append(
            {
                "date": doc["date"],
                "total": len(items),
                **counts,
                "ap": sum(1 for i in items if i.get("ap")),
                "sample": bool(doc.get("sample")),
            }
        )
    index = {"generated_at": datetime.now(IST).isoformat(timespec="seconds"), "days": days}
    (data_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")


# ----------------------------------------------------------- "All releases" sweep
def fetch_allrel(session: requests.Session, cfg: dict, day: date) -> list[tuple[str, str]]:
    """Best-effort sweep of PIB's 'All releases' page for one day.

    The page is an ASP.NET form with ministry/day/month/year drop-downs, so this finds the
    drop-downs by their contents instead of hard-coding field names. If PIB changes the page
    this returns [] and the normal RSS path keeps working.
    """
    base = cfg["allrel_url"]
    page = http_get(session, base)
    if not page:
        return []
    try:
        soup = BeautifulSoup(page, "html.parser")
        form = soup.find("form")
        if not form:
            return []
        payload: dict[str, str] = {}
        for inp in form.find_all("input"):
            if inp.get("name") and inp.get("type") in (None, "hidden", "text"):
                payload[inp["name"]] = inp.get("value", "")

        picks = {}
        for sel in form.find_all("select"):
            name = sel.get("name")
            opts = [(o.get_text(strip=True), o.get("value", "")) for o in sel.find_all("option")]
            texts = [t for t, _ in opts]
            chosen = next((v for (t, v), o in zip(opts, sel.find_all("option")) if o.has_attr("selected")), None)
            payload[name] = chosen if chosen is not None else (opts[0][1] if opts else "")
            if str(day.year) in texts and "2017" in texts:
                picks["year"] = (name, next(v for t, v in opts if t == str(day.year)))
            elif any(t.lower().startswith(("jan", "feb")) for t in texts):
                picks["month"] = (name, next((v for t, v in opts if t.lower()[:3] == day.strftime("%b").lower()), None)
                                  or str(day.month))
            elif "31" in texts and "15" in texts:
                picks["day"] = (name, next(v for t, v in opts if t == str(day.day)))
        if len(picks) < 3:
            log.warning("allRel: could not identify day/month/year drop-downs; skipping sweep")
            return []
        for name, val in picks.values():
            payload[name] = val
        payload["__EVENTTARGET"] = picks["day"][0]
        payload["__EVENTARGUMENT"] = ""

        resp = session.post(urljoin(base, form.get("action") or base), data=payload, timeout=40)
        if resp.status_code != 200:
            log.warning("allRel: POST returned HTTP %s", resp.status_code)
            return []
        result = BeautifulSoup(resp.content.decode("utf-8-sig", errors="replace"), "html.parser")
        found: dict[str, str] = {}
        for a in result.select("a[href*='PRID=']"):
            m = PRID_RE.search(a["href"])
            if m and a.get_text(strip=True):
                found.setdefault(m.group(1), a.get_text(" ", strip=True))
        log.info("allRel: %s releases listed for %s", len(found), day)
        return list(found.items())
    except Exception as e:  # never let the optional sweep break the run
        log.warning("allRel sweep failed: %s", e)
        return []


# ------------------------------------------------------------------- pipeline
def collect_candidates(session, cfg, fixtures: Path | None) -> list[tuple[str, str]]:
    cands: dict[str, str] = {}
    if fixtures:
        feed = fixtures / "feed.xml"
        for prid, title in parse_feed(feed.read_text(encoding="utf-8")):
            cands.setdefault(prid, title)
        return list(cands.items())
    for feed in cfg["feeds"] + cfg.get("extra_feeds", []):
        text = http_get(session, feed["url"])
        if not text:
            continue
        got = parse_feed(text)
        log.info("feed %-40s %d items", feed["name"], len(got))
        for prid, title in got:
            cands.setdefault(prid, title)
        time.sleep(0.5)
    return list(cands.items())


def fetch_release_html(session, cfg, prid: str, fixtures: Path | None) -> str | None:
    if fixtures:
        p = fixtures / f"{prid}.html"
        return p.read_text(encoding="utf-8") if p.exists() else None
    page = http_get(session, cfg["release_url"].format(prid=prid))
    if page and "Posted On" in page:
        return page
    # fall back to the iframe version, which holds only the release itself
    return http_get(session, cfg["iframe_url"].format(prid=prid)) or page


def run(args: argparse.Namespace) -> int:
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    fixtures = Path(args.fixtures) if args.fixtures else None
    session = make_session()
    clf = Classifier(cfg)

    candidates = collect_candidates(session, cfg, fixtures)
    if args.allrel and not fixtures:
        d = datetime.now(IST).date() if args.allrel == "today" else date.fromisoformat(args.allrel)
        extra = fetch_allrel(session, cfg, d)
        known = {p for p, _ in candidates}
        candidates += [(p, t) for p, t in extra if p not in known]

    seen = recent_prids(data_dir, cfg["recent_days_for_dedupe"])
    fresh = [(p, t) for p, t in candidates if p not in seen]
    cap = args.max_new or cfg["max_new_per_run"]
    log.info("%d candidates, %d new (processing up to %d)", len(candidates), len(fresh), cap)
    fresh = fresh[:cap]

    docs: dict[str, dict] = {}
    pending_ai: dict[str, list[dict]] = {}
    saved = 0
    failed = 0
    min_pri = cfg["enrich"]["min_priority"]
    order = ["skip", "skim", "good", "must"]

    for prid, feed_title in fresh:
        page = fetch_release_html(session, cfg, prid, fixtures)
        if not page:
            failed += 1
            continue
        rel = parse_release(page, feed_title)
        if not rel:
            failed += 1
            continue
        posted = rel["posted_at"] or datetime.now(IST)
        d = posted.date().isoformat()
        tags = clf.classify(rel["title"], rel["ministry"], rel["body"], rel["office"])
        item = {
            "prid": prid,
            "url": f"https://www.pib.gov.in/PressReleasePage.aspx?PRID={prid}",
            "title": rel["title"],
            "ministry": rel["ministry"],
            "office": rel["office"],
            "posted_at": posted.isoformat(timespec="minutes"),
            "excerpt": make_excerpt(rel["body"]),
            **tags,
        }
        doc = docs.setdefault(d, load_day(data_dir, d))
        doc["items"] = [i for i in doc["items"] if str(i["prid"]) != prid] + [item]
        saved += 1
        if order.index(tags["priority"]) >= order.index(min_pri):
            pending_ai.setdefault(d, []).append({"item": item, "body": rel["body"]})
        if not fixtures:
            time.sleep(cfg["request_delay_seconds"])

    # Optional Claude enrichment, capped per day
    enriched = 0
    if not args.no_enrich:
        for d, pend in pending_ai.items():
            already = sum(1 for i in docs[d]["items"] if i.get("ai"))
            pend.sort(key=lambda e: -e["item"]["score"])
            enriched += enrich_mod.enrich_items(pend, cfg["enrich"], cfg["enrich"]["max_items_per_day"] - already)

    if saved and not args.sample and not fixtures:
        removed = purge_samples(data_dir)
        if removed:
            log.info("removed %d demo day file(s)", removed)
    for d, doc in docs.items():
        save_day(data_dir, doc, cfg["thresholds"], sample=args.sample)
    if not args.sample:
        prune_old(data_dir, cfg["keep_days"])
    rebuild_index(data_dir)

    log.info("saved %d new, %d failed to parse/fetch, %d enriched", saved, failed, enriched)
    if candidates and saved == 0 and failed == len(fresh) and fresh:
        log.error("every new release failed to fetch or parse; PIB may have changed its page layout")
        return 2
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(ROOT / "config.json"))
    ap.add_argument("--data-dir", default=str(ROOT / "site" / "data"))
    ap.add_argument("--fixtures", help="read feed.xml and PRID.html from this folder instead of the network")
    ap.add_argument("--sample", action="store_true", help="mark written day files as demo data")
    ap.add_argument("--allrel", metavar="DATE|today", help="also sweep PIB's All-releases page for this day (best effort)")
    ap.add_argument("--max-new", type=int, default=0, help="cap on new releases fetched this run")
    ap.add_argument("--no-enrich", action="store_true", help="skip the optional Claude enrichment")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
