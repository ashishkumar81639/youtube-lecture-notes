#!/usr/bin/env python3
"""
Split a long lecture into chunks that are processed independently, so context can
be cleared between them.

WHY 25 MINUTES: measured on a 22:18 run that produced good notes -
  transcript 7.7k + images 34.2k + notes 12.2k + research ~18k = ~72k working context
scaling that:
  20 min -> ~65k     45 min -> ~145k
  25 min -> ~81k     60 min -> ~194k
Past ~45 min the failure mode is not hitting a limit, it is COMPRESSING instead of
reasoning - which is invisible in the output. 25 min keeps headroom to think.

WHY BOUNDARIES BEAT THE CLOCK: splitting mid-derivation separates a decision from
its reasoning and breaks the "preserve WHY" requirement outright. So the target is
25 min but any boundary between --min and --max is preferred if it lands on a real
section start.

Usage:
    chunk_plan.py TRANSCRIPT.txt --duration SECONDS [--target 25] [--min 15] [--max 40]
                  [--sections signals.json] [--out chunks/manifest.json]
"""
import argparse, json, os, re, sys

SECTION = [
    r"next up", r"let'?s (?:dive|jump|get|move) (?:in)?to", r"moving on", r"deep dive",
    r"so that'?s (?:the |our )?\w+ done", r"let'?s (?:start|begin) (?:with|off)",
    r"the (?:first|second|third|next|last) (?:part|thing|step|topic)",
    r"now (?:let'?s|we)", r"in this (?:section|part|video)", r"to summari[sz]e",
]


def parse(p):
    out, prev = [], -1
    for ln in open(p, encoding="utf-8"):
        m = re.match(r"\[(\d\d):(\d\d):(\d\d)\]\s*(.*)", ln)
        if not m:
            continue
        t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        if out and t < prev - 5:      # monotonic prefix only (skip appendices)
            break
        prev = t
        out.append((t, m.group(4).strip()))
    return out


def hms(t):
    return f"{t//3600:02d}:{(t%3600)//60:02d}:{t%60:02d}"


def slug(s, n=42):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:n].rstrip("-") or "section"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("--duration", type=float, required=True)
    ap.add_argument("--target", type=float, default=25.0)
    ap.add_argument("--min", type=float, default=15.0)
    ap.add_argument("--max", type=float, default=40.0)
    ap.add_argument("--sections", default=None, help="JSON with a 'sections' list")
    ap.add_argument("--out", default="chunks/manifest.json")
    a = ap.parse_args()

    lines = parse(a.transcript)
    if not lines:
        sys.exit("no [HH:MM:SS] lines")

    # candidate boundaries: explicit sections if supplied, else keyword hits
    if a.sections and os.path.exists(a.sections):
        sig = json.load(open(a.sections))
        cands = [(s["t"], s.get("title", "")) for s in sig.get("sections", [])]
    else:
        rx = re.compile("|".join(SECTION), re.I)
        cands = [(t, x[:60]) for t, x in lines if rx.search(x)]
    cands.sort()

    tgt, lo, hi = a.target * 60, a.min * 60, a.max * 60
    chunks, start = [], 0.0
    while start < a.duration - lo / 2:
        ideal = start + tgt
        window = [c for c in cands if start + lo <= c[0] <= start + hi]
        if window:
            cut, title = min(window, key=lambda c: abs(c[0] - ideal))
            snapped = True
        else:
            cut, title, snapped = min(ideal, a.duration), "", False
        if a.duration - cut < lo:       # absorb a short tail
            cut, title = a.duration, title
        chunks.append({
            "index": len(chunks) + 1,
            "start": round(start, 1), "end": round(cut, 1),
            "minutes": round((cut - start) / 60, 1),
            "title": title, "snapped_to_section": snapped,
            "dir": f"chunks/{len(chunks)+1:02d}-{slug(title) if title else 'part'}",
            "status": "pending",
        })
        start = cut
        if cut >= a.duration:
            break

    print(f"{a.duration/60:.1f} min -> {len(chunks)} chunks "
          f"(target {a.target:.0f}, range {a.min:.0f}-{a.max:.0f})\n")
    unsnapped = 0
    for c in chunks:
        flag = "" if c["snapped_to_section"] else "   <- CLOCK CUT, verify it is not mid-topic"
        if not c["snapped_to_section"]:
            unsnapped += 1
        print(f"  {c['index']:>2}. {hms(int(c['start']))}-{hms(int(c['end']))} "
              f"({c['minutes']:>4.1f}m)  {c['title'][:48]}{flag}")
    est = 72 * (sum(c['minutes'] for c in chunks) / len(chunks)) / 22.3
    print(f"\n  est. working context per chunk ~{est:.0f}k tokens")
    if unsnapped:
        print(f"  {unsnapped} chunk(s) cut on the clock - review those boundaries by hand")

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump({"duration": a.duration, "target_minutes": a.target, "chunks": chunks},
              open(a.out, "w"), indent=1)
    print(f"\n  -> {a.out}   (status field makes the run resumable)")


if __name__ == "__main__":
    main()
