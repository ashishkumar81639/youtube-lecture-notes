# Execution playbook

Operational knowledge from actually running `SPEC.md` end-to-end (22-min system-design lecture,
1080p, macOS/M3/16 GB). **Keyed to the spec's section numbers.** The spec says *what*; this says
*how*, and flags where the obvious approach fails.

Read this before starting. Several items below cost an hour to discover.

---

## §2 — Environment

```bash
for t in yt-dlp ffmpeg ffprobe python3 pip3; do
  printf "%-10s: " "$t"; command -v $t >/dev/null && ($t --version 2>&1|head -1) || echo MISSING
done
```

**Always build a venv, and build it ONCE — outside the project.** Homebrew Python is PEP 668
externally-managed, so bare `pip3 install` dies with `error: externally-managed-environment`.

Measured on a one-hour lecture: the venv is **1.3 GB**, against 148 MB of source and 16 MB of kept
frames. A per-project venv is by far the largest thing in the directory and is identical every time.

```bash
VENV=~/.cache/youtube-lecture-notes/venv
[ -d "$VENV" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --pre "yt-dlp[default,curl-cffi]" mlx-whisper pillow imagehash numpy \
    pyobjc-framework-Vision pyobjc-framework-Quartz
```

Breakdown of the 1.3 GB: torch 536 MB (an `mlx-whisper` dependency), mlx 196 MB, llvmlite 125 MB,
scipy 99 MB, sympy 76 MB. None of it is per-lecture state.

Do **not** install `tesseract`. Slides at 1080p are directly legible to a vision model; OCR was
never needed on a full run (see §14). **Do** install `pyobjc-framework-Vision` — `verify_notes.py`
uses it to check Layer 2, and without it that check silently no-ops with `OCR unavailable`.

| Gotcha | Reality |
|---|---|
| Bash tool **cwd persists across calls** | `mkdir -p x && cd x` then a later `cd x` fails — you are already inside it |
| No `timeout` on macOS | use `gtimeout` (coreutils) or drop it; `timeout ... ` silently becomes "command not found" for the whole chain |
| MLX process shows ~68 MB RSS | **not a stall.** Weights live in unified/GPU memory and don't appear in RSS |
| `imagehash` distances are numpy `int64` | `int()` before `json.dump` or it raises `TypeError: not JSON serializable` |

---

## §4 — Metadata and captions

```bash
yt-dlp --skip-download --print "TITLE: %(title)s" --print "DURATION: %(duration_string)s" \
       --print "CHANNEL: %(uploader)s" URL
yt-dlp --list-subs --skip-download URL     # header says "automatic captions" if no manual subs
```

**Download captions even when you intend to run Whisper.** They are not a fallback — they are the
independent second opinion that catches proper nouns (§9). This is the single highest-value cheap
step in the whole pipeline.

```bash
yt-dlp --skip-download --write-auto-subs --sub-langs "en.*" --sub-format vtt \
       -o "source/lecture.%(ext)s" URL
```

- YouTube auto-captions are now **punctuated and capitalised** — far better than expected.
- `en` and `en-orig` are often byte-identical; `cmp -s` them and keep one.
- VTT has **rolling repeats** (each cue repeats the previous line). Dedupe on exact line text when
  converting, or the transcript triples in size. Use `scripts/vtt_to_text.py`.

---

## §5 — Download (expect a fight)

**YouTube's SABR-only experiment makes every DASH HD URL return `HTTP 403`.** All of these failed on
a real run: default client, `web_safari`, `tv`, `ios`, `android_vr`, `--impersonate chrome`, and even
a bgutil-generated PO token. Escalate in order, stop at first success:

```bash
# 1. plain
yt-dlp -f "bestvideo[height<=1080]+bestaudio" --merge-output-format mp4 -o "source/lecture.%(ext)s" URL

# 2. alternate clients
yt-dlp --extractor-args "youtube:player_client=web_safari,tv,ios" -f ... URL

# 3. impersonation (needs curl-cffi in the venv)
yt-dlp --impersonate chrome -f ... URL

# 4. >>> THE ONE THAT WORKED <<<  nightly build
$VENV/bin/pip install -q --upgrade --pre "yt-dlp[default,curl-cffi]"
$VENV/bin/yt-dlp --no-cache-dir -f "bestvideo[height<=1080]+bestaudio" \
    --merge-output-format mp4 -o "source/lecture.%(ext)s" URL

# 5. last resort: Brainicism/bgutil-ytdlp-pot-provider (needs node)
```

**The `mweb` trap.** `--extractor-args "youtube:player_client=mweb"` downloads successfully and
reports success — but only offers **format 18 (640x360)**. Unusable for reading diagrams. Never
trust "download succeeded"; always verify the resolution:

```bash
ffprobe -v error -show_entries format=duration,size \
        -show_entries stream=codec_type,codec_name,width,height -of default=nw=1 source/lecture.mp4
ffmpeg -v error -ss 300 -i source/lecture.mp4 -frames:v 1 -f null - && echo "decode OK"
```

The 1080p stream may be **AV1 + Opus**, not H.264/AAC. Run the decode test before building the rest
of the pipeline on it. (1080p for 22 min was only 35 MB — size is rarely the constraint.)

```bash
ffmpeg -y -v error -i source/lecture.mp4 -vn -ac 1 -ar 16000 -c:a pcm_s16le source/lecture-audio.wav
```

---

## §6–§7 — Transcription

**On Apple Silicon use `mlx-whisper`, not `faster-whisper`.** faster-whisper (CTranslate2) is
CPU-only on macOS. `mlx-whisper` is Metal-accelerated and `large-v3` sits comfortably in 16 GB.

```bash
$VENV/bin/pip install -q mlx-whisper   # model: mlx-community/whisper-large-v3-mlx
```

