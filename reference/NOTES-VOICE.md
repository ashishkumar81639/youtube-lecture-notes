# Notes voice (verbatim)

The user's directive on how `study-notes.md` must read. Preserved unchanged, like `SPEC.md`.

**`SPEC.md` says what must be true of the notes. This file says how they read.** The two no longer
conflict — SPEC §16, §33, §34 and §40 were amended to match (see its changelog). If a future
disagreement appears, fix it at source rather than adding an override layer here: two documents
stating the same rule is how the duplicate-label bug in `verify_notes.py` happened.

---

NOTES VOICE — overrides the default write-up style.

These notes are for future-me revising the material, not for reconstructing
the video. Thoroughness is required. Video narration is not.

Reader
  Assume I can see every embedded image. Write as a student who understood
  the lecture and wrote the ideas down in their own words. State facts I
  now know. Keep the lecturer's names, formulas, examples, and numbers.
  Paraphrase everything else. Quote only when the exact wording is what I
  must memorise (a definition, an interview answer).

Do not write
  - canvas / webcam / scroll / title-card / "he draws" / "the video then…"
  - production metadata (resolution, tool, Whisper, captions, hallucination
    audit, how the notes were produced)
  - a "how to read these notes" or three-layer preamble
  - timestamps except on section headings
  - transcription disagreements that do not change a fact
  - accessibility captions of what a picture looks like (colours, layout,
    "a white rectangle labelled…")

Do write
  - why a choice was made, and the alternative that was rejected
  - worked examples with the lecturer's actual numbers, step by step
  - formulas as they were built, piece by piece
  - interview traps the lecturer flagged, quoted if the wording is the answer
  - places the lecturer was wrong or incomplete, labelled as such
  - labelled external checks only where they change understanding

Diagrams
  Embed the screenshot. Then extract content: labels, formulas, arrows, the
  claim the picture makes. If the image already shows it, do not also
  prose-describe it. Never write a "What the diagram shows" section that is
  an accessibility caption.

Structure
  Follow the lecturer's agenda. Bullets, tables, formulas, short paragraphs.
  Prose is fine when it carries reasoning. Prose is wrong when it carries
  stage direction.

Audit / pipeline logs
  If they must exist, put them in sidecar files (transcript/, research/).
  They do not belong in study-notes.md.

The lecture is the source of truth, not the subject of the notes.

---

# What SPEC still owns

Style is this file's. **Substance is SPEC's, and none of it is relaxed:** the three source layers,
labelled external research (§21–§25), WHY and rejected alternatives (§28), worked examples (§29),
formulas (§30), trade-offs (§31), diagram fidelity (§18), the frame manifest (§13), and the §41
status report — which goes to the user, never into `study-notes.md`.

Notes that read beautifully but drop a rejected alternative or an unlabelled external claim are a
failure of the spec, and this file is no defence.

## Timestamps

Section headings carry a timestamp range so future-me can jump back to the video. Nothing else does.
Do not timestamp individual claims, quotes, or diagram references.

```markdown
## 4.5 The cost function            ← range on the heading is right
*(24:55 – 30:31)*

He divides by 2m ...                ← no timestamp here
```

## The two failure modes, with the output that actually produced them

Both of these came from a real run of this skill (Krish Naik, ML, 1 h). The prose rules above did not
prevent them, which is why they are written out concretely and why `voice_lint.py` exists.

### Failure 1 — the subject of the sentence is the video, not the material

Count the grammatical subjects. If they are *the lecturer* or *the video*, the notes are about a
recording. Future-me is revising machine learning, not the recording of it.

```markdown
BAD   Krish builds this as a set of nested regions.
BAD   | **θ₀** | Intercept | Meaning as he defines it ... |
BAD   ## 4.4 The aim — and an alternative he explicitly rejects

GOOD  AI ⊃ ML ⊃ DL. Data science spans all three.
GOOD  θ₀ is the intercept: the value of h(x) when x = 0 — where the line meets the y-axis.
GOOD  ## 4.4 Why not just try many lines
```

The lecturer's **name** survives where attribution is the fact (`the θ notation follows Andrew Ng`)
and where an interview answer is his framing. It does not survive as the subject of every sentence.

### Failure 2 — the caption and the content say the same thing, and the caption is the worthless copy

This is structural, not stylistic. Treating "embed the image" and "explain the section" as two
separate obligations produces the content **twice**: once as a description of shapes, once as actual
teaching. One real section shipped the image, then a code block of the slide text, then a prose
description of the same graph, then a table redefining the same two symbols — four passes, three of
them redundant.

```markdown
BAD   ### What the diagram shows
      - A white **rectangle** labelled `AI` — the whole universe.
      - Inside it, a red **circle** labelled `ML`.
      - Inside that, a green **circle** labelled `DL`.
      - Red arrow into the ML circle: `Stats tools to analyze, Visualize...`

      ## AI — the outermost set
      Artificial Intelligence is defined functionally...     <-- the real content, said AGAIN
```

```markdown
GOOD  ![AI, ML and DL](frames/selected/07-52-....png)

      **AI** — an application that does its task without human intervention.
      Netflix recommendations, Amazon's iPhone→headphones, Tesla self-driving.
      **ML** ⊂ AI — statistical tools to analyse, visualise, predict and forecast.
      **DL** ⊂ ML — multi-layered neural networks that mimic the human brain.
```

Colour, position and shape are never content. **If the reader can see it, do not say it.** Extract
only what the picture *asserts*: formulas, labels, arrow semantics, the claim being made.

Test: delete every sentence that would still be true if the diagram showed a completely different
subject. `A white rectangle labelled X contains a red circle labelled Y` survives that deletion —
which is exactly why it is worthless.

## Scope: this governs `diagrams/recreated/*.md` too

Recreations are notes, not build logs. The same rules apply — with **one carve-out**, because
SPEC §18 requires stating where a recreation might mislead.

**A fidelity note survives only if it changes how the diagram should be trusted.** Write it as a
claim about the *subject*, not about the act of copying.

```markdown
BAD   Reproduced **exactly as drawn**. On screen this is a white rectangle
      labelled `AI`, containing a red circle labelled `ML`.
BAD   | Ink colour | Written text | Attached to |
BAD   **Follows the frame at 07:52** (`frames/selected/07-52-....png`)

GOOD  **Data science has no region here.** It is described as spanning all
      three but never given a boundary, so none is invented.
GOOD  **The equations are verbatim; the control flow is a reconstruction.**
      The branch on the sign of the slope is argued explicitly but was never
      drawn as a decision node.
```

The first three say what was copied and in what colour. The last two tell you **what you may and
may not conclude from the picture** — which is the entire reason SPEC §18 asks for a fidelity note.

Cite the source moment in the **heading** (`*(07:52)*`), never mid-sentence.

## Sanctioned labels

Only these are recognised by `verify_notes.py` as Layer-3 / aside blocks. Anything else silently
loses the quote exemption and gets flagged as a misquote of the lecturer:

```
> **External check:**            a source that confirms or corrects
> **External clarification:**    a source that supplies context SPEC 23
> **Further context:**           ditto
> **Verification note:**         a claim checked against documentation
> **Interview insight:**         use sparingly; say if it is your inference
> **Interview trap:**            a trap the lecturer flagged
> **Error, corrected in place:** the lecturer was wrong and fixed it
> **Incomplete as listed:**      the lecturer was incomplete
```

## The test for a sentence

> Would a student who understood the lecture and never saw the recording write this sentence?

If it only makes sense to someone reconstructing a *video* — "he then draws", "the canvas scrolls",
"the captions garble this" — it fails, and belongs in a sidecar or nowhere.
