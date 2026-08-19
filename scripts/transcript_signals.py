#!/usr/bin/env python3
"""
Mine a transcript for signals that GUIDE frame selection - before any image is
looked at. Text is ~5x cheaper than the visual pass it optimises, so run FIRST.

Produces: ad_spans (exclude from frames), visual_pointers (boost), sections.

FOUR MODES - pick by WHERE you are running:

  prep      DEFAULT, and the right one inside Claude Code / any agent loop.
            Prints a compact digest of the transcript plus the exact schema to
            fill in. The LLM already in the loop reads it and writes the JSON.
            NO API KEY, NO EXTRA CALL, NO DOUBLE BILLING - that agent is already
            reading this transcript to write the notes.

  validate  Check the JSON the LLM wrote, sanity-check it against the transcript,
            and print the ready-to-paste --exclude string for refine_frames.py.

  api       Standalone Claude call. ONLY for headless use - cron, CI, or a plain
            shell with no agent present. Needs credentials. Inside Claude Code
            this is pure waste.

  regex     Offline keyword fallback. Emits CANDIDATES only; every span must be
            confirmed. Measured failures: flagged "every SUBSCRIBED client's
            port" as a sponsor read, and missed 21s of promo containing no
            keyword at all.

Usage:
    transcript_signals.py TRANSCRIPT.txt                      # prep  (default)
    transcript_signals.py TRANSCRIPT.txt --validate sig.json
    transcript_signals.py TRANSCRIPT.txt --mode regex --json sig.json
    transcript_signals.py TRANSCRIPT.txt --mode api   --json sig.json
"""
import argparse, json, re, sys

SCHEMA = """{
  "ad_spans":        [{"start": <sec>, "end": <sec>, "reason": "...",
                       "confidence": "high|medium|low"}],
  "visual_pointers": [{"t": <sec>, "what": "what is being pointed at on screen"}],
  "sections":        [{"t": <sec>, "title": "short section title"}]
}"""

TASK = """Read the digest below and produce the JSON described.

ad_spans - promotional rather than lecture content: sponsor reads, the presenter
  plugging their own product/course, subscribe/like appeals, sign-off outros.
  Give the FULL span - from where the promo actually starts to where lecture
  content actually resumes. Promo talk usually runs well past the obvious trigger
  phrase (measured: one ran 21s past the last keyword).
  Do NOT flag technical content that merely uses a promo-sounding word, e.g.
  "every subscribed client's port" when discussing multicast is NOT an ad.
  When unsure, mark confidence "low" and keep it. Deleting real teaching is much
  worse than keeping a few seconds of ad.

visual_pointers - moments the lecturer points at something on screen ("as you can
  see", "here we have our sequencer"). These mark high-value frames.

sections - the lecture's own topical structure. If the lecturer reads out an
  agenda, use their names."""

AD = [r"check (?:it |them )?out", r"link in the (?:description|bio)", r"like and subscribe",
      r"\bsubscribe\b", r"sign up", r"discount|coupon|promo code", r"\bsponsor", r"my course",
      r"full write[- ]?up", r"helped me go from", r"share with a friend", r"helps the channel"]
POINTER = [r"as you can see", r"(?:you )?can see (?:here|that|this)", r"here we (?:have|see)",
           r"this (?:diagram|table|slide|chart|code|example|architecture)",
           r"looking at (?:the|this|our)", r"on the (?:screen|left|right|slide)", r"shown here",
           r"we'?ve got (?:our|a|the) [\w\s]{2,28} here", r"(?:this|that) (?:is|shows) (?:the|our)"]


def parse(p):
    """Take only the MONOTONIC PREFIX of timestamped lines.

    transcript-clean.txt carries a correction-log appendix that quotes its own
    [HH:MM:SS] timestamps. Parsing naively pulls those in, so the 'end of
    lecture' is wrong and appendix prose leaks into the digest. Real transcript
    timestamps only ever increase; a large backwards jump means we have left the
    transcript body.
    """
    out = []
    for ln in open(p, encoding="utf-8"):
        m = re.match(r"\[(\d\d):(\d\d):(\d\d)\]\s*(.*)", ln)
        if not m:
            continue
        t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        if out and t < out[-1][0] - 5:
            break
        out.append((t, m.group(4).strip()))
    return out


def ms(t): return f"{t // 60:02d}:{t % 60:02d}"


def prep(lines, every):
    """Compact digest for the in-loop LLM. Merges lines into ~`every`-second blocks."""
    print("=" * 78)
    print("TRANSCRIPT DIGEST - fill in this JSON, save it, then run --validate")
    print("=" * 78)
    print(f"\n{TASK}\n\nSCHEMA (timestamps are SECONDS):\n{SCHEMA}\n")
    print("=" * 78)
    buf, start = [], lines[0][0]
    for t, x in lines:
        if t - start >= every and buf:
            print(f"[{start}s | {ms(start)}] {' '.join(buf)}")
            buf, start = [], t
        buf.append(x)
    if buf:
        print(f"[{start}s | {ms(start)}] {' '.join(buf)}")


