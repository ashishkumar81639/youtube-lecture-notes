---
name: youtube-lecture-notes
description: |
  Turn a YouTube technical lecture into rich multimodal study notes that combine spoken content, on-screen diagrams/slides/code, and clearly-labelled external research. Downloads the video, transcribes locally with Whisper large-v3, extracts and triages the visuals, recreates important diagrams, and writes an audited study-notes.md that preserves the lecturer's reasoning, examples and trade-offs. Use whenever the user gives a YouTube URL and asks for notes, a summary, a write-up, a study guide, or "process this lecture" — especially for system design, distributed systems, databases, ML, or any lecture where diagrams and code on screen matter as much as the audio.
metadata:
  version: "2.0.0"
  platform: "macOS / Apple Silicon (adaptable)"
---

# YouTube lecture → multimodal technical study notes

Produce notes that read like a strong engineer watched the whole lecture, captured the important
diagrams, understood the reasoning, and selectively researched the gaps.

Optimise for **faithfulness + understanding + technical depth + visual learning + interview
revision** — not brevity. The lecture is always the primary source.

## Files in this skill

| File | Read it when |
|---|---|
| **`reference/SPEC.md`** | **Read first, always.** The full 41-point specification — the definition of done. |
| **`reference/PLAYBOOK.md`** | **Read before running any command.** Exact commands, measured token economics, and the failure modes that cost an hour to discover. Keyed to the spec's section numbers. |
| **`reference/NOTES-VOICE.md`** | **Read before writing a single line of `study-notes.md`.** How the notes must READ — and `diagrams/recreated/*.md` too. SPEC says what must be true; this says how it reads. |
| `scripts/*.py` | Ready-to-run pipeline tooling (see below) |

---

## The transcript is the SPINE, not one layer of three

The three layers are not peers. The transcript is the artifact the pipeline invests most in — it is
**continuous** (covers every second), **timestamped**, **reconciled from two independent sources**
(Whisper + captions), **corrected with an auditable log**, and **checked for hallucination**. Nothing
else in the pipeline is verified that heavily.

So treat it as the narrative spine:

```
TRANSCRIPT   continuous, most-verified          → the backbone of the notes
FRAMES       point evidence attached to it      → detail the spine cannot carry
EXTERNAL     confirmation only                  → never supplies, only corroborates
```

Practical consequences:

- **Extract at the transcript's timestamps, not only where pixels changed.** Run
  `transcript_frames.py` — on the reference video 3 of 5 "look at this" moments had **no**
  pixel-selected frame near them. `refine_frames.py` now reports these as POINTER HOLES.
