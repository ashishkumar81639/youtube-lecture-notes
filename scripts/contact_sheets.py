#!/usr/bin/env python3
"""
Tile candidate frames into labelled contact sheets for cheap visual triage.

This is THE token-saving step. Reading 110 thumbnails as 6 tiled sheets costs
roughly the same as 6 images instead of 110 round-trips, and it reveals slide
*animation structure* (which slides build up bullet-by-bullet) that tells you
which single timestamp per slide is worth a full-resolution look.

Usage:
    contact_sheets.py KEPT_JSON OUT_DIR [--cols 3] [--rows 4] [--tile-w 600]

Requires: pillow
"""
import argparse, json, os, re, sys

try:
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit("pip install pillow")


def load_transcript(path):
    """[(seconds, text)] - monotonic prefix only, so appendices are ignored."""
    out, prev = [], -1
    if not path or not os.path.exists(path):
        return out
    for ln in open(path, encoding="utf-8"):
        m = re.match(r"\[(\d\d):(\d\d):(\d\d)\]\s*(.*)", ln)
        if not m:
            continue
        s = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        if out and s < prev - 5:
            break
        prev = s
        out.append((s, m.group(4).strip()))
    return out


def said_at(lines, t, span=6):
    """What was being said around this frame."""
    if not lines:
        return ""
    txt = " ".join(x for s, x in lines if t - span <= s <= t + span)
    if not txt:                      # fall back to the nearest line
        s, x = min(lines, key=lambda p: abs(p[0] - t))
        txt = x
    return re.sub(r"\s+", " ", txt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kept_json")
    ap.add_argument("out_dir")
    ap.add_argument("--cols", type=int, default=4,
                    help="4 is the measured optimum. Dropping to 3 makes text "
                         "more legible but needs ~66%% more sheets, and only pays "
                         "off if it saves >6 full-res re-reads (it usually won't).")
    ap.add_argument("--rows", type=int, default=5)
    ap.add_argument("--tile-w", type=int, default=600)
    ap.add_argument("--quality", type=int, default=75)
    ap.add_argument("--transcript", default=None,
                    help="print what was being SAID under each tile. Strongly "
                         "recommended: triage decisions made without speech context "
                         "throw away the most-verified artifact in the pipeline.")
    ap.add_argument("--caption-chars", type=int, default=88)
    a = ap.parse_args()

    kept = json.load(open(a.kept_json))
    os.makedirs(a.out_dir, exist_ok=True)

    lines = load_transcript(a.transcript)
    W = a.tile_w
    H = int(W * 9 / 16)
    LABEL = 18
    CAP = 26 if lines else 0          # room for the spoken-context caption
    per = a.cols * a.rows

    made = []
    for s in range(0, len(kept), per):
        chunk = kept[s:s + per]
        sheet = Image.new("RGB", (a.cols * W, a.rows * (H + LABEL + CAP)), "white")
        d = ImageDraw.Draw(sheet)
        for i, r in enumerate(chunk):
            im = Image.open(r["file"]).resize((W, H))
            x = (i % a.cols) * W
            y = (i // a.cols) * (H + LABEL + CAP)
            sheet.paste(im, (x, y + LABEL))
            t = r["t"]
            d.text((x + 4, y + 4), f"{t // 60:02d}:{t % 60:02d}", fill="black")
            if lines:
                cap = said_at(lines, t)[:a.caption_chars]
                half = a.caption_chars // 2
                d.text((x + 4, y + LABEL + H + 3), cap[:half], fill=(60, 60, 60))
                d.text((x + 4, y + LABEL + H + 14), cap[half:], fill=(60, 60, 60))
        p = os.path.join(a.out_dir, f"sheet{s // per}.jpg")
        sheet.save(p, quality=a.quality)
        made.append(p)
        print(f"{p}  ({len(chunk)} frames)")

    print(f"\n{len(kept)} candidates -> {len(made)} sheets", file=sys.stderr)


if __name__ == "__main__":
    main()