Timings on M3 / 22-min audio: **~2 min** one-off model download (2.9 GB) + **~12 min** transcription
(≈ half the audio duration). Budget accordingly and **run it in the background** — do the entire
frame pipeline (§11) while it works.

```python
res = mlx_whisper.transcribe(
    "source/lecture-audio.wav",
    path_or_hf_repo="mlx-community/whisper-large-v3-mlx",
    language="en",
    temperature=0.0,
    condition_on_previous_text=False,   # prevents hallucination loops on repetitive slide text
    word_timestamps=False,              # segment-level is enough; word-level is much slower
    initial_prompt="<DOMAIN GLOSSARY>",
)
```

**Always pass a domain `initial_prompt`.** Seed with terms you expect on screen. It measurably
improves proper-noun accuracy. Use `scripts/transcribe.py`, which has a system-design glossary
built in and a `--glossary` override.

**Strategy that worked:** Whisper as *primary*, captions as *cross-check*, **slides as tiebreaker**.
The spec's preference order (§6) puts captions first, but for technical terminology a local
large-v3 pass plus reconciliation beats either source alone.

---

## §8–§9 — Cleaning, and the tiebreaker rule

> **When Whisper and the captions disagree on a technical term, the on-screen slide decides.**

This is the most valuable thing learned on the whole run. Real cases:

| Whisper heard | Captions heard | Slide showed | Resolution |
|---|---|---|---|
| "Arion", "Arianne", "area cluster" | "Aeron" | **`Aeron`** | Aeron |
| "SPE" | "SBE" | **`Simple Binary Encoding (SBE)`** | SBE |
| "pulls the network interface card" | "polls the..." | — | **polls** (DPDK = poll-mode drivers) |
| "CPU cache and validation" | "cache invalidation" | — | **invalidation** |
| "custom training application" | "trading" | — | **trading** |
| "150 dollars and one cent" | — | **`Price Level $150.01 Ask`** | $150.01 |
| "a **trade** execution" | "a **a** execution" (stutter) | **`Trade Execution`** edge label | trade execution |

Method: bucket both sources into 30-s windows, diff the word sets, inspect only the divergences.
`scripts/compare_sources.py` does this.

Rules that matter:
- Keep a **correction log** at the bottom of `transcript-clean.txt`: pattern → replacement →
  **evidence** → timestamps. Evidence is what makes the notes auditable.
- A mid-sentence **self-correction by the lecturer is not an error** — leave it verbatim and note it.
- Where captions and audio genuinely disagree and no slide settles it, **flag rather than resolve**
  (e.g. "zero latency *pauses*" vs "*pulses*" — kept "pauses" since the topic is GC, flagged anyway).
- **Substring trap:** `grep -c itch` matches every `switch`. Word-boundary your term counts.

---

## §10–§11 — Frame extraction: the part that fails by default

> **ffmpeg scene detection is near-useless for slide decks that animate.**
> `select='gt(scene,0.06)'` found only **32 hard cuts in 22 minutes** — because the deck builds up
> bullet-by-bullet and box-by-box. Whole 90-second stretches of a diagram being drawn registered as
> a single "scene".

Use dense sampling + perceptual hashing instead. Still run scene detection first, but only to
*locate slide boundaries* (useful for §12), never as the frame selector.

```bash
# ONE invocation, ONE decode pass. 640px because these are only ever hashed, never read.
ffmpeg -y -v error -i source/lecture.mp4 -vf "fps=1/2,scale=640:-1" -q:v 4 frames/raw/f%04d.jpg
#   -> 669 frames, 11 MB, ~15 s

$PY scripts/dedupe_frames.py frames/raw --interval 2 --threshold 22 --json kept.json
#   -> 669 -> 110 candidates
```

**Critical detail:** hash distance must be chained against the **last *kept* frame**, not the
previous frame. Against the previous frame, a slowly-building slide never accumulates enough delta
to trip the threshold. Combined pHash + dHash at `hash_size=16` (256-bit), threshold ≈ 22.

---

## §12–§13 — Triage via contact sheets, then targeted re-extraction

Read **tiled sheets**, not individual frames:

```bash
$PY scripts/contact_sheets.py kept.json ./sheets --cols 4 --rows 5   # 110 -> 6 sheets
```

The sheets do two jobs. Obvious one: cheap triage. Non-obvious one: **they reveal which slides are
animated builds**, which tells you the single timestamp per slide worth a full-resolution look. That
insight is what collapsed 110 candidates to 9 full-res reads.

**Capture the FINAL state of each animated slide** — sample a few seconds *before* the next hard cut
(from the scene-detection list), not when the slide first appears:

```bash
for t in 03:28 05:42 08:12 12:10; do n=${t//:/-}
  ffmpeg -y -v error -ss $t -i source/lecture.mp4 -frames:v 1 -q:v 2 "frames/selected/$n.png"
done
```

`-ss` **before** `-i` is input seeking — jumps to the nearest keyframe, ~0.2 s per call regardless
of position.

**Animated transitions need before/after pairs.** A slide animating a linked-list node being
unlinked is two frames; either alone loses the entire point. Real case: order-book cancel at
`12:20` (A⇄B⇄C, hash 101/102/103) and `13:30` (A⇄C, hash 101/103) — same slide, two states.

**Skip sponsor/product-promo segments entirely.** ~25 s of the run was the presenter's own app UI.
Zero study value; excluded from `frames/selected/`.

Name files **after** triage, from understood content: `12-20-order-book-price-level-before-cancel.png`.
You cannot name descriptively before you know what the frame shows — so naming is a post-triage step.

---

## §10–§13 — Transcript-guided frame selection (added after run 1)

**Run 1 got the ordering wrong.** Frame extraction ran while Whisper was still going, so the
transcript was never wired into frame selection at all — the two tracks were treated as independent
pipelines that merge only when writing. That was an unexamined assumption, not a decision. Captions
arrive in **seconds**; there was no reason to wait.

