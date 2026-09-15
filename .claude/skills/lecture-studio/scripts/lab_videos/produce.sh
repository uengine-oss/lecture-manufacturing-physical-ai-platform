#!/usr/bin/env bash
# 사용: LECTURE_ROOT=<강의 루트> OPENAI_ENV_FILE=<.env> PYTHON=<python> produce.sh P01 P02 ...
# 사양 검증 → gpt-6-astra 다듬기 → TTS → 렌더(실제 실행 녹화) → 합성. 로그: $LAB_VIDEOS_DIR/build/<ID>/produce.log
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
export LECTURE_ROOT="${LECTURE_ROOT:-$PWD}"
export LAB_VIDEOS_DIR="${LAB_VIDEOS_DIR:-$LECTURE_ROOT/video/lab_videos}"
PY="${PYTHON:-python3}"
for ID in "$@"; do
  mkdir -p "$LAB_VIDEOS_DIR/build/$ID"
  LOG="$LAB_VIDEOS_DIR/build/$ID/produce.log"
  {
    echo "== $ID $(date +%T) validate"; "$PY" "$HERE/validate_spec.py" "$ID" || exit 1
    echo "== $ID $(date +%T) polish (gpt-6-astra)"; "$PY" "$HERE/polish.py" "$ID" || exit 1
    echo "== $ID $(date +%T) tts"; "$PY" "$HERE/tts.py" "$ID" || exit 1
    echo "== $ID $(date +%T) render"; node "$HERE/render.mjs" "$ID" || exit 1
    echo "== $ID $(date +%T) assemble"; "$PY" "$HERE/assemble.py" "$ID" || exit 1
    echo "== $ID $(date +%T) DONE"
  } > "$LOG" 2>&1 || { echo "== $ID FAILED" >> "$LOG"; echo "$ID FAILED (see $LOG)"; continue; }
  grep -E "PASS|CHECK" "$LOG" | tail -1
done
