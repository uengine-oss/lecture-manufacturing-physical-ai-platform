#!/usr/bin/env bash
# 사용: tools/after.sh "<기다릴 ID들>" <만들 ID들...>  — 앞 ID 들의 produce.log 가 끝나면 이어서 제작
cd "$(dirname "$0")/.."
for W in $1; do until grep -qE "== $W .*DONE|== $W FAILED" build/$W/produce.log 2>/dev/null; do sleep 20; done; done
shift; exec tools/produce.sh "$@"
