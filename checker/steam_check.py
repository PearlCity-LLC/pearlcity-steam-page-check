#!/usr/bin/env python3
"""Steam store-page checker (Pearlcity LLC).

Fetches PUBLIC Steam storefront data for one app and prints a scored
markdown checklist. Stdlib only, no API key.

Usage:
  python3 steam_check.py 1145360
  python3 steam_check.py "https://store.steampowered.com/app/1145360/Hades/"
  python3 steam_check.py --from-text "$ISSUE_BODY"      # extracts the first app ID
  python3 steam_check.py 1145360 --json                 # raw scores as JSON
"""
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request

UA = "PearlcitySteamPageCheck/0.1 (+public storefront data only)"
COOKIE = "birthtime=0; lastagecheckage=1-0-1990; wants_mature_content=1"
TIMEOUT = 20


def http_get(url, as_json=True, retries=2):
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Cookie": COOKIE,
                                                       "Accept-Language": "en-US,en;q=0.8"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                body = r.read().decode("utf-8", "replace")
            return json.loads(body) if as_json else body
        except Exception as e:  # polite backoff, then give up
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"fetch failed: {last}")


def extract_appid(text):
    if not text:
        return None
    m = re.search(r"store\.steampowered\.com/app/(\d{1,8})", text)
    if m:
        return m.group(1)
    m = re.search(r"(?i)app\s*id\D{0,10}(\d{3,8})", text)
    if m:
        return m.group(1)
    m = re.search(r"\b(\d{3,8})\b", text)
    return m.group(1) if m else None


def appdetails(appid):
    r = http_get(f"https://store.steampowered.com/api/appdetails?appids={appid}&cc=us&l=english")
    entry = (r or {}).get(str(appid)) or {}
    if not entry.get("success"):
        return None
    return entry["data"]


def reviews(appid):
    try:
        r = http_get(f"https://store.steampowered.com/appreviews/{appid}?json=1&language=all"
                     f"&purchase_type=all&num_per_page=0")
        return r.get("query_summary", {})
    except Exception:
        return {}


def store_page(appid):
    """User tags and standalone demos live only on the store page HTML."""
    try:
        h = http_get(f"https://store.steampowered.com/app/{appid}/?l=english&cc=us", as_json=False)
    except Exception:
        return None, []
    tags = None
    m = re.search(r"InitAppTagModal\(\s*\d+,\s*(\[.*?\])\s*,", h, re.S)
    if m:
        try:
            tags = [t["name"] for t in json.loads(m.group(1))]
        except Exception:
            tags = None
    if tags is None:
        found = re.findall(r'class="app_tag"[^>]*>\s*([^<]+?)\s*<', h)
        tags = [html.unescape(t) for t in found if t != "+"] or None
    demo_ids = []
    u = html.unescape(h)
    for key in ("demo_appid", "standalone_demo_appid"):
        mm = re.search(r'"' + key + r'":\[([\d,\s]*)\]', u)
        if mm:
            demo_ids += [x.strip() for x in mm.group(1).split(",") if x.strip()]
    return tags, demo_ids


