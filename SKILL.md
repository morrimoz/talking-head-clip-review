---
name: talking-head-clip-review
description: Use when someone has filmed themselves talking to camera and needs the best clips picked. Covers multiple takes of the same script (align every take per script line and compare them side by side) and one long recording (cut every talking point into keep-or-skip clips). Transcribes locally with word timestamps, trims pauses and restarts, scores fluency, builds an HTML review page with playable clips, Use/Skip and notes, exports decisions to JSON, then assembles the selects as an ffmpeg render, EDL and CSV. Plain shell plus python, so it works in Claude Code, Codex and Cursor.
---

# Talking-head clip review

Turn raw talking-head footage into approved selects without anyone scrubbing through it by hand. The agent transcribes, aligns and suggests. A person approves on one page. The agent then assembles exactly what was approved.

Transcription stays on the machine. Source videos are never modified.

## Hard rules
- Never modify, move or re-export the source videos. Everything is in/out points plus derived files.
- Never delete the user's footage or empty the Trash. If disk is tight, say so and let them do it.
- Work out of a scratch folder. Only previews, posters, the review page and selects go next to the media.
- Do not invent wording. Clip text comes from the transcript. Optional phrase corrections live in a JSON map passed with `--fix` (see `references/term-corrections.example.json`). Do not apply the example file.
- Check facts said on camera (times, numbers, "10 minutes ago") against the real recording before picking them.
- No monitor glances, mic bumps, clicks or breath noises in a kept span. Re-run gaze (step 5) and listen to every edit point after any re-edit, not only at the first selects. Mute or cut the noise, never the word next to it.
- Pickups and re-recorded lines must match the main take's tone, level and room (same mic, gain, distance, EQ and denoise). Flag a line that will sound muffled or boxed-in instead of shipping it.
- Use hyphens, not em dashes, in anything you write for the user.
- Word boundaries are hard limits, even when a prompt asks for tight cuts or gaze trims. Clips get a 0.15s pre-roll and a 0.25s tail around Whisper's word times (its word edges are often early or late), clamped so they never run into a neighbouring word. Pause and gaze trims only cut inside gaps between words and keep at least 0.1s next to each word. If a look-away overlaps a spoken word, keep the word and flag it (`away_words`, red border in the stringout), never cut it. Use `build_review.py --gaze-trim` for edge trims instead of writing your own trimming script. Hand-set `exact_spans` are pushed back out to word edges too.

## Setup (once per machine)
Run `scripts/check_deps.sh`. It needs ffmpeg, ffprobe, python3 and one whisper backend. Swift is optional for the gaze step. Install steps: [references/setup.md](references/setup.md).

## Layout
```
WORK/                      scratch folder, for example ./talk/
  tx/<take>.wav|json|txt   16 kHz mono audio, whisper JSON with words, readable transcript
  picks.json               beats + candidates (agent edits this)
  picks_resolved.json      word-accurate spans, text, durations (generated)
  pose.json                look-away intervals (optional, macOS)
REVIEW/                    next to the media, for example ./review/
  previews/<take>.mp4      540p H.264 copies for the page
  posters/<beat>-<i>.jpg
  "<Title> - take review.html"
  "<Title> - picks stringout (540p).mp4"
SELECTS/                   selects.json, selects.csv, selects.edl, selects.mp4
```
Name the episode after the piece, for example `launch-01`. Keep take keys short (A, B, C) and map them to file names in `picks.json`.

