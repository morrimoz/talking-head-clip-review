#!/usr/bin/env python3
"""Optional (macOS only): find frames where the speaker looks away from camera (e.g. at a script monitor).

  gaze.py --work WORK --review REVIEW_DIR [--fps 10] [--delta 0.17] [--th take-a=0.2]
Compiles pose.swift once into WORK/bin/pose, scans every picked span on the 540p previews, and writes
WORK/pose.json = {take_file: [[start, end], ...]} of look-away intervals (source seconds).
Threshold: abs(yaw - that take's median yaw) > --delta, or yaw > per-take --th. A desk setup often has the camera near yaw 0 and a side monitor higher; pass --th when the median is a poor camera baseline. build_review --stringout draws these as red borders; assemble lists them so
the editor covers them with screen recording and keeps the audio.
This script only detects. Trimming is done by build_review.py --gaze-trim, which never cuts inside a word.
"""
import argparse, json, os, statistics, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser(); ap.add_argument('--work', required=True); ap.add_argument('--review', required=True)
ap.add_argument('--fps', type=float, default=10); ap.add_argument('--delta', type=float, default=0.17); ap.add_argument('--th', nargs='*', default=[])
ap.add_argument('--all', action='store_true', help='scan every candidate, not only picks')
a = ap.parse_args()
if sys.platform != 'darwin': sys.exit('gaze.py needs macOS Vision; skip this step on other systems.')
B = os.path.join(a.work, 'bin', 'pose'); os.makedirs(os.path.dirname(B), exist_ok=True)
if not os.path.exists(B): subprocess.run(['swiftc', '-O', os.path.join(HERE, 'pose.swift'), '-o', B], check=True)
P = json.load(open(os.path.join(a.work, 'picks_resolved.json'))); TH = dict((k, float(v)) for k, v in (x.split('=') for x in a.th))
rows = {}
for b in P['beats']:
    for c in b['cands']:
        if not (a.all or c.get('pick')) or c.get('audio_only'): continue
        f = P['takes'][c['take']]
        for s, e in c['spans']:
            out = subprocess.run([B, os.path.join(a.review, 'previews', f + '.mp4'), str(s), str(e), str(a.fps)], capture_output=True, text=True).stdout
            rows.setdefault(f, []).extend((float(t), float(y)) for t, y in (l.split() for l in out.splitlines() if l and 'nan' not in l))
res = {}
for f, r in rows.items():
    if not r: continue
    med = statistics.median(y for _, y in r)
    flag = sorted(t for t, y in r if ((y > TH[f]) if f in TH else abs(y - med) > a.delta))
    iv = []
    for t in flag:
        if iv and t - iv[-1][1] <= 1.5 / a.fps: iv[-1][1] = round(t + 1 / a.fps, 2)
        else: iv.append([round(t, 2), round(t + 1 / a.fps, 2)])
    res[f] = iv; print(f'{f}: median yaw {med:.2f}, {len(iv)} look-away interval(s), {sum(y - x for x, y in iv):.1f}s')
json.dump(res, open(os.path.join(a.work, 'pose.json'), 'w'), indent=1)