def strip_html(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def count_languages(s):
    s = re.sub(r"<br>.*$", "", s or "", flags=re.S)  # drop "*languages with full audio support"
    parts = [p for p in re.split(r",", strip_html(s).replace("*", "")) if p.strip()]
    full_audio = (s or "").count("<strong>*</strong>")
    return len(parts), full_audio


MONTHS = r"(january|february|march|april|may|june|july|august|september|october|november|december|" \
         r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\.?"


def date_score(date):
    """Score an unreleased game's shown release date out of 8. More specific scores higher."""
    t = (date or "").strip().lower()
    if not t:
        return 0, "blank"
    if re.search(r"coming soon|to be announced|\btba\b|\btbd\b", t):
        return 2, "coming soon / TBA"
    has_month = re.search(r"\b" + MONTHS + r"(?![a-z])", t)
    has_day = re.search(r"\b\d{1,2}(st|nd|rd|th)?\b", re.sub(r"\b\d{4}\b", "", t))
    if has_month and has_day:
        return 8, "exact date"
    if has_month:
        return 7, "month"
    if re.search(r"\bq[1-4]\b|quarter|spring|summer|fall|autumn|winter|early|mid|late", t):
        return 5, "season / quarter"
    if re.fullmatch(r"\d{4}", t):
        return 4, "year only"
    return 8, "exact date"


def about_tip(words, media):
    tips = []
    if words < 200:
        tips.append(f"Add more description: {words} words is thin; aim for 200+ covering what you do, "
                    f"the hook and features, under short headers.")
    if media < 2:
        tips.append("Break the About section with 2–5 GIFs or images; most visitors skim.")
    return " ".join(tips)


def check(appid):
    d = appdetails(appid)
    if d is None:
        return {"error": f"Steam returned no public data for app {appid}. Check the ID, or the page may "
                         f"not be public yet / region-locked."}
    note = None
    sent_demo = None
    if d.get("type") == "demo" and d.get("fullgame", {}).get("appid"):
        note = f"You sent the demo's ID ({appid}); I checked the main game page ({d['fullgame']['appid']})."
        sent_demo = appid
        appid = str(d["fullgame"]["appid"])
        time.sleep(1.5)
        d = appdetails(appid) or d
    time.sleep(1.0)
    rv = reviews(appid)
    time.sleep(1.0)
    tags, page_demos = store_page(appid)

    rel = d.get("release_date") or {}
    coming = bool(rel.get("coming_soon"))
    items = []  # (key, title, earned, max or None for N/A, status, detail, tip)

    def add(title, earned, mx, detail, tip=""):
        if mx is None:
            items.append({"title": title, "earned": 0, "max": 0, "status": "info", "detail": detail, "tip": tip})
            return
        ratio = earned / mx if mx else 0
        status = "pass" if ratio >= 0.99 else ("warn" if ratio > 0 else "fail")
        items.append({"title": title, "earned": round(earned, 1), "max": mx, "status": status,
                      "detail": detail, "tip": "" if status == "pass" else tip})

    # 1 short description
    sd = strip_html(d.get("short_description", ""))
    n = len(sd)
    genre_words = {w.lower() for g in d.get("genres", []) for w in g["description"].split()}
    genre_words |= {w.lower() for t in (tags or [])[:12] for w in re.split(r"[\s-]+", t)}
    genre_words -= {"game", "games", "based", "free", "play", "early", "access", "indie", "great"}
    first = re.split(r"(?<=[.!?])\s", sd)[0].lower() if sd else ""
    names_genre = any(re.search(r"\b" + re.escape(w) + r"\b", first) for w in genre_words if len(w) > 3)
    pts = 0
    if n:
        pts += 6 if 120 <= n <= 300 else (3 if n >= 60 else 1)
        pts += 6 if names_genre else 0
    add("Short description says what the game is", pts, 12,
        f"{n}/300 characters. First sentence {'names' if names_genre else 'does not clearly name'} "
        f"a genre or top tag. “{sd[:140]}{'…' if n > 140 else ''}”",
        "Lead with genre + hook in one sentence (e.g. “A cozy farming roguelite where…”). Aim for 150–300 characters.")

    # 2 screenshots
    shots = len(d.get("screenshots", []))
    add("Screenshots (Valve requires at least 5)", 12 if shots >= 8 else (8 if shots >= 5 else (3 if shots else 0)), 12,
        f"{shots} screenshots.",
        "Use 8–12 real gameplay screenshots; put the most readable one first (it shows in hover previews).")

    # 3 trailer
    movies = d.get("movies", [])
    add("Trailer", 12 if movies else 0, 12, f"{len(movies)} video(s).",
        "Add a 30–90 s gameplay-first trailer; show the game in the first 5 seconds.")

    # 4 capsule/header
    has_header = bool(d.get("header_image"))
    add("Header capsule present", 4 if has_header else 0, 4,
        "Header image found. Manual check: Valve's rules allow only game art + logo/name (no review quotes, "
        "awards or taglines)." if has_header else "No header image in public data.",
        "Upload a header capsule following Steamworks graphical-asset rules.")

    # 5 tags
    if tags is None:
        add("User tags", 0, None, "Couldn't read tags from the store page this run.")
    else:
        tn = len(tags)
        add("User tags (20 slots available)", 10 if tn >= 15 else (6 if tn >= 10 else (2 if tn else 0)), 10,
            f"{tn} tags: {', '.join(tags[:10])}{'…' if tn > 10 else ''}",
            "Fill all 20 tag slots in Steamworks and order them most-specific-first; tags drive "
            "‘More like this’ and Next Fest category pages.")

    # 6 languages
    ln, audio = count_languages(d.get("supported_languages", ""))
    add("Languages", 8 if ln >= 5 else (6 if ln >= 2 else (3 if ln == 1 else 0)), 8,
        f"{ln} language(s) listed{f', {audio} with full audio' if audio else ''}.",
        "Even interface + subtitles in Simplified Chinese, German, Spanish, Japanese, Russian or Portuguese-BR "
        "widens your audience a lot.")

    # 7 release date
    date = (rel.get("date") or "").strip()
    if coming:
        pts, kind = date_score(date)
        add("Release date (unreleased)", pts, 8,
            f"Shown as “{date or 'blank'}” ({kind}).",
            "A specific month or date (even an estimate) beats “Coming soon”; it tells wishlisters when to expect you.")
    else:
        add("Release date", 0, None, f"Released: {date or 'unknown'}.")

    # 8 demo
    demos = [str(x.get("appid")) for x in (d.get("demos") or [])] + page_demos
    if sent_demo and sent_demo not in demos:
        demos.append(sent_demo)
    demos = list(dict.fromkeys(demos))
    if coming:
        ddetail = (f"Demo found (app {', '.join(demos)})." if demos else "No demo linked on the main page.")
        add("Playable demo (key for Next Fest)", 10 if demos else 0, 10, ddetail,
            "Next Fest rewards demos: players filter by them. Link the demo app to this page.")
    else:
        add("Demo", 0, None, f"Demo found (app {', '.join(demos)})." if demos else "No demo (optional for released games).")

    # 9 price
    if coming:
        add("Price", 0, None, "Not shown until release (normal).")
    else:
        po = d.get("price_overview")
        if d.get("is_free"):
            add("Price", 5, 5, "Free to play.")
        elif po:
            disc = po.get("discount_percent", 0)
            add("Price", 5, 5, f"{po.get('final_formatted')}{f' ({disc}% off now)' if disc else ''}.")
        else:
            add("Price", 0, 5, "No US price visible.", "Make sure a US price/package is live.")

    # 10 reviews
    if coming:
        add("Reviews", 0, None, "Unreleased, so no reviews yet.")
    else:
        tr = rv.get("total_reviews", 0) or 0
        desc = rv.get("review_score_desc", "")
        pos = (rv.get("total_positive", 0) / tr * 100) if tr else 0
        p = (4 if tr >= 50 else 2 if tr >= 10 else 0) + (4 if pos >= 80 else 2 if pos >= 70 else 0)
        add("Reviews", p, 8, f"{tr:,} reviews, {pos:.0f}% positive ({desc or 'no score yet'}).",
            "Under 10 reviews Steam shows no score; ask your community/Discord to leave honest reviews.")

    # 11 long description
    about = d.get("about_the_game") or d.get("detailed_description") or ""
    words = len(strip_html(about).split())
    media = len(re.findall(r"<img|<video", about))
    p = (4 if words >= 200 else 2 if words >= 80 else 0) + (4 if media >= 2 else 2 if media == 1 else 0)
    add("About section (text + GIFs)", p, 8, f"{words} words, {media} inline image/GIF/video(s).",
        about_tip(words, media))

    # 12 categories / features
    cats = list(dict.fromkeys(c["description"] for c in d.get("categories", [])))
    add("Feature categories", 4 if len(cats) >= 3 else 2 if cats else 0, 4,
        f"{len(cats)}: {', '.join(cats[:8])}",
        "Tick every true feature in Steamworks (Steam Achievements, Cloud, controller support, Steam Deck…).")

    # 13 controller / platforms
    plats = [k for k, v in (d.get("platforms") or {}).items() if v]
    ctrl = d.get("controller_support")
    if not ctrl:
        cc = [c for c in cats if "controller support" in c.lower()]
        ctrl = ("partial (from feature list)" if any("partial" in c.lower() for c in cc)
                else "full (from feature list)" if any("full" in c.lower() for c in cc)
                else "gamepad listed" if cc else None)
    add("Controller support / platforms", (2 if ctrl else 0) + (2 if plats else 0), 4,
        f"Controller: {ctrl or 'not declared'}. Platforms: {', '.join(plats) or 'none'}.",
        "If it plays well on a gamepad, declare controller support; Steam Deck players filter on it.")

    # 14 system requirements
    pcr = d.get("pc_requirements")
    has_req = isinstance(pcr, dict) and bool(strip_html(pcr.get("minimum", "")))
    add("System requirements", 4 if has_req else 0, 4,
        "Minimum PC requirements filled in." if has_req else "No minimum PC requirements.",
        "Fill in minimum requirements; blank specs make buyers hesitate.")

    # 15 website
    add("Website / community link", 2 if d.get("website") else 0, 2,
        f"{d.get('website') or 'none'}", "Link a site, Discord or press kit.")

    earned = sum(i["earned"] for i in items)
    mx = sum(i["max"] for i in items)
    score = round(earned / mx * 100) if mx else 0
    return {"appid": appid, "name": d.get("name"), "coming_soon": coming, "score": score,
            "earned": earned, "max": mx, "items": items, "note": note,
            "url": f"https://store.steampowered.com/app/{appid}/"}


ICON = {"pass": "✅", "warn": "⚠️", "fail": "❌", "info": "ℹ️"}


def grade(s):
    return "A" if s >= 90 else "B" if s >= 80 else "C" if s >= 65 else "D" if s >= 50 else "E"


def to_markdown(r):
    if "error" in r:
        return f"⚠️ **Couldn't check this one.** {r['error']}\n"
    out = [f"## Steam page check: [{r['name']}]({r['url']})",
           f"**Score: {r['score']}/100 (grade {grade(r['score'])})** · "
           f"{'Unreleased / coming soon' if r['coming_soon'] else 'Released'}"]
    if r.get("note"):
        out.append(f"> {r['note']}")
    out += ["", "| | Check | Points | What we saw |", "|---|---|---|---|"]
    for i in r["items"]:
        pts = "n/a" if i["status"] == "info" else f"{i['earned']:g}/{i['max']}"
        out.append(f"| {ICON[i['status']]} | {i['title']} | {pts} | {i['detail'].replace('|', '/')} |")
    fixes = [i for i in r["items"] if i["status"] in ("fail", "warn") and i["tip"]]
    fixes.sort(key=lambda i: i["max"] - i["earned"], reverse=True)
    if fixes:
        out += ["", "### Top fixes"]
        out += [f"{n}. **{i['title']}:** {i['tip']}" for n, i in enumerate(fixes[:3], 1)]
    out += ["", "_Automated check of public store data only; it can't judge art quality or fun. "
                "Capsule art rules and trailer pacing still need a human eye._",
            "", "**Was this useful?** React 👍 or 👎 on this comment, or reply with what we missed. "
                "That's how we decide whether to keep building it.",
            "", "<sub>Free tool by Pearlcity LLC. Data: Steam public storefront.</sub>"]
    return "\n".join(out) + "\n"


def main(argv):
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    if argv[:1] == ["--from-text"]:
        appid = extract_appid(" ".join(argv[1:]))
    else:
        appid = extract_appid(" ".join(argv))
    if not appid:
        print("⚠️ **No Steam app ID found.** Paste your store URL "
              "(https://store.steampowered.com/app/123456/...) or the numeric app ID.")
        return 2
    r = check(appid)
    print(json.dumps(r, indent=2, ensure_ascii=False) if as_json else to_markdown(r))
    return 0 if "error" not in r else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
