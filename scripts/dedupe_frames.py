#!/usr/bin/env python3
"""
Reduce a densely-sampled frame directory to visually-distinct candidates.

Designed for lecture video where slides are built up INCREMENTALLY (bullet by
bullet, box by box). ffmpeg's scene-change filter is near-useless for that
case; perceptual hashing against the last *kept* frame is not.

Usage:
    dedupe_frames.py FRAMES_DIR [--interval 2] [--threshold 22] [--json out.json]

FRAMES_DIR must contain f0001.jpg, f0002.jpg, ... as produced by:
    ffmpeg -i in.mp4 -vf "fps=1/2,scale=640:-1" -q:v 4 frames/raw/f%04d.jpg

Requires: pillow, imagehash
"""
import argparse, glob, json, os, sys

try:
    from PIL import Image
    import imagehash
except ImportError:
    sys.exit("pip install pillow imagehash")


def hhmmss(t: int) -> str:
    return f"{t // 3600:02d}:{(t % 3600) // 60:02d}:{t % 60:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames_dir")
    ap.add_argument("--interval", type=float, default=2.0,
                    help="seconds between sampled frames (must match the fps filter used)")
    ap.add_argument("--threshold", type=int, default=22,
                    help="combined pHash+dHash hamming distance to count as a new visual")
    ap.add_argument("--hash-size", type=int, default=16, help="16 => 256-bit hashes")
    ap.add_argument("--json", default=None, help="write kept-frame manifest here")
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.frames_dir, "f*.jpg")) +
                   glob.glob(os.path.join(a.frames_dir, "f*.png")))
    if not files:
        sys.exit(f"no f*.jpg / f*.png in {a.frames_dir}")

    rows = []
    for f in files:
        idx = int("".join(c for c in os.path.basename(f) if c.isdigit()))
        im = Image.open(f)
        rows.append({
            "idx": idx,
            "t": int((idx - 1) * a.interval),
            "file": f,
            "p": imagehash.phash(im, hash_size=a.hash_size),
            "d": imagehash.dhash(im, hash_size=a.hash_size),
        })

    # Chain distance against the last KEPT frame, not the previous frame.
    # This is what lets a slowly-building slide accumulate enough delta to
    # register, instead of every 2s step looking "almost identical".
    kept, last = [], None
    for r in rows:
        dist = 999 if last is None else (r["p"] - last["p"]) + (r["d"] - last["d"])
        r["dist"] = int(dist)
        if dist >= a.threshold:
            kept.append(r)
            last = r

    print(f"sampled {len(rows)} -> kept {len(kept)}  "
          f"(interval={a.interval}s threshold={a.threshold})", file=sys.stderr)
    for r in kept:
        print(f"{hhmmss(r['t'])}  idx={r['idx']:>4}  d={r['dist']}")

    if a.json:
        with open(a.json, "w") as fh:
            json.dump([{"t": r["t"], "idx": r["idx"], "d": r["dist"],
                        "file": r["file"]} for r in kept], fh, indent=1)
        print(f"wrote {a.json}", file=sys.stderr)


if __name__ == "__main__":
    main()
