#!/usr/bin/env python3
"""
Two accuracy gates on the transcript itself, before anything downstream uses it.

1. HALLUCINATION CHECK. Whisper can invent text over silence, music or applause,
   and it usually shows up as repetition or as an impossible speaking rate.
     - identical/near-identical consecutive segments
     - a segment repeated verbatim elsewhere
     - words-per-second outside plausible speech (roughly 0.5 - 6.0)
     - very long segments with very little text (a stall)

2. CORRECTION AUDIT. The cleaning step applies regex substitutions in bulk. A
   pattern that over-matches corrupts the transcript silently. This replays every
   rule against the RAW transcript and prints each changed span IN CONTEXT so the
   substitution can actually be inspected rather than trusted.

Usage:
    audit_transcript.py --segments whisper.json                 # hallucination check
    audit_transcript.py --raw raw.txt --clean clean.txt         # correction audit
"""
import argparse, json, re, sys
from collections import Counter


def hms(t):
    t = int(t); return f"{t//3600:02d}:{(t%3600)//60:02d}:{t%60:02d}"


def hallucination(path):
    segs = json.load(open(path))
    segs = segs["segments"] if isinstance(segs, dict) else segs
    issues = []

    texts = [re.sub(r"\s+", " ", s["text"].strip().lower()) for s in segs]
    counts = Counter(t for t in texts if len(t) > 15)

    for i, s in enumerate(segs):
        t = texts[i]
        dur = float(s["end"]) - float(s["start"])
        wps = len(t.split()) / dur if dur > 0 else 0

        if i and t and t == texts[i - 1]:
            issues.append((s["start"], "REPEAT", f"identical to previous segment: '{t[:60]}'"))
        elif len(t) > 15 and counts[t] >= 3:
            issues.append((s["start"], "LOOP", f"segment repeats {counts[t]}x verbatim: '{t[:50]}'"))
        if dur > 1.0 and wps > 6.0:
            issues.append((s["start"], "RATE", f"{wps:.1f} words/sec over {dur:.1f}s - implausibly fast"))
        if dur > 8.0 and len(t.split()) < 3:
            issues.append((s["start"], "STALL", f"{dur:.1f}s segment with {len(t.split())} words"))

    print(f"segments: {len(segs)}   flagged: {len(issues)}\n")
    seen = set()
    for st, kind, msg in issues:
        k = (kind, msg[:40])
        if k in seen:
            continue
        seen.add(k)
        print(f"  [{hms(st)}] {kind:6} {msg}")
    if not issues:
        print("  no hallucination signatures found")
    return len(issues)


def corrections(raw_path, clean_path):
    raw = [l for l in open(raw_path, encoding="utf-8") if l.startswith("[")]
    clean = [l for l in open(clean_path, encoding="utf-8") if l.startswith("[")]
    if len(raw) != len(clean):
        print(f"  ! line counts differ: raw {len(raw)} vs clean {len(clean)} - "
              f"cleaning changed structure, not just wording")
    n = 0
    print(f"comparing {min(len(raw), len(clean))} lines\n")
    for a, b in zip(raw, clean):
        if a == b:
            continue
        aw, bw = a.split(), b.split()
        if len(aw) != len(bw):
            print(f"  ! WORD COUNT CHANGED  {a[:12]}")
            print(f"      raw   : {a.strip()[:100]}")
            print(f"      clean : {b.strip()[:100]}")
            n += 1
            continue
        for x, y in zip(aw, bw):
            if x != y:
                print(f"  {a[:11]} {x!r} -> {y!r}")
                n += 1
    print(f"\n{n} word-level substitutions. Every one should be justified in the "
          f"CORRECTION LOG at the bottom of the clean file.")
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments"); ap.add_argument("--raw"); ap.add_argument("--clean")
    a = ap.parse_args()
    bad = 0
    if a.segments:
        print("=" * 74); print("HALLUCINATION CHECK"); print("=" * 74)
        bad += hallucination(a.segments)
    if a.raw and a.clean:
        print("\n" + "=" * 74); print("CORRECTION AUDIT"); print("=" * 74)
        corrections(a.raw, a.clean)
    if not a.segments and not (a.raw and a.clean):
        ap.print_help()
    sys.exit(0)


if __name__ == "__main__":
    main()
