# Free Steam store-page check

Open an issue with your Steam store URL or app ID, and a bot comments a scored checklist for your page within about a minute. Built for **Steam Next Fest (Oct 19–26, 2026)**. Free, by Pearlcity LLC.

**[→ Check my page](../../issues/new?template=page-check.yml)**

## What it checks (public store data only)
Short description (length, does it say what the game is) · screenshots (Valve minimum 5) · trailer · header capsule · user tags (20 slots) · languages · release date (specific vs "Coming soon") · demo · price · reviews · About section text + GIFs · feature categories · controller/platforms · system requirements · website. You get a 0–100 score, a grade, and your top 3 fixes. Demo IDs are resolved to the main game automatically. Comment `/recheck` after you update your page.

It can't judge art quality or fun. Capsule-art rules and trailer pacing still need a human eye.

## How it works
`.github/workflows/page-check.yml` runs `checker/steam_check.py` (Python stdlib, no keys) on new issues labelled `page-check`. Data comes from Steam's public storefront: `api/appdetails`, `appreviews` summary, and the public store page for tags/demos. One check runs at a time to stay polite.

Run locally: `python3 checker/steam_check.py 1145360` (or a store URL). See `samples/` for real output.

## Setup after repo creation (one time)
1. Create labels `page-check` and `checked` (Issues → Labels).
2. Settings → Actions → General → Workflow permissions: "Read and write" (needed to comment).
3. Keep/kill numbers: Actions → "Keep/kill metrics" → Run workflow (also runs daily).

Not affiliated with Valve. "Steam" is a trademark of Valve Corporation.