### Do the judgement in-loop — do NOT call the API from the script

**Inside Claude Code the agent IS the LLM, and it is already reading this transcript to write the
notes.** A script that makes its own API call means a second charge, a second set of credentials,
and a model with *less* context than the agent about to consume the result. Default `--mode prep`
prints a compact digest plus the schema; the agent writes the JSON; `--validate` checks it. No API
key involved.

```bash
python scripts/transcript_signals.py /tmp/captions.txt                  # digest + schema
#   ...agent writes /tmp/sig.json...
python scripts/transcript_signals.py /tmp/captions.txt --validate /tmp/sig.json
```

Three signals come back:

| Signal | Use |
|---|---|
| `ad_spans` | spans to exclude from frame extraction entirely |
| `visual_pointers` | "as you can see", "we've got our sequencer here" → boost frames nearby |
| `sections` | the lecture's own structure → the notes outline |

`--mode api` exists only for headless runs (cron, CI, no agent present): `claude-opus-5`, adaptive
thinking, `effort=high`, Pydantic `output_format` so malformed JSON cannot reach the pipeline.

### Why not regex (`--mode regex`, offline fallback only)

Keyword matching was tried first and fails in **both** directions:

- **False positives.** A bare `subscribe` pattern flagged *"instantly copies it to every
  **subscribed** client's port"* — core multicast content — as a sponsor read. Two of four spans
  were wrong until the pattern was word-bounded.
- **Under-reach.** The promo ran to **01:44**; the last keyword hit was **01:21**. Regex finds the
  trigger phrase, not the segment boundary. Those 23s contained no keyword at all, so no pattern
  tuning would ever have caught them.

Judging intent and span boundaries is exactly what regex cannot do.

### Always run `--validate`

It cross-checks spans against the transcript: reversed ranges, spans past the end, suspiciously long
spans, and total ad coverage above 25% of runtime.

It earned its place on the first real run by flagging an ad span as *"past end of lecture (17:25)"*
for a 22:19 video. The JSON was fine — the **parser** was wrong. `transcript-clean.txt` carries a
correction-log appendix that quotes its own `[HH:MM:SS]` timestamps, and naive parsing swallowed
them, so "end of lecture" became the last line of the appendix. Fixed by taking only the
**monotonic prefix**: real transcript timestamps only increase, so a large backwards jump means the
body has ended. Any transcript file with an appendix hits this.

Section hints were the strongest signal on a narrated deck (17 hits, all genuine boundaries).
Deixis was sparse (7) — expect the reverse on a whiteboard talk.

---

## §11–§12 — The refinement pass (`refine_frames.py`)

The first-pass chained dedup is necessary but not sufficient. Run it, then refine.

### Recurring templates — the chain's blind spot

Chained dedup compares each frame to the last **kept** frame, so a slide that *returns* is re-kept
every time. Run 1's agenda slide recurred **9 times** (`02:00, 03:32, 05:58, 09:14, 12:18, 14:02,
15:36, 20:18, 22:04`) and consumed 9 of 110 candidate slots.

Global clustering across the whole timeline collapses them to one — and the recurrence pattern
**hands you the deck's section boundaries for free**.

> **Clustering must require a time gap.** Only recurring templates are far apart; frames close
> together are distinct states of the *same* slide. Without a `--recur-span` guard, clustering
> silently re-merges the before/after pair described below (they differ by only 20, under any usable
> cluster threshold). This bug appeared and was fixed during development — do not remove the guard.

### Plateaus, not distances

To find a slide's final state, segment at hard cuts then locate **plateaus** — runs where the frame
stops changing. The last plateau is the settled final state, and walking back to it automatically
skips fade transitions.

To decide which *earlier* states are worth keeping, distance is the wrong signal. Measured on the
order-book cancel animation:

```
before-cancel vs after-cancel  =  20     <- below any usable threshold
plateau durations              =  88s then 8s   <- unmistakable
```

Ordinary build-up steps often differ by *more* than 20 while meaning less. Duration separates a
state the lecturer dwelled on from a transient build step.

### Additive vs destructive — the ink test

A slide gaining bullets needs only its final frame; the final already contains every earlier state.
A slide that *removes* something needs both. Distinguish them with a one-line "ink" measure
(fraction of lit pixels):

```
order book   0.0367 -> 0.0343   DOWN  content REMOVED    -> keep both frames
requirements 0.0356 -> 0.0493   UP    additive build     -> keep final only
API design   0.0177 -> 0.0563   UP    additive build     -> keep final only
```

Keep an earlier plateau only when ink **decreased**. This is what makes before/after pair detection
automatic rather than a manual eyeball.

### The final state must NOT be required to sit on a plateau

First implementation demanded a >=6s plateau for the final state too. That is wrong: a lecturer
routinely adds the last annotation and moves straight on, so the completed slide may be on screen
for only 2-4s. Requiring a plateau there silently falls back to an **earlier, less complete**
state.

Measured on the Complete Architecture slide, which kept building right up to the cut:

```
20:10  ink 0.0694   <- what the plateau rule returned (missing the last annotations)
20:12  ink 0.0724
20:16  ink 0.0747   <- the true final state, 2s before the hard cut
20:18  ink 0.0611   <- next slide
```

Correct rule: **final = the last frame of the segment**, walking back only past genuine fade-out
frames (ink collapsed below half the segment maximum). The plateau requirement stays where it
belongs - on *intermediate* states, where it is what separates a state the lecturer dwelled on from
a transient build step.

### Measured result, verified

```
run 1 (manual triage) : 669 -> 110 candidates -> 6 sheets -> 16 frames
run 2 (refined)       : 669 ->  32 candidates -> 2 sheets -> 16 frames
```

**3.4x less to triage, with 16/16 coverage verified** by `scripts/verify_coverage.py` - every frame
chosen by hand is present in the automatic set (15 at hash distance <= 4, most exactly 0; the last
at 13, confirmed pixel-identical by eye). These now fall out automatically: the 10x agenda collapse,
ad spans dropped, the order-book pair at `13:48` + `13:58`, and every key architecture frame.

### Measuring coverage: compare LIKE FOR LIKE

The first coverage test reported **11/16** and sent me hunting for bugs that did not exist. The
fault was the measurement: it hashed 640x360 JPEGs from `frames/raw` against 1920x1080 PNGs in
`frames/selected`. Resampling and codec differences alone produce distances of 13-34 between frames
that are **pixel-identical in content** - one such pair differed by a maximum of 25 grey levels with
*zero* pixels over a threshold of 30.

Re-extracting the candidates at full resolution through the same ffmpeg path gave the true answer:
**16/16**. Never compare perceptual hashes across resolutions or codecs. `verify_coverage.py` does
the re-extraction for you; run it after touching any threshold.

What still needs a human/LLM glance: intro title cards and logo stings. They are legitimately
low-value but structurally identical to real content, so no cheap signal catches them. Two contact
sheets is a cheap place to make that call — do not try to automate it.

---

## §13 — Emit the manifest (missed in run 1)

Run 1 satisfied §13 *implicitly* by placing each image beside its explanation, but never produced
the standalone artifact. That is a compliance gap: the association was inferable, not auditable.

```bash
python scripts/frame_manifest.py frames/selected transcript/transcript-clean.txt \
    -o frames/selected/manifest.md
