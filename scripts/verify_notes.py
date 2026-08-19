#!/usr/bin/env python3
"""
Accuracy gate. Every factual claim in the notes must trace to one of the THREE
LAYERS, or it is flagged.

These notes are for studying. A fabricated number is worse than a missing one:
when revising, it is indistinguishable from a real one.

A number is legitimate if it appears in ANY of:
  Layer 1  the transcript                     (spoken)
  Layer 2  OCR of the selected frames         (on screen)   <- needs --frames
  Layer 3  inside a labelled external block   (researched)

Anything in none of those is reported. Headings, code blocks, timestamps, file
paths, URLs and the External-references table are excluded - they are structure,
not claims.

NOTE ON LAYER 2: OCR is reliable on PRINTED slides and useless on handwriting
(measured: Apple Vision returned garbage on Apple Pencil notes). For handwritten
sources, pass --visual-unverifiable so those numbers are reported as
"needs-human-check" rather than as errors.

Usage:
    verify_notes.py NOTES.md TRANSCRIPT.txt [--frames frames/selected]
                    [--visual-unverifiable] [--strict]
"""
import argparse, glob, os, re, sys

# Sanctioned Layer-3 / aside labels. Quotes inside these blocks cite external docs, not the
# lecturer, so they are exempt from the verbatim-against-transcript check. Keep in sync with
# reference/NOTES-VOICE.md - an unrecognised label silently loses the exemption.
EXT_LABELS = ["External clarification", "Further context", "Verification note",
              "External check", "Interview insight", "Interview trap",
              "Error, corrected in place", "Incomplete as listed"]
_ALT = "|".join(re.escape(x) for x in EXT_LABELS)
EXT_MARKER = re.compile(rf"\*\*({_ALT})\b", re.I)
# SPEC 33-34 (as amended): the transcription correction log lives in
# transcript/transcript-clean.txt, and visual ambiguities are written inline where they
# change a fact rather than as a catch-all section. Requiring them here made the verifier
# flag CORRECT notes as broken - the failure mode that gets a verifier ignored.
REQUIRED = ["Key takeaways", "Things worth revisiting", "External references"]
RETIRED = {"Transcription uncertainties": "transcript/transcript-clean.txt correction log",
           "Visual uncertainties": "inline, where the ambiguity changes a fact"}
WORDNUM = {"one":"1","two":"2","three":"3","four":"4","five":"5","six":"6","seven":"7",
           "eight":"8","nine":"9","ten":"10","twenty":"20","thirty":"30","forty":"40",
           "fifty":"50","sixty":"60","ninety":"90","hundred":"100","thousand":"1000",
           "million":"1000000","billion":"1000000000"}


def nums_in(text):
    out = set(x.replace(",", "").rstrip(".").lower()
              for x in re.findall(r"\d[\d,]*\.?\d*", text))
    low = text.lower()
    for w, d in WORDNUM.items():
        if re.search(rf"\b{w}\b", low):
            out.add(d)
    return out


