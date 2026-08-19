#!/usr/bin/env python3
"""
Convert a YouTube .vtt caption file to timestamped plain text.

Handles the two things that break naive VTT parsing:
  1. inline karaoke tags  <00:00:00.320><c> word</c>
  2. ROLLING REPEATS - each cue restates the previous line, so a naive parse
     roughly triples the transcript length.

Usage: vtt_to_text.py IN.vtt [-o OUT.txt]
"""
import argparse, re, sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("vtt")
    ap.add_argument("-o", "--out", default=None)
    a = ap.parse_args()

    src = open(a.vtt, encoding="utf-8").read()
    lines, seen = [], set()

    for block in re.split(r"\n\n+", src):
        m = re.search(r"(\d\d:\d\d:\d\d)\.\d\d\d --> ", block)
        if not m:
            continue
        body = re.sub(r"<[^>]+>", "", "\n".join(block.split("\n")[1:]))
        for ln in body.split("\n"):
            ln = ln.strip()
            if ln and ln not in seen:      # kill rolling repeats
                seen.add(ln)
                lines.append((m.group(1), ln))

    out = "".join(f"[{t}] {l}\n" for t, l in lines)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(out)
        print(f"{len(lines)} lines -> {a.out}", file=sys.stderr)
    else:
        sys.stdout.write(out)


if __name__ == "__main__":
    main()
