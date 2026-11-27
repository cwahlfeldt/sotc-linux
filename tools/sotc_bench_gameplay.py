#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""sotc (Linux): gameplay benchmark through sotc.py, the native build, uncapped 60 FPS mode.

    python3 tools/sotc_bench_gameplay.py [--label NAME] [--measure 60] [--move] [NAME=VALUE ...]

The title screen's run is mostly the intro movie; this one plays: scripted pad input
(BB_PAD_FILE) holds X 4 s at a time (the intro's "hold X to skip", then "Press Any Button" and the
menu's Continue) until the log says "st_gameflow() starting game", waits for the save to load and
measures Wander standing at the Shrine of Worship's altar (the save's place). Then the SOTC FPS
lines written in the next --measure seconds (the first one dropped, it began before the window)
give the gameplay FPS, with the draw and command processor threads' time per frame and the
commands per frame (the scene's weight: compare runs only when it matches). Needs a save at the
Shrine (Continue). --move walks left, then forward, and turns the camera first: a heavier view,
but the walk passes the top of a staircase and ends either up on the terrace (~7300 commands per
frame) or down the stairs (~9300), so two runs often measure different scenes.

NAME=VALUE pairs go to the game's environment (A/B switches, SOTC_PROFILE=...). The window's start
creates SOTC_PROFILE_START's file, so SOTC_PROFILE / SOTC_THREAD_TIMES with SOTC_PROFILE_DELAY=0
cover exactly the measured seconds. Screenshots are taken 5 s in (out/bench/<label>.png) and
right after it (out/bench/<label>-end.png: the heavy view after the save's cutscene).
Logs: out/bench/<label>.log; one line per run appended to out/bench/summary.txt.
SOTC_BENCH_WRAP: a command in front of the game, e.g. "systemd-run --user --scope
--slice=sotc.slice -p MemoryHigh=12G" (keeps a test run out of the desktop session's memory).
"""
import argparse
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STARTED = 'st_gameflow() starting game'


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--label', default=time.strftime('run-%H%M%S'))
    parser.add_argument('--measure', type=float, default=60.0, help='seconds measured (default 60)')
    parser.add_argument('--load', type=float, default=20.0, help='seconds for the save to load (default 20)')
    parser.add_argument('--move', action='store_true', help='walk and turn the camera first')
    parser.add_argument('env', nargs='*', help='NAME=VALUE for the game')
    args = parser.parse_args()
    out = ROOT / 'out' / 'bench'
    out.mkdir(parents=True, exist_ok=True)
    log_path, pad = out / f'{args.label}.log', out / f'{args.label}.pad'
    start_file, shot = out / f'{args.label}.start', out / f'{args.label}.shot'
    for f in (start_file, shot):
        f.unlink(missing_ok=True)
    pad.write_text('')
    # The player's settings (user/settings.json, sotc.py) must not change what is measured: no FPS
    # limit, no dynamic step, no frame generation; the window opens without the focus.
    env = ['SOTC_PREFETCH=0', 'SOTC_MODES=fps60,af16', 'SOTC_FPS_CAP=off', 'SOTC_FPS=1',
           'SOTC_FPS_LIMIT=0', 'SOTC_FPS_DYNAMIC=0', 'SOTC_FRAMEGEN=off', 'SOTC_WINDOW_BEHIND=1',
           f'BB_PAD_FILE={pad}', f'BB_FRAME_DUMP_TRIGGER={shot}', f'SOTC_PROFILE_START={start_file}', *args.env]
    command = [*shlex.split(os.environ.get('SOTC_BENCH_WRAP', '')), 'env', *env,
               'timeout', '--signal=INT', '600', sys.executable, 'sotc.py']
    t0 = time.monotonic()
    with open(log_path, 'wb') as log:
        game = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    begin = end = None

    def text():
        return log_path.read_bytes().decode('utf-8', 'replace')

    def press(what, seconds):
        pad.write_text(what)
        time.sleep(seconds)
        pad.write_text('')

    def note(message):
        print(f'[{time.monotonic() - t0:6.1f}s] {message}', flush=True)

    try:
        note('holding X through the intro and the menus')
        while STARTED not in text():
            if game.poll() is not None or time.monotonic() - t0 > 300:
                note(f'no "{STARTED}" line: stopped')
                return 1
            pad.write_text('cross')
            for _ in range(16):
                if STARTED in text():
                    break
                time.sleep(0.25)
            pad.write_text('')
            time.sleep(1.0)
        note('in game; loading')
        time.sleep(args.load)
        if args.move:
            press('lx=0', 1.5)    # left
            time.sleep(0.3)
            press('ly=0', 1.5)    # forward
            time.sleep(0.3)
            press('rx=255', 1.0)  # camera to the right
        time.sleep(3)
        begin = len(log_path.read_bytes())
        start_file.touch()
        note(f'measuring {args.measure:.0f} s')
        time.sleep(5)
        shot.touch()
        time.sleep(max(0.0, args.measure - 5))
        end = len(log_path.read_bytes())
        shot.touch()  # after the window: the view it ended on
        time.sleep(2)
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
    screenshots = ROOT / 'user' / 'screenshots'
    shots = sorted(screenshots.glob('*.png'), key=lambda p: p.stat().st_mtime) if screenshots.is_dir() else []
    shots = [p for p in shots if p.stat().st_mtime > time.time() - (time.monotonic() - t0)][-2:]
    for path, name in zip(shots, (f'{args.label}.png', f'{args.label}-end.png')):
        shutil.copy(path, out / name)
    window = log_path.read_bytes()[begin:end].decode('utf-8', 'replace')
    lines = re.findall(r'SOTC FPS ([0-9.]+) at \d+s; (\d+) cmds/frame', window)[1:]
    fps = [float(f) for f, _ in lines]
    commands = [int(c) for _, c in lines]
    threads = [(float(a), float(b)) for a, b in
               re.findall(r'draw busy ([0-9.]+) ms, command parse ([0-9.]+) ms', window)][1:]
    line = f'{args.label}: gameplay {sum(fps) / max(1, len(fps)):.2f} FPS, min {min(fps, default=0):.1f} ({len(fps)} samples)'
    if commands:
        line += f', {sum(commands) / len(commands):.0f} commands/frame'
    if threads:
        line += (f'; per frame: draw busy {sum(a for a, _ in threads) / len(threads):.2f} ms, '
                 f'command parse {sum(b for _, b in threads) / len(threads):.2f} ms')
    line += '  [' + ' '.join(f'{f:.1f}' for f in fps) + ']'
    print(line, flush=True)
    with open(out / 'summary.txt', 'a') as summary:
        summary.write(line + '\n')
    return 0 if fps else 1


if __name__ == '__main__':
    sys.exit(main())