def regex_mode(lines, pad, gap):
    def hits(pats):
        rx = re.compile("|".join(pats), re.I)
        return [(t, x) for t, x in lines if rx.search(x)]
    spans = []
    for t, _ in hits(AD):
        if spans and t - spans[-1][1] <= gap:
            spans[-1][1] = t
        else:
            spans.append([t, t])
    return {"ad_spans": [{"start": max(0, s - pad), "end": e + pad,
                          "reason": "keyword match", "confidence": "low"} for s, e in spans],
            "visual_pointers": [{"t": t, "what": x[:90]} for t, x in hits(POINTER)],
            "sections": [],
            "_mode": "regex (CANDIDATES ONLY - confirm before excluding)"}


def api_mode(lines, model, effort):
    try:
        import anthropic
        from pydantic import BaseModel, Field
        from typing import List, Literal
    except ImportError:
        sys.exit("pip install anthropic pydantic")

    class AdSpan(BaseModel):
        start: int; end: int; reason: str
        confidence: Literal["high", "medium", "low"]

    class Pointer(BaseModel):
        t: int; what: str

    class Section(BaseModel):
        t: int; title: str

    class Signals(BaseModel):
        ad_spans: List[AdSpan]; visual_pointers: List[Pointer]; sections: List[Section]

    body = "\n".join(f"[{t}s] {x}" for t, x in lines)
    client = anthropic.Anthropic()
    print(f"calling {model} (effort={effort})...", file=sys.stderr)
    with client.messages.stream(
        model=model, max_tokens=16000,
        thinking={"type": "adaptive"}, output_config={"effort": effort},
        messages=[{"role": "user", "content": f"{TASK}\n\nTRANSCRIPT:\n{body}"}],
        output_format=Signals,
    ) as st:
        r = st.get_final_message()
    if r.stop_reason == "refusal":
        sys.exit(f"model declined: {r.stop_details}")
    return {**json.loads(r.parsed_output.model_dump_json()), "_mode": f"api ({model})"}


def validate(sig, lines):
    """Sanity-check LLM-written JSON against the transcript before it is trusted."""
    end = max(t for t, _ in lines)
    warn = []
    for s in sig.get("ad_spans", []):
        for k in ("start", "end"):
            if k not in s:
                warn.append(f"ad_span missing '{k}': {s}"); continue
        if s.get("start", 0) > s.get("end", 0):
            warn.append(f"ad_span reversed: {s}")
        if s.get("end", 0) > end + 30:
            warn.append(f"ad_span past end of lecture ({ms(end)}): {s}")
        dur = s.get("end", 0) - s.get("start", 0)
        if dur > 180:
            warn.append(f"ad_span {ms(s['start'])}-{ms(s['end'])} is {dur}s - unusually long, "
                        f"check it is not swallowing lecture content")
    covered = sum(s.get("end", 0) - s.get("start", 0) for s in sig.get("ad_spans", []))
    if covered > 0.25 * end:
        warn.append(f"ad_spans cover {covered}s of {end}s ({covered / end:.0%}) - too much")
    return warn


def report(r, lines):
    print("=" * 78); print(f"MODE: {r.get('_mode', 'llm (in-loop)')}"); print("=" * 78)
    print(f"\nAD / PROMO SPANS ({len(r.get('ad_spans', []))})")
    for s in r.get("ad_spans", []):
        print(f"  {ms(s['start'])}-{ms(s['end'])}  [{s.get('confidence', '?')}]  {s.get('reason', '')}")
    print(f"\nVISUAL POINTERS ({len(r.get('visual_pointers', []))})")
    for p in r.get("visual_pointers", []):
        print(f"  {ms(p['t'])}  {p['what'][:86]}")
    if r.get("sections"):
        print(f"\nSECTIONS ({len(r['sections'])})")
        for s in r["sections"]:
            print(f"  {ms(s['t'])}  {s['title'][:86]}")
    w = validate(r, lines)
    if w:
        print("\n!! WARNINGS")
        for x in w:
            print(f"  - {x}")
    ex = ",".join(f"{ms(s['start'])}-{ms(s['end'])}" for s in r.get("ad_spans", []))
    if ex:
        print(f"\nPass to refine_frames.py:\n  --exclude {ex}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("--mode", choices=["prep", "regex", "api"], default="prep")
    ap.add_argument("--validate", metavar="JSON", default=None)
    ap.add_argument("--json", default=None)
    ap.add_argument("--every", type=int, default=20, help="prep: seconds per digest block")
    ap.add_argument("--model", default="claude-opus-5")
    ap.add_argument("--effort", default="high",
                    choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--pad", type=int, default=8)
    ap.add_argument("--gap", type=int, default=25)
    a = ap.parse_args()

    lines = parse(a.transcript)
    if not lines:
        sys.exit("no [HH:MM:SS] lines found")

    if a.validate:
        r = json.load(open(a.validate)); report(r, lines); return
    if a.mode == "prep":
        prep(lines, a.every); return

    r = regex_mode(lines, a.pad, a.gap) if a.mode == "regex" else api_mode(lines, a.model, a.effort)
    report(r, lines)
    if a.json:
        json.dump(r, open(a.json, "w"), indent=1)
        print(f"\n-> {a.json}", file=sys.stderr)


if __name__ == "__main__":
    main()
