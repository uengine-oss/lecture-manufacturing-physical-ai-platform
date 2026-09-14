#!/usr/bin/env bash
# 사용: tools/produce.sh P02 P03 ...   — 사양 검증 → gpt-6-astra 다듬기 → TTS → 렌더(실제 실행 녹화) → 합성
set -euo pipefail
cd "$(dirname "$0")/.."
PY=/Users/uengine/uengine-platform/lecture/system/.venv/bin/python
for ID in "$@"; do
  mkdir -p build/$ID
  {
    echo "== $ID $(date +%T) validate"; $PY tools/validate_spec.py $ID
    echo "== $ID $(date +%T) polish (gpt-6-astra)"; $PY tools/polish.py $ID
    echo "== $ID $(date +%T) tts"; $PY tools/tts.py $ID
    echo "== $ID $(date +%T) render"; node tools/render.mjs $ID
    echo "== $ID $(date +%T) assemble"; $PY tools/assemble.py $ID
    echo "== $ID $(date +%T) DONE"
  } > build/$ID/produce.log 2>&1 || { echo "== $ID FAILED" >> build/$ID/produce.log; echo "$ID FAILED"; continue; }
  tail -1 build/$ID/produce.log; grep "PASS\|CHECK" build/$ID/produce.log | tail -1
done
