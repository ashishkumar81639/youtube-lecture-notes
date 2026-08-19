#!/usr/bin/env bash
# Set up everything this skill needs. Idempotent - safe to run before every lecture.
#
#   source scripts/bootstrap.sh      # exports $VENV and $PY for the rest of the pipeline
#   bash   scripts/bootstrap.sh      # just installs, prints the paths
#
# ONE venv is shared by every lecture. It is ~1.3 GB (torch, an mlx-whisper dependency, is
# 536 MB of that) and identical every time, so a per-project venv would be larger than every
# artifact the pipeline produces combined.

set -uo pipefail

VENV="${YLN_VENV:-$HOME/.cache/youtube-lecture-notes/venv}"
PY="$VENV/bin/python"

# ---- system tools -----------------------------------------------------------
missing=()
for t in python3 ffmpeg ffprobe; do
  command -v "$t" >/dev/null 2>&1 || missing+=("$t")
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "MISSING system tools: ${missing[*]}" >&2
  echo "  macOS:  brew install ffmpeg" >&2
  echo "  Debian: sudo apt install ffmpeg python3-venv" >&2
  return 1 2>/dev/null || exit 1
fi

# ---- platform ---------------------------------------------------------------
OS="$(uname -s)"; ARCH="$(uname -m)"
APPLE_SILICON=false
[ "$OS" = "Darwin" ] && [ "$ARCH" = "arm64" ] && APPLE_SILICON=true

# ---- venv -------------------------------------------------------------------
if [ ! -x "$PY" ]; then
  echo "creating shared venv at $VENV"
  python3 -m venv "$VENV" || { echo "venv creation failed" >&2; return 1 2>/dev/null || exit 1; }
  "$VENV/bin/pip" install -q --upgrade pip
fi

# yt-dlp NIGHTLY: the stable build 403s on YouTube's SABR-only DASH URLs (PLAYBOOK §5).
CORE=(--pre "yt-dlp[default,curl-cffi]" pillow imagehash numpy)
"$VENV/bin/pip" install -q --upgrade "${CORE[@]}" || {
  echo "core dependency install failed" >&2; return 1 2>/dev/null || exit 1; }

if $APPLE_SILICON; then
  # mlx-whisper is Metal-accelerated; faster-whisper is CPU-only on macOS.
  "$VENV/bin/pip" install -q mlx-whisper || echo "WARN: mlx-whisper failed - transcribe.py unavailable" >&2
  # ~5 MB, no torch. Without it verify_notes.py SILENTLY skips Layer 2 and prints
  # "OCR unavailable" - a check you believe is running when it is not.
  "$VENV/bin/pip" install -q pyobjc-framework-Vision pyobjc-framework-Quartz \
    || echo "WARN: pyobjc Vision failed - verify_notes.py will not check Layer 2" >&2
else
  echo "NOTE: not Apple Silicon ($OS/$ARCH)."
  echo "      mlx-whisper and Apple Vision OCR are skipped. Local transcription and the"
  echo "      Layer-2 OCR check are unavailable; captions still work, and openai-whisper or"
  echo "      faster-whisper can be installed manually as a substitute."
fi

export VENV PY
echo
echo "VENV=$VENV"
echo "PY=\$VENV/bin/python"
"$PY" - <<'PYCHECK'
import importlib.util, sys
need = ["yt_dlp", "PIL", "imagehash", "numpy"]
opt  = ["mlx_whisper", "Vision"]
miss = [m for m in need if not importlib.util.find_spec(m)]
gone = [m for m in opt  if not importlib.util.find_spec(m)]
print("  core:     " + ("ok" if not miss else "MISSING " + ", ".join(miss)))
print("  optional: " + ("ok" if not gone else "unavailable -> " + ", ".join(gone)))
sys.exit(1 if miss else 0)
PYCHECK