- **Never read a frame without its speech context.** Pass `--transcript` to `contact_sheets.py` so
  every tile carries what was being said. Triage decisions made blind throw away the most-verified
  artifact you have. (The order-book frame is ambiguous alone; its caption — *"node is simply
  unlinked by updating the next and previous pointers"* — resolves it instantly.)
- **When a visual is unclear, the transcript at that timestamp outranks external knowledge.** It is
  primary source; the external is not.
- **When the transcript itself is flagged uncertain at a timestamp, treat any frame reading there as
  weaker too.** Uncertainty propagates.

## The rule that governs everything

Three knowledge layers, **never blurred**:

| Layer | Source | How it appears |
|---|---|---|
| **1 — Speech** | captions, transcription | plain text |
| **2 — Visuals** | diagrams, slides, code, schemas, tables, whiteboard, terminal, UI | embedded image + its extracted *content* (labels, formulas, the claim it makes) — never a layout caption, see `NOTES-VOICE.md` |
| **3 — External** | docs, specs, papers | a labelled blockquote — the sanctioned set is `EXT_LABELS` in `verify_notes.py`, listed in `NOTES-VOICE.md`. An unlisted label silently loses its quote exemption |

**Never make externally researched information look like something the lecturer said.** A reader
must be able to tell at a glance which layer any sentence came from.

Also: `> **Interview insight:**` — sparingly, and say when it's your inference rather than the
lecturer's claim.

---

## Pipeline — text FIRST, then pixels

```text
captions (arrive in seconds)
   └─► transcript_signals.py ─► ad spans · visual pointers · section hints
                                          │
                                          ▼  guides everything below
video ─► dense sample ─► pHash dedup ─► refine_frames.py ─► contact sheets ─► few full-res reads
                                       (settle · plateau · cluster · exclude)

audio ─► Whisper large-v3 ─► cross-check vs captions ─► slides break ties ─► clean transcript
```

**Order matters.** Reading the transcript costs ~6k tokens; the visual pass it optimises costs
~34k. Text is ~5× cheaper than the images it improves, so mine it first — it tells you where the
ads are, where the sections break, and which timestamps the lecturer points at. Getting this
backwards means paying to look at sponsor segments.

Everything else is local except the contact sheets and a handful of full-res frame reads.

**Run the bootstrap first. It is idempotent — run it before every lecture.**

```bash
source ~/.claude/skills/youtube-lecture-notes/scripts/bootstrap.sh   # exports $VENV and $PY
```

It checks for `ffmpeg`/`ffprobe`, creates ONE shared venv at `~/.cache/youtube-lecture-notes/venv`
(override with `YLN_VENV`), installs the yt-dlp **nightly** (the stable build 403s on YouTube's
SABR-only URLs), and on Apple Silicon adds `mlx-whisper` plus Apple Vision OCR. On other platforms
it says plainly what is unavailable instead of failing silently.

The venv is ~1.3 GB — larger than every artifact a lecture produces — so it is shared, never
per-project. `pyobjc-framework-Vision` matters: without it `verify_notes.py` silently skips Layer 2
and prints `OCR unavailable`, a check you believe is running when it is not.

```bash
SK=~/.claude/skills/youtube-lecture-notes/scripts

# 0a. HAVE WE SEEN THIS CHANNEL BEFORE?  exit 0 = known (use its tier+params),
#     exit 2 = new (run discovery, then record the result at the end)
$PY $SK/channel_profile.py --url URL --lookup

# 0b. PROBE BEFORE EXTRACTING ANYTHING - 2.3s, constant regardless of length.
#     Deciding the tier after a full decode wastes 7 min on a 6-hour video.
$PY $SK/probe_video.py source/lecture.mp4 --json /tmp/probe.json

# 0c. LONG VIDEO (>~45 min)? Split it. State goes on disk so context can be cleared.
$PY $SK/chunk_plan.py /tmp/captions.txt --duration <sec> --target 25 \
    --sections /tmp/sig.json --out chunks/manifest.json
#     Then process each chunk independently, writing chunks/NN/notes-part.md +
#     carry-forward.md. Merge at the end WITHOUT re-reading the fragments.

# 1. metadata + captions (download captions EVEN IF using Whisper — they're the cross-check)
yt-dlp --list-subs --skip-download URL
yt-dlp --skip-download --write-auto-subs --sub-langs "en.*" --sub-format vtt -o "source/lecture.%(ext)s" URL
$PY $SK/vtt_to_text.py source/lecture.en.vtt -o /tmp/captions.txt

# 2. video at 1080p — see PLAYBOOK §5, expect HTTP 403 and ALWAYS verify resolution afterwards
$VENV/bin/pip install -q --upgrade --pre "yt-dlp[default,curl-cffi]"
$VENV/bin/yt-dlp --no-cache-dir -f "bestvideo[height<=1080]+bestaudio" \
    --merge-output-format mp4 -o "source/lecture.%(ext)s" URL
ffprobe -v error -show_entries stream=codec_name,width,height -of default=nw=1 source/lecture.mp4
ffmpeg -y -v error -i source/lecture.mp4 -vn -ac 1 -ar 16000 -c:a pcm_s16le source/lecture-audio.wav

# 3. transcribe IN THE BACKGROUND (~half the audio duration on M3), do frames meanwhile
$PY $SK/transcribe.py source/lecture-audio.wav --outdir transcript --json /tmp/w.json

# 3b. MINE THE TRANSCRIPT FIRST - ad spans, visual pointers, sections
#     You are the LLM. Read the digest, write the JSON yourself. No API key,
#     no second call - you are reading this transcript anyway to write the notes.
$PY $SK/transcript_signals.py /tmp/captions.txt        # prints digest + schema
#     ...write /tmp/sig.json, then have it checked:
$PY $SK/transcript_signals.py /tmp/captions.txt --validate /tmp/sig.json
#   --mode api    = standalone Claude call, ONLY for headless/cron use
#   --mode regex  = offline fallback, CANDIDATES only

# 4. frames: ONE ffmpeg pass, then PROFILE (skip if the channel was already known)
ffmpeg -y -v error -i source/lecture.mp4 -vf "fps=1/2,scale=640:-1" -q:v 4 frames/raw/f%04d.jpg
$PY $SK/profile_video.py frames/raw
#   -> prints a TIER (0-3) with the exact commands for it. ~20s.
#   tier 1 also: $PY $SK/deocclude.py frames/raw --at <seconds>

# 4z. RECORD what you learned, so the next video from this channel skips discovery
$PY $SK/channel_profile.py --url URL --record --tier N --params "..." \
    --still .. --cuts-min .. --median .. --camera static|moving --note "..."
$PY $SK/refine_frames.py frames/raw --out /tmp/ref.json \
    --signals /tmp/sig.json --exclude 01:00-01:44,21:53-22:22
$PY $SK/contact_sheets.py /tmp/ref.json /tmp/sheets --cols 4 --rows 5 \
    --transcript transcript/transcript-clean.txt        # ALWAYS pass this
#   -> READ THE SHEETS, pick timestamps, re-extract those at full res with `-ss` before `-i`
#   (dedupe_frames.py is the simpler first-pass-only path; refine_frames.py supersedes it)

# 5. reconcile transcript sources, then resolve each divergence using the slides
$PY $SK/compare_sources.py transcript/transcript-timestamped.txt /tmp/captions.txt

# 5b. REGRESSION TEST after changing any refine_frames threshold or statistic
$PY $SK/verify_coverage.py frames/selected /tmp/ref.json source/lecture.mp4
$PY ~/.claude/skills/youtube-lecture-notes/tests/run_regression.py \
    --video source/lecture.mp4 --frames frames/raw --truth frames/selected

# 5b2. TRANSCRIPT GATES - run before anything downstream trusts it
$PY $SK/audit_transcript.py --segments /tmp/w.json          # hallucination
$PY $SK/audit_transcript.py --raw transcript/transcript-timestamped.txt \
    --clean transcript/transcript-clean.txt                               # every substitution

# 5c. ACCURACY GATE - every number must trace to a layer. Run before declaring done.
$PY $SK/verify_notes.py study-notes.md transcript/transcript-clean.txt \
    --frames frames/selected

# 5d. VOICE GATE - are these notes about the SUBJECT, or about a video? Must exit 0.
$PY $SK/voice_lint.py study-notes.md diagrams/recreated/*.md

# 5e. CLEAN UP - drop the regenerable frame dirs. Refuses to run before selection
#      is finished and the notes reference the selected frames.
$PY $SK/cleanup_artifacts.py .            # dry run first
$PY $SK/cleanup_artifacts.py . --apply

# 6. SPEC 13 - emit the frame -> transcript manifest once frames are named
#    NAME FRAMES BY THE TIMESTAMP YOU EXTRACTED AT, not when the slide first appeared
$PY $SK/frame_manifest.py frames/selected transcript/transcript-clean.txt \
    -o frames/selected/manifest.md
```

---

## The seven things that go wrong by default

Full detail in `PLAYBOOK.md`. These are the ones that silently ruin a run:

1. **ffmpeg scene detection is useless for animated slide decks.** It found 32 hard cuts in a 22-min
   deck because slides build up bullet-by-bullet. Use it for slide *boundaries* only; select frames
   by chained perceptual hash against the last *kept* frame.

2. **"Download succeeded" does not mean you got HD.** YouTube's SABR experiment 403s DASH HD URLs;
   the `mweb` fallback cheerfully returns 360p and reports success. The yt-dlp **nightly** build is
   what actually works. Always `ffprobe` the result, and decode-test it — 1080p may be AV1.

3. **Capture the *final* state of each animated slide**, and treat animated transitions as
   **before/after pairs**. `refine_frames.py` does both automatically — it walks back to each
   slide's settled state, and keeps an earlier state only when the final frame has *less* content
   (something was removed). Distance alone cannot find these: one measured pair differed by just
   **20**, while ordinary build-up steps differ by more.

4. **Slides break transcript ties.** Whisper said "Arion", captions said "Aeron", the slide read
   `Aeron`. Cross-check Whisper against captions, then let the visual decide.

5. **Tile frames for triage.** Sending 669 raw frames ≈ 205k tokens, or 1.23M at 1080p; tiled
   triage plus a few full-res reads ≈ 34k. Use `--cols 4` — measured optimum.

6. **Notes written without `NOTES-VOICE.md` come out as narration of a video.** Measured on a real
   run: 24 "What the diagram shows" accessibility captions, 21 stage directions, 13 mentions of
   Whisper/1080p/captions, and the same content stated twice — once as a description of coloured
   shapes, once as actual teaching. Read `reference/NOTES-VOICE.md` before Phase D and run
   `voice_lint.py` after it.

7. **Mine the transcript before touching a single frame.** It is ~5× cheaper than the visual pass
   and tells you what to skip. Getting the order backwards was the biggest structural mistake in
   the first run. Do the judgement yourself in `prep`/`--validate` mode — keyword matching flagged
   *"every **subscribed** client's port"* as a sponsor read, and missed 21s of promo containing no
   keyword at all.

---

## Non-slide-deck videos: escalate, never degrade silently

`profile_video.py` measures the video and picks a tier. **Never skip a tier to save tokens — a
cheap run that misses the diagrams is worth less than an expensive one that doesn't.**

| Tier | When | Method | Cost (22 min) |
|---|---|---|---|
| **0** | still ≥45%, clear cuts | hash triage + contact sheets | ~34k tok |
| **1** | occluded but camera static, **or additive canvas** | + `deocclude.py` / transcript milestones | ~34k + local compute |
| **2** | moving camera / constant churn | **transcript-driven** timestamps + 30s sweep | ~1.5–2× tier 0 |
| **3** | anything else, or tier 2 looks thin | uniform 15–20s sweep, review every sheet | ~2–3× tier 0 |

Measured: TechPrep slide deck → **tier 0** (74% still). MIT blackboard → **tier 2** (5% still,
camera pans). Live coding → **tier 2** (12% still, webcam bottom-right). Krish Naik iPad +
Apple Pencil → **tier 1 additive canvas** (`corr(ink,time)=+0.93`, webcam top-right).

**Handwriting:** local OCR is useless on it (measured). Escalate to frontier vision and accept the
tokens — it reads it perfectly. Do not retry local OCR there.

## When a visual is unclear — triangulate, never guess

Resolve in order: **internal consistency** (another part of the same frame) → **adjacent frames** →
**transcript at that timestamp** → **topic context** → **external canonical form** → **flag it**.

> **External knowledge may CONFIRM a reading. It may never SUPPLY one.** If external is the only
> evidence, it is a guess wearing a citation.

Record both what is written and the correction, never just the corrected version — see
`PLAYBOOK.md` for the worked AdaBoost example.

Generality by layer:

| Layer | Generality |
|---|---|
| Download · audio · transcription · captions · tiling · manifest · notes structure | **Fully general** |
| Whisper `--glossary` | **Swap per domain** — the default is system-design vocabulary and will mislead the decoder on other subjects |
| `refine_frames.py` thresholds | **Tuned on a slide deck** — profile first |

## Writing the notes — the order matters

The steps above produce *artifacts*. This is how to turn them into notes, and the sequence is not
arbitrary.

**Phase A — transcript COMPLETE first.** Not partially, not in parallel with writing. It is the
spine: it gives the section structure that becomes the outline, the ad spans, the pointer
timestamps, and the vocabulary. You cannot tell what a diagram *means* without knowing what was
being said over it. Gate it with `audit_transcript.py` before anything downstream trusts it.

**Phase B — select frames, guided by that transcript.** Pixel change alone proposes the wrong set:
measured, 3 of 5 "look at this" moments had no pixel-selected frame. Run `refine_frames.py
--signals` and `transcript_frames.py`, and fill any POINTER HOLES.

**Phase C — the visual-only pass.** ← *systematically, not by noticing*

```bash
$PY $SK/visual_only.py frames/selected transcript/transcript-clean.txt
```

Lists every on-screen term never spoken anywhere. On the reference lecture: 111 terms, including
`ITCH for NASDAQ`, `Mechanical Sympathy`, and every edge annotation on the architecture slide. In
the first run these were found by *happening to notice them* — which does not repeat. Do this pass
before writing, and mark the results as visual-only in the notes.

**Phase D — write section by section, with that section's frames present.** **Read
`reference/NOTES-VOICE.md` first — it governs how every sentence reads.** Not prose first and
images bolted on afterwards; that produces exactly the screenshot dump SPEC §16 forbids. For each
section: the transcript carries the argument, the frames carry what speech cannot (figures,
formulas, labels, code, tables), and external clarifies only where genuinely needed.

**Phase E — verify.** `verify_notes.py` (every number traces to a layer), `verify_coverage.py`, and
`voice_lint.py` over **`study-notes.md` AND `diagrams/recreated/*.md`** (recreations are
notes too). All three must pass. Then `cleanup_artifacts.py --apply` — ship the 26 frames that are
used, not the 3,600 that were considered.

## Output

> **`reference/NOTES-VOICE.md` governs everything below.** The notes are for a reader revising the
> material, not reconstructing the video. No production metadata, no stage direction, no three-layer
> preamble, no timestamps except on section headings. Read it before writing.

Follow the **lecturer's own flow** — if there's an agenda slide, that agenda is your outline. Never
force a predetermined system-design template.

Preserve, always: **WHY** (decision + motivation + problem solved + trade-off), rejected
alternatives and why, worked examples with the lecturer's actual values, formulas as discussed,
and trade-off tables.

Hunt for **visual-only content** — anything on screen that is never spoken. That's pure Layer-2
value a transcript-only workflow loses entirely. Write each find as a **fact**, not as a remark about
the medium — unless the slide/narration *discrepancy* is itself the point.

Closing sections, and where uncertainty goes, are defined in **SPEC §33–§37** — read them there.
In short: the notes end with **Key takeaways · Things worth revisiting · External references**;
transcription disagreements live in the correction log; visual ambiguity appears inline where it
changes a conclusion.

The **§41 status report** and the 2–4 findings a reader would not get from reading the notes
linearly (a slide contradicting the narration, slide-only items, claims you could not verify) go
**to the user in chat — never into `study-notes.md`.**

**Never fabricate successful processing.** If a stage fails, say so and say why.

Before declaring done: every link resolves, and every saved artifact is referenced — **frames and
recreated diagrams both**. Commands in `PLAYBOOK.md`.
