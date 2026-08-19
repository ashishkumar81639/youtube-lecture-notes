#!/usr/bin/env python3
"""
Build a frame candidate set FROM THE TRANSCRIPT rather than from pixel change.

This is the missing half of the pipeline. `refine_frames.py` asks "where did the
pixels change?" - which is the wrong question for two of the four video classes:

  ADDITIVE CANVAS (handwritten notes)  content only accumulates, so pixel change
                                       does not track conceptual progress at all
  TIER 2 (moving camera / churn)       pixels change constantly and meaninglessly

For both, the transcript is the reliable signal. It is also the most-verified
artifact in the pipeline - reconciled from two sources, corrected with an audit
log, hallucination-checked - so driving selection from it is not a fallback, it
is the stronger choice.

Frames are taken at:
  1. every visual_pointer   ("as you can see", "we've got our sequencer here")
  2. every section boundary + --settle-delay, so the new slide has rendered
  3. a fixed sweep every --sweep seconds, to cover what nobody narrated
  4. any timestamp flagged uncertain in the transcript, marked for closer reading

then deduplicated by perceptual hash so the same slide is not captured twice.

Usage:
    transcript_frames.py VIDEO --signals sig.json --out cand.json
        [--sweep 30] [--settle-delay 4] [--dedup 18] [--outdir frames/transcript]
"""
import argparse, json, os, subprocess, sys

try:
    from PIL import Image
    import imagehash
except ImportError:
    sys.exit("pip install pillow imagehash")


def hms(t):
    t = int(t); return f"{t//3600:02d}:{(t%3600)//60:02d}:{t%60:02d}"


def duration(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", p], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def grab(video, t, out, width=640):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", video,
                    "-frames:v", "1", "-vf", f"scale={width}:-1", "-q:v", "3", out],
                   check=False)
    return os.path.exists(out) and os.path.getsize(out) > 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--signals", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--outdir", default="frames/transcript")
    ap.add_argument("--sweep", type=float, default=30.0,
                    help="seconds between gap-filling frames (0 disables)")
    ap.add_argument("--settle-delay", type=float, default=4.0,
                    help="seconds after a section start before grabbing, so the "
                         "new slide has actually rendered")
    ap.add_argument("--dedup", type=int, default=18,
                    help="hash distance below which two frames are the same slide")
    ap.add_argument("--uncertain", default=None,
                    help="comma-separated seconds flagged uncertain in the transcript")
    a = ap.parse_args()

    sig = json.load(open(a.signals))
    D = duration(a.video)
    os.makedirs(a.outdir, exist_ok=True)

    wanted = {}          # t -> reason (first reason wins, most specific first)

    def want(t, why):
        t = round(max(0.0, min(t, D - 0.5)), 1)
        if t not in wanted:
            wanted[t] = why

    for p in sig.get("visual_pointers", []):
        want(float(p["t"]), f"pointer: {p.get('what','')[:60]}")
    for s in sig.get("sections", []):
        want(float(s["t"]) + a.settle_delay, f"section: {s.get('title','')[:60]}")
    if a.uncertain:
        for x in a.uncertain.split(","):
            if x.strip():
                want(float(x), "TRANSCRIPT UNCERTAIN here - read this frame closely")
    if a.sweep > 0:
        t = a.sweep
        while t < D:
            want(t, "sweep")
            t += a.sweep

    ads = [(c["start"], c["end"]) for c in sig.get("ad_spans", [])]
    times = sorted(t for t in wanted if not any(s <= t <= e for s, e in ads))
    dropped_ads = len(wanted) - len(times)

    print(f"{len(times)} candidate timestamps "
          f"(pointers + sections + sweep/{a.sweep:.0f}s), {dropped_ads} inside ad spans\n")

    kept, seen = [], []
    for t in times:
        p = os.path.join(a.outdir, f"t{int(t):06d}.jpg")
        if not grab(a.video, t, p):
            continue
        im = Image.open(p)
        h = (imagehash.phash(im, hash_size=16), imagehash.dhash(im, hash_size=16))
        dup = next((kt for kh, kt in seen
                    if (h[0] - kh[0]) + (h[1] - kh[1]) <= a.dedup), None)
        why = wanted[t]
        if dup is not None and not why.startswith(("pointer", "TRANSCRIPT")):
            os.remove(p)                    # sweep/section dupes are noise
            continue
        seen.append((h, t))
        kept.append({"t": int(t), "file": p, "reason": why,
                     "role": "transcript-driven",
                     "duplicate_of": dup if dup is not None else None})
        mark = "!" if why.startswith("TRANSCRIPT") else ("*" if why.startswith("pointer") else " ")
        print(f" {mark} {hms(t)}  {why[:78]}")

    json.dump(kept, open(a.out, "w"), indent=1)
    print(f"\n{len(times)} timestamps -> {len(kept)} frames after dedup  -> {a.out}")
    print("  * = lecturer pointed at the screen here   ! = transcript uncertain here")
    print("  Pointer frames are NEVER deduped away - if the lecturer said 'look at")
    print("  this', that frame is wanted even if it resembles another.")


if __name__ == "__main__":
    main()
