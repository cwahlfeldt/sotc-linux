#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""sotc (Linux): temple benchmark through sotc.py. Wander is put at fixed stations in and around
the Shrine of Worship by the engine's own setPlayerPos console command (an engine automation plan,
as in sotc_ride_bench.py), held there, and the camera keeps turning (right stick), so every run
measures the same places from every direction: no pad route to drift.

    python3 tools/sotc_temple_tour.py [--label NAME] [--only t33,t67] [--hold 9] [--pan 200]
                                      [--cap 0] [--res 3440x1440] [--render WxH] [NAME=VALUE ...]
    python3 tools/sotc_temple_tour.py --stats out/bench/NAME.log

X is pressed through the intro and the menus (Continue: the save, at the Shrine) until gameplay
starts and held again to skip the save's cutscene; the plan waits for that, then puts Wander at
each station once (he stands there; nothing holds him) for --hold seconds (default 9: one camera
turn at --pan 200). Each station starts with a printPlayerPos line (the marker); the per-second
"SOTC SCREEN FPS" lines between two markers give its FPS (mean of the seconds, the lowest one) and
commands per frame; a screenshot of each station goes to out/bench/<label>-<name>.png.

The stations are where the player's frame rate dropped, read from a play session with the
position logged once a second (tools/sotc_track_play.sh): each one is the position, height and
facing of the slowest second of a slow stretch. A grid of positions at one height does not work:
around the temple the ground is higher than the altar, Wander ends up inside it and the camera in
the grass.

