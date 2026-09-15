#!/usr/bin/env bash
# 사용: after.sh "<기다릴 ID들>" <만들 ID들...> — 앞 ID 들의 produce.log 가 DONE/FAILED 가 되면 이어서 제작
HERE="$(cd "$(dirname "$0")" && pwd)"
LV="${LAB_VIDEOS_DIR:-${LECTURE_ROOT:-$PWD}/video/lab_videos}"
for W in $1; do until grep -qE "== $W .*DONE|== $W FAILED" "$LV/build/$W/produce.log" 2>/dev/null; do sleep 20; done; done
shift; exec "$HERE/produce.sh" "$@"
