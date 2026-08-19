# youtube-lecture-notes

A Claude Code skill that turns a YouTube technical lecture into **auditable** multimodal study
notes — spoken content, on-screen diagrams and code, and clearly-labelled external research, with
every claim traceable back to a source.

There are several good "let Claude watch a video" skills already. This one is built around a
different goal: **you should be able to check the notes against the lecture.**

## What makes it different

| | most video→notes tools | this |
|---|---|---|
| transcript | captions, or Whisper as a fallback | **both**, reconciled — and where they disagree, the on-screen writing breaks the tie |
| provenance | one undifferentiated block of prose | three layers never blurred: what was **said**, what was **shown**, what was **researched** |
| verification | none | hallucination audit, every number traced to a layer, every quote checked verbatim, an auditable correction log |
| frame triage | send N frames | 1800 sampled → contact sheets → a handful of full-resolution reads |
| ads / sponsors | not handled | excluded from frame selection before you pay to look at them |
| long videos | "split it yourself" | chunk plan that snaps to the lecturer's own section boundaries |

The tie-breaking is not theoretical. On one run it settled `α = 0.01` against audio that variously
said "0.1" and "0.001", recovered a dataset row the captions rendered as `257 uh 62`, and turned
`dv scan` into `DBSCAN`.

## Install

```bash
git clone https://github.com/<you>/youtube-lecture-notes ~/.claude/skills/youtube-lecture-notes
source ~/.claude/skills/youtube-lecture-notes/scripts/bootstrap.sh
```

`bootstrap.sh` is idempotent. It verifies `ffmpeg`/`ffprobe`, builds one shared venv at
`~/.cache/youtube-lecture-notes/venv` (override with `YLN_VENV`), and installs the yt-dlp nightly —
the stable build gets `HTTP 403` on YouTube's SABR-only DASH URLs.

Then just ask Claude Code:

> process this lecture: https://www.youtube.com/watch?v=...

## Requirements

- `ffmpeg`, `ffprobe`, `python3`
- **Apple Silicon** for local transcription (`mlx-whisper`, Metal-accelerated) and Layer-2 OCR
  (Apple Vision). Elsewhere the pipeline still runs on captions; bootstrap tells you what is
  unavailable rather than failing quietly.
- ~1.3 GB for the shared venv (536 MB of that is torch, an `mlx-whisper` dependency)

## Output

```
study-notes.md              the deliverable
frames/selected/            only the frames actually used, descriptively named
  manifest.md               frame → transcript → classification
diagrams/recreated/         clean Mermaid/ASCII versions of important diagrams
transcript/
  transcript-clean.txt      + a correction log: pattern → replacement → evidence
research/external-research.md   why researched → source → findings → verdict → where used
```

Intermediate frames and the extracted WAV are deleted after the notes are written
(`cleanup_artifacts.py`) — they are one ffmpeg command from the video, which is kept, so the audit
trail survives. A one-hour lecture ends at ~164 MB instead of ~1.6 GB.

## Documentation

| File | What it is |
|---|---|
| `SKILL.md` | the pipeline, in order, with the commands |
| `reference/SPEC.md` | the 41-point contract — the definition of done |
| `reference/PLAYBOOK.md` | measured operational knowledge: token economics, and the failure modes that cost an hour to find |
| `reference/NOTES-VOICE.md` | how the notes must read, and the two ways they go wrong |

`PLAYBOOK.md` is the most useful file if you are adapting this. It records what was **measured**,
including things that were tried and rejected — local OCR on handwriting, "maximum-ink frame" as an
occlusion proxy, ffmpeg scene detection on animated slides.

## Honest limitations

- **Tuned on macOS / Apple Silicon.** Portable in principle; only tested there.
- **Frame thresholds were calibrated on a slide deck.** `profile_video.py` measures each video and
  picks a tier, but a video type nobody has tried may still need hand-tuning.
- **Handwriting needs frontier vision.** Local OCR on it was measured and is useless — do not retry it.
- **Ink-based page detection misses scrolling.** If a canvas scrolls rather than wipes, content can
  leave the screen without triggering a new page.
- **`cache/channels.json` is seed data**, not your history. Your own profiles go to
  `~/.cache/youtube-lecture-notes/channels.json` so they never end up in a commit.

## Prior art worth knowing

[`claude-real-video`](https://github.com/HUANGCHIHHUNGLeo/claude-real-video) and
[`claude-watch`](https://github.com/devinilabs/claude-watch) (both MIT) solve the frames+transcript
problem well and are simpler to run if you do not need the verification layer.

## Licence

MIT — see `LICENSE`.
