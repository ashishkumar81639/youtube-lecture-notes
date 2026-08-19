# The specification

The 41-point brief. It is the **contract** — the definition of done. `PLAYBOOK.md` holds the
operational knowledge for executing it; `NOTES-VOICE.md` governs how the finished notes read.
All three are keyed to these section numbers.

**Amendments.** §16, §33, §34 and §40 were amended after a real run showed the original wording
producing notes *about a video* rather than notes *about a subject* — 24 accessibility captions and
a table of every transcription disagreement. The substance requirements are untouched. See the
changelog at the foot of this file.

---

# YouTube Lecture → Rich Multimodal Technical Study Notes

Process this YouTube lecture end-to-end.

Produce high-quality technical study notes based primarily on the actual lecture, including:

* spoken content
* diagrams
* architecture drawings
* slides
* code shown on screen
* equations
* tables
* whiteboard explanations
* important visual demonstrations
* carefully selected external explanations where they genuinely improve understanding

The final result should feel like detailed notes made by a strong engineer who watched the entire
lecture carefully, captured the important diagrams, understood the reasoning, and selectively
researched concepts that needed additional explanation.

---

# 1. Core Source Policy

Maintain three clearly separated knowledge layers.

## Layer 1 — Lecture Speech

Anything obtained from captions, subtitles, audio transcription, lecturer's spoken explanations.
Treat this as primary lecture material.

## Layer 2 — Lecture Visuals

Anything actually visible in the video: architecture diagrams, sequence diagrams, flowcharts,
slides, code, terminal output, database schemas, tables, formulas, whiteboard drawings, UI
demonstrations. This is also primary lecture material.

## Layer 3 — External Enrichment

External research is ALLOWED when it materially improves understanding. However:

**Never make externally researched information look like something the lecturer said.**

Clearly label external additions as `> **External clarification**` or `> **Further context**`.

The final notes should make it possible to distinguish lecture material from supplementary research.

---

# 2. Inspect My Environment

Environment: macOS, Apple Silicon M3, 16 GB RAM.

Check availability of `yt-dlp`, `ffmpeg`, `ffprobe`, `python3`, `pip3`.

Also check for suitable local transcription and image-processing tools.

Install only what is necessary. Prefer Homebrew where appropriate (`brew install yt-dlp ffmpeg`).
Do not install unnecessary dependencies.

---

# 3. Create Project Structure

```text
lecture-notes/
├── source/
│   ├── lecture.mp4
│   ├── lecture-audio.*
│   └── captions.*
├── transcript/
│   ├── transcript-raw.txt
│   ├── transcript-timestamped.txt
│   └── transcript-clean.txt
├── frames/
│   ├── raw/
│   └── selected/
├── diagrams/
│   └── recreated/
├── research/
│   └── external-research.md
└── study-notes.md
```

Keep intermediate artifacts so the final notes can be audited against the original lecture —
but **only the ones that are expensive to reproduce**. `source/`, `transcript/`, `diagrams/`,
`research/` and `frames/selected/` are kept.

`frames/raw`, `frames/masked` and `frames/tf` are **deleted once selection is finished**
(`cleanup_artifacts.py`). They are deterministic functions of `source/lecture.mp4`, which is kept, so
the audit trail is the recorded ffmpeg command in `frames/REGENERATE.md`, not 1800 thumbnails of a
video you still have. On a one-hour lecture this is 3,661 files and ~67 MB of pure redundancy
against 26 frames that are actually used.

---

# 4. Inspect YouTube Metadata and Captions

Use `yt-dlp` to inspect video metadata, duration, title, available formats, manual subtitles,
automatic subtitles, languages.

Prefer manually created English subtitles when available. Otherwise inspect English auto-generated
captions. Save available captions.

Do not assume captions are technically correct.

---

# 5. Download the Video

Unlike an audio-only workflow, download the VIDEO because visual information is important.

1080p is preferred when available because diagrams/code must remain readable. 720p is acceptable if
1080p would create an unnecessarily large file. Avoid downloading 4K unless genuinely necessary.

