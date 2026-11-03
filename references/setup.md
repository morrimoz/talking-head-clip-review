# Setup

Needs ffmpeg, ffprobe, python3, and one local Whisper backend. Gaze detection is optional and macOS-only.

- macOS, Apple Silicon: `brew install ffmpeg`, then `/usr/bin/python3 -m pip install --user mlx-whisper`. The first transcription downloads the model (about 1.6GB). If `mlx-whisper` is installed for the system `python3` rather than Homebrew `python3`, run `transcribe.py` with that interpreter. `scripts/check_deps.sh` prints which one it found.
- Linux or Intel Mac: `python3 -m pip install faster-whisper` (or `openai-whisper`). `transcribe.py` uses whichever backend imports.
- Gaze detection: macOS only, needs Xcode command line tools (`xcode-select --install`).
- Some ffmpeg builds omit `drawtext`. The scripts mark frames with `drawbox` or `hue` instead.
- Run `scripts/check_deps.sh` to confirm. It installs nothing.

The other scripts use the Python standard library. Open the HTML review page with `open` on macOS or `xdg-open` on Linux. No specific coding agent is required.
