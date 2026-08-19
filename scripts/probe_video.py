#!/usr/bin/env python3
"""
Decide the tier BEFORE extracting anything. Seek-based, so cost is constant
regardless of video length.

Why not just extract everything first: a full 2s decode of a 22-min video is
24s; of a 6-hour video, ~7 min and ~12,000 frames - and if the profile then says
"tier 2, sample every 20s" you threw 90% of it away. This probe costs 2.3s on
any video.

    22 min : full decode 24.4s + 2x hashing 2.6s  vs  probe 2.3s
    6 hours: full decode ~7 min                   vs  probe 2.3s

SAMPLING DESIGN - random ANCHORS expanded into BURSTS, not a uniform interval.
Stillness is a LOCAL property. Sampled 20s apart every pair is a different slide,
so every video reads as churn:

    burst sampling  -> stillness 81%   (true value 73.7%)  classifies correctly
    uniform 20s     -> stillness ~0%   would call a slide deck tier 2

Usage:
    probe_video.py VIDEO [--anchors 8] [--burst 4] [--interval 2] [--json out.json]
"""
import argparse, json, os, random, subprocess, sys, tempfile

try:
    from PIL import Image
    import imagehash
    import numpy as np
except ImportError:
    sys.exit("pip install pillow imagehash numpy")


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True)
    return float(out.stdout.strip())


def grab(video, t, out):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", video,
                    "-frames:v", "1", "-vf", "scale=640:-1", "-q:v", "4", out],
                   check=False)
    return os.path.exists(out) and os.path.getsize(out) > 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--anchors", type=int, default=8)
    ap.add_argument("--burst", type=int, default=4, help="consecutive frames per anchor")
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    D = duration(a.video)
    random.seed(a.seed)
    # stratified: one random anchor inside each of N equal blocks, skipping the
    # first and last 5% (intros and outros are not representative)
    lo, hi = D * 0.05, D * 0.95
    block = (hi - lo) / a.anchors
    anchors = [lo + i * block + random.random() * max(0.0, block - a.burst * a.interval)
               for i in range(a.anchors)]

    with tempfile.TemporaryDirectory() as tmp:
        frames = []            # (anchor_index, t, path)
        for ai, anc in enumerate(anchors):
            for k in range(a.burst):
                t = anc + k * a.interval
                p = os.path.join(tmp, f"a{ai}_{k}.jpg")
                if grab(a.video, t, p):
                    frames.append((ai, t, p))
        if len(frames) < a.anchors:
            sys.exit("probe failed: too few frames extracted")

        H = {}
        for ai, t, p in frames:
            im = Image.open(p)
            H[(ai, t)] = (imagehash.phash(im, hash_size=16),
                          imagehash.dhash(im, hash_size=16),
                          float(min((np.asarray(im.convert("L"), dtype=np.float32) > 60).mean(),
                                    1 - (np.asarray(im.convert("L"), dtype=np.float32) > 60).mean())))

        def dist(x, y):
            return int((H[x][0] - H[y][0]) + (H[x][1] - H[y][1]))

        keys = sorted(H)
        within = [dist(keys[i], keys[i + 1]) for i in range(len(keys) - 1)
                  if keys[i][0] == keys[i + 1][0]]
        between = [dist(keys[i], keys[i + 1]) for i in range(len(keys) - 1)
                   if keys[i][0] != keys[i + 1][0]]

        w = np.array(within) if within else np.array([0])
        still = float((w <= 4).mean())
        micro = float(((w > 4) & (w <= 20)).mean())
        cuts_like = float((w >= 60).mean())
        # additive canvas? does ink climb monotonically across the whole video
        inks = np.array([H[k][2] for k in keys])
        ts = np.array([k[1] for k in keys])
        corr = float(np.corrcoef(ts, inks)[0, 1]) if len(inks) > 3 else 0.0

    med_between = int(np.median(between)) if between else 0
    print(f"probe: {len(frames)} frames from {a.anchors} anchors, video {D/60:.1f} min\n")
    print(f"  still (<=4)          {still:6.1%}   frozen frame - plateaus exist")
    print(f"  micro (5-20)         {micro:6.1%}   small edits (a bullet, a pen stroke)")
    print(f"  cut-like (>=60)      {cuts_like:6.1%}  within-burst")
    print(f"  between-anchor dist  {med_between:6d}   global diversity")
    print(f"  corr(ink, time)      {corr:+6.2f}   >+0.7 = additive canvas")

    if corr > 0.7:
        tier, why = 1, "ADDITIVE CANVAS (handwritten notes / annotated page)"
    elif still >= 0.45:
        tier, why = 0, "slide-deck-like"
    elif micro >= 0.40:
        tier, why = 1, "continuous small edits, camera likely static"
    else:
        tier, why = 2, "low stillness and low micro-edit rate - pixels unreliable"

    print(f"\nTIER {tier}  ({why})")
    if tier == 0:
        print("  -> extract at 2s, refine_frames.py defaults are calibrated for this")
    elif tier == 1:
        print("  -> extract at 2s; run motion_mask.py first (mask any webcam inset),")
        print("     then refine_frames.py with lowered --cut/--settle.")
        if corr > 0.7:
            print("     ADDITIVE: the last frame of a page contains everything. Use the")
            print("     TRANSCRIPT to choose intermediate milestones - pixel change does")
            print("     not track conceptual progress when content only accumulates.")
    else:
        print("  -> do NOT trust hash triage. Transcript-driven timestamps + fixed sweep.")
        print("     Escalate to a dense sweep rather than risk missing content.")

    print(f"\n  probe cost: ~{len(frames)} seeks, independent of the {D/60:.0f}-min runtime")

    if a.json:
        json.dump({"duration": D, "tier": tier, "reason": why, "still": still,
                   "micro": micro, "ink_time_corr": corr,
                   "median_between": med_between}, open(a.json, "w"), indent=1)
        print(f"  -> {a.json}", file=sys.stderr)


if __name__ == "__main__":
    main()