## Steps
1. **Inventory.** `ffprobe` every take (duration, size, fps, rotation). Phone footage is often variable frame rate and portrait. Previews and renders normalise it. Ask which files are the graded exports to cut, and which are camera originals to ignore.
2. **Transcribe.** `python3 scripts/transcribe.py --out WORK/tx TAKE...`. Use the interpreter `check_deps.sh` reported if the Whisper package is not on the default `python3`. If files are still exporting, use `--watch FOLDER --expect N` in the background: it waits until each file has stopped growing for 30s. Preferred model on Apple Silicon: `mlx-community/whisper-large-v3-turbo`, word timestamps, with `condition_on_previous_text` off. Set `--lang` when the speech is not English.
3. **Draft the picks.**
   - Mode (a), takes of one script: write `WORK/script.txt` with one line or talking point per line (`id | name | text` if you want ids). Run `python3 scripts/segment.py takes --tx WORK/tx --script WORK/script.txt --out WORK/picks.json A=take-a B=take-b ...`. It finds every attempt at each line in every take (fuzzy word-window match, so restarts appear as separate candidates) and pre-ticks the most fluent one.
   - Mode (b), one long video: `python3 scripts/segment.py single --tx WORK/tx --out WORK/picks.json A=long-take` cuts at pauses of 1.2s or more and at sentence ends, into clips of 4-40s.
   - Then read the `.txt` transcripts yourself. Fix in/out points, add `cut: [[a,b]]` for restarts and glitches, merge or split beats, and write a real `why` per candidate (clean, restart, wrong word, matches the screen recording). Prefer the take that was filmed with the matching screen recording. The auto score only breaks ties.
4. **Build the page.** `python3 scripts/build_review.py --work WORK --media SRC --out REVIEW --title "launch-01" --stringout`. Spans are split at word gaps over 0.6s and tightened with `silencedetect -35dB / 0.35s`. Add `keep_pauses: true` on a candidate to skip that. Padding flags: `--pre 0.15 --tail 0.25 --guard 0.1`. Pass `--fix path/to/corrections.json` only when you have a real phrase map. Open the HTML in the browser. Videos load on click, so the page opens fast.
5. **Optional, macOS: gaze.** `python3 scripts/gaze.py --work WORK --review REVIEW`, then re-run step 4 with `--stringout --gaze-trim`. Look-away frames get a red border in the stringout. Cover them later with screen footage and keep the audio.
6. **Human review.** Tell the user what to do: Play, Use/Skip, notes, then "Save decisions (JSON)". It downloads `<slug>-decisions.json`. "Copy as text" is the fallback. Untouched cards keep the suggestion.
7. **Apply notes.** Read the decisions JSON. Turn every note into picks.json edits: `cut`, `in`/`out`, `audio_only: true`, `grade: "eq=gamma=1.28:brightness=0.03"`, `optional: true`. Keep a backup first (`cp picks.json picks.before-notes.json`). Re-run step 4 and summarise each note and what you did.
8. **Assemble.** `python3 scripts/assemble.py --work WORK --media SRC --decisions /path/to/<slug>-decisions.json --out SELECTS --render`. You get a frame-accurate full-res `selects.mp4`, a CMX3600 `selects.edl` (Premiere, Resolve, Final Cut via import), `selects.csv` and `selects.json` with look-away ranges and notes.
9. **Verify.** Listen to every edit point (no clipped first or last syllable, no glance, no noise). `ffprobe` the render duration against the sum in `selects.json`, and make a contact sheet: `ffmpeg -i selects.mp4 -vf "fps=1/6,scale=180:-1,tile=10x3" -frames:v 1 sheet.jpg`. View it, then report the length, what changed and what still needs the user.

## picks.json shape
```json
{"episode":"launch-01","mode":"takes","takes":{"A":"take-a","B":"take-b"},
 "beats":[{"id":"01a","name":"Hook","script":"...","cands":[
   {"take":"B","in":0.82,"out":21.2,"pick":true,"why":"Clean, matches the screen.","cut":[[51.4,53.82]],
    "note":"","audio_only":false,"grade":null,"optional":false,"signals":{"dur":20.1,"wpm":162,"fillers":0,"repeats":0}}]}]}
```

## Tips
- Spot-check any word timing with the transcript JSON. A dump of `word@start-end` around a note is the fastest way to place a cut.
- If ffmpeg has no `drawtext`, mark frames with `drawbox` or `hue`, not text.
- Big renders: check free disk first. 4K takes add up fast.
