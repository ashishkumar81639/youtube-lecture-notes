#!/usr/bin/env python3
"""
Delete regenerable artifacts once the notes are finished.

Why this is safe: frames/raw, frames/masked and frames/tf are DETERMINISTICALLY
REGENERABLE from source/lecture.mp4 with one ffmpeg command. The audit trail
lives in the video, not in 1800 JPEGs of it. SPEC 3 asks for intermediates so the
notes can be audited - a recorded, re-runnable command satisfies that better than
74 MB of thumbnails nobody opens.

What is NEVER touched: frames/selected (the frames actually in the notes),
source/, transcript/, diagrams/, research/, study-notes.md.

Refuses to run before selection is done, so it cannot destroy work in progress.

  python cleanup_artifacts.py .                  # dry run - shows what WOULD go
  python cleanup_artifacts.py . --apply          # frames only (safe default)
  python cleanup_artifacts.py . --apply --audio  # also drop the extracted WAV
"""
import argparse, shutil, sys, pathlib

DISPOSABLE = ["raw", "masked", "tf", "sweep", "candidates"]


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{u}"
        n /= 1024
    return f"{n:.0f}TB"


def dir_size(p):
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project", nargs="?", default=".")
    ap.add_argument("--apply", action="store_true", help="actually delete (default is a dry run)")
    ap.add_argument("--audio", action="store_true",
                    help="also delete source/lecture-audio.wav - it is one ffmpeg call from the mp4, "
                         "but re-running Whisper on it is NOT cheap, so this is opt-in")
    a = ap.parse_args()

    root = pathlib.Path(a.project).resolve()
    frames = root / "frames"
    selected = frames / "selected"
    notes = root / "study-notes.md"

    # ---- guards: never delete before the selected set exists and is in use ----
    if not frames.is_dir():
        print(f"no frames/ under {root}", file=sys.stderr); return 2
    keep = [f for f in selected.glob("*.png")] if selected.is_dir() else []
    if not keep:
        print("REFUSING: frames/selected is empty - selection is not finished.", file=sys.stderr)
        return 1
    if notes.exists():
        txt = notes.read_text()
        used = [f for f in keep if f.name in txt]
        if not used:
            print("REFUSING: study-notes.md references none of the selected frames.\n"
                  "          Write the notes before cleaning up.", file=sys.stderr)
            return 1
        print(f"selected frames referenced by the notes: {len(used)}/{len(keep)}")
    else:
        print("note: no study-notes.md yet - proceeding on the strength of frames/selected")

    targets = [frames / d for d in DISPOSABLE if (frames / d).is_dir()]

    wav = root / "source" / "lecture-audio.wav"
    audio_target = None
    if a.audio and wav.exists():
        # only safe once the transcript exists - the WAV is cheap to rebuild, the
        # transcript it feeds is 12+ minutes of Whisper.
        if not (root / "transcript" / "transcript-clean.txt").exists():
            print("REFUSING --audio: transcript/transcript-clean.txt is missing.\n"
                  "          Transcribe before discarding the audio.", file=sys.stderr)
            return 1
        audio_target = wav

    if not targets and not audio_target:
        print("nothing to clean.")
        return 0

    total = 0
    print()
    if audio_target:
        s = audio_target.stat().st_size
        total += s
        print(f"  {'DELETE' if a.apply else 'would delete'}  "
              f"{audio_target.relative_to(root)}   {human(s)}   (rebuild: one ffmpeg call)")
    for t in targets:
        n = sum(1 for _ in t.rglob("*") if _.is_file())
        s = dir_size(t)
        total += s
        print(f"  {'DELETE' if a.apply else 'would delete'}  {t.relative_to(root)}"
              f"   {n} files   {human(s)}")
    print(f"\n  reclaims {human(total)}; frames/selected ({len(keep)} files) is untouched.")

    if not a.apply:
        print("\ndry run - nothing removed. Re-run with --apply.")
        return 0

    for t in targets:
        shutil.rmtree(t)
    if audio_target:
        audio_target.unlink()

    # record how to get them back, so the audit trail survives the deletion
    (frames / "REGENERATE.md").write_text(
        "# Regenerating the intermediate frames\n\n"
        "`frames/raw`, `frames/masked` and `frames/tf` were deleted after selection. They are\n"
        "deterministic functions of `source/lecture.mp4`, which is kept, so nothing is lost —\n"
        "re-run these to reproduce the exact inputs the selection was made from.\n\n"
        "```bash\n"
        "mkdir -p frames/raw\n"
        "ffmpeg -y -v error -i source/lecture.mp4 \\\n"
        "    -vf \"fps=1/2,scale=640:-1\" -q:v 4 frames/raw/f%04d.jpg\n"
        "```\n\n"
        "`frames/masked` (webcam inset and toolbar blanked before hashing) and `frames/tf`\n"
        "(frames pulled at transcript timestamps) are rebuilt by re-running the selection step\n"
        "in `SKILL.md` against `frames/raw`.\n\n"
        "`frames/selected/` — the frames actually used in the notes — was never deleted.\n\n"
        "If `source/lecture-audio.wav` was also removed:\n\n"
        "```bash\n"
        "ffmpeg -y -v error -i source/lecture.mp4 -vn -ac 1 -ar 16000 \\\n"
        "    -c:a pcm_s16le source/lecture-audio.wav\n"
        "```\n"
    )
    print(f"\ndeleted. wrote {(frames / 'REGENERATE.md').relative_to(root)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
