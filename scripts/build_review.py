#!/usr/bin/env python3
"""Resolve picks.json to word-accurate spans and build the HTML review page (plus an optional stringout).

build_review.py --work WORK --media SRC_DIR --out REVIEW_DIR [--title "launch-01"] [--stringout] [--fix corrections.json]
WORK holds picks.json and tx/. Writes WORK/picks_resolved.json, REVIEW_DIR/previews/*.mp4 (540p, made once),
REVIEW_DIR/posters/*.jpg and "REVIEW_DIR/<title> - take review.html". Never touches the source videos.
"""
import argparse, html, json, os, re, shutil, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
E = html.escape
HERE = os.path.dirname(os.path.abspath(__file__))

ap = argparse.ArgumentParser()
ap.add_argument('--work', required=True); ap.add_argument('--media', required=True); ap.add_argument('--out', required=True)
ap.add_argument('--title', default=None); ap.add_argument('--stringout', action='store_true'); ap.add_argument('--fix')
ap.add_argument('--pause', type=float, default=0.6, help='split spans at word gaps longer than this')
ap.add_argument('--sil-db', default='-35dB'); ap.add_argument('--sil-d', type=float, default=0.35)
# Word boundaries are hard limits. Whisper word edges are often early/late, so pad and never cut inside a word.
ap.add_argument('--pre', type=float, default=0.15, help='pre-roll before the first word of a span')
ap.add_argument('--tail', type=float, default=0.25, help='tail after the last word of a span')
ap.add_argument('--guard', type=float, default=0.1, help='minimum audio kept around any word by pause or gaze trims')
ap.add_argument('--gaze-trim', action='store_true', help='trim look-away (WORK/pose.json) at span edges, only inside silent gaps')
a = ap.parse_args()
TX = os.path.join(a.work, 'tx'); OUT = a.out.rstrip('/') + '/'
os.makedirs(OUT + 'previews', exist_ok=True); os.makedirs(OUT + 'posters', exist_ok=True)
P = json.load(open(os.path.join(a.work, 'picks.json')))
TITLE = a.title or P.get('episode', 'Review')
FIX = json.load(open(a.fix)) if a.fix else {}
ENC = ['-c:v', 'h264_videotoolbox', '-b:v', '2500k'] if 'h264_videotoolbox' in subprocess.run(
    ['ffmpeg', '-hide_banner', '-encoders'], capture_output=True, text=True).stdout else ['-c:v', 'libx264', '-crf', '26', '-preset', 'veryfast']

def src(name):
    for ext in ('.mov', '.mp4', '.m4v', '.MOV', '.MP4', '.mkv', '.webm'):
        p = os.path.join(a.media, name + ext)
        if os.path.exists(p): return p
    j = os.path.join(TX, name + '.json')
    if os.path.exists(j) and json.load(open(j)).get('source'): return json.load(open(j))['source']
    sys.exit(f'source video for {name} not found in {a.media}')

words = {}
for k, f in P['takes'].items():
    words[k] = [x for s in json.load(open(os.path.join(TX, f + '.json')))['segments'] for x in s.get('words', []) if x['word'].strip()]

def spans(c):
    """Word-accurate spans: drop `cut` ranges, split at pauses > --pause, pad with --pre/--tail clamped to neighbour words."""
    allw = words[c['take']]
    ws = [w for w in allw if w['start'] >= c['in'] - 0.3 and w['end'] <= c['out'] + 0.3
          and not any(x <= w['start'] < y for x, y in c.get('cut', []))]
    if not ws: return [], '', []
    groups = [[ws[0]]]
    for w in ws[1:]:
        if w['start'] - groups[-1][-1]['end'] > a.pause: groups.append([w])
        else: groups[-1].append(w)
    out = []
    for g in groups:
        i, j = allw.index(g[0]), allw.index(g[-1])
        lo = allw[i - 1]['end'] + 0.02 if i > 0 else 0          # never run into the neighbouring word
        hi = allw[j + 1]['start'] - 0.02 if j + 1 < len(allw) else g[-1]['end'] + a.tail
        out.append((max(lo, g[0]['start'] - a.pre, 0), min(hi, g[-1]['end'] + a.tail) if hi > g[-1]['end'] else g[-1]['end']))
    t = ''.join(w['word'] for w in ws).strip()
    for x, y in FIX.items(): t = t.replace(x, y)
    return [(round(x, 3), round(y, 3)) for x, y in out], t, ws

