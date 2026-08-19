#!/usr/bin/env python3
"""
Remove a presenter who is standing in front of the board.

Takes the per-pixel TEMPORAL MEDIAN over a window of frames. Anything that moves
through the frame (a person) is outvoted by the static background (the board), so
the median reconstructs what was written even though no single frame shows it.

ONLY VALID WITH A STATIC CAMERA, and the script enforces that itself. If the
camera pans or zooms, the board sits at different pixels in each frame and the
median is smear, not reconstruction. A sharpness self-check catches this:

    composite_sharpness / source_sharpness
      ~0.99  static camera  -> composite is real            (measured, slide deck)
      ~0.16  camera moved   -> composite is garbage, REJECT (measured, MIT lecture)

Anything below --min-sharp is refused rather than silently handed on. When it
refuses, escalate the tier instead (see profile_video.py).

Usage:
    deocclude.py FRAMES_DIR --at 66,198,286 [--window 40] [--out DIR]
        --at        timestamps in SECONDS to reconstruct
        --window    seconds of surrounding frames to vote over (default 40)

Requires: pillow, numpy
"""
import argparse, glob, os, sys

try:
    from PIL import Image
    import numpy as np
except ImportError:
    sys.exit("pip install pillow numpy")


def sharpness(arr):
    g = np.asarray(Image.fromarray(arr).convert("L"), dtype=np.float32)
    lap = (-4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:])
    return float(lap.var())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames_dir")
    ap.add_argument("--at", required=True, help="comma-separated seconds")
    ap.add_argument("--window", type=float, default=40.0)
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--out", default="frames/deoccluded")
    ap.add_argument("--min-sharp", type=float, default=0.60,
                    help="reject composite below this sharpness ratio")
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.frames_dir, "f*.jpg")) +
                   glob.glob(os.path.join(a.frames_dir, "f*.png")))
    if not files:
        sys.exit(f"no frames in {a.frames_dir}")
    os.makedirs(a.out, exist_ok=True)

    half = int(a.window / a.interval / 2)
    ok = rejected = 0
    for ts in [int(x) for x in a.at.split(",")]:
        c = int(ts / a.interval)
        lo, hi = max(0, c - half), min(len(files), c + half + 1)
        win = files[lo:hi]
        if len(win) < 5:
            print(f"{ts:>6}s  SKIP (only {len(win)} frames in window)")
            continue

        src = [np.asarray(Image.open(f).convert("RGB"), dtype=np.uint8) for f in win]
        med = np.median(np.stack(src), axis=0).astype(np.uint8)
        s_src = float(np.median([sharpness(x) for x in src]))
        ratio = sharpness(med) / s_src if s_src else 0.0

        tag = f"{ts // 60:02d}-{ts % 60:02d}"
        if ratio >= a.min_sharp:
            p = os.path.join(a.out, f"{tag}-deoccluded.png")
            Image.fromarray(med).save(p)
            ok += 1
            print(f"{ts:>6}s  OK      ratio={ratio:.2f}  {len(win)} frames -> {p}")
        else:
            rejected += 1
            print(f"{ts:>6}s  REJECT  ratio={ratio:.2f}  camera is not static here; "
                  f"composite would be smear")

    print(f"\n{ok} reconstructed, {rejected} rejected")
    if rejected:
        print("Rejections mean this video needs a higher tier, not different parameters.")
        print("Run profile_video.py and follow the TIER it recommends.")


if __name__ == "__main__":
    main()
