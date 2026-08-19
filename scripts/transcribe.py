#!/usr/bin/env python3
"""
Local Whisper large-v3 transcription via MLX (Metal) on Apple Silicon.

Emits transcript-raw.txt, transcript-timestamped.txt and a .json of raw segments.
Run this in the BACKGROUND and do the frame pipeline while it works
(~half the audio duration on an M3, plus a one-off 2.9 GB model download).

Usage:
    transcribe.py AUDIO.wav --outdir transcript/ [--json seg.json] [--glossary "term, term, ..."]

Requires: mlx-whisper  (pip install mlx-whisper)
"""
import argparse, json, os, sys, textwrap, time

# Seeding the decoder with expected vocabulary measurably improves proper-noun
# accuracy. Override with --glossary for a different domain.
DEFAULT_GLOSSARY = (
    "Technical system design lecture. Expected terminology: order book, matching engine, "
    "limit order, market order, bid, ask, FIFO, price-time priority, sequencer, deterministic, "
    "event sourcing, state machine, idempotent, Kafka, Aeron, Redis, WebSocket, Postgres, "
    "PostgreSQL, sharding, partitioning, replication, consensus, Raft, quorum, latency, "
    "throughput, TCP, UDP, multicast, gRPC, REST, SBE, FIX protocol, ring buffer, "
    "LMAX Disruptor, lock-free, mutex, cache line, false sharing, kernel bypass, DPDK, "
    "FPGA, write-ahead log, snapshot, in-memory, garbage collection."
)


def hhmmss(s: float) -> str:
    s = int(s)
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--outdir", default="transcript")
    ap.add_argument("--json", default=None)
    ap.add_argument("--model", default="mlx-community/whisper-large-v3-mlx")
    ap.add_argument("--glossary", default=DEFAULT_GLOSSARY)
    ap.add_argument("--language", default="en")
    a = ap.parse_args()

    try:
        import mlx_whisper
    except ImportError:
        sys.exit("pip install mlx-whisper  (Apple Silicon; faster-whisper is CPU-only on macOS)")

    os.makedirs(a.outdir, exist_ok=True)
    t0 = time.time()
    res = mlx_whisper.transcribe(
        a.audio,
        path_or_hf_repo=a.model,
        language=a.language,
        temperature=0.0,
        condition_on_previous_text=False,  # avoids hallucination loops on repetitive slides
        word_timestamps=False,
        initial_prompt=a.glossary,
        verbose=False,
    )
    segs = res["segments"]
    hdr = (f"# Source: local Whisper via MLX/Metal, model={a.model}\n"
           f"# UNEDITED model output. Corrections belong in transcript-clean.txt\n\n")

    with open(f"{a.outdir}/transcript-raw.txt", "w") as f:
        f.write(hdr + textwrap.fill(res["text"].strip(), 100) + "\n")

    with open(f"{a.outdir}/transcript-timestamped.txt", "w") as f:
        f.write(hdr)
        for s in segs:
            f.write(f"[{hhmmss(s['start'])}] {s['text'].strip()}\n")

    if a.json:
        json.dump(res, open(a.json, "w"))

    print(f"DONE segments={len(segs)} covered={hhmmss(segs[-1]['end'])} "
          f"elapsed={time.time() - t0:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
