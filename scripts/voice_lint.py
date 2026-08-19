#!/usr/bin/env python3
"""
Enforce reference/NOTES-VOICE.md on study-notes.md.

A prose style directive did not survive contact with a real run - the notes shipped 24
accessibility captions, 21 stage directions and 13 production-metadata mentions. Every other
rule in this skill has a checker; this is that checker.

Checks are deliberately mechanical. It cannot judge whether a paragraph is insightful; it CAN
catch the vocabulary and structures that mean the notes are about a video instead of a subject.

  python voice_lint.py study-notes.md
  python voice_lint.py study-notes.md --quiet     # exit code only
"""
import argparse, re, sys, pathlib

# (regex, label, why it is wrong)
BANNED = [
    (r"###+\s*What the diagram shows",
     "accessibility-caption heading",
     "Extract what the picture ASSERTS (formulas, labels, claims), not what it looks like."),
    (r"\b(canvas|webcam|title[- ]card|slide deck scrolls?|the canvas scrolls?)\b",
     "production/stage vocabulary",
     "The medium is not the subject."),
    (r"\b(he|she|they)\s+(draws?|writes?|sketches?|circles?|underlines?|erases?)\b",
     "stage direction",
     "State the fact, not the act of recording it."),
    (r"\b(the (video|recording|lecture) (then|now|continues|cuts))\b",
     "narration of the recording",
     "Future-me is revising the material, not replaying the video."),
    (r"\b(Whisper|auto[- ]captions?|hallucination audit|transcription (audit|log)|ffmpeg|yt-dlp|1080p|contact sheets?)\b",
     "production metadata",
     "Belongs in transcript/ or research/, never in study-notes.md."),
    (r"^#+\s*How to read these notes",
     "three-layer preamble",
     "No preamble. Start with the material."),
    (r"^#+\s*Transcription uncertainties",
     "transcription-uncertainty section",
     "Moves to the correction log in transcript/transcript-clean.txt."),
    (r"\b(a|an|the)\s+(white|red|green|blue|yellow|black)\s+(rectangle|circle|box|line|arrow|dot|curve)\b",
     "colour/shape description",
     "Colour and shape are never content - the reader can see the image."),
    (r"\b(top|bottom)[- ](left|right)\b.{0,30}\b(inset|corner|of the (frame|screen))\b",
     "frame-layout description",
     "Layout is not content."),
    (r"\b(exactly )?as drawn\b|\breproduced (exactly|as)\b|\bon screen (this|it|the)\b",
     "reproduction narration",
     "State what the diagram asserts; 'as drawn' describes the act of copying."),
    (r"\bink colou?rs?\b|\b(colou?r|shade) of the (ink|pen|marker)\b",
     "ink-colour description",
     "Which pen was used is never content."),
    (r"\bfollows the frame at\b|\bthe frame (shows|at)\b|\bin the frame\b",
     "frame reference in prose",
     "Cite the source in the heading, not mid-sentence."),
]

# Markdown emphasis defeats word-boundary patterns: "a white **rectangle**" slipped past the
# colour/shape rule because \s+ cannot cross the asterisks. Strip emphasis before matching.
EMPH = re.compile(r"(\*{1,3}|_{1,3}|`)")

# inline timestamps: allowed on a heading or the italic range line directly under one
TS = re.compile(r"\(?\b\d{1,2}:\d{2}(?::\d{2})?\b\)?")


def lint(path: pathlib.Path):
    lines = path.read_text().splitlines()
    hits = []
    in_code = False
    prev_heading = False

    for i, raw in enumerate(lines, 1):
        if raw.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue

        is_heading = raw.lstrip().startswith("#")

        probe = EMPH.sub("", raw)          # see EMPH note above
        for pat, label, why in BANNED:
            flags = re.I | (re.M if pat.startswith("^") else 0)
            if re.search(pat, raw, flags) or re.search(pat, probe, flags):
                hits.append((i, label, why, raw.strip()[:90]))

        # timestamps outside headings / the range line under a heading
        if not is_heading and not prev_heading and TS.search(raw):
            # a table row of ranges is a legitimate index; only flag prose
            if not raw.lstrip().startswith("|"):
                hits.append((i, "inline timestamp", "Timestamps belong on section headings only.",
                             raw.strip()[:90]))

        prev_heading = is_heading or (prev_heading and not raw.strip())

    return hits, len(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("notes", nargs="+",
                    help="study-notes.md and diagrams/recreated/*.md - recreations are notes too")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    worst = 0
    for target in a.notes:
        rc = lint_one(pathlib.Path(target), a.quiet)
        worst = max(worst, rc)
    return worst


def lint_one(p, quiet):
    if not p.exists():
        print(f"no such file: {p}", file=sys.stderr)
        return 2

    hits, n = lint(p)
    if not quiet:
        print(f"{p}  ({n} lines)\n")
        if not hits:
            print("VOICE OK - no stage direction, captions, production metadata or stray timestamps.")
        else:
            by = {}
            for ln, label, why, txt in hits:
                by.setdefault(label, []).append((ln, why, txt))
            print(f"VOICE VIOLATIONS: {len(hits)} across {len(by)} categories\n")
            for label, rows in sorted(by.items(), key=lambda kv: -len(kv[1])):
                print(f"  {label}  x{len(rows)}")
                print(f"    -> {rows[0][1]}")
                for ln, _why, txt in rows[:4]:
                    print(f"       line {ln}: {txt}")
                if len(rows) > 4:
                    print(f"       ... and {len(rows) - 4} more")
                print()
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