```

Run it **after** frames are descriptively named — it reads timestamps from the filenames.

---

## Preflight for other video types

Run 1 was a static-camera screencast of a dark deck — near-ideal. Two adjustments for anything else:

```bash
# letterboxing or a persistent webcam inset dilutes every fingerprint with static pixels
ffmpeg -i source/lecture.mp4 -t 120 -vf cropdetect -f null - 2>&1 | tail -3
#   -> feed the reported crop=W:H:X:Y into the sampling filter chain
```

`--cut`, `--settle` and `--cluster` are tuned for slide decks. A whiteboard talk changes
continuously and has no hard cuts — expect to lower `--cut` substantially and lean on
`--min-plateau` instead. Neither has been validated on that video type yet.

---

## §14 — Visual understanding

**OCR was never needed.** At 1080p a vision model reads slide body text directly, and more
accurately than tesseract would. Only reach for OCR if a frame is genuinely degraded.

**Hunt for visual-only content** — things on screen that are *never spoken*. These are pure Layer-2
value and a transcript-only workflow loses them entirely. Real finds:
- `ITCH for NASDAQ` (API Design slide) — never said aloud
- `Mechanical Sympathy` (Deep Dive 4 bullet) — never said aloud
- every edge annotation on the final architecture slide (`Ring Buffer / LMAX Disruptor`,
  `SBE Binary Protocol`, `Async Write`, `In memory margin check`, ...)

Call these out explicitly in the notes as slide-only.

---

## §17–§18 — Recreation and fidelity

**When the slide and the narration disagree, reproduce both and flag it.** Do not silently pick one.

Real case: the slide drew `Primary Matching Engine → Hot Standby Replica`, but the lecturer said
secondaries *"consume the exact same sequencer log"*. Only the spoken version makes the failover
argument coherent. Resolution: the complete-architecture recreation kept the arrow the slide shows;
the failover recreation followed the **narration**; both files cross-reference the conflict,
and it is flagged at the point of use per SPEC §34 — a slide contradicting the narration is exactly
the kind of ambiguity that changes a conclusion.

Also expect **diagrams that differ between slides** — the final "Complete Architecture" slide
dropped a box (`Entire Market / Clients`) that the earlier HLD slide had. Note which slide a
recreation follows.

Where structure exists only in **speech** (e.g. the price-ladder array wrapping the one drawn price
level), reconstruct it but label it as reconstructed-from-narration.

---

## §19–§20 — Structure

**If the lecture has an agenda slide, that agenda IS your outline.** This one had a 10-item
"Process" slide that recurred between sections with completed items struck through — it gave both the
outline and clean section boundaries for free. Look for it early.

Read the complete transcript before writing any section. The captions arrive in seconds, so you can
understand the full arc while Whisper is still running.

---

## §38–§39 — Token economics (measured)

| Approach | Images to model | Est. tokens |
|---|---|---|
| **Contact sheets + targeted full-res reads** | **16** | **~34k** |
| Deduped frames sent individually @640px | 110 | ~34k — *same cost, 110 round-trips, no structure visible* |
| All raw frames @640px | 669 | ~205k |
| All raw frames @1080p | 669 | ~1.23M |

Estimates: `(w × h) / 750`, long edge capped at 1568 px.

**Use 4 columns, not 3.** Measured, not guessed. 3-col is more legible but needs ~66% more sheets,
and a sheet costs about the same as a full-res read — so 3-col only wins if it saves **>6** re-reads,
which it won't:

```
4-col:  6 sheets (14.8k) +  9 full-res (16.6k) = ~31.4k   <-- measured actual
3-col: 10 sheets (25.8k) +  6 full-res (11.1k) = ~36.9k
```

Final counts for a 22-min lecture: **669 sampled → 110 deduped → 16 model reads → 16 frames used**.
That lands inside the spec's 10–40 guidance (§39) without trying.

---

## §21–§25 — External research

Aim for **one authoritative source per genuinely-unexplained concept**; 9 sources for a 22-min
lecture felt right. Every fetch should answer a specific question you can name in advance.

What worked: verifying vendor claims against vendor docs (Aeron's Raft claim — confirmed), verifying
spec details (FIX MsgType D/F/8 — all three confirmed), and verifying that a described architecture
matches production reality (Nasdaq MoldUDP64 gap-fill — confirmed).

**Be honest about what you could NOT verify.** Two lecture figures had no documentary support —
DPDK's docs confirm poll-mode drivers but publish no "10–20 µs" number; Aeron's docs stress
*predictable* latency without a µs figure. Say so in the `Verification note` rather than implying
the source endorsed the number.

Log research in `research/external-research.md` as: why researched → source → findings → verdict →
where used. That file is the audit trail for Layer 3.

---

## §41 — Reporting

Fill the template exactly. Then add what the template can't capture: **the 2–4 findings a reader
would not get from reading the notes linearly.** For this run those were the slide/narration
conflict, the two slide-only items, the animated before/after pair, and the two unverifiable figures.

**Report failures plainly.** The 403 download saga belongs in the report — it changes what the user
should expect next time.

---

## Final check before declaring done

```bash
# every image and link in the notes actually resolves
grep -oE '\]\((frames|diagrams|research|transcript)/[^)]+\)' study-notes.md \
  | tr -d '])(' | sort -u | while read p; do [ -e "$p" ] || echo "MISSING: $p"; done