Ensure resulting media can be decoded by ffmpeg. Verify: file exists, duration, video stream, audio
stream, resolution, file size.

If downloading fails, clearly report why. **Never fabricate subsequent results.**

---

# 6. Obtain the Best Transcript

Preference order:

1. High-quality manually created captions
2. High-quality automatic captions
3. Local speech-to-text transcription

If captions appear unreliable for technical terminology, use audio transcription to verify or
replace them. When useful, compare captions against transcription rather than blindly trusting
either source.

---

# 7. Local Audio Transcription

If transcription is needed, use a high-quality model. Preferred options:

1. faster-whisper `large-v3`
2. Whisper `large-v3`
3. another reliable high-quality Whisper implementation
4. highest-quality model that runs reliably on this machine

Hardware: Apple M3 / 16 GB RAM. Prefer Apple Silicon / Metal acceleration where supported. Do not
use a configuration likely to exhaust memory. **Accuracy is more important than speed.**

If `large-v3` is impractical, use the strongest reliable alternative and report which model was used.

---

# 8. Generate Timestamped Transcript

Create `transcript/transcript-raw.txt`, `transcript/transcript-timestamped.txt`,
`transcript/transcript-clean.txt`.

Timestamp format: `[00:03:42] The matching engine receives...`

Preserve actual spoken meaning. **Do not summarize during transcription.**

---

# 9. Correct Technical Transcription Errors

After transcription, clean obvious speech-to-text mistakes using context. Pay particular attention
to: distributed systems, system design, databases, concurrency, networking, APIs, queues, event
streaming, Kafka, Redis, SQL, NoSQL, financial systems, trading terminology, algorithms, cloud
infrastructure, programming terminology.

Examples: `"order hook" → "order book"`, `"Kaf ka" → "Kafka"`, `"Post grass" → "Postgres"`,
`"web socket" → "WebSocket"`.

Only correct something when reasonably confident. When uncertain, mark
`[Unclear term: possibly "..."]`. **Never silently invent technical terminology.**

---

# 10. Analyze the VIDEO, Not Just the Audio

This is critical. A technical lecture communicates information visually that may never appear in the
transcript.

Inspect the complete video for architecture diagrams, boxes/arrows, flowcharts, sequence diagrams,
database schemas, code, SQL, terminal commands, equations, calculations, tables, important slides,
whiteboard explanations, demonstrations.

Treat meaningful visual information as part of the lecture source.

---

# 11. Intelligent Frame Extraction

Do NOT blindly screenshot every N seconds. That creates excessive duplicate images and wastes
processing/tokens.

Instead use scene-change detection, perceptual similarity, visual difference, slide changes, diagram
changes to identify meaningful visual transitions.

Extract candidate frames. Then remove duplicates, near-duplicates, transition frames, blank screens,
irrelevant presenter-only frames, frames with no meaningful study value.

Keep only useful frames.

---

# 12. Prefer High-Value Visuals

Prioritize frames containing: (1) architecture diagrams, (2) system-design drawings, (3) sequence
diagrams, (4) important flowcharts, (5) data models, (6) code, (7) equations, (8) tables,
(9) whiteboard explanations, (10) important summary slides.

Do not include images merely to make the notes visually attractive. **Every image should provide
learning value.**

---

# 13. Associate Frames With Transcript Timestamps

For every selected frame: record its video timestamp, identify the corresponding transcript section,
determine what the lecturer is explaining at that moment.

```text
Frame:          00:18:42
Transcript:     Discussion of matching-engine architecture.
Classification: Architecture diagram
```

This prevents diagrams from becoming detached from their explanations.

---

# 14. Visual Understanding

Analyze selected frames carefully.

- **Diagrams:** components, arrows, data flow, dependencies, boundaries, labels, databases, queues,
  services, protocols.
- **Code:** important classes/functions, algorithms, APIs, schemas, queries.
- **Equations:** variables, formulas, example calculations.

