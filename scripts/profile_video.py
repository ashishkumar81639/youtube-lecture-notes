#!/usr/bin/env python3
"""
Profile a video's VISUAL STRUCTURE before running the frame pipeline, and say
whether the refine_frames.py defaults will work on it.

The defaults were tuned on a slide-deck screencast: static camera, hard cuts
between slides, long still stretches. Videos that break those assumptions -
talking heads, blackboard lectures, scrolling code, continuous animation - need
different parameters or a different approach. This tells you which you have,
in about 20 seconds, instead of discovering it after a bad run.

Usage:
    profile_video.py FRAMES_DIR [--interval 2]

Run it on the densely-sampled frames/raw directory.

Requires: pillow, imagehash, numpy
"""
import argparse, glob, os, sys

try:
    from PIL import Image
    import imagehash
    import numpy as np
except ImportError:
    sys.exit("pip install pillow imagehash numpy")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames_dir")
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--hash-size", type=int, default=16)
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.frames_dir, "f*.jpg")) +
                   glob.glob(os.path.join(a.frames_dir, "f*.png")))
    if len(files) < 10:
        sys.exit("need at least 10 sampled frames")

    H = []
    for f in files:
        im = Image.open(f)
        H.append((imagehash.phash(im, hash_size=a.hash_size),
                  imagehash.dhash(im, hash_size=a.hash_size)))
    nb = np.array([0] + [int((H[i][0] - H[i - 1][0]) + (H[i][1] - H[i - 1][1]))
                         for i in range(1, len(H))])
    d = nb[1:]

    still = float((d <= 4).mean())
    micro = float(((d > 4) & (d <= 20)).mean())
    cuts = int((d >= 60).sum())
    mins = len(files) * a.interval / 60

    print(f"frames {len(files)}  ({mins:.1f} min at {a.interval}s sampling)\n")
    print(f"  still      (dist <= 4)   {still:6.1%}   frame frozen - plateaus exist here")
    print(f"  micro      (5-20)        {micro:6.1%}   small edits: a bullet, a stroke, a typed line")
    print(f"  churn      (21-59)       {float(((d > 20) & (d < 60)).mean()):6.1%}   large redraw, scroll, or camera motion")
    print(f"  hard cuts  (>= 60)       {cuts} total ({cuts / mins:.1f}/min)")
    print(f"  median distance          {int(np.median(d))}")

    # ---- is the camera static? (does temporal median reconstruct or smear?) ----
    mid = len(files) // 2
    win = files[max(0, mid - 10):mid + 11]
    src = [np.asarray(Image.open(f).convert("RGB"), dtype=np.uint8) for f in win]

    def sharp(arr):
        g = np.asarray(Image.fromarray(arr).convert("L"), dtype=np.float32)
        lap = (-4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:])
        return float(lap.var())

    med = np.median(np.stack(src), axis=0).astype(np.uint8)
    s_src = float(np.median([sharp(x) for x in src])) or 1.0
    cam_ratio = sharp(med) / s_src
    static_cam = cam_ratio >= 0.60
    print(f"  camera                   {'STATIC' if static_cam else 'MOVING'} "
          f"(median-composite sharpness ratio {cam_ratio:.2f})")

    # ---- tier ---------------------------------------------------------------
    cuts_min = cuts / mins
    if still >= 0.45 and cuts_min >= 0.5:
        tier, why = 0, "slide-deck-like: mostly still, clear cuts between states"
    elif still < 0.45 and static_cam:
        tier, why = 1, "content is occluded or always moving, but the CAMERA is static"
    elif float(np.median(d)) > 20 or not static_cam:
        tier, why = 2, "pixels are unreliable (moving camera / constant churn)"
    else:
        tier, why = 0, "borderline; defaults with adjusted thresholds"

    sug_cut = max(20, int(np.percentile(d, 90)))
    sug_settle = max(4, int(np.percentile(d, 25)))

    print(f"\nTIER {tier}   ({why})\n")
    if tier == 0:
        print("  Cheapest path. Hash triage works; the defaults are calibrated for this.")
        print("    python refine_frames.py frames/raw --out ref.json --signals sig.json")
        if cuts_min < 0.5:
            print(f"    (few cuts - add --cut {sug_cut})")
        print("  Expected: ~95% of frames discarded, ~34k image tokens for a 22-min video.")
    elif tier == 1:
        print("  Hash triage is unreliable, but the camera is static so the presenter can be")
        print("  removed by temporal median - the board is reconstructed from surrounding frames.")
        print(f"    python refine_frames.py frames/raw --out ref.json --cut {sug_cut} --settle {sug_settle}")
        print("    python deocclude.py frames/raw --at <seconds,from,ref.json>")
        print("  Cost: same as tier 0 plus local compute. deocclude.py self-checks and")
        print("  refuses any composite that would be smear.")
    elif tier == 2:
        print("  Do NOT trust hash triage here. Drive frame selection from the TRANSCRIPT:")
        print("  extract at every visual_pointer and section boundary, plus a fixed sweep.")
        print("    python transcript_signals.py transcript.txt          # get pointers/sections")
        print("    # extract those timestamps, then sweep every 30s to fill gaps")
        print("  Cost: roughly 1.5-2x tier 0. Accept it - the alternative is missing content.")
        print("  If the result still looks thin, ESCALATE TO TIER 3.")
    print()
    print("  TIER 3 (always available, last resort): abandon selection entirely.")
    print("  Uniform sweep every 15-20s, tile everything, review every sheet.")
    n20 = int(len(files) * a.interval / 20)
    print(f"    ffmpeg -i VIDEO -vf 'fps=1/20,scale=640:-1' -q:v 4 sweep/f%04d.jpg")
    print(f"    -> ~{n20} frames, ~{max(1, n20 // 20)} sheets, ~{max(1, n20 // 20) * 2500 // 1000}k image tokens")
    print("  Costs more, but guarantees nothing is missed. Spending tokens beats")
    print("  silently producing notes with the diagrams left out.")

    print("\n  distance percentiles: " + "  ".join(
        f"p{p}={int(np.percentile(d, p))}" for p in (50, 75, 90, 95, 99)))
    print(f"\n  record it:  python channel_profile.py --url URL --record --tier {tier} \\")
    print(f"                --still {still:.2f} --cuts-min {cuts_min:.1f} "
          f"--median {int(np.median(d))} --camera {'static' if static_cam else 'moving'}")


if __name__ == "__main__":
    main()