SIL = {}
def silences(f):
    """Pauses (mostly glances at the script monitor) from the audio, not the transcript."""
    if f not in SIL:
        r = subprocess.run(['ffmpeg', '-v', 'info', '-i', os.path.join(TX, f + '.wav'), '-af', f'silencedetect=n={a.sil_db}:d={a.sil_d}', '-f', 'null', '-'],
                           capture_output=True, text=True).stderr
        SIL[f] = [(float(e) - float(d), float(e)) for e, d in re.findall(r'silence_end: ([0-9.]+) \| silence_duration: ([0-9.]+)', r)]
    return SIL[f]

def tighten(f, sp, ws):
    """Remove silences only inside gaps between words, keeping --guard seconds of audio next to each word."""
    gaps = [(p['end'] + a.guard, n['start'] - a.guard) for p, n in zip(ws, ws[1:])]
    out = []
    for x, y in sp:
        cur = x
        for s, e in silences(f):
            for ga, gb in gaps:
                cs, ce = max(s, ga, cur), min(e, gb, y)
                if ce - cs > 0.12: out.append((cur, cs)); cur = ce
        out.append((cur, y))
    return [(round(x, 3), round(y, 3)) for x, y in out if y - x > 0.12]

def gaze_edges(f, sp, ws):
    """Trim look-away at span edges, never past --guard before the first word or after the last word."""
    if not sp or not ws: return sp
    AW = POSE.get(f, [])
    (s0, e0), (s1, e1) = sp[0], sp[-1]
    first = min((w['start'] for w in ws if w['start'] >= s0 - 0.01), default=s0)
    last = max((w['end'] for w in ws if w['end'] <= e1 + 0.01), default=e1)
    for x, y in AW:
        if x <= s0 < y: s0 = min(max(s0, y), first - a.guard)
        if x < e1 <= y: e1 = max(min(e1, x), last + a.guard)
    sp = list(sp); sp[0] = (round(max(sp[0][0], s0), 3), sp[0][1]); sp[-1] = (sp[-1][0], round(min(sp[-1][1], e1), 3))
    return sp

def enforce(sp, allw):
    """Hard guard for any span (generated or hand-set exact_spans): an edge inside a word moves out to include it,
    with up to --guard of padding but never into the neighbouring word. Overlapping spans are merged."""
    out = []
    for x, y in sp:
        for i, w in enumerate(allw):
            if w['start'] - a.guard < x < w['end']:
                x = max(w['start'] - a.guard, allw[i - 1]['end'] if i else 0, 0); break
        for i, w in enumerate(allw):
            if w['start'] < y < w['end'] + a.guard:
                y = min(w['end'] + a.guard, allw[i + 1]['start'] if i + 1 < len(allw) else 1e9); break
        if out and x <= out[-1][1]: out[-1] = (out[-1][0], max(out[-1][1], y))
        else: out.append((x, y))
    return [(round(x, 3), round(y, 3)) for x, y in out]

POSE = json.load(open(os.path.join(a.work, 'pose.json'))) if os.path.exists(os.path.join(a.work, 'pose.json')) else {}
for b in P['beats']:
    for c in b['cands']:
        f = P['takes'][c['take']]
        c['spans'], c['text'], ws = spans(c)
        if c.get('exact_spans'): c['spans'] = [tuple(x) for x in c['exact_spans']]
        elif not c.get('keep_pauses'): c['spans'] = tighten(f, c['spans'], ws)
        if a.gaze_trim and not c.get('exact_spans'): c['spans'] = gaze_edges(f, c['spans'], ws)
        c['spans'] = enforce(c['spans'], words[c['take']])
        # look-away that overlaps a spoken word is kept and flagged, never cut
        c['away_words'] = [w['word'].strip() for w in ws for x, y in POSE.get(f, []) if x < w['end'] and y > w['start']
                           and any(s <= w['start'] and w['end'] <= e for s, e in c['spans'])]
        c['dur'] = round(sum(e - s for s, e in c['spans']), 1)
json.dump(P, open(os.path.join(a.work, 'picks_resolved.json'), 'w'), indent=1)

# 540p previews (once per take) and one poster per card
def preview(f):
    o = OUT + 'previews/' + f + '.mp4'
    if os.path.exists(o): return
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', src(f), '-vf', "scale='if(gt(iw,ih),960,540)':-2,fps=30", *ENC,
                    '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', o], check=True)
with ThreadPoolExecutor(4) as ex: list(ex.map(preview, sorted(set(P['takes'].values()))))
jobs = [(b['id'], i, P['takes'][c['take']], c['spans'][0][0] + 0.4) for b in P['beats'] for i, c in enumerate(b['cands']) if c['spans']]
def poster(j):
    bid, i, f, t = j
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{t:.2f}', '-i', OUT + 'previews/' + f + '.mp4', '-frames:v', '1', '-q:v', '5', OUT + f'posters/{bid}-{i}.jpg'])
with ThreadPoolExecutor(6) as ex: list(ex.map(poster, jobs))