# every saved ARTIFACT is actually used (no orphans) - frames AND recreated diagrams.
# Checking only frames/ is not enough: a rewrite once dropped all four diagram links and
# nothing noticed, because the recreations were built, saved, and never referenced.
for d in frames/selected diagrams/recreated; do
  [ -d "$d" ] || continue
  ls "$d" | grep -v '^manifest' | while read f; do
    grep -q "$f" study-notes.md || echo "UNUSED: $d/$f"
  done
done
```

Both must come back empty.

---

## Generality: which video types this actually works on (measured)

Everything above was tuned on ONE video: a static-camera screencast of a dark slide deck. These are
measured profiles of contrasting types, taken with `scripts/profile_video.py` on 5-minute segments.

| Video type | still | hard cuts/min | median dist | DEFAULT params | with profiler params |
|---|---|---|---|---|---|
| **Slide deck** (tuned baseline) | **73.7%** | 2.4 | 2 | 669 → 32 (**95%** cut) | — |
| **Blackboard lecture** (MIT, camera on presenter) | **4.7%** | 21.8 | 123 | 150 → 110 (27%) **FAILS** | 150 → 17 (89%) |
| **Live coding** (screencast + scrolling editor) | **12.1%** | 4.8 | 26 | 150 → 25 (83%) degraded | 150 → 20 (87%) |

**Read the "still" column first.** It is the single best predictor. Above ~45% still, the defaults
work. Below, the frame never stops changing, so "the final state of a slide" is not a meaningful
idea and plateau detection has nothing to find.

The blackboard case's "21.8 hard cuts/min" is not slide changes - it is the lecture camera cutting
between angles plus the presenter moving. The hash is tracking **the human, not the content**.

### Blackboard/whiteboard: tuning helps, but does not solve it

With profiler-suggested parameters the blackboard segment drops from 110 to 17 candidates, and the
board content is legible. But inspecting those 17: **most have the presenter's body occluding what
they just wrote.** The genuinely useful frames are the few where they step aside. Perceptual hashing
cannot see the difference - a person moving in front of a static board looks exactly like content
changing.

**Tested and rejected:** "pick the maximum-ink frame in each segment" as an occlusion proxy. It does
not hold - a confirmed clear board shot scored `0.3730` while an occluded frame scored `0.3884`.
The `min(lit, 1-lit)` ink measure tracks overall luminance, not chalk, and a clothed human wrecks
it. Do not ship this heuristic; it was measured and it fails.

For this class, prefer **transcript-driven** timestamps (`visual_pointers` from
`transcript_signals.py`) over hash triage, and expect to hand-pick from a larger sheet.

### What is safe everywhere

Fully general - no assumptions about content or filming style:

- download + verification, audio extraction, Whisper transcription
- caption handling, the Whisper-vs-captions cross-check, the slides-break-ties rule
- contact-sheet tiling, `frame_manifest.py`, `verify_coverage.py`
- the entire notes structure: three source layers, WHY preservation, uncertainty sections,
  external-research labelling

**Swap per domain:** `transcribe.py --glossary`. The default is system-design vocabulary; on a
biology or law lecture it will actively mislead the decoder. Always pass a domain glossary.

**Tuned, verify first:** every threshold in `refine_frames.py`. Run `profile_video.py` on
`frames/raw` before trusting them - it takes ~20s and tells you which assumption the video breaks.

---

# Session 3 additions: probe-first, long videos, triangulation

## Probe BEFORE extracting (`probe_video.py`)

Deciding the tier after a full extraction is backwards. Measured:

```
                      22-min video      6-hour video
full decode @2s          24.4 s            ~7 min  (11,936 frames)
hash all frames x2        2.6 s            ~1 min
probe (28 seeks)          2.3 s             2.3 s   <- constant
```

If the profile then says "tier 2, sample every 20s", the entire extraction was wasted.

**Sampling design matters as much as sampling first.** Stillness is a LOCAL property:

```
random anchors x 4-frame bursts -> stillness 81%   (true 73.7%)  correct tier
uniform every 20s               -> stillness ~0%   calls a slide deck tier 2
```

Sampled 20s apart, every pair is a different slide, so *every* video reads as churn. Use stratified
random anchors expanded into short bursts; between-anchor distances still give global diversity.
Skip the first and last 5% - intros and outros are unrepresentative.

Also: pass `--hash-cache` to `refine_frames.py`. Cold 1.81s, warm 0.18s.

## The additive-canvas class (handwritten notes / annotated slides)

A fourth video type, with a clean fingerprint:

```
                        ink rises   corr(ink, time)
