#!/usr/bin/env python3
"""
Remember what each YouTube channel's videos look like, so the SECOND video from
a channel skips discovery and starts on known-good settings.

Channels are consistent: a given creator uses the same recording setup, the same
deck template, the same camera work, and reads their sponsor in the same place.
That is exactly the kind of thing worth caching.

    channel_profile.py --url URL --lookup
    channel_profile.py --url URL --record --tier 0 --params "--cut 60 --settle 4" \
        --still 0.74 --cuts-min 2.4 --median 2 --camera static --note "dark deck"
    channel_profile.py --list

Cache: <skill>/cache/channels.json   (plain JSON, safe to edit or delete)
"""
import argparse, json, os, subprocess, sys, time

# Your own channel history is USER state, not skill content - it must not land in the repo
# when this skill is shared. Writes go to the user cache; the shipped cache/channels.json is
# read-only seed data (measured reference profiles) and is merged in underneath.
_SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED = os.path.join(_SKILL, "cache", "channels.json")
CACHE = os.environ.get("YLN_CHANNEL_CACHE") or os.path.join(
    os.path.expanduser("~"), ".cache", "youtube-lecture-notes", "channels.json")


def _load_all():
    """Seed profiles shipped with the skill, overlaid with the user's own."""
    data = {}
    for path in (SEED, CACHE):
        try:
            with open(path) as fh:
                data.update(json.load(fh))
        except (OSError, ValueError):
            pass
    return data


def load():
    return _load_all()


def save(db):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump(db, open(CACHE, "w"), indent=1, sort_keys=True)


def resolve(url):
    """Ask yt-dlp for the channel id/name without downloading anything."""
    venv = os.environ.get("VENV") or os.path.join(
        os.path.expanduser("~"), ".cache", "youtube-lecture-notes", "venv")
    for exe in (os.path.join(venv, "bin", "yt-dlp"), "./.venv/bin/yt-dlp", "yt-dlp"):
        try:
            out = subprocess.run(
                [exe, "--skip-download", "--print", "%(channel_id)s|%(channel)s|%(id)s",
                 "--playlist-items", "1", url],
                capture_output=True, text=True, timeout=90)
            for line in out.stdout.strip().splitlines():
                if "|" in line:
                    cid, name, vid = line.split("|")[:3]
                    return cid, name, vid
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None, None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    ap.add_argument("--channel-id")
    ap.add_argument("--lookup", action="store_true")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--tier", type=int)
    ap.add_argument("--params", default="")
    ap.add_argument("--glossary", default="")
    ap.add_argument("--still", type=float)
    ap.add_argument("--cuts-min", type=float)
    ap.add_argument("--median", type=int)
    ap.add_argument("--camera", choices=["static", "moving"])
    ap.add_argument("--note", default="")
    a = ap.parse_args()

    db = load()

    if a.list:
        if not db:
            print("no channels profiled yet")
            return
        for cid, e in sorted(db.items(), key=lambda kv: kv[1].get("name", "")):
            print(f"{e.get('name', '?')[:34]:36} tier {e.get('tier', '?')}  "
                  f"still {e.get('still', 0):.0%}  cam {e.get('camera', '?'):6}  "
                  f"seen {e.get('videos_seen', 0)}x")
            if e.get("params"):
                print(f"    params: {e['params']}")
            if e.get("note"):
                print(f"    note  : {e['note']}")
        return

    cid, name = a.channel_id, None
    if a.url:
        cid, name, _ = resolve(a.url)
        if not cid:
            sys.exit("could not resolve channel (yt-dlp failed)")
    if not cid:
        sys.exit("need --url or --channel-id")

    if a.lookup:
        e = db.get(cid)
        if not e:
            print(f"NEW CHANNEL: {name or cid}")
            print("No profile cached. Run the full discovery path:")
            print("  1. sample frames   2. profile_video.py   3. record the result here")
            sys.exit(2)          # exit 2 = unknown, so callers can branch
        print(f"KNOWN CHANNEL: {e.get('name', cid)}  (seen {e.get('videos_seen', 0)}x, "
              f"updated {e.get('updated', '?')})")
        print(f"  tier      : {e.get('tier')}")
        print(f"  params    : {e.get('params') or '(defaults)'}")
        print(f"  glossary  : {e.get('glossary') or '(default)'}")
        print(f"  stats     : still {e.get('still', 0):.0%}  "
              f"cuts/min {e.get('cuts_min', 0)}  median {e.get('median', 0)}  "
              f"camera {e.get('camera', '?')}")
        if e.get("note"):
            print(f"  note      : {e['note']}")
        return

    if a.record:
        e = db.get(cid, {})
        e.update({k: v for k, v in {
            "name": name or e.get("name") or cid, "tier": a.tier,
            "params": a.params or e.get("params", ""),
            "glossary": a.glossary or e.get("glossary", ""),
            "still": a.still, "cuts_min": a.cuts_min, "median": a.median,
            "camera": a.camera, "note": a.note or e.get("note", ""),
        }.items() if v is not None})
        e["videos_seen"] = e.get("videos_seen", 0) + 1
        e["updated"] = time.strftime("%Y-%m-%d")
        db[cid] = e
        save(db)
        print(f"recorded {e['name']} (tier {e.get('tier')}, seen {e['videos_seen']}x) -> {CACHE}")
        return

    ap.print_help()


if __name__ == "__main__":
    main()
