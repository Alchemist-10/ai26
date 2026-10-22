#!/usr/bin/env bash
# Render Manim scenes -> site/public/clips/manim-*.{mp4,webm,png}
# Usage: ./render.sh [SceneClass ...]   (default: all)
set -euo pipefail
cd "$(dirname "$0")"
[ -x .venv/bin/manim ] || { uv venv -q .venv --python 3.12 && uv pip install -q --python .venv/bin/python manim; }
out=../public/clips; mkdir -p "$out"
declare -A names=([Pipeline]=pipeline [Consensus]=consensus [Tracking]=tracking [Scaling]=scaling [Scheduler]=scheduler)
scenes=("${@:-Pipeline Consensus Tracking Scaling Scheduler}"); scenes=(${scenes[*]})
for s in "${scenes[@]}"; do
  n=manim-${names[$s]}
  .venv/bin/manim render -q h -r 1920,1080 --fps 30 --disable_caching --progress_bar none -o "$n" scenes.py "$s" >/dev/null
  src=media/videos/scenes/1080p30/$n.mp4
  ffmpeg -loglevel error -y -i "$src" -an -vf scale=1280:720:flags=lanczos -c:v libx264 -preset slow -crf 26 \
    -pix_fmt yuv420p -movflags +faststart "$out/$n.mp4"
  ffmpeg -loglevel error -y -i "$src" -an -vf scale=1280:720:flags=lanczos -c:v libvpx-vp9 -crf 38 -b:v 0 \
    -row-mt 1 -pix_fmt yuv420p "$out/$n.webm"
  # poster: last settled frame, just before the outro fade (outro = 1.1 s)
  d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$src")
  ffmpeg -loglevel error -y -ss "$(awk "BEGIN{print $d-1.25}")" -i "$src" -frames:v 1 -vf scale=1280:720:flags=lanczos "$out/$n.png"
  printf '%s %.1fs mp4=%s webm=%s\n' "$n" "$d" "$(du -h "$out/$n.mp4" | cut -f1)" "$(du -h "$out/$n.webm" | cut -f1)"
done