iPad + Apple Pencil       69.9%        +0.91        content ACCUMULATES
slide deck                50.1%        -0.08        slides replace each other
live coding               46.3%        -0.46
```

`corr(ink,time) > 0.7` detects it. It changes the strategy: when content only accumulates, **the
last frame of a page contains everything**, and pixel-change stops tracking *conceptual* progress.
Use the TRANSCRIPT to pick intermediate milestones, not the hash.

## Inset detection: shape, not magnitude (`motion_mask.py`)

Three attempts, two failed - same trap as the ink heuristic:

| Attempt | Statistic | Outcome |
|---|---|---|
| 1 | change **magnitude** | flagged a slide deck's *diagram area* as a webcam inset |
| 2 | absolute frequency threshold | detected nothing anywhere |
| 3 | **distribution shape** (p99/mean) | all four videos classify correctly |

A slide bullet is a *huge one-time* change; a webcam is a *modest constant* one. Magnitude scores
them alike; frequency separates them.

```
slide deck   mean 0.049  p99 0.100  ratio  2.0  -> content only
blackboard   mean 0.184  p99 0.417  ratio  2.3  -> GLOBAL motion (camera moving)
live coding  mean 0.037  p99 0.225  ratio  6.1  -> inset, bottom-right (confirmed by eye)
iPad         mean 0.005  p99 0.067  ratio 12.3  -> inset, top-right   (confirmed by eye)
```

Known limitation: the ninth-grid LOCATION is reliable; the pixel bounding box is not - scattered
hot pixels inflate it to the whole frame. Mask the winning ninth (crude but safe) until connected
components are implemented.

## OCR: printed slides YES, handwriting NO (`vision_ocr.py`)

Apple Vision, `pyobjc-framework-Vision` (~5 MB, no torch, Neural Engine, 0.032 s/frame warm).

```
printed slide  -> extracted "ITCH for NASDAQ" correctly - a slide-only term that
                  a transcript-only workflow loses entirely
handwriting    -> "fble Urnilled (4141 li-t 13 r(-"IP - @fcrffr_ S&MP I-TF TE"
                  upscaling 2x did not help
```

**Do not retry OCR on lecture handwriting.** Measured and rejected. For handwritten sources the
correct move is to escalate to frontier vision and accept the tokens - which reads it perfectly.

## Long videos: chunk, do not just fall back (`chunk_plan.py`)

Frontier fallback fixes *capability*, not *cost or coherence*. On a 6h37m video:

```
local Whisper large-v3   3.6 HOURS of compute      <- the real blocker, not vision
transcript tokens        ~79k
150 full-res frames      ~277k
tier-3 sweep triage      ~146k
```

400-500k tokens fits in context but degrades synthesis - you start compressing instead of
reasoning, and that is invisible in the output.

**Chunk size: 25 minutes**, from the measured 22:18 run that produced good notes (~72k working
context: transcript 7.7k + images 34.2k + notes 12.2k + research ~18k).

```
20 min -> ~65k     45 min -> ~145k
25 min -> ~81k     60 min -> ~194k
```

**Snap to the lecturer's section boundaries, not the clock.** Splitting mid-derivation separates a
decision from its reasoning and breaks "preserve WHY" outright. Target 25, accept 15-40 to land on
a real boundary.

State lives on DISK so context can be cleared between chunks:

```
chunks/manifest.json      plan + per-chunk status (the resume point)
chunks/NN-title/          transcript, frames, notes-part.md  (self-contained)
carry-forward.md          the ONLY thing crossing boundaries (~2-3k tokens):
                          running glossary, section outline, open threads,
                          sources already fetched
```

**Do not re-read fragments to merge.** 16 x 12k = 192k reintroduces the problem. Concatenate in
order; generate title/TOC/intro and the GLOBAL sections (key takeaways, revisit list, deduped
references) from `carry-forward.md`. Merge context ~20-30k.

For videos over ~90 min, prefer CAPTIONS over local Whisper (3.6h of compute), reserving Whisper
for chunks where terminology is dense.

## Cross-modal triangulation (when a VISUAL is unclear)

The "slides break transcript ties" rule runs in both directions. When a frame is ambiguous, resolve
in this order and stop at the first that settles it:

| # | Source | Note |
|---|---|---|
| 1 | **Internal consistency** - another part of the same frame | free and strongest |
| 2 | **Adjacent frames** (+/- 10s) | already on disk; the pen may have been covering it |
| 3 | **Transcript at that timestamp** | independent modality |
| 4 | **Topic context** | the surrounding derivation constrains it |
| 5 | **External / canonical form** | weak for reading, strong for confirming |
| 6 | **Unresolved** -> flag it | never guess |

> **THE RULE: external knowledge may CONFIRM a reading. It may never SUPPLY one.**
> If external is the only evidence, that is a guess wearing a citation. Flag it instead.

Worked example (Krish Naik AdaBoost, 06:40). The denominator reads as `1/2`; adjacent frames and
zoom did not resolve it. Internal consistency did:

```
denominator 1/7 -> (1 - 1/7)/(1/7) = 6      -> 1/2 ln 6     = 0.8959  matches the written 0.895
denominator 1/2 -> (1 - 1/7)/(1/2) = 1.714  -> 1/2 ln 1.714 = 0.269   does not
```

Record BOTH readings - never silently print the corrected version, or a student comparing notes
against the video is baffled:

> **As written (06:40):** 1/2 log_e((1 - 1/7)/(1/2)) = 0.895
> **Verification note:** the denominator must be 1/7. The lecturer's own result 0.895 = 1/2 ln 6;
> with 1/2 it would be 0.269. Canonical AdaBoost alpha = 1/2 ln((1-e)/e) uses the same quantity in
> both positions. Either the glyph is a 7 written like a 2, or he slipped while writing and
> computed correctly.

Apply this only where a misreading changes understanding - formulas, numbers, arrows, labels. Not
to every fuzzy word; it costs re-extraction and re-reading.

## The accuracy gate (`verify_notes.py`)

Run it before declaring done. Every number must trace to a layer: transcript (spoken), OCR of the
selected frames (on screen), or a labelled external block.

First version cried wolf - it flagged section headings (`### 2.1`) and, worse, treated **visual-only
content as unsupported** because it only checked the transcript. A verifier that cries wolf gets
ignored, which is worse than none. It now checks all three layers, skips headings/code/URLs/the
references table, and separates "PROBLEMS" from "NEEDS HUMAN CHECK".

