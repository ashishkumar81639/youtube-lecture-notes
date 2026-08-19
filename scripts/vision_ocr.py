#!/usr/bin/env python3
"""Apple Vision OCR probe. macOS native, no model download, runs on Neural Engine."""
import os, sys, json
import Vision, Quartz
from Foundation import NSURL


def _read(path, level, langs):
    url = NSURL.fileURLWithPath_(path)
    src = Quartz.CGImageSourceCreateWithURL(url, None)
    if src is None:
        return []
    img = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(img, None)
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(level)
    req.setUsesLanguageCorrection_(True)
    req.setRecognitionLanguages_(list(langs))
    ok, err = handler.performRequests_error_([req], None)
    out = []
    for obs in (req.results() or []):
        c = obs.topCandidates_(1)
        if c and len(c):
            box = obs.boundingBox()
            out.append({
                "text": c[0].string(),
                "conf": float(c[0].confidence()),
                "x": float(box.origin.x), "y": float(box.origin.y),
                "w": float(box.size.width), "h": float(box.size.height),
            })
    return out


def ocr(path, level=1, langs=("en-US",), both=True):
    """OCR a frame. level: 1 = accurate, 0 = fast.

    both=True also reads an INVERTED copy and merges the results. Apple Vision is
    tuned for dark text on light paper; a dark-mode slide deck is the inverse and
    recall collapses. Measured on one Deep Dive slide:

        as-is     ->  7 text regions, ALL FOUR BULLETS MISSED
        inverted  -> 38 text regions, every bullet recovered
                     (including "Mechanical Sympathy", a term never spoken aloud)

    Doubling the work costs ~0.03s/frame. Recall matters more than speed here -
    a missed bullet is content that silently never reaches the notes.
    """
    out = _read(path, level, langs)
    if not both:
        return out
    try:
        import tempfile
        from PIL import Image, ImageOps
        im = Image.open(path).convert("L")
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
            tmp = fh.name
        ImageOps.invert(im).save(tmp)
        inv = _read(tmp, level, langs)
        os.unlink(tmp)
    except Exception:
        return out
    seen = {r["text"].strip().lower() for r in out}
    for r in inv:
        k = r["text"].strip().lower()
        if k and k not in seen:
            seen.add(k); out.append(r)
    return out


if __name__ == "__main__":
    import time, glob
    paths = sys.argv[1:]
    if len(paths) == 1 and "*" in paths[0]:
        paths = sorted(glob.glob(paths[0]))
    t0 = time.time()
    for p in paths:
        r = ocr(p)
        txt = " ".join(x["text"] for x in r)
        avg = sum(x["conf"] for x in r) / len(r) if r else 0
        print(f"\n=== {p.split('/')[-1]}  ({len(r)} regions, avg conf {avg:.2f})")
        print(txt[:600] if txt else "  (no text found)")
    print(f"\n[{len(paths)} frames in {time.time()-t0:.1f}s = "
          f"{(time.time()-t0)/max(1,len(paths)):.2f}s/frame]", file=sys.stderr)
