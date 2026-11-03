#!/usr/bin/env python3
"""Transcribe talking-head takes with word timestamps (local, nothing uploaded).

Usage:
  transcribe.py --out WORK/tx TAKE.mov [TAKE2.mov ...]
  transcribe.py --out WORK/tx --watch FOLDER [--expect 12]   # transcribe each file once its export finishes
Writes WORK/tx/<name>.wav (16 kHz mono), <name>.json (full whisper result with words) and <name>.txt.
Skips any take that already has a .json, so it is safe to re-run.
Backend: mlx-whisper (Apple Silicon) with mlx-community/whisper-large-v3-turbo, else faster-whisper, else openai-whisper.
"""
import argparse, json, os, subprocess, sys, time

VID = ('.mov', '.mp4', '.m4v', '.mkv', '.webm', '.wav', '.m4a', '.mp3')

def log(*a): print(time.strftime('%H:%M:%S'), *a, flush=True)

def backend(model):
    try:
        import mlx_whisper
        def run(wav):
            return mlx_whisper.transcribe(wav, path_or_hf_repo=model or 'mlx-community/whisper-large-v3-turbo',
                                          word_timestamps=True, language='en', condition_on_previous_text=False)
        return 'mlx-whisper', run
    except ImportError: pass
    try:
        from faster_whisper import WhisperModel
        m = WhisperModel(model or 'large-v3-turbo', compute_type='auto')
        def run(wav):
            segs, _ = m.transcribe(wav, word_timestamps=True, language='en', condition_on_previous_text=False)
            out = []
            for s in segs:
                out.append({'start': s.start, 'end': s.end, 'text': s.text,
                            'words': [{'word': w.word, 'start': w.start, 'end': w.end, 'probability': w.probability} for w in (s.words or [])]})
            return {'segments': out, 'text': ''.join(s['text'] for s in out)}
        return 'faster-whisper', run
    except ImportError: pass
    try:
        import whisper
        m = whisper.load_model(model or 'turbo')
        return 'openai-whisper', lambda wav: m.transcribe(wav, word_timestamps=True, language='en', condition_on_previous_text=False)
    except ImportError:
        sys.exit('No whisper backend. Install one: /usr/bin/python3 -m pip install --user mlx-whisper  (see references/setup.md)')

def one(path, out, run):
    b = os.path.splitext(os.path.basename(path))[0]
    if os.path.exists(f'{out}/{b}.json'): log('skip (done)', b); return
    wav = f'{out}/{b}.wav'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', path, '-vn', '-ac', '1', '-ar', '16000', wav], check=True)
    log('transcribing', b)
    r = run(wav)
    r['source'] = os.path.abspath(path)
    json.dump(r, open(f'{out}/{b}.json', 'w'))
    with open(f'{out}/{b}.txt', 'w') as t:
        for s in r['segments']: t.write(f"[{s['start']:7.2f}-{s['end']:7.2f}] {s['text'].strip()}\n")
    log('done', b, len(r['segments']), 'segments')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True); ap.add_argument('--model'); ap.add_argument('--watch')
    ap.add_argument('--expect', type=int, default=0); ap.add_argument('files', nargs='*')
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    name, run = backend(a.model); log('backend', name)
    if not a.watch:
        for f in a.files: one(f, a.out, run)
        return
    seen = {}; log('watching', a.watch)
    while True:
        for f in sorted(os.listdir(a.watch)):
            if not f.lower().endswith(VID): continue
            p = os.path.join(a.watch, f); b = os.path.splitext(f)[0]
            if os.path.exists(f'{a.out}/{b}.json'): continue
            sz = os.path.getsize(p); prev = seen.get(f)
            seen[f] = (sz, time.time()) if not prev or prev[0] != sz else prev
            if time.time() - seen[f][1] < 30: continue          # still being written (Photos export)
            if subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', p], capture_output=True).returncode: continue
            one(p, a.out, run)
        done = len([x for x in os.listdir(a.out) if x.endswith('.json')])
        if a.expect and done >= a.expect: log('ALL DONE'); break
        time.sleep(15)

if __name__ == '__main__': main()
