#!/usr/bin/env python3
"""
Diff a Whisper transcript against YouTube captions to surface ONLY the divergences
worth inspecting - which is where technical proper nouns go wrong.

Buckets both sources into fixed time windows and reports words unique to each.
Then resolve each divergence using the on-screen SLIDE as the tiebreaker.

Usage:
    compare_sources.py WHISPER_TIMESTAMPED.txt CAPTIONS.txt [--window 30] [--minlen 4]

Both inputs must be lines of the form:  [HH:MM:SS] text
"""
import argparse, re, sys
from collections import defaultdict


def load(path, window):
    buckets = defaultdict(list)
    for ln in open(path, encoding="utf-8"):
        m = re.match(r"\[(\d\d):(\d\d):(\d\d)\]\s*(.*)", ln)
        if not m:
            continue
        t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        buckets[t // window].extend(re.findall(r"[a-z0-9$.]+", m.group(4).lower()))
    return buckets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("whisper")
    ap.add_argument("captions")
    ap.add_argument("--window", type=int, default=30)
    ap.add_argument("--minlen", type=int, default=4,
                    help="ignore short words; they are noise, not terminology")
    a = ap.parse_args()

    W, C = load(a.whisper, a.window), load(a.captions, a.window)
    n = 0
    for k in sorted(set(W) | set(C)):
        ws, cs = set(W.get(k, [])), set(C.get(k, []))
        ow = sorted(x for x in ws - cs if len(x) >= a.minlen)
        oc = sorted(x for x in cs - ws if len(x) >= a.minlen)
        if ow or oc:
            n += 1
            t = k * a.window
            print(f"[{t // 60:02d}:{t % 60:02d}]")
            print(f"   whisper-only : {' '.join(ow)[:120]}")
            print(f"   captions-only: {' '.join(oc)[:120]}")
    print(f"\n{n} windows with divergence. Resolve each using the on-screen slide.",
          file=sys.stderr)


if __name__ == "__main__":
    main()
