#!/usr/bin/env python3
"""Keep/kill metrics: distinct app IDs submitted and devs who said it helped.
Uses the `gh` CLI (GH_TOKEN from the Action's built-in GITHUB_TOKEN). Prints markdown."""
import json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(__file__))
from steam_check import extract_appid

repo = os.environ.get("GITHUB_REPOSITORY")
def gh(*args):
    return json.loads(subprocess.check_output(["gh", "api", "--paginate", *args]))

issues = gh(f"repos/{repo}/issues?state=all&labels=page-check&per_page=100")
apps, helped = set(), set()
for i in issues:
    a = extract_appid((i.get("body") or "") + " " + i.get("title", ""))
    if a: apps.add(a)
    for c in gh(f"repos/{repo}/issues/{i['number']}/comments?per_page=100"):
        if c["user"]["type"] == "Bot":
            for r in gh(f"repos/{repo}/issues/comments/{c['id']}/reactions?per_page=100"):
                if r["content"] in ("+1", "heart", "hooray"): helped.add(r["user"]["login"])
        elif re.search(r"(?i)\b(thanks|thank you|helpful|useful|helped|great)\b", c.get("body") or ""):
            helped.add(c["user"]["login"])
print(f"## Keep/kill (target by 2026-10-30: >=30 app IDs AND >=5 devs helped)\n")
print(f"- Distinct app IDs: **{len(apps)}** / 30")
print(f"- Devs who said it helped (👍/❤️/🎉 or thanks comment): **{len(helped)}** / 5")
print(f"- Verdict so far: **{'KEEP' if len(apps)>=30 and len(helped)>=5 else 'not yet'}**")
