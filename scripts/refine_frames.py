#!/usr/bin/env python3
"""
Second pass over densely-sampled frames. Removes the last manual judgement from
the mechanical half of the pipeline.

Four things the first-pass chained dedup cannot do:

  1. SEGMENT + SETTLE - split the timeline at hard cuts, then within each segment
     find PLATEAUS (runs where the frame stops changing). The last plateau is the
     slide's FINAL state, with every bullet drawn and no fade transition.

  2. KEEP DESTRUCTIVE INTERMEDIATES - an earlier plateau is kept only when the
     final frame has LESS content than it, i.e. something was REMOVED. That is
     the before/after pair case (a list node being unlinked). Additive build-up -
     bullets appearing one by one - is dropped, because the final frame already
     contains every earlier state.
       measured: order-book pair  ink 0.0367 -> 0.0343  (DOWN, kept)
                 requirements     ink 0.0356 -> 0.0493  (UP, dropped)
     Distance alone cannot do this: that pair differs by only 20, well under any
     usable threshold, while adjacent build steps often differ by more.

  3. GLOBAL CLUSTER - the first pass compares to the last KEPT frame, so a
     recurring template (agenda / section divider) is re-kept on every return.
     Clustering across the whole timeline collapses those AND exposes the deck's
     section structure for free.

  4. TRANSCRIPT SIGNALS - drop frames inside confirmed ad spans, flag frames the
     lecturer verbally points at. See transcript_signals.py.

Usage:
    refine_frames.py FRAMES_DIR --out refined.json
        [--interval 2] [--cut 60] [--settle 4] [--min-plateau 6] [--cluster 26]
        [--signals sig.json] [--exclude 01:04-01:29,21:53-22:22]

Requires: pillow, imagehash, numpy
"""
import argparse, glob, json, os, sys

try:
    from PIL import Image
    import imagehash
    import numpy as np
except ImportError:
    sys.exit("pip install pillow imagehash numpy")


def otsu(vals, nbins=256):
    """1-D Otsu threshold: split a bimodal distribution at the valley between modes.

    Frame-to-frame distances ARE bimodal - a 'same content' cluster near the
    encoder noise floor, and a 'content changed' cluster far above it. Otsu finds
    the split that maximises between-class variance, so the threshold comes from
    THIS video instead of a constant tuned on some other one.
    """
    v = np.asarray(vals, dtype=np.float64)
    if v.size < 8 or v.max() <= v.min():
        return float(v.max() if v.size else 0)
    hist, edges = np.histogram(v, bins=nbins)
    total = hist.sum()
    idx = np.arange(nbins)
    sum_all = float((hist * idx).sum())
    wB = 0.0; sumB = 0.0; best = -1.0; thr = 0
    for i in range(nbins):
        wB += hist[i]
        if wB == 0:
            continue
        wF = total - wB
        if wF == 0:
            break
        sumB += i * hist[i]
        mB = sumB / wB
        mF = (sum_all - sumB) / wF
        between = wB * wF * (mB - mF) ** 2
        if between > best:
            best, thr = between, i
    return float(edges[min(thr + 1, nbins)])


def calibrate(nb):
    """Derive cut / settle / cluster from this video's own distance distribution."""
    d = np.asarray(nb[1:], dtype=np.float64)
    cut = otsu(d)
    # noise floor: the low tail is encoder noise on a static frame, not content
    settle = max(2.0, float(np.percentile(d, 35)))
    if settle >= cut * 0.5:                 # degenerate (almost everything moves)
        settle = max(2.0, cut * 0.15)
    cluster = max(settle * 3.0, cut * 0.45)
    return int(round(cut)), int(round(settle)), int(round(cluster))


def ms(t):  return f"{t // 60:02d}:{t % 60:02d}"
def hms(t): return f"{t // 3600:02d}:{(t % 3600) // 60:02d}:{t % 60:02d}"


