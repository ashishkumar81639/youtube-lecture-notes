#!/usr/bin/env python3
"""
Regression test: does the automatic candidate set still contain every frame a
human actually chose?

Run it after changing any threshold in refine_frames.py. A tuning tweak that
quietly drops an important slide is otherwise invisible.

    verify_coverage.py SELECTED_DIR CANDIDATES_JSON VIDEO [--tol 12]

CRITICAL - compare like for like. Candidates in frames/raw are 640x360 JPEGs;
selected frames are 1920x1080 PNGs. Hashing across that gap produces distances
of 13-34 for frames that are PIXEL-IDENTICAL in content, which reads as a false
failure. Measured on a real run: naive comparison reported 11/16 covered; after
re-extracting the candidates at full resolution through the same ffmpeg path,
the true figure was 16/16 (15 at distance <= 4, the last confirmed identical by
eye). This script therefore re-extracts every candidate from the video at full
resolution before comparing.

Requires: pillow, imagehash, ffmpeg on PATH
"""
import argparse, glob, json, os, subprocess, sys, tempfile

try:
    from PIL import Image
    import imagehash
except ImportError:
    sys.exit("pip install pillow imagehash")


def H(p):
    im = Image.open(p)
    return imagehash.phash(im, hash_size=16), imagehash.dhash(im, hash_size=16)


def d(a, b):
    return int((a[0] - b[0]) + (a[1] - b[1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("selected_dir")
    ap.add_argument("candidates_json")
    ap.add_argument("video")
    ap.add_argument("--tol", type=int, default=12,
                    help="hash distance still counting as the same slide state")
    a = ap.parse_args()

    cands = json.load(open(a.candidates_json))
    sel = sorted(glob.glob(os.path.join(a.selected_dir, "*.png")) +
                 glob.glob(os.path.join(a.selected_dir, "*.jpg")))
    if not sel:
        sys.exit(f"no images in {a.selected_dir}")

    with tempfile.TemporaryDirectory() as tmp:
        ch = []
        for c in cands:
            t = c["t"]
            out = os.path.join(tmp, f"{t}.png")
            ts = f"{t // 3600:02d}:{(t % 3600) // 60:02d}:{t % 60:02d}"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", ts, "-i", a.video,
                            "-frames:v", "1", "-q:v", "2", out], check=True)
            ch.append((t, H(out)))

        print(f"selected {len(sel)}   candidates {len(ch)}   tol {a.tol}\n")
        print(f"{'selected frame':52} {'cand':>6} {'dist':>5}")
        print("-" * 70)
        miss = []
        for s in sel:
            hs = H(s)
            t, dist = min(((t, d(hs, h)) for t, h in ch), key=lambda x: x[1])
            ok = dist <= a.tol
            if not ok:
                miss.append((os.path.basename(s), t, dist))
            print(f"{os.path.basename(s)[:52]:52} {t // 60:02d}:{t % 60:02d} {dist:>5}"
                  f"  {'ok' if ok else 'MISS'}")

    print(f"\nCOVERED {len(sel) - len(miss)}/{len(sel)}")
    if miss:
        print("\nInspect each MISS by eye before assuming it is real - a slide settle/fade")
        print("animation can shift anti-aliasing enough to cost ~13 with identical content:")
        for n, t, dist in miss:
            print(f"  {n}  vs  {t // 60:02d}:{t % 60:02d}  (dist {dist})")
        sys.exit(1)


if __name__ == "__main__":
    main()