Findings from auditing the first run's own notes:
- numeric claims: **clean** once Layer 2 was included
- quotes: several were **not verbatim against the cited file** - e.g. the notes quote "blasts them
  out" (from the captions) while `transcript-clean.txt` (Whisper) says "blast them out"

**Discipline:** a quoted string must be verbatim from the source you name. If you normalise it,
drop the quote marks or say so. Substantively-right-but-not-verbatim is still a citation error.


---

## Transcript primacy (the fix for a real design flaw)

The first design treated the three layers as peers. They are not. The transcript is **continuous,
timestamped, reconciled from two independent sources, corrected with an auditable log, and checked
for hallucination** — nothing else in the pipeline is verified that heavily. Frames are *point
evidence*; external is *confirmation only*.

The flaw this exposed: frames were being READ without their speech context. Triage happened on
pixels alone, and the transcript only entered later as a fallback in the triangulation ladder. That
throws away the best artifact at the exact moment it is most useful.

**Fix:** `contact_sheets.py --transcript` prints what was being said under every tile. Always pass
it. Example from a real sheet — the order-book "after cancel" frame is ambiguous in isolation, but
its caption reads *"node is simply unlinked by updating the next and previous pointers of its
neighbors in O(1)"*, which settles it without any extra step.

Uncertainty also propagates: where the transcript is flagged uncertain (e.g. the "pauses"/"pulses"
disagreement at 18:35), a frame reading at that timestamp is weaker too and should be marked.

## Transcript gates (`audit_transcript.py`)

Run BOTH before anything downstream consumes the transcript.

**Hallucination check** — Whisper invents text over silence/music, and it shows up as repetition or
impossible speaking rate: identical consecutive segments, a segment repeated 3+ times verbatim,
words-per-second outside 0.5–6.0, or long segments with almost no words. *Result on the reference
run: 247 segments, 0 flagged.*

**Correction audit** — the cleaning step applies substitutions in bulk; a pattern that over-matches
corrupts silently. This replays every rule and prints each change in context. *Result: 55
word-level substitutions across 21 distinct rules, all justified — `fixed→FIX` ×7, `Arion→Aeron`,
`SPE→SBE`, `training→trading`, `interrupted→interrupt`, plus casing. No over-matching.*

## Frame naming: name by EXTRACTION time (bug found in the reference run)

Frames were named by when a slide first appeared but extracted at its settled final state, so
`09-38-high-level-design.png` was really frame 12:10 — and `frame_manifest.py` quoted the transcript
at 09:38, the wrong moment. All 16 frames were renamed to their true extraction timestamps and the
manifest regenerated. **Name by the timestamp you actually extracted at.**

## Quote discipline

The reference notes quoted *"blasts them out"* while citing `transcript-clean.txt`, which says
*"blast them out"* — the wording had been taken from the captions. Substantively right, technically
a misquote, and exactly the class of error that is invisible when revising.

**A quoted string must be verbatim from the source you name.** If you normalise it, drop the quote
marks or say so. Five such quotes were corrected in the reference notes.

Two verifier bugs were also fixed while doing this, both of which produced false alarms:
timestamps were not stripped before flattening the transcript (so any quote spanning a line break
failed), and quotes inside Layer-3 blocks — which cite external docs, not the lecturer — were not
exempt. A verifier that cries wolf gets ignored, which is worse than not having one.

---

## Thresholds: derived, not tuned (`--auto`)

The nine constants in `refine_frames.py` were calibrated on ONE video. That is not the same as
validated, and it was the largest remaining risk on an unfamiliar channel.

**Fix: derive the three that actually vary from the video's own distance distribution.**

Frame-to-frame distances are genuinely bimodal - a "same content" cluster near the encoder noise
floor, and a "content changed" cluster far above it. **Otsu's method** finds the valley between
them, so the cut threshold comes from THIS video rather than from someone else's deck.

```
cut     = otsu(neighbour distances)          the valley between the two modes
settle  = p35 of the distribution            the noise floor (static frame, not content)
cluster = max(settle x 3, cut x 0.45)        same scale as the rest
```

`--min-plateau`, `--ink-drop`, `--recur-span`, `--boost-window` stay fixed: they are *semantic*
constants (how long a state must persist to be deliberate, how far apart a recurrence must be), not
properties of the encoder.

Derived vs hand-tuned across four videos:

| video | auto | hand-tuned |
|---|---|---|
| slide deck | `--cut 97 --settle 2 --cluster 44` | 60 / 4 / 26 |
| iPad pencil | `--cut 60 --settle 10 --cluster 31` | 32 / 7 |
| blackboard | `--cut 111 --settle 17 --cluster 50` | 215 / 51 |
| live coding | `--cut 54 --settle 17 --cluster 50` | 78 / 11 |

Candidates kept, auto vs fixed defaults: slide deck **37 vs 47**, iPad **11 vs 11**, blackboard
**84 vs 110**, live coding **30 vs 25**. Better or equal on three of four.

**The validated claim** (the only one that can be made, since only one video has ground truth):
on the reference video `--auto` gives **16/16 coverage with 24 candidates instead of 32** - same
recall, less to triage. Blackboard staying at 84/150 is not a calibration failure; it confirms the
profiler's tier-2 verdict that hash triage does not work there at all.