def parse_span(s):
    def sec(x):
        p = [int(i) for i in x.split(":")]
        return p[0] * 60 + p[1] if len(p) == 2 else p[0] * 3600 + p[1] * 60 + p[2]
    a, b = s.split("-")
    return sec(a), sec(b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames_dir")
    ap.add_argument("--out", required=True)
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--hash-size", type=int, default=16)
    ap.add_argument("--cut", type=int, default=60,
                    help="neighbour distance above this = hard cut / new slide")
    ap.add_argument("--settle", type=int, default=4,
                    help="neighbour distance below this = frame has stopped changing")
    ap.add_argument("--min-plateau", type=float, default=6.0,
                    help="seconds a state must persist to count as deliberate")
    ap.add_argument("--ink-drop", type=float, default=0.02,
                    help="relative ink decrease that counts as content REMOVED")
    ap.add_argument("--cluster", type=int, default=26,
                    help="distance below which two frames are the same template")
    ap.add_argument("--recur-span", type=int, default=60,
                    help="a template must recur at least this far apart to be a divider")
    ap.add_argument("--signals", default=None, help="JSON from transcript_signals.py")
    ap.add_argument("--exclude", default=None, help="MM:SS-MM:SS,... confirmed ad spans")
    ap.add_argument("--boost-window", type=int, default=12)
    ap.add_argument("--auto", action="store_true",
                    help="derive --cut/--settle/--cluster from THIS video (Otsu on the "
                         "distance distribution) instead of constants tuned elsewhere")
    ap.add_argument("--hash-cache", default=None,
                    help="reuse hashes across runs; profile+refine otherwise hash twice")
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.frames_dir, "f*.jpg")) +
                   glob.glob(os.path.join(a.frames_dir, "f*.png")))
    if not files:
        sys.exit(f"no f*.jpg / f*.png in {a.frames_dir}")

    cache = {}
    if a.hash_cache and os.path.exists(a.hash_cache):
        try:
            cache = json.load(open(a.hash_cache))
        except json.JSONDecodeError:
            cache = {}

    F = []
    for f in files:
        idx = int("".join(c for c in os.path.basename(f) if c.isdigit()))
        c = cache.get(f)
        if c:
            F.append({"idx": idx, "t": int((idx - 1) * a.interval), "file": f,
                      "p": imagehash.hex_to_hash(c[0]), "d": imagehash.hex_to_hash(c[1]),
                      "ink": c[2]})
            continue
        im = Image.open(f)
        g = np.asarray(im.convert("L"), dtype=np.float32)
        lit = float((g > 60).mean())
        # dark-on-light decks invert: use whichever polarity is the minority (= the ink)
        F.append({"idx": idx, "t": int((idx - 1) * a.interval), "file": f,
                  "p": imagehash.phash(im, hash_size=a.hash_size),
                  "d": imagehash.dhash(im, hash_size=a.hash_size),
                  "ink": min(lit, 1.0 - lit)})
        cache[f] = [str(F[-1]["p"]), str(F[-1]["d"]), F[-1]["ink"]]

    if a.hash_cache:
        json.dump(cache, open(a.hash_cache, "w"))

    def dist(x, y):
        return int((x["p"] - y["p"]) + (x["d"] - y["d"]))

    nb = [0] + [dist(F[i - 1], F[i]) for i in range(1, len(F))]

    if a.auto:
        c, s, cl = calibrate(nb)
        given = {x.split("=")[0] for x in sys.argv if x.startswith("--")}
        if "--cut" not in given:     a.cut = c
        if "--settle" not in given:  a.settle = s
        if "--cluster" not in given: a.cluster = cl
        print(f"auto-calibrated from this video: --cut {a.cut} --settle {a.settle} "
              f"--cluster {a.cluster}", file=sys.stderr)

    need = max(2, int(round(a.min_plateau / a.interval)))

    # ---- 1. segment at hard cuts -------------------------------------------
    bounds = [0] + [i for i in range(1, len(F)) if nb[i] >= a.cut] + [len(F)]
    segments = [(bounds[k], bounds[k + 1] - 1) for k in range(len(bounds) - 1)
                if bounds[k + 1] - 1 >= bounds[k]]

    # ---- 2. plateaus, then keep final + destructive intermediates -----------
    picked = []
    for (s, e) in segments:
        # FINAL = the LAST frame of the segment, skipping only genuine fade-out
        # frames (ink collapsed toward the next slide).
        #
        # Do NOT require the final state to sit on a long plateau. A lecturer
        # routinely adds the last annotation and immediately moves on, so the
        # completed slide may be on screen for only 2-4s. Requiring a plateau
        # there silently falls back to an EARLIER, less complete state - measured
        # on the Complete Architecture slide, which kept building to 20:16
        # (ink 0.0747, the maximum) while a 6s-plateau rule returned 20:10
        # (ink 0.0694), losing the final annotations.
        maxink = max(F[k]["ink"] for k in range(s, e + 1))
        j = e
        while j > s and F[j]["ink"] < 0.5 * maxink:
            j -= 1
        final = F[j]
        run_s = j
        while run_s > s and nb[run_s] <= a.settle:
            run_s -= 1
        picked.append({**final, "role": "final",
                       "plateau_s": (j - run_s + 1) * a.interval})

        # INTERMEDIATES still require a plateau - that is what separates a state
        # the lecturer dwelled on from a transient build step - AND an ink drop,
        # which is what marks content having been REMOVED rather than added.
        runs, st = [], s
        for i in range(s + 1, j + 1):
            if nb[i] > a.settle:
                if (i - 1) - st + 1 >= need:
                    runs.append((st, i - 1))
                st = i
        for (rs, re_) in runs:
            cand = F[re_]
            if final["ink"] < cand["ink"] * (1.0 - a.ink_drop):   # content REMOVED
                picked.append({**cand, "role": "state-before",
                               "plateau_s": (re_ - rs + 1) * a.interval})
    picked.sort(key=lambda r: r["t"])

    # transcript signals must be read BEFORE clustering so pointer frames can be
    # protected from it
    _excl = [parse_span(s) for s in a.exclude.split(",")] if a.exclude else []
    _ptrs, _unc = [], []
    if a.signals:
        _sig = json.load(open(a.signals))
        _ptrs = [p["t"] for p in _sig.get("visual_pointers", [])]
        _unc = [u for u in _sig.get("uncertain", [])]
        # transcript_signals.py emits "ad_spans"; an older build read
        # "ad_candidates" here, so signal-driven ad exclusion SILENTLY DID
        # NOTHING (measured: 37 frames kept instead of 24, ads included).
        _ads = _sig.get("ad_spans") or _sig.get("ad_candidates") or []
        if not _excl:
            _excl = [(c["start"], c["end"]) for c in _ads]
    for r in picked:
        r["protected"] = any(abs(r["t"] - p) <= a.boost_window for p in _ptrs)
        r["uncertain"] = any(abs(r["t"] - u) <= a.boost_window for u in _unc)

    # ---- 3. global clustering ----------------------------------------------
    # Clustering exists ONLY to collapse RECURRING templates, which are by
    # definition far apart in time. Frames close together are distinct states of
    # the same slide (a before/after pair can differ by as little as 20) and must
    # never be merged.
    # PROTECTED frames are never clustered away. If the lecturer verbally pointed
    # at the screen at time T, that frame is wanted even if it resembles another -
    # the transcript is the most-verified signal we have, and letting a pixel
    # heuristic overrule it throws that away. (Before this, `boost` was computed
    # and printed but changed nothing: pure decoration.)
    clusters = []
    for r in picked:
        if r.get("protected"):
            clusters.append({"rep": r, "members": [r]}); continue
        for c in clusters:
            if (dist(r, c["rep"]) <= a.cluster
                    and abs(r["t"] - c["members"][-1]["t"]) >= a.recur_span
                    and not c["rep"].get("protected")):
                c["members"].append(r); break
        else:
            clusters.append({"rep": r, "members": [r]})

    out = []
    for cid, c in enumerate(clusters):
        times = [m["t"] for m in c["members"]]
        rep = c["members"][0]
        out.append({**rep, "cluster": cid, "recurs": len(times), "recurs_at": times,
                    "is_divider": len(times) > 1 and (max(times) - min(times)) >= a.recur_span})
    out.sort(key=lambda r: r["t"])

    # ---- 4. transcript signals ---------------------------------------------
    excl, ptrs = _excl, _ptrs

    kept, dropped = [], []
    for r in out:
        if any(s <= r["t"] <= e for s, e in excl):
            dropped.append(r); continue
        r["boost"] = r.get("protected", False)
        kept.append(r)

    # A POINTER HOLE is the case protection CANNOT fix: the lecturer said "look at
    # this" and pixel-based selection produced NOTHING there. Protection only
    # defends frames that already exist. Measured on the reference video, 3 of 5
    # pointers had no candidate within the window - the transcript was asking for
    # frames the pixel heuristic never proposed. THAT is the real gap, and it is
    # why transcript_frames.py exists.
    holes = [q for q in ptrs
             if not any(abs(r["t"] - q) <= a.boost_window for r in kept)
             and not any(s <= q <= e for s, e in excl)]

    # ---- report -------------------------------------------------------------
    er = lambda *x: print(*x, file=sys.stderr)
    er(f"sampled {len(F)} -> segments {len(segments)} -> plateaus {len(picked)} "
       f"-> clustered {len(out)} -> kept {len(kept)}")
    if dropped:
        er(f"\nDROPPED {len(dropped)} inside excluded spans: "
           f"{', '.join(ms(r['t']) for r in dropped)}")
    if holes:
        er(f"\nPOINTER HOLES ({len(holes)}) - lecturer pointed at the screen but")
        er("  selection produced no frame there. Grab them with transcript_frames.py:")
        for hq in holes:
            er(f"   {ms(hq)}")
    unc = [r for r in kept if r.get("uncertain")]
    if unc:
        er(f"\nTRANSCRIPT UNCERTAIN at {len(unc)} kept frame(s) - the spoken source is")
        er("  weak there too, read closely: " + ", ".join(ms(r["t"]) for r in unc))

    div = [r for r in kept if r["is_divider"]]
    if div:
        er("\nRECURRING TEMPLATES (section dividers):")
        for r in div:
            er(f"   {ms(r['t'])}  x{r['recurs']}  {', '.join(ms(t) for t in r['recurs_at'])}")
    pairs = [r for r in kept if r["role"] == "state-before"]
    if pairs:
        er(f"\nBEFORE/AFTER PAIRS (content removed later in the same slide):")
        for r in pairs:
            er(f"   {ms(r['t'])}  held {r['plateau_s']:.0f}s")

    print()
    for r in kept:
        tag = "DIVIDER" if r["is_divider"] else r["role"]
        print(f"{hms(r['t'])}  {tag:<13} held {r['plateau_s']:>5.0f}s"
              f"{'  <<POINTER' if r.get('boost') else ''}")

    json.dump([{k: v for k, v in r.items() if k not in ("p", "d")} for r in kept],
              open(a.out, "w"), indent=1)
    er(f"\n-> {a.out}")


if __name__ == "__main__":
    main()
