#!/usr/bin/env python3
"""
Find what is ON SCREEN but NEVER SPOKEN.

This is the highest-value content a transcript-only workflow loses entirely, and
in the reference run it was found by NOTICING rather than by process - which does
not scale and does not repeat. Real examples that were only on the slide:

    "ITCH for NASDAQ"        (API Design slide)
    "Mechanical Sympathy"    (Deep Dive 4 bullet)
    every edge annotation on the final architecture slide

Method: OCR each selected frame, then subtract the words spoken anywhere near
that timestamp. What remains is visual-only and belongs in the notes explicitly
marked as such.

LIMIT: OCR is reliable on printed slides and USELESS on handwriting (measured).
With --handwritten the script does not guess - it lists the frames for a human or
frontier-vision read instead of emitting garbage.

Usage:
    visual_only.py FRAMES_DIR TRANSCRIPT.txt [--window 45] [--min-len 4]
                   [--handwritten]
"""
import argparse, glob, os, re, sys

STOP = set("""the a an and or of to in on for with is are be by as at from this that these those
it its we you they he she our your their i us them not no yes so then than but if when while
what which who how why can could should would will shall may might must do does did done have
has had been being was were am into over under about after before during between each all any
some more most other another such only just also very too much many one two three new use used
using make makes made get gets got go goes going see sees seen say says said like well now here
there where because""".split())


def words(s):
    return [w for w in re.findall(r"[a-z0-9][a-z0-9+#.\-]{2,}", s.lower())
            if w not in STOP]


def parse_ts(name):
    m = re.match(r"^(\d{2})-(\d{2})-(\d{2})-", name)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    m = re.match(r"^(\d{2})-(\d{2})-", name)
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames_dir"); ap.add_argument("transcript")
    ap.add_argument("--window", type=int, default=45,
                    help="seconds of speech around the frame that counts as 'spoken'")
    ap.add_argument("--min-len", type=int, default=4)
    ap.add_argument("--handwritten", action="store_true",
                    help="skip OCR entirely; list frames for a human/frontier read")
    a = ap.parse_args()

    lines, prev = [], -1
    for ln in open(a.transcript, encoding="utf-8"):
        m = re.match(r"\[(\d\d):(\d\d):(\d\d)\]\s*(.*)", ln)
        if not m:
            continue
        t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        if lines and t < prev - 5:
            break
        prev = t
        lines.append((t, m.group(4)))
    spoken_all = set(words(" ".join(x for _, x in lines)))

    frames = sorted(glob.glob(os.path.join(a.frames_dir, "*.png")) +
                    glob.glob(os.path.join(a.frames_dir, "*.jpg")))
    if not frames:
        sys.exit(f"no images in {a.frames_dir}")

    if a.handwritten:
        print("HANDWRITTEN SOURCE - OCR is unreliable here (measured), not guessing.\n"
              "Read each frame directly and note anything written but not said:\n")
        for f in frames:
            t = parse_ts(os.path.basename(f))
            print(f"  {'--:--' if t is None else f'{t//60:02d}:{t%60:02d}'}  {os.path.basename(f)}")
        return

    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from vision_ocr import ocr
    except Exception as e:
        sys.exit(f"OCR unavailable ({e}). Use --handwritten, or install "
                 f"pyobjc-framework-Vision.")

    total = 0
    for f in frames:
        t = parse_ts(os.path.basename(f))
        try:
            on_screen = words(" ".join(r["text"] for r in ocr(f)))
        except Exception:
            continue
        if t is None:
            near = spoken_all
        else:
            near = set(words(" ".join(x for s, x in lines
                                      if t - a.window <= s <= t + a.window)))
        # visual-only = on screen, not said nearby, and not said ANYWHERE either
        only = [w for w in dict.fromkeys(on_screen)
                if len(w) >= a.min_len and w not in near and w not in spoken_all]
        if only:
            total += len(only)
            ts = "--:--" if t is None else f"{t//60:02d}:{t%60:02d}"
            print(f"\n  {ts}  {os.path.basename(f)}")
            print(f"     {', '.join(only[:18])}")

    print(f"\n{total} on-screen terms never spoken anywhere in the lecture.")
    print("Mark these in the notes as VISUAL-ONLY - they are pure Layer-2 value and")
    print("a transcript-only workflow loses every one of them.")


if __name__ == "__main__":
    main()
