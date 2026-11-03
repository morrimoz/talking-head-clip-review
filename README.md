# Talking-head clip review

**Category: Creative AI workflows | Format: Agent skill and local scripts**

Turn raw talking-head takes into approved selects. An agent transcribes on the machine, lines the takes up against a script, and builds one HTML page. A person marks Use or Skip. The agent assembles only those decisions into a picture render, an edit-decision list, and a CSV.

Source videos stay untouched. Audio is not uploaded for transcription.

## What is included

| File | Purpose |
| --- | --- |
| [SKILL.md](SKILL.md) | The review workflow, from inventory through the final listen |
| `scripts/transcribe.py` | Local Whisper transcription with word timestamps |
| `scripts/segment.py` | Draft picks for many takes of one script, or one long recording |
| `scripts/build_review.py` | Word-accurate spans and the HTML review page |
| `scripts/gaze.py` | Optional macOS look-away detection |
| `scripts/assemble.py` | Render, EDL, and CSV from the saved decisions |
| [references/setup.md](references/setup.md) | ffmpeg and Whisper install notes |

## Install

For Cursor:

```bash
mkdir -p ~/.cursor/skills
git clone https://github.com/morrimoz/talking-head-clip-review.git ~/.cursor/skills/talking-head-clip-review
```

For Claude Code, use `~/.claude/skills/talking-head-clip-review`. For Codex, use `~/.codex/skills/talking-head-clip-review`. Start a new agent session after installation.

Then run `scripts/check_deps.sh`. It needs ffmpeg and one local Whisper backend. It installs nothing. Gaze detection needs macOS.

## Example request

```text
Use talking-head-clip-review on the takes in ./footage.
Build the review page and wait for my Use/Skip file before rendering.
```

## Tradeoffs

The fluency score only breaks ties. A person still approves the selects. Gaze detection does not replace listening to each edit point. The scripts assume a local ffmpeg and will not send media to a hosted transcription API.

## Related tools

- [Video script and storyboard](https://github.com/morrimoz/video-script-storyboard) - Write the piece before anyone films it.
- [Directing motion films](https://github.com/morrimoz/directing-motion-films-with-claude-design) - Cut the approved selects into a designed film.

[MIT license](LICENSE)