Use OCR only when necessary. Do not rely blindly on OCR when visual inspection provides better
understanding. **If text cannot be read reliably, say so.**

---

# 15. Save Important Lecture Images

Store useful frames under `frames/selected/`. Use descriptive names where possible:

```text
00-18-42-matching-engine-architecture.png
00-27-13-order-book.png
00-41-05-database-schema.png
```

Do not use meaningless names such as `frame382.png` when the visual content is understood.

---

# 16. Embed Visuals in Study Notes

Place images near the relevant explanation.

Embed the image, then **extract what it asserts** — labels, formulas, arrow semantics, the claim it
makes. Never describe colour, shape or position: the reader can see the picture, and a description
of it is a second, worthless copy of the content.

```markdown
## Matching engine

![Matching engine architecture](frames/selected/00-18-42-matching-engine-architecture.png)

Orders arrive at the API layer and are passed to the matching engine, which owns the order book.
Persistence is asynchronous — the engine never blocks on a write.
```

```markdown
BAD:  ### What the diagram shows
      - A blue box on the left labelled `API`, with an arrow to a green box.
```

**Do not create a giant screenshot dump at the end.** Images should appear where they help
understanding.

---

# 17. Recreate Important Diagrams When Useful

Some lecture diagrams may be handwritten, messy, low resolution, spread across multiple frames, or
difficult to review later.

For especially important diagrams, create a clean representation. Prefer Mermaid when appropriate.
ASCII diagrams are acceptable when Mermaid is inappropriate.

Save recreated diagrams under `diagrams/recreated/`.

---

# 18. Diagram Fidelity Rule

When recreating a diagram: **preserve the lecturer's architecture exactly.**

Do not add components, remove components, change technologies, redesign architecture, or "improve"
the lecturer's design.

If interpretation is uncertain, explicitly state:

> Diagram reconstruction contains an uncertain relationship between X and Y.

The purpose is faithful cleanup, not redesign.

---

# 19. Read and Understand the COMPLETE Lecture

Before generating final notes: process the entire transcript, inspect selected visuals, understand
the lecture's progression, identify major sections, identify dependencies between concepts.

**Do not generate final notes after analyzing only the beginning.**

---

# 20. Follow the Lecturer's Actual Flow

Organize notes according to the lecture's natural structure. Do NOT force a predetermined
system-design template.

If the lecturer progresses `Requirements → Capacity estimation → APIs → Order book → Matching →
Persistence → Scaling`, follow that. If the lecture uses another progression, follow that instead.

---

# 21. External Research Is Allowed

External research may be used when it materially improves understanding. Good reasons include:

* lecturer introduces a concept very quickly
* important terminology needs clarification
* a subtle distributed-systems concept needs more explanation
* lecturer references a technology without explaining it
* an important technical claim should be verified
* a concept is particularly useful for interview preparation
* official documentation provides helpful context

Do NOT perform external research simply to make the notes longer.

---

# 22. External Research Source Priority

Prefer: (1) official documentation, (2) original papers/specifications, (3) authoritative
engineering documentation, (4) reputable engineering blogs, (5) high-quality educational resources,
(6) community sources only where practical experience is specifically useful.

Avoid low-quality SEO content.

---

# 23. Clearly Label External Knowledge

Never mix external information invisibly into lecture content. Use `> **External clarification:**`
or `> **Further context:**`.

```markdown
The lecturer uses Kafka to distribute events to downstream consumers.

> **External clarification:** Kafka consumer groups allow multiple consumers to divide partitions
> among themselves, enabling parallel processing while maintaining partition-level ordering.
```

This tells the reader what the lecturer taught, and what was added to improve understanding.

---

# 24. External Research Must Be Surgical

Do NOT turn every mentioned technology into a tutorial.

Lecturer mentions Kafka. **BAD:** add three pages explaining Kafka architecture. **GOOD:** add 2–5
bullets explaining the specific Kafka concept necessary to understand the lecturer's design.

