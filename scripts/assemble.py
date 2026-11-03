#!/usr/bin/env python3
"""Assemble the approved selects from the review decisions.

  assemble.py --work WORK --media SRC_DIR --decisions /path/to/<slug>-decisions.json --out SELECTS_DIR [--render] [--fps 30]
Reads WORK/picks_resolved.json (spans) + the decisions export. A clip is in when decision=='use', or when it was left
untouched and was the suggestion. Notes are NOT applied automatically: the agent reads them, edits picks.json
(cut ranges, in/out, audio_only, grade), re-runs build_review.py, then runs this again.
Writes SELECTS_DIR/selects.json, selects.csv, selects.edl (CMX3600, one event per span, source timecode) and,
with --render, selects.mp4 from the full-resolution sources (re-encoded, frame-accurate). Sources are never modified.
"""
import argparse, csv, json, os, subprocess, sys
ap = argparse.ArgumentParser()
for k in ('--work', '--media', '--decisions', '--out'): ap.add_argument(k, required=True)
ap.add_argument('--render', action='store_true'); ap.add_argument('--fps', type=float, default=30); ap.add_argument('--size', default='')
a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
P = json.load(open(os.path.join(a.work, 'picks_resolved.json'))); D = json.load(open(os.path.expanduser(a.decisions)))
POSE = json.load(open(os.path.join(a.work, 'pose.json'))) if os.path.exists(os.path.join(a.work, 'pose.json')) else {}
dec = {(c['beat'], c['i']): c for c in D['clips']}
def src(name):
    for ext in ('.mov', '.mp4', '.m4v', '.MOV', '.MP4', '.mkv', '.webm'):
        p = os.path.join(a.media, name + ext)
        if os.path.exists(p): return p
    sys.exit(f'source for {name} not found')
def tc(t, fps):
    f = int(round(t * fps)); n = int(round(fps))
    return f'{f // (3600 * n):02d}:{f // (60 * n) % 60:02d}:{f // n % 60:02d}:{f % n:02d}'
sel = []
for b in P['beats']:
    for i, c in enumerate(b['cands']):
        d = dec.get((b['id'], i), {}); use = d.get('use', bool(c.get('pick')))
        if not use or not c['spans']: continue
        f = P['takes'][c['take']]
        for s, e in c['spans']:
            away = [[max(s, x), min(e, y)] for x, y in POSE.get(f, []) if x < e and y > s]
            sel.append({'beat': b['id'], 'name': b['name'], 'take': c['take'], 'file': f, 'src': src(f), 'in': s, 'out': e,
                        'audio_only': bool(c.get('audio_only')), 'grade': c.get('grade'), 'look_away': away, 'note': d.get('note', ''), 'text': c['text']})
json.dump(sel, open(os.path.join(a.out, 'selects.json'), 'w'), indent=1)
with open(os.path.join(a.out, 'selects.csv'), 'w', newline='') as fh:
    w = csv.writer(fh); w.writerow(['#', 'beat', 'take', 'file', 'in', 'out', 'dur', 'audio_only', 'look_away', 'note', 'text'])
    for n, x in enumerate(sel, 1): w.writerow([n, x['beat'], x['take'], x['file'], f"{x['in']:.3f}", f"{x['out']:.3f}", f"{x['out'] - x['in']:.2f}", x['audio_only'], x['look_away'], x['note'], x['text']])
rec = 3600.0; L = [f"TITLE: {P.get('episode', 'Selects')}", 'FCM: NON-DROP FRAME', '']
for n, x in enumerate(sel, 1):
    d = x['out'] - x['in']; reel = x['file'][:8].upper().replace(' ', '_')
    L += [f"{n:03d}  {reel:<8} {'A   ' if x['audio_only'] else 'AA/V'}  C        {tc(x['in'], a.fps)} {tc(x['out'], a.fps)} {tc(rec, a.fps)} {tc(rec + d, a.fps)}",
          f"* FROM CLIP NAME: {os.path.basename(x['src'])}", f"* BEAT {x['beat']} {x['name']}"]
    if x['look_away']: L.append(f"* LOOK-AWAY (cover with screen, keep audio): {x['look_away']}")
    if x['note']: L.append(f"* NOTE: {x['note']}")
    L.append(''); rec += d
open(os.path.join(a.out, 'selects.edl'), 'w').write('\n'.join(L))
total = sum(x['out'] - x['in'] for x in sel)
print(f'{len(sel)} spans from {len({(x["beat"], x["take"]) for x in sel})} clips, {total:.1f}s -> {a.out}')
if a.render and sel:
    if a.size: W, H = a.size.split('x')
    else:   # displayed size of the first clip (iPhone portrait files carry a 90-degree rotation)
        st = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height:stream_side_data=rotation',
                                        '-of', 'json', sel[0]['src']], capture_output=True, text=True).stdout)['streams'][0]
        W, H = st['width'], st['height']
        if abs(int(next((d.get('rotation', 0) for d in st.get('side_data_list', [])), 0))) % 180 == 90: W, H = H, W
    ins, pre = [], ''
    for n, x in enumerate(sel):
        ins += ['-ss', f"{x['in']:.3f}", '-t', f"{x['out'] - x['in']:.3f}", '-i', x['src']]
        vf = [f'scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={a.fps}'] + ([x['grade']] if x['grade'] else [])
        pre += f"[{n}:v]{','.join(vf)}[v{n}];[{n}:a]aresample=48000[a{n}];"
    fc = pre + ''.join(f'[v{n}][a{n}]' for n in range(len(sel))) + f'concat=n={len(sel)}:v=1:a=1[v][a]'
    o = os.path.join(a.out, 'selects.mp4')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', *ins, '-filter_complex', fc, '-map', '[v]', '-map', '[a]', '-c:v', 'libx264', '-crf', '18', '-preset', 'medium',
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', o], check=True)
    print('rendered', o)
