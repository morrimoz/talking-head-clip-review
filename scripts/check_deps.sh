#!/usr/bin/env bash
# Check what talking-head-clip-review needs. Prints install hints; installs nothing.
ok(){ printf '  ok   %s\n' "$*"; }; no(){ printf '  MISSING %s\n' "$*"; }
echo "talking-head-clip-review dependencies"
for b in ffmpeg ffprobe python3; do command -v $b >/dev/null && ok "$b ($(command -v $b))" || no "$b - brew install ffmpeg python"; done
ffmpeg -hide_banner -filters 2>/dev/null | grep -q silencedetect && ok "ffmpeg silencedetect" || no "ffmpeg silencedetect filter"
ffmpeg -hide_banner -encoders 2>/dev/null | grep -q h264_videotoolbox && ok "h264_videotoolbox (fast previews)" || echo "  info  no videotoolbox, previews use libx264"
ffmpeg -hide_banner -filters 2>/dev/null | grep -q drawtext && ok "drawtext" || echo "  info  no drawtext in this ffmpeg; scripts use drawbox/hue instead"
W=""
for p in /usr/bin/python3 "$(command -v python3)" /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  [ -x "$p" ] || continue
  for m in mlx_whisper faster_whisper whisper; do "$p" -c "import $m" 2>/dev/null && { W="$p:$m"; break 2; }; done
done
[ -n "$W" ] && ok "whisper backend ${W#*:} in ${W%%:*}  (run transcribe.py with ${W%%:*})" || no "whisper - Apple Silicon: /usr/bin/python3 -m pip install --user mlx-whisper ; else: python3 -m pip install faster-whisper"
ls -d ~/.cache/huggingface/hub/models--mlx-community--whisper-large-v3-turbo >/dev/null 2>&1 && ok "model whisper-large-v3-turbo cached" || echo "  info  model downloads on first run (~1.6GB)"
if [ "$(uname)" = Darwin ]; then command -v swiftc >/dev/null && ok "swiftc (gaze.py)" || echo "  info  no swiftc; skip gaze.py (xcode-select --install)"; else echo "  info  not macOS; gaze.py unavailable"; fi
df -h ~ | tail -1 | awk '{print "  disk  "$4" free"}'