## The regression test (`tests/run_regression.py`)

What turns "calibrated" into "validated". Pins the known-good result so a future threshold change
is caught instead of quietly costing recall.

```bash
python tests/run_regression.py --video V.mp4 --frames frames/raw --truth frames/selected \
    --transcript-segments whisper.json --exclude 01:02-01:44,21:53-22:19
```

Asserts: every ground-truth frame still covered (auto AND fixed), candidate count inside a sane
band, `--auto` no worse than the defaults, and the transcript free of hallucination signatures.

**Confirmed it actually fails on real breakage** - an untested test is worthless. With
`--cluster 80 --recur-span 5` it loses three frames, matching them to entirely different slides at
distances 85 and 87. With `--min-plateau 20` it still passes 16/16, which is evidence the
final-state fix (final state does not require a plateau) is robust rather than luck.

**Add a fixture per new channel.** One video with hand-picked frames is enough to lock in behaviour
for that channel's style, and `channel_profile.py` already records which parameters that channel
needs.

---

## Is the transcript actually given enough weight? (audit, and the answer was NO)

Documentation claimed the transcript was "the spine". An audit of what the CODE does found three
gaps - the claim was prose, not behaviour.

**Gap 1: `boost` was pure decoration.** `refine_frames.py` computed which frames sat near a
`visual_pointer` and printed `<<POINTER`, then ignored it. The transcript said "look here" and
selection did not care. Now a pointer-adjacent frame is `protected`: it forms its own cluster and is
never merged away.

**Gap 2 (the big one): pointer HOLES.** Protection only defends frames that already exist. Measured
on the reference video: **3 of 5 pointers had no candidate anywhere near them.** The lecturer said
*"we've got our sequencer here"* at 10:23 and pixel-based selection proposed nothing. Protection
cannot fix that; only extracting at the transcript's timestamps can. Holes are now reported, and
`transcript_frames.py` builds a candidate set directly FROM the transcript - pointers, section
boundaries (+ settle delay), a configurable sweep - deduped by hash, with pointer frames never
deduped away.

That script is also the missing implementation of the tier-1 additive-canvas and tier-2 strategies,
both of which the docs recommended and no tool provided.

**Gap 3: uncertainty did not propagate.** Where the transcript is flagged uncertain, a frame reading
at that timestamp is weaker too. Frames now carry `uncertain` and are listed for closer reading.

### A silent schema mismatch found while fixing this

`refine_frames.py` read `sig["ad_candidates"]` while `transcript_signals.py` had moved to
`ad_spans`. Signal-driven ad exclusion **had been doing nothing**: 37 frames kept instead of 24,
with the sponsor segment included. It only ever worked because `--exclude` was being passed by hand.
Now reads `ad_spans` with an `ad_candidates` fallback.

**Process lesson:** two of these patches were applied with `str.replace`, which silently no-ops when
the anchor does not match. Compilation still passed, so nothing looked wrong. In one case an
assertion fired *before* `write_text`, so the whole edit was silently discarded while the terminal
showed "compiles". **Validate every anchor before mutating, and re-read the written file to confirm
the change landed.** Checking that a file still compiles proves nothing about whether the edit
applied.

---

## Synthesis order (the pipeline generated artifacts but never said how to write)

Steps 0a-6 produce artifacts. Nothing said in what ORDER to turn them into notes, and the ordering
is load-bearing:

**A. Transcript complete first.** It is the spine - section structure becomes the outline, and a
diagram cannot be interpreted without knowing what was said over it. Gate with
`audit_transcript.py`.

**B. Frames selected, guided by the transcript.** Pixels alone propose the wrong set (3 of 5
pointers had no frame). `refine_frames.py --signals` + `transcript_frames.py`.

**C. The visual-only pass** (`visual_only.py`) - systematically, not by noticing.

**D. Write section by section with that section's frames present.** Prose-first-then-images is
precisely the screenshot dump SPEC 16 forbids.

**E. Verify** (`verify_notes.py`, `verify_coverage.py`).

## OCR polarity: invert dark slides (measured, large effect)

Apple Vision is tuned for dark text on light paper. A dark-mode deck is the inverse and recall
COLLAPSES - silently, since it returns text, just not all of it.

```
Deep Dive 4 slide, as-is    ->  7 regions, ALL FOUR BULLETS MISSED
                inverted    -> 38 regions, every bullet recovered
```

The missed bullets included **"Mechanical Sympathy"** - a term never spoken aloud, so the transcript
could not supply it either. It reached the reference notes only because a human happened to read
the frame.

`vision_ocr.ocr(..., both=True)` (the default) now reads both polarities and merges. Cost ~0.03s
extra per frame; visual-only terms recovered on the reference lecture went **91 -> 111**.

**Generalisation: a silent recall failure is worse than a loud one.** OCR returning *some* text
looks like success. Always check recall against something you know is on the slide before trusting
a frame's OCR to be complete.

## visual_only.py - what is on screen but never said

The highest-value Layer-2 content, and the easiest to lose. Method: OCR each selected frame,
subtract every word spoken anywhere in the lecture, and report the remainder.

Reference results: `itch`, `nasdaq`, `msgtype`, `orderqty`, `clordid`, `executionreport`,
`mechanical`, `sympathy`, `single-threaded`, `hashmap`, `async`, `postgresql`, `openonload`,
`sub-microsecond` - 111 terms across 16 frames.

**Limits, stated plainly:** OCR is useless on handwriting, so `--handwritten` skips it entirely and
lists frames for a frontier read rather than emitting garbage. Even on printed slides OCR gives a
FLOOR, not a complete list - some fragments come back mangled (`plnnlng`, `blnary`). Treat the
output as candidates that make the frontier read faster, never as a substitute for it.
