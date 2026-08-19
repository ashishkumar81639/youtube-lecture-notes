#!/usr/bin/env python3
"""
Emit the frame -> transcript association manifest (SPEC section 13).

For every selected frame: its timestamp, what the lecturer is saying at that
moment, and a classification slot. Without this the association between a
diagram and its explanation is only implicit in the notes, and cannot be audited.

Reads timestamps from the filename. Accepts MM-SS-*.png and HH-MM-SS-*.png.

NAMING CONVENTION - name a frame by the timestamp you ACTUALLY EXTRACTED IT AT,
not by when the slide first appeared. An animated slide is often extracted at its
settled final state minutes after it appears; naming it by first-appearance makes
this manifest quote the wrong part of the transcript. (This bug was present in the
first run: a frame extracted at 12:10 was named 09-38.) The window is widened to
25s to soften the damage, but the fix is the naming.

Usage:
    frame_manifest.py FRAMES_DIR TRANSCRIPT.txt [-o manifest.md] [--window 12]
"""
import argparse, os, re, sys


def parse_ts(name):
    m = re.match(r"^(\d{2})-(\d{2})-(\d{2})-", name)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    m = re.match(r"^(\d{2})-(\d{2})-", name)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames_dir")
    ap.add_argument("transcript")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--window", type=int, default=25,
                    help="seconds of transcript context to quote around the frame")
    a = ap.parse_args()

    lines = []
    for ln in open(a.transcript, encoding="utf-8"):
        m = re.match(r"\[(\d\d):(\d\d):(\d\d)\]\s*(.*)", ln)
        if m:
            t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
            lines.append((t, m.group(4).strip()))

    frames = sorted(f for f in os.listdir(a.frames_dir)
                    if f.lower().endswith((".png", ".jpg")))
    if not frames:
        sys.exit(f"no images in {a.frames_dir}")

    o = ["# Frame → transcript manifest",
         "",
         "SPEC §13. One row per selected frame: timestamp, what the lecturer is saying",
         "there, and how the visual is classified. Fill `Classification` after viewing.",
         ""]
    missing = 0
    for f in frames:
        t = parse_ts(f)
        if t is None:
            missing += 1
            o += [f"## `{f}`", "", "- **Timestamp:** could not parse from filename", ""]
            continue
        ctx = [x for tt, x in lines if t - a.window <= tt <= t + a.window]
        o += [f"## {t // 3600:02d}:{(t % 3600) // 60:02d}:{t % 60:02d} — `{f}`",
              "",
              "**Lecturer is saying:**",
              "",
              "> " + (" ".join(ctx)[:420] if ctx else "*(no transcript in window)*"),
              "",
              "**Classification:** _(architecture diagram / sequence diagram / data model /",
              "code / table / equation / summary slide / whiteboard)_",
              ""]

    txt = "\n".join(o)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(txt)
        print(f"{len(frames)} frames -> {a.out}"
              + (f"  ({missing} unparsed timestamps)" if missing else ""), file=sys.stderr)
    else:
        sys.stdout.write(txt)


if __name__ == "__main__":
    main()