Defaults: uncapped (--cap 0: the slow places show as lower FPS, not as missed 60 FPS frames), the
60 FPS mode, no dynamic FPS, no frame generation, no read-ahead; NAME=VALUE pairs go to the game.
The size is pinned too (user/settings.json would leak in otherwise): --res is the output size
(default 3440x1440), --render the size the game draws at (default: --res; smaller is scaled up
by FSR 1), RCAS sharpening at its default strength.
Logs: out/bench/<label>.log; one line per run appended to out/bench/summary.txt.
SOTC_BENCH_WRAP: a command in front of the game, as in sotc_bench_gameplay.py.
"""
import argparse
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STARTED = 'st_gameflow() starting game'
DONE = 'Automation completed'
FAILED = 'Command in root stage failed'
POSITION = 'Player Position:'
PLAN = ROOT / 'user' / 'temp0' / 'sotc_temple_plan.txt'
# The tour: (name, x, y, z, yaw) in engine coordinates (printPlayerPos), from the player's session
# of 2026-11-26 (21:00, 21:9, 60 FPS mode): the slowest second of each slow stretch in and around
# the temple; the name is the stretch's start (s), the comment its slowest second.
STATIONS = [
    ('t33', 300.00, 9.76, -295.96, -0.0),    # lowest 48 FPS, 12158 commands per frame
    ('t41', 290.93, 9.76, -285.98, -66.1),   # lowest 56, 11949
    ('t50', 296.85, 10.51, -283.09, -66.3),  # lowest 52, 11444
    ('t67', 278.49, 0.87, -254.02, 72.8),    # lowest 49, 11368
    ('t90', 335.00, -2.35, -224.01, 53.0),   # lowest 55, 5457
]
SCREEN = re.compile(r'SOTC SCREEN FPS \d+s: lowest (\d+), now (\d+), (\d+) cmds/frame')


def plan_text(stations, hold):
    # The harness skips the save's cutscene during the first wait (X held).
    lines = ['*stage "Temple"', 'waitForGameToStart', 'wait 30']
    for _, x, y, z, yaw in stations:
        lines += [f'setPlayerPos {x:.2f} {y:.2f} {z:.2f} 0 {yaw:.1f} 0', 'printPlayerPos',
                  f'wait {hold:g}']
    lines += ['printPlayerPos', '*endstage']
    return '\n'.join(lines) + '\n'


def tour_stats(text, stations, settle=2):
    """Per station: (name, mean FPS, lowest FPS, commands per frame, seconds) from the seconds
    between its marker and the next one, the first `settle` seconds left out."""
    marks = [m.start() for m in re.finditer(re.escape(POSITION), text)]
    rows = []
    for k, (name, *_rest) in enumerate(stations):
        if k + 1 >= len(marks):
            break
        seconds = [(int(lo), int(now), int(c)) for lo, now, c in
                   SCREEN.findall(text[marks[k]:marks[k + 1]])][settle:]
        if not seconds:
            continue
        rows.append((name, sum(s[1] for s in seconds) / len(seconds), min(s[0] for s in seconds),
                     sum(s[2] for s in seconds) / len(seconds), len(seconds)))
    return rows


def report(rows, stations):
    where = {name: (x, y, z) for name, x, y, z, _ in stations}
    lines = [f'{"station":10s} {"x":>7s} {"y":>6s} {"z":>7s} {"cmds":>6s} {"FPS":>6s} {"low":>4s}']
    for name, fps, low, cmds, n in rows:
        x, y, z = where[name]
        lines.append(f'{name:10s} {x:7.1f} {y:6.1f} {z:7.1f} {cmds:6.0f} {fps:6.1f} {low:4d}')
    if rows:
        lines.append(f'tour: {sum(r[1] for r in rows) / len(rows):.1f} FPS over {len(rows)} stations, '
                     f'lowest station {min(rows, key=lambda r: r[1])[0]} '
                     f'{min(r[1] for r in rows):.1f} FPS, lowest second {min(r[2] for r in rows)}')
    return '\n'.join(lines)


def run_once(label, stations, args):
    out = ROOT / 'out' / 'bench'
    out.mkdir(parents=True, exist_ok=True)
    log_path, pad, shot = out / f'{label}.log', out / f'{label}.pad', out / f'{label}.shot'
    pad.write_text('')
    shot.unlink(missing_ok=True)
    PLAN.parent.mkdir(parents=True, exist_ok=True)
    PLAN.write_text(plan_text(stations, args.hold))
    cvars = f'nointro RetailBuild=0 automate_loadfile(/temp0/{PLAN.name}) automate_go'
    env = ['SOTC_PREFETCH=0', 'SOTC_MODES=fps60,af16', 'SOTC_FPS_CAP=off', 'SOTC_FPS=1',
           f'SOTC_FPS_LIMIT={args.cap}', 'SOTC_FPS_DYNAMIC=0', 'SOTC_FRAMEGEN=off',
           'SOTC_WINDOW_BEHIND=1', 'SOTC_SAVE_PROMPT=auto', f'SOTC_EXTRA_CVARS={cvars}',
           f'SOTC_OUTPUT_RES={args.res}', f'SOTC_RENDER_RES={args.render or args.res}', 'BB_FSR1=1',
           'BB_RCAS=1', 'BB_RCAS_ATTENUATION=250',
           f'BB_PAD_FILE={pad}', f'BB_FRAME_DUMP_TRIGGER={shot}', *args.env]
    limit = 120 + len(stations) * (args.hold + 1)
    command = [*shlex.split(os.environ.get('SOTC_BENCH_WRAP', '')), 'env', *env,
               'timeout', '--signal=INT', str(int(limit) + 300), sys.executable, 'sotc.py']
    t0 = time.monotonic()
    with open(log_path, 'wb') as log:
        game = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL)

    def text():
        return log_path.read_bytes().decode('utf-8', 'replace')

    def note(message):
        print(f'[{time.monotonic() - t0:6.1f}s] {message}', flush=True)

    def press(what, seconds):
        pad.write_text(what)
        time.sleep(seconds)
        pad.write_text('')

    result = 'stopped'
    shots = []
    try:
        note('holding X through the intro and the menus')
        while STARTED not in text():
            if game.poll() is not None or time.monotonic() - t0 > 300:
                return log_path, f'no "{STARTED}" line', shots
            pad.write_text('cross')
            for _ in range(16):
                if STARTED in text():
                    break
                time.sleep(0.25)
            pad.write_text('')
            time.sleep(1.0)
        started = time.monotonic()
        loaded_at = len(log_path.read_bytes())
        while time.monotonic() - started < 40:
            seconds = SCREEN.findall(log_path.read_bytes()[loaded_at:].decode('utf-8', 'replace'))
            if seconds and int(seconds[-1][2]) >= 6000:
                break
            time.sleep(0.5)
        note("in game; holding X to skip the save's cutscene")
        for _ in range(3):
            press('cross', 2.5)
            time.sleep(2.0)
        pad.write_text(f'rx={args.pan}')
        note(f'turning the camera; {len(stations)} stations of {args.hold:.0f} s')
        seen = 0
        while True:
            t = text()
            marks = t.count(POSITION)
            if marks > seen:
                # A new station: its screenshot once it has settled.
                if seen < len(stations) and marks <= len(stations):
                    time.sleep(3.0)
                    shot.touch()
                    shots.append(stations[marks - 1][0])
                seen = marks
            if DONE in t:
                result = 'done'
                break
            if FAILED in t:
                result = 'the plan failed'
                break
            if POSITION not in t and time.monotonic() - started > 120:
                result = 'the plan did not start (no printPlayerPos 120 s after gameplay began)'
                break
            if game.poll() is not None or time.monotonic() - started > limit:
                result = f'the game ended or the plan took over {limit:.0f} s'
                break
            time.sleep(0.2)
        note(result)
    finally:
        pad.write_text('')
        if game.poll() is None:
            # The wrapper (systemd-run --scope, env) execs timeout, which passes INT on to the game.
            game.send_signal(signal.SIGINT)
            try:
                game.wait(timeout=60)
            except subprocess.TimeoutExpired:
                game.kill()
                game.wait()
        pad.unlink(missing_ok=True)
        PLAN.unlink(missing_ok=True)
    return log_path, result, shots


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--label', default=time.strftime('temple-%H%M%S'))
    parser.add_argument('--only', help='comma-separated station names (default: all)')
    parser.add_argument('--hold', type=float, default=9.0, help='seconds per station (default 9)')
    parser.add_argument('--pan', type=int, default=200, help='right stick x while measuring (default 200)')
    parser.add_argument('--cap', type=int, default=0, help='FPS limit (default 0: uncapped)')
    parser.add_argument('--res', default='3440x1440', help='output size (default 3440x1440)')
    parser.add_argument('--render', help='render size (default: --res; smaller: FSR 1 scales up)')
    parser.add_argument('--stats', help='print the stations of an existing log and exit')
    parser.add_argument('env', nargs='*', help='NAME=VALUE for the game')
    args = parser.parse_args()
    stations = STATIONS
    if args.only:
        wanted = args.only.split(',')
        stations = [st for st in STATIONS if st[0] in wanted]
        if not stations:
            parser.error(f'no station named {args.only}')
    if args.stats:
        text = Path(args.stats).read_text(encoding='utf-8', errors='replace')
        print(report(tour_stats(text, stations), stations))
        return 0
    log_path, result, shots = run_once(args.label, stations, args)
    # The screenshots, in the order taken, named after their station.
    screenshots = ROOT / 'user' / 'screenshots'
    if screenshots.is_dir() and shots:
        recent = sorted(screenshots.glob('*.png'), key=lambda p: p.stat().st_mtime)[-len(shots):]
        if len(recent) == len(shots):
            for path, name in zip(recent, shots):
                (ROOT / 'out' / 'bench' / f'{args.label}-{name}.png').write_bytes(path.read_bytes())
    text = log_path.read_text(encoding='utf-8', errors='replace')
    rows = tour_stats(text, stations)
    table = report(rows, stations)
    print(table, flush=True)
    summary = table.splitlines()[-1] if rows else 'no stations measured'
    size = args.res if not args.render or args.render == args.res else f'{args.render}->{args.res}'
    line = (f'{args.label} ({size}): {summary}' if result == 'done'
            else f'{args.label} ({size}): INVALID ({result}; {summary})')
    print(line, flush=True)
    with open(ROOT / 'out' / 'bench' / 'summary.txt', 'a') as out:
        out.write(line + '\n')
    return 0 if result == 'done' and rows else 1


if __name__ == '__main__':
    sys.exit(main())