External enrichment should improve comprehension without overwhelming the original lecture.

---

# 25. Verify Questionable Claims

If something in the lecture seems technically questionable, do not silently replace it. Write:

> **Lecture:** The lecturer states that ...

Then, if verification is useful:

> **Verification note:** According to [authoritative source], ...

Preserve the distinction.

---

# 26. Generate Rich Study Notes

Create `study-notes.md`. Write in your own words. **Do NOT merely reformat the transcript.**

Use concise bullets, nested bullets where necessary, diagrams, screenshots, Mermaid, formulas,
tables, code blocks, examples, external clarification boxes.

Avoid unnecessary prose.

---

# 27. Bold Key Terms

Bold important technical concepts on first meaningful use.

* The **Matching Engine** processes compatible orders.
* The **Order Book** stores outstanding orders.

Avoid excessive bold formatting.

---

# 28. Preserve WHY

Whenever the lecturer explains why a design decision works or why an alternative was rejected,
preserve that reasoning.

Do not reduce *"We serialize operations because two concurrent operations could produce inconsistent
matching..."* into *"Use serialized operations."*

Capture: decision, motivation, problem it solves, relevant trade-off.

This reasoning is especially important for system-design interviews.

---

# 29. Preserve Examples

If the lecturer gives a worked example, retain it. Examples may involve order matching, prices,
quantities, throughput, latency, storage, partitioning, APIs, database records.

Rewrite examples clearly while preserving the lecturer's logic and values.

---

# 30. Preserve Formulas

Keep formulas and calculations. Use clean notation.

```text
Estimated throughput = requests per day / 86,400
```

Only include formulas actually discussed by the lecturer.

---

# 31. Preserve Trade-offs

Capture trade-offs (Option A vs Option B) and explain why the lecturer prefers one. Use a table when
useful:

| Approach | Advantage | Disadvantage | Lecturer's reasoning |
| -------- | --------- | ------------ | -------------------- |

Only include trade-offs actually discussed, or clearly label externally added analysis.

---

# 32. Interview-Relevant Insights

When something is particularly useful for system-design interviews, mark it
`> **Interview insight:** ...`. **Use this sparingly.**

This can include important trade-offs, assumptions worth stating, subtle consistency problems,
scaling decisions, failure scenarios.

If the insight is your inference rather than something explicitly stated by the lecturer, say so.

---

# 33. Transcription Uncertainties

Record uncertain terminology, unintelligible speech, ambiguous technical phrases, and places where
captions and audio disagree — **in the correction log at the foot of
`transcript/transcript-clean.txt`**, with timestamps and the evidence that settled each one.

This does **not** belong in `study-notes.md` as a section. A table of every divergence is an audit
artifact, not revision material. Raise a disagreement in the notes only when it changes a fact the
reader would rely on, and then **inline, where that fact is used**.

---

# 34. Visual Uncertainties

Where a visual is ambiguous **in a way that changes what the reader should conclude**, say so at the
point of use: a formula that could read two ways, a diagram that contradicts the narration, a
reconstruction that may be wrong, a figure assembled from several frames.

Do **not** list every label that was hard to read, and never describe layout. If the ambiguity does
not change a conclusion, it is not worth the reader's attention. For recreated diagrams the same
rule applies to the fidelity note (§18): keep it only if it changes how the diagram should be
trusted.

---

# 35. Key Takeaways

End with `# Key takeaways`. Provide **5–8** of the most important lessons. Each should be useful for
later revision. Avoid generic filler.

---

# 36. Things Worth Revisiting

Add `# Things worth revisiting`. Include concepts that are technically subtle, easy to forget,
particularly interview-relevant, insufficiently explained, unclear in audio/video, or dependent on
prerequisite knowledge.

Keep it concise.

---

# 37. External Research References

Add `# External references`. List only sources actually used for enrichment. For each source
include: source name, URL, what it was used to clarify.

Do not create a giant bibliography of unused sources.

---

