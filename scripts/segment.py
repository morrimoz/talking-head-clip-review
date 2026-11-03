#!/usr/bin/env python3
"""Draft picks.json from transcripts: one beat per script line (takes mode) or per talking point (single mode).

  takes mode : segment.py takes  --tx WORK/tx --script script.txt --out WORK/picks.json A=take-a B=take-b ...
  single mode: segment.py single --tx WORK/tx --out WORK/picks.json A=long_video [--gap 1.2 --min 4 --max 40]

script.txt: one line or talking point per line. Optional "id | name | text". Blank lines and # comments ignored.
The draft is a starting point. The agent then reads the .txt transcripts, fixes in/out points, adds `cut`
ranges for restarts and writes a real `why` per candidate. The draft is not the edit.
"""
import argparse, json, re, difflib

FILLERS = ['um', 'uh', 'erm', 'ah', 'like', 'you know', 'i mean', 'sort of', 'kind of', 'basically', 'actually', 'so yeah']
norm = lambda s: re.sub(r"[^a-z0-9' ]", '', s.lower()).split()

def words(tx, f):
    w = []
    for s in json.load(open(f'{tx}/{f}.json'))['segments']:
        w += [x for x in s.get('words', []) if x['word'].strip()]
    return w

def signals(ws):
    if not ws: return {}
    toks = [t for w in ws for t in norm(w['word'])]
    txt = ' ' + ' '.join(toks) + ' '
    fill = sum(txt.count(f' {f} ') for f in FILLERS)
    rep = sum(1 for i in range(1, len(toks)) if toks[i] == toks[i - 1]) + \
          sum(1 for i in range(3, len(toks)) if toks[i - 1:i + 1] == toks[i - 3:i - 1])
    gaps = [b['start'] - a['end'] for a, b in zip(ws, ws[1:])]
    dur = ws[-1]['end'] - ws[0]['start']
    lowc = sum(1 for w in ws if w.get('probability', 1) < 0.5)
    return {'dur': round(dur, 1), 'wpm': round(len(toks) / dur * 60) if dur > 0 else 0, 'fillers': fill,
            'repeats': rep, 'long_pauses': sum(1 for g in gaps if g > 0.8),
            'max_pause': round(max(gaps), 2) if gaps else 0, 'low_conf': lowc}

def score(sig, match=1.0):
    # fluency: higher is better; used only to pre-tick a suggestion
    return match * 10 - sig.get('fillers', 0) * 1.0 - sig.get('repeats', 0) * 1.5 - sig.get('long_pauses', 0) * 0.7 - sig.get('low_conf', 0) * 0.3

def why(sig, match=None):
    bits = []
    if match is not None: bits.append(f'matches script {match:.0%}')
    if sig.get('repeats'): bits.append(f"{sig['repeats']} possible restart(s)")
    if sig.get('fillers'): bits.append(f"{sig['fillers']} filler(s)")
    if sig.get('long_pauses'): bits.append(f"{sig['long_pauses']} pause(s) > 0.8s")
    return 'Auto: ' + (', '.join(bits) or 'clean') + '.'

def script_lines(p):
    out = []
    for i, l in enumerate([l.strip() for l in open(p) if l.strip() and not l.strip().startswith('#')]):
        parts = [x.strip() for x in l.split('|')]
        if len(parts) >= 3: out.append((parts[0], parts[1], parts[2]))
        else: out.append((f'{i + 1:02d}', ' '.join(l.split()[:5]), l))
    return out

def find_attempts(ws, line, thr):
    """Every attempt at `line` in one take (restarts give several). Sliding fuzzy match on word windows."""
    tgt = norm(line); n = len(tgt)
    if not n: return []
    toks = [(' '.join(norm(w['word'])), i) for i, w in enumerate(ws)]
    flat = [t for t, _ in toks]
    hits = []
    for L in sorted({max(2, int(n * k)) for k in (0.7, 0.85, 1.0, 1.15, 1.3)}):
        for i in range(0, max(1, len(flat) - L + 1)):
            sm = difflib.SequenceMatcher(None, tgt, flat[i:i + L], autojunk=False)
            if sm.real_quick_ratio() < thr or sm.quick_ratio() < thr: continue
            r = sm.ratio()
            if r >= thr: hits.append((r, i, i + L - 1))
    hits.sort(reverse=True); keep = []
    for r, a, b in hits:                      # non-overlapping, best first
        if all(b < ka or a > kb for _, ka, kb in keep): keep.append((r, a, b))
    return sorted(keep, key=lambda h: h[1])

def takes_mode(a, T):
    W = {k: words(a.tx, f) for k, f in T.items()}
    beats = []
    for bid, name, text in script_lines(a.script):
        cands = []
        for k, ws in W.items():
            for r, i, j in find_attempts(ws, text, a.thr):
                seg = ws[i:j + 1]; sig = signals(seg)
                cands.append({'take': k, 'in': round(max(0, seg[0]['start'] - 0.1), 2), 'out': round(seg[-1]['end'] + 0.15, 2),
                              'match': round(r, 2), 'signals': sig, 'why': why(sig, r), '_s': score(sig, r)})
        cands.sort(key=lambda c: -c['_s'])
        if cands: cands[0]['pick'] = True
        for c in cands: c.pop('_s')
        beats.append({'id': bid, 'name': name, 'script': text, 'cands': cands[:a.keep]})
    return beats

def single_mode(a, T):
    beats = []
    for k, f in T.items():
        ws = words(a.tx, f); cur = []
        def flush():
            if not cur: return
            sig = signals(cur); t = ''.join(w['word'] for w in cur).strip()
            beats.append({'id': f'{len(beats) + 1:02d}', 'name': ' '.join(t.split()[:6]) + '...', 'cands': [
                {'take': k, 'in': round(max(0, cur[0]['start'] - 0.1), 2), 'out': round(cur[-1]['end'] + 0.15, 2),
                 'signals': sig, 'why': why(sig), 'pick': score(sig) >= 7}]})
        for w in ws:
            if cur:
                gap = w['start'] - cur[-1]['end']; dur = cur[-1]['end'] - cur[0]['start']
                sentence_end = cur[-1]['word'].strip().endswith(('.', '?', '!'))
                if (gap >= a.gap and dur >= a.min) or dur >= a.max or (sentence_end and gap >= 0.6 and dur >= a.min * 2):
                    flush(); cur = []
            cur.append(w)
        flush()
    return beats

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['takes', 'single']); ap.add_argument('--tx', required=True)
    ap.add_argument('--out', required=True); ap.add_argument('--script'); ap.add_argument('--episode', default='Review')
    ap.add_argument('--thr', type=float, default=0.55); ap.add_argument('--keep', type=int, default=6)
    ap.add_argument('--gap', type=float, default=1.2); ap.add_argument('--min', type=float, default=4)
    ap.add_argument('--max', type=float, default=40); ap.add_argument('takes', nargs='+', help='KEY=transcript-name')
    a = ap.parse_args()
    T = dict(x.split('=', 1) for x in a.takes)
    if a.mode == 'takes' and not a.script: ap.error('takes mode needs --script')
    beats = takes_mode(a, T) if a.mode == 'takes' else single_mode(a, T)
    json.dump({'episode': a.episode, 'mode': a.mode, 'takes': T, 'beats': beats}, open(a.out, 'w'), indent=1)
    print(len(beats), 'beats', sum(len(b['cands']) for b in beats), 'candidates', sum(1 for b in beats for c in b['cands'] if c.get('pick')), 'suggested picks')

if __name__ == '__main__': main()
