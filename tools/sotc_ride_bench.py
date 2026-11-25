#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""sotc (Linux): world-streaming benchmark through sotc.py. Wander is carried along a fixed
~5.8 km loop through the Forbidden Land by the engine's own setPlayerPos console command (an
engine automation plan), so every run streams the same areas in the same order, with no pad
route, horse or camera to drift. Ported from the Windows tool (upstream tools/sotc_ride_bench.py,
same plan), which ran it through the installed launcher.

    python3 tools/sotc_ride_bench.py [--label NAME] [--runs N] [NAME=VALUE ...]
    python3 tools/sotc_ride_bench.py --stats out/bench/NAME.log

Wander is held 80 m above the shrine level (above the terrain on this loop) and moved 2.5 m per
step, one step per 0.1 s (~25 m/s); he is set down at the shrine at both ends. The plan goes to
user/temp0/sotc_ride_plan.txt (the game's /temp0) and is started by the engine cvars
automate_loadfile/automate_go; X is pressed through the intro and the menus (Continue: the save)
until gameplay starts, and the plan's own waitForGameToStart holds it until then.

Defaults: the 60 FPS mode (SOTC_FPS_LIMIT=60), no frame generation, no read-ahead; NAME=VALUE
pairs override them (SOTC_FPS_LIMIT=0 measures uncapped). Frame times come from SOTC_FRAME_LOG
between the plan's first and last printPlayerPos: p50/p99, frames over 20 ms (a missed frame at
60 FPS), 25/33/50/100 ms, the worst one, and SOTC_STALL_MS=40's suspects for the slow ones.
The first run after a shader-cache change compiles new pipelines; compare warm runs.
Logs: out/bench/<label>.log; one line per run appended to out/bench/summary.txt.
SOTC_BENCH_WRAP: a command in front of the game, as in sotc_bench_gameplay.py.
"""
import argparse
import math
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
# (x, z) waypoints in engine coordinates (printPlayerPos): shrine, east, north, south-west,
# south, shrine.
WAYPOINTS = [(298, -198), (1387, -324), (294, 296), (-831, -996), (269, -909), (298, -198)]
SHRINE = 'setPlayerPos 298 -6 -198'
HEIGHT = 80
STEP = 2.5
FRAME = re.compile(r'SOTCFRAME \d+ t=\d+ms us=(\d+)')
PLAN = ROOT / 'user' / 'temp0' / 'sotc_ride_plan.txt'


def plan_text():
    lines = ['*stage "Ride"', 'waitForGameToStart', 'wait 8', SHRINE, 'wait 10', 'printPlayerPos']
    for (ax, az), (bx, bz) in zip(WAYPOINTS, WAYPOINTS[1:]):
        n = max(1, round(math.hypot(bx - ax, bz - az) / STEP))
        for i in range(n):
            lines += [f'setPlayerPos {ax + (bx - ax) * i / n:.1f} {HEIGHT} {az + (bz - az) * i / n:.1f}',
                      'wait 0.1']
    lines += [SHRINE, 'wait 3', 'printPlayerPos', '*endstage']
    return '\n'.join(lines) + '\n'


def ride_stats(text):
    lines = text.splitlines()
    marks = [i for i, line in enumerate(lines) if POSITION in line]
    if len(marks) < 2:
        return None, 'no ride in the log'
    us = [int(m.group(1)) for line in lines[marks[0]:marks[-1]] if (m := FRAME.match(line))]
    if len(us) < 100:
        return None, 'no frame log (SOTC_FRAME_LOG)'
    seq = [(b - a) / 1000 for a, b in zip(us, us[1:])]
    d = sorted(seq)
    n = len(d)
    p = lambda q: d[min(n - 1, int(q * n))]  # noqa: E731
    over = lambda ms: sum(x > ms for x in d)  # noqa: E731
    jitter = sum(abs(b - a) for a, b in zip(seq, seq[1:])) / (n - 1)
    stalls = len([line for line in lines[marks[0]:marks[-1]] if line.startswith('SOTCSTALL')])
    return seq, (f'fps {n / ((us[-1] - us[0]) / 1e6):.1f} p50 {p(.5):.1f} p99 {p(.99):.1f} '
                 f'worst {d[-1]:.0f} ms | >20 {over(20)} >25 {over(25)} >33 {over(33.4)} '
                 f'>50 {over(50)} >100 {over(100)} | jitter {jitter:.2f} ms | stall lines {stalls} '
                 f'({n} frames)')


def run_once(label, extra_env, limit):
    out = ROOT / 'out' / 'bench'
    out.mkdir(parents=True, exist_ok=True)
    log_path, pad = out / f'{label}.log', out / f'{label}.pad'
    pad.write_text('')
    PLAN.parent.mkdir(parents=True, exist_ok=True)
    PLAN.write_text(plan_text())
    cvars = f'nointro RetailBuild=0 automate_loadfile(/temp0/{PLAN.name}) automate_go'
    env = ['SOTC_PREFETCH=0', 'SOTC_MODES=fps60,af16', 'SOTC_FPS_CAP=off', 'SOTC_FPS=1',
           'SOTC_FPS_LIMIT=60', 'SOTC_FPS_DYNAMIC=0', 'SOTC_FRAMEGEN=off', 'SOTC_WINDOW_BEHIND=1',
           'SOTC_FRAME_LOG=1', 'SOTC_STALL_MS=40', 'SOTC_SAVE_PROMPT=auto',
           f'SOTC_EXTRA_CVARS={cvars}', f'BB_PAD_FILE={pad}', *extra_env]
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

    result = 'stopped'
    try:
        note('holding X through the intro and the menus')
        while STARTED not in text():
            if game.poll() is not None or time.monotonic() - t0 > 300:
                result = f'no "{STARTED}" line'
                return log_path, result
            pad.write_text('cross')
            for _ in range(16):
                if STARTED in text():
                    break
                time.sleep(0.25)
            pad.write_text('')
            time.sleep(1.0)
        started = time.monotonic()
        note('in game; the plan runs')
        while True:
            t = text()
            if DONE in t:
                result = 'done'
                break
            if FAILED in t:
                result = 'the plan failed'
                break
            if POSITION not in t and time.monotonic() - started > 90:
                result = 'the plan did not start (no printPlayerPos 90 s after gameplay began)'
                break
            if game.poll() is not None or time.monotonic() - started > limit:
                result = f'the game ended or the plan took over {limit:.0f} s'
                break
            time.sleep(1.0)
        note(result)
    finally:
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
    return log_path, result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--label', default=time.strftime('ride-%H%M%S'))
    parser.add_argument('--runs', type=int, default=1)
    parser.add_argument('--stats', help='print the stats of an existing log and exit')
    parser.add_argument('--limit', type=float, default=600.0,
                        help='seconds the plan may take once gameplay began (default 600)')
    parser.add_argument('env', nargs='*', help='NAME=VALUE for the game')
    args = parser.parse_args()
    if args.stats:
        print(ride_stats(Path(args.stats).read_text(encoding='utf-8', errors='replace'))[1])
        return 0
    ok = True
    for run in range(1, args.runs + 1):
        label = args.label if args.runs == 1 else f'{args.label}-{run}'
        log_path, result = run_once(label, args.env, args.limit)
        seq, stats = ride_stats(log_path.read_text(encoding='utf-8', errors='replace'))
        line = f'{label}: {stats}' if result == 'done' and seq else f'{label}: INVALID ({result}; {stats})'
        ok = ok and result == 'done' and bool(seq)
        print(line, flush=True)
        with open(ROOT / 'out' / 'bench' / 'summary.txt', 'a') as summary:
            summary.write(line + '\n')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