if a.stringout:   # picks in order, from previews, pauses already trimmed; graded / audio-only / look-away marked
    parts = [(P['takes'][c['take']], s, e, c.get('grade'), c.get('audio_only'), c.get('away', []))
             for b in P['beats'] for c in b['cands'] if c.get('pick') for s, e in c['spans']]
    ins, pre = [], ''
    for n, (f, s, e, g, ao, aw) in enumerate(parts):
        ins += ['-ss', f'{s:.3f}', '-t', f'{e - s:.3f}', '-i', OUT + 'previews/' + f + '.mp4']
        vf = ['scale=540:960:force_original_aspect_ratio=decrease,pad=540:960:(ow-iw)/2:(oh-ih)/2,setsar=1']
        if g: vf.append(g)
        if ao: vf.append('hue=s=0,drawbox=c=black@0.6:t=fill')            # grey = audio only, screen goes here
        for x, y in POSE.get(f, []):                                        # red border = looking away from camera
            if x < e and y > s: vf.append(f"drawbox=x=0:y=0:w=iw:h=ih:c=red@0.9:t=14:enable='between(t,{max(0, x - s):.2f},{min(e, y) - s:.2f})'")
        pre += f'[{n}:v]{",".join(vf)}[v{n}];'
    if parts:
        fc = pre + ''.join(f'[v{n}][{n}:a]' for n in range(len(parts))) + f'concat=n={len(parts)}:v=1:a=1[v][a]'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', *ins, '-filter_complex', fc, '-map', '[v]', '-map', '[a]', *ENC, '-c:a', 'aac',
                        '-movflags', '+faststart', OUT + f'{TITLE} - picks stringout (540p).mp4'], check=True)
    print('stringout parts', len(parts))

KEY = re.sub(r'[^a-z0-9]+', '-', TITLE.lower()).strip('-') + '-review-v1'
rows = ''
for b in P['beats']:
    cards = ''
    for i, c in enumerate(b['cands']):
        if not c['spans']: continue
        sig = c.get('signals', {})
        chips = ''.join(f'<span class="chip">{E(k)} {E(str(v))}</span>' for k, v in
                        [('dur', f"{c['dur']}s"), ('wpm', sig.get('wpm')), ('fillers', sig.get('fillers')), ('restarts', sig.get('repeats')),
                         ('pauses', sig.get('long_pauses')), ('match', f"{c['match']:.0%}" if 'match' in c else None)] if v not in (None, ''))
        cards += f'''<div class="c{' pk' if c.get('pick') else ''}" data-beat="{E(b['id'])}" data-i="{i}" data-take="{E(c['take'])}" data-file="{E(P['takes'][c['take']])}" data-in="{c['in']}" data-out="{c['out']}">
<div class="top"><span class="tk">Take {E(c['take'])} · {E(P['takes'][c['take']])} · {c['in']:.0f}s</span>{'<span class="mine">Suggested</span>' if c.get('pick') else ''}</div>
<video preload="none" poster="posters/{E(b['id'])}-{i}.jpg" data-src="previews/{E(P['takes'][c['take']])}.mp4" data-spans='{json.dumps(c['spans'])}' playsinline></video>
<div class="ctl"><button class="play">Play</button><button class="dec use" data-d="use">Use</button><button class="dec skip" data-d="skip">Skip</button></div>
<div class="chips">{chips}</div>
<p class="tx">&ldquo;{E(c['text'])}&rdquo;</p><p class="why">{('<b>Look-away on words (kept):</b> ' + E(', '.join(dict.fromkeys(c['away_words']))) + '. ') if c.get('away_words') else ''}{E(c.get('why', ''))}{(' <b>Note:</b> ' + E(c['note'])) if c.get('note') else ''}</p>
<textarea placeholder="Notes (e.g. cut the restart, audio only, brighten)"></textarea></div>'''
    script = f'<p class="scr">Script: {E(b["script"])}</p>' if b.get('script') else ''
    rows += f'<section><h2>{E(b["id"])} · {E(b["name"])}</h2>{script}<div class="grid">{cards}</div></section>'
tpl = open(os.path.join(HERE, 'review_template.html')).read()
page = tpl.replace('__TITLE__', E(TITLE)).replace('__ROWS__', rows).replace('__KEY__', KEY).replace('__MODE__', P.get('mode', 'takes'))
name = OUT + f'{TITLE} - take review.html'
open(name, 'w').write(page)
print('page written:', name)
print('decisions export will download as:', KEY.replace('-review-v1', '') + '-decisions.json')
