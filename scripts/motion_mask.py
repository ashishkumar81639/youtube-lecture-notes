#!/usr/bin/env python3
"""
Find the region of the frame that moves PERSISTENTLY - a webcam inset, a
presenter, a rolling ticker - as opposed to regions that change because content
was added.

Method: over pairs of frames a short interval apart, accumulate |diff|. A slide
region changes only when something is written there (sparse, transient). An
inset changes in EVERY pair (dense, persistent). Averaging many pairs separates
them: persistent motion stays high, transient edits average down.

No model. Pure numpy.
"""
import glob, sys
import numpy as np
from PIL import Image


def motion_map(files, stride=1, max_pairs=120, delta=12.0):
    """Per-pixel CHANGE FREQUENCY: in what fraction of frame pairs did this pixel move?

    Magnitude is the wrong statistic - a slide bullet appearing is a huge but
    ONE-TIME change, while a webcam inset is a modest but CONSTANT one. Averaging
    magnitude scores them alike (measured: it flagged a slide deck's diagram area
    as an 'inset'). Frequency separates them cleanly.
    """
    acc, n = None, 0
    for i in range(0, len(files) - stride, stride):
        if n >= max_pairs:
            break
        a = np.asarray(Image.open(files[i]).convert("L"), dtype=np.float32)
        b = np.asarray(Image.open(files[i + stride]).convert("L"), dtype=np.float32)
        moved = (np.abs(a - b) > delta).astype(np.float32)
        acc = moved if acc is None else acc + moved
        n += 1
    return acc / max(1, n)


def report(files, label):
    m = motion_map(files)
    H, W = m.shape
    # Absolute thresholds do not transfer between videos. What discriminates is the
    # SHAPE: an inset is a small area moving far more often than everything else,
    # so p99 >> mean. A moving camera lifts the whole distribution, so mean itself
    # is high. Content-only changes leave both low.
    mean, p99 = float(m.mean()), float(np.percentile(m, 99))
    ratio = p99 / max(mean, 1e-6)
    hot = m > max(0.12, p99 * 0.6)
    print(f"\n=== {label}  ({W}x{H}, {len(files)} frames)")
    print(f"  change-freq: mean {mean:.3f}  p99 {p99:.3f}  p99/mean {ratio:.1f}  "
          f"hot area {hot.mean():.2%}")
    # which 3x3 cell holds the motion?
    gh, gw = H // 3, W // 3
    grid = [[hot[r*gh:(r+1)*gh, c*gw:(c+1)*gw].mean() for c in range(3)] for r in range(3)]
    names = [["top-L","top-C","top-R"],["mid-L","mid-C","mid-R"],["bot-L","bot-C","bot-R"]]
    print("  motion by ninth:")
    for r in range(3):
        print("    " + "  ".join(f"{names[r][c]}={grid[r][c]:6.2%}" for c in range(3)))
    flat = sorted(((grid[r][c], names[r][c]) for r in range(3) for c in range(3)), reverse=True)
    top, rest = flat[0], np.mean([v for v, _ in flat[1:]])
    if mean > 0.12:
        print(f"  -> GLOBAL MOTION (mean {mean:.3f}). Moving camera. Masking will not help;")
        print("     this video needs a higher tier.")
    elif ratio >= 4.0 and p99 >= 0.15:
        print(f"  -> LOCALISED MOTION in {top[1]} ({top[0]:.1%} hot vs {rest:.1%} elsewhere)")
        print("     webcam inset / picture-in-picture. MASK IT, then hash normally -")
        print("     the underlying content is probably tier 0.")
    else:
        print("  -> No persistent motion region. Content-only changes; hash triage is safe.")


if __name__ == "__main__":
    for pat in sys.argv[1:]:
        fs = sorted(glob.glob(pat + "/f*.jpg"))
        if fs:
            report(fs, pat.split("/")[-1])