def ocr_corpus(frames_dir):
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from vision_ocr import ocr
    except Exception as e:
        print(f"  (OCR unavailable: {e}; Layer 2 will not be checked)", file=sys.stderr)
        return None
    txt = []
    for f in sorted(glob.glob(os.path.join(frames_dir, "*.png")) +
                    glob.glob(os.path.join(frames_dir, "*.jpg"))):
        try:
            txt.extend(r["text"] for r in ocr(f))
        except Exception:
            pass
    return " ".join(txt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("notes"); ap.add_argument("transcript")
    ap.add_argument("--frames", default=None)
    ap.add_argument("--visual-unverifiable", action="store_true")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()

    notes = open(a.notes, encoding="utf-8").read()
    tr = open(a.transcript, encoding="utf-8").read()
    supported = nums_in(tr)
    vis_txt = ocr_corpus(a.frames) if a.frames else None
    if vis_txt:
        supported |= nums_in(vis_txt)

    problems, needs_eye, warnings = [], [], []
    lines = notes.split("\n")

    in_code = False
    in_refs = False
    ext_depth = 0
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("```"):
            in_code = not in_code; continue
        if re.match(r"^#+\s", s):
            in_refs = bool(re.search(r"External references", s, re.I))
            continue                                     # headings are structure
        if in_code or in_refs:
            continue
        if s.startswith(">"):
            # A marked blockquote is exempt for its WHOLE length, not a fixed window.
            # The old rule (depth 2, decaying) covered the marker line plus one, so a quote
            # on the third line of an external block was flagged as a misquote of the lecturer.
            if EXT_MARKER.search(s):
                ext_depth = 1
            if ext_depth:
                continue
        else:
            ext_depth = 0                                # blockquote ended

        clean = re.sub(r"\d\d:\d\d(:\d\d)?", " ", ln)
        clean = re.sub(r"[\w./-]*\.(png|jpg|md|json|mp4|txt|py|pdf)", " ", clean)
        clean = re.sub(r"https?://\S+", " ", clean)
        clean = re.sub(r"§\s*[\d.]+", " ", clean)
        clean = re.sub(r"`[^`]*`", " ", clean)           # inline code is quoted material
        for m in re.finditer(r"(?<![\w.])(\d[\d,]*\.?\d*)(?![\w])", clean):
            n = m.group(1).replace(",", "").rstrip(".").lower()
            if n in supported or len(n) < 2:
                continue
            if n in {"1","2","3","4","5","6","7","8","9","10"}:
                continue
            entry = f"line {i+1}: '{m.group(1)}'  |  {s[:84]}"
            if vis_txt is None or a.visual_unverifiable:
                needs_eye.append(entry)
            else:
                problems.append(entry)

    # quoted lecture speech: only inside blockquotes or after "the lecturer".
    # STRIP TIMESTAMPS FIRST - a quote spanning a line break otherwise has
    # "[00:05:43]" sitting in the middle of it and never matches. (Real bug: it
    # produced 3 false alarms on quotes that were verbatim.)
    tr_notime = re.sub(r"\[\d\d:\d\d:\d\d\]", " ", tr.lower())
    flat = re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", tr_notime))
    # Layer-3 blocks quote external DOCS, not the lecturer - exempt them.
    # Built from EXT_LABELS - this used to carry its OWN hardcoded list of three labels,
    # so any other sanctioned label silently lost the exemption and its external quotes were
    # reported as misquotes of the lecturer. One source of truth.
    ext_spans = [(m.start(), m.end()) for m in re.finditer(
        rf"^>.*?\*\*({_ALT})\b.*?(?=\n\n|\Z)", notes, re.M | re.S | re.I)]

    def in_ext(pos):
        return any(s <= pos <= e for s, e in ext_spans)

    for m in re.finditer(r'(?:^>|lecturer|states?|says?)[^\n]*?[""]([^""\n]{30,200})[""]',
                         notes, re.M | re.I):
        if in_ext(m.start()):
            continue
        q = re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", m.group(1).lower())).split()
        if len(q) >= 6 and " ".join(q[:6]) not in flat:
            warnings.append(f'quote not verbatim: "{m.group(1)[:76]}..."')

    for sec in REQUIRED:
        if not re.search(rf"^#+\s*{re.escape(sec)}", notes, re.I | re.M):
            problems.append(f"MISSING required section: '{sec}'")

    for sec, moved_to in RETIRED.items():
        if re.search(rf"^#+\s*{re.escape(sec)}", notes, re.I | re.M):
            warnings.append(f"'{sec}' section is retired by NOTES-VOICE.md - move it to {moved_to}")

    base = os.path.dirname(os.path.abspath(a.notes))
    for m in re.finditer(r"\]\((?!https?:)([^)#]+)\)", notes):
        if not os.path.exists(os.path.join(base, m.group(1).strip())):
            problems.append(f"broken link: {m.group(1).strip()}")

    print(f"{os.path.basename(a.notes)}  vs  transcript"
          f"{' + OCR of ' + a.frames if vis_txt else ''}")
    print(f"supported numbers indexed: {len(supported)}\n")
    print(f"PROBLEMS ({len(problems)})" if problems else "PROBLEMS: none")
    for p in problems[:30]:
        print(f"  ! {p}")
    if needs_eye:
        print(f"\nNEEDS HUMAN CHECK ({len(needs_eye)}) - not in transcript; verify against the frame")
        for n in needs_eye[:20]:
            print(f"  ? {n}")
    if warnings:
        print(f"\nWARNINGS ({len(warnings)}) - may be paraphrase rather than fabrication")
        for w in warnings[:12]:
            print(f"  ? {w}")
    if not problems and not needs_eye and not warnings:
        print("\nEvery numeric claim and quote traces to a layer.")
    sys.exit(1 if problems or (a.strict and (needs_eye or warnings)) else 0)


if __name__ == "__main__":
    main()
