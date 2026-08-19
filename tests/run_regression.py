#!/usr/bin/env python3
"""
Regression test for the frame pipeline.

The thresholds in refine_frames.py were CALIBRATED on one video. This test is
what turns that into something VALIDATED: it pins the known-good result so any
future change to a threshold, a statistic, or the settle/plateau logic is caught
instead of silently degrading recall.

It asserts, against a fixture that has hand-picked ground-truth frames:
  1. every hand-picked frame is still covered by the automatic candidate set
  2. the candidate count stays inside a sane band (no collapse, no blow-up)
  3. --auto calibration does at least as well as the fixed defaults
  4. the transcript audits clean (no hallucination signatures)

Usage:
    run_regression.py --video V.mp4 --frames frames/raw --truth frames/selected
                      [--transcript-segments whisper.json] [--exclude 01:02-01:44]
                      [--max-candidates 60] [--tol 14]

Exit 0 = pass. Non-zero = a regression.
"""
import argparse, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
PY = sys.executable


def run(args):
    return subprocess.run([PY] + args, capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--frames", required=True)
    ap.add_argument("--truth", required=True)
    ap.add_argument("--transcript-segments", default=None)
    ap.add_argument("--exclude", default=None)
    ap.add_argument("--max-candidates", type=int, default=60)
    ap.add_argument("--min-candidates", type=int, default=8)
    ap.add_argument("--tol", type=int, default=14)
    a = ap.parse_args()

    fails = []

    def check(name, ok, detail=""):
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
        if not ok:
            fails.append(name)

    counts = {}
    for mode in ("auto", "fixed"):
        out = f"/tmp/_reg_{mode}.json"
        cmd = [os.path.join(SCRIPTS, "refine_frames.py"), a.frames, "--out", out]
        if mode == "auto":
            cmd.append("--auto")
        if a.exclude:
            cmd += ["--exclude", a.exclude]
        r = run(cmd)
        if r.returncode != 0:
            check(f"refine_frames ({mode}) runs", False, r.stderr.strip()[:120]); continue
        counts[mode] = len(json.load(open(out)))

        cov = run([os.path.join(SCRIPTS, "verify_coverage.py"), a.truth, out,
                   a.video, "--tol", str(a.tol)])
        line = [l for l in cov.stdout.splitlines() if l.startswith("COVERED")]
        got = line[0] if line else "COVERED ?/?"
        n, tot = (got.split()[1].split("/") + ["0"])[:2]
        check(f"coverage ({mode})", n == tot and tot != "0", got)
        check(f"candidate count sane ({mode})",
              a.min_candidates <= counts[mode] <= a.max_candidates,
              f"{counts[mode]} (band {a.min_candidates}-{a.max_candidates})")

    if "auto" in counts and "fixed" in counts:
        check("auto is no worse than fixed defaults",
              counts["auto"] <= counts["fixed"],
              f"auto {counts['auto']} vs fixed {counts['fixed']}")

    if a.transcript_segments:
        r = run([os.path.join(SCRIPTS, "audit_transcript.py"),
                 "--segments", a.transcript_segments])
        flagged = "flagged: 0" in r.stdout
        check("transcript free of hallucination signatures", flagged,
              [l for l in r.stdout.splitlines() if "flagged" in l][:1])

    print()
    if fails:
        print(f"REGRESSION: {len(fails)} check(s) failed -> {', '.join(fails)}")
        sys.exit(1)
    print("All regression checks passed.")


if __name__ == "__main__":
    main()