# 38. Cost / Efficiency Rules

Be computationally and token efficient. Do NOT send the entire video frame-by-frame to a multimodal
model. Instead:

```text
Video → Local scene detection → Candidate frames → Local duplicate removal
      → High-value frame selection → Multimodal analysis

Audio → Local Whisper → Transcript → LLM analysis
```

Use local processing whenever practical for: audio extraction, transcription, scene detection, frame
extraction, perceptual hashing, duplicate detection, resizing.

Reserve expensive LLM/multimodal analysis for information requiring reasoning.

---

# 39. Avoid Excessive Image Analysis

If 500 candidate frames are extracted, do NOT send all 500 to the model. Use local filtering first.

Reduce them to a manageable set of genuinely meaningful frames. For a typical technical lecture,
something like **10–40 high-value visual frames** may be reasonable depending on length and visual
density. This is guidance, not a hard limit.

---

# 40. Final Quality Check

**Source:** actual YouTube video obtained · actual audio obtained · captions checked · video
duration verified

**Transcript:** complete lecture processed · timestamped transcript created · technical terminology
cleaned · uncertain terms flagged

**Visuals:** complete video considered · scene changes analyzed · duplicate frames removed ·
important diagrams captured · important code/slides captured · images associated with transcript
timestamps · useful images embedded in notes

**Diagrams:** important diagrams recreated where useful · recreations faithfully match lecturer ·
no invented architecture

**Notes:** follow lecturer's actual flow · concepts clearly explained · WHY reasoning preserved ·
examples preserved · formulas preserved · trade-offs preserved

**External research:** used only where beneficial · clearly separated from lecture material ·
high-quality sources preferred · no unnecessary tutorials added · sources recorded

**Final sections:** 5–8 key takeaways · things worth revisiting · external references
(transcription uncertainties live in the correction log per §33; visual ambiguities appear inline
per §34)

**Voice:** notes read as notes, not as narration of a video — no stage direction, no production
metadata, no accessibility captions, no timestamps outside section headings (`NOTES-VOICE.md`)

---

# 41. Final Status Report

```text
VIDEO
Download: success / failed
Duration:
Resolution:
File size:

TRANSCRIPTION
Source: manual captions / auto captions / Whisper
Model:
Complete: yes / no
Uncertainties:

VISUAL ANALYSIS
Candidate frames:
Frames after deduplication:
Frames used in notes:
Diagrams recreated:

EXTERNAL RESEARCH
Research performed: yes / no
Number of external sources:
Topics enriched:

OUTPUT
study-notes.md: success / failed
transcript: success / failed
images: success / failed
diagrams: success / failed
```

If any critical stage fails, clearly explain the failure. **Never fabricate successful processing.**

---

# Final Principle

The final document should optimize for:

**faithfulness + understanding + technical depth + visual learning + interview revision**

not simply brevity.

The lecture remains the primary source. External knowledge exists to make difficult concepts easier
to understand — never to silently rewrite what the lecturer taught.

---

# Changelog

| § | Was | Now | Why |
|---|---|---|---|
| **16** | Example showed a `### What the diagram shows` heading with bullets | Extract what the image *asserts*; explicit BAD example | The heading was copied literally and filled with colour/shape descriptions — 24 of them in one run, each duplicating content stated properly later |
| **33** | `# Transcription uncertainties` section in the notes | Correction log in `transcript/transcript-clean.txt`; inline only when it changes a fact | A table of every Whisper/caption divergence is an audit artifact; it never gets read during revision |
| **34** | `# Visual uncertainties` section listing unreadable labels | Only ambiguities that change a conclusion, at the point of use | "This label was hard to read" changes nothing; "the slide contradicts the narration" changes everything |
| **40** | Final-sections checklist named §33/§34 sections | Updated to match; added a voice line | Kept the checklist consistent with the above |

Unchanged: every substance requirement — the three source layers, WHY preservation, worked examples,
formulas, trade-offs, external labelling and verification, and the §41 status report.
