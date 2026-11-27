#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""sotc (Linux): gameplay benchmark through sotc.py, the native build, uncapped 60 FPS mode.

    python3 tools/sotc_bench_gameplay.py [--label NAME] [--measure 60] [--move] [--pan X]
                                         [--skip N] [--replay FILE] [NAME=VALUE ...]

The title screen's run is mostly the intro movie; this one plays: scripted pad input
(BB_PAD_FILE) holds X 4 s at a time (the intro's "hold X to skip", then "Press Any Button" and the
menu's Continue) until the log says "st_gameflow() starting game", waits for the save's first
view (the per-second "SOTC SCREEN FPS" line's commands per frame), holds X --skip times (default
3, 2.5 s each) to skip the cutscene that follows ("Thy next foe is...", ~50 s, which otherwise
fills the window and eats the walk) and measures Wander at the Shrine of Worship's altar (the
save's place). Then the SOTC FPS lines written in the next --measure seconds (the first one
dropped, it began before the window) give the gameplay FPS, with the draw and command processor
threads' time per frame and the commands per frame (the scene's weight: compare runs only when it
matches). Needs a save at the Shrine (Continue). --move then walks left, then forward, and turns
the camera (it ends up in the bushes, a lighter view). --pan X holds the right stick at X (0..255,
128 is still; 160 is inside the dead zone, 200 turns once every ~8.7 s) during the window, so the
camera keeps turning and the window averages every direction: `--pan 200` without --move sweeps
the temple from the altar (~3,700-12,400 commands per frame). The summary line counts the window's
seconds in stretches of 5 s or more under 5,000 commands per frame ("cutscene s"): a cutscene
the skip missed. --replay FILE plays back a route the player recorded (BB_PAD_RECORD=FILE, F9 once
Wander can move at the altar after the cutscene, F9 again at the end) from the window's start;
the window then lasts the recording unless --measure is given. Replay at the FPS limit the route
was recorded with (--cap 60 for the 60 FPS mode): uncapped, the same stick input took Wander off
the recorded path within ~20 s.

NAME=VALUE pairs go to the game's environment (A/B switches, SOTC_PROFILE=...). The window's start
creates SOTC_PROFILE_START's file, so SOTC_PROFILE / SOTC_THREAD_TIMES with SOTC_PROFILE_DELAY=0
cover exactly the measured seconds. Screenshots: the save's first view (<label>-loaded.png),
after the skip (-skipped), after the walk (-moved), 5 s into the window (<label>.png) and right
after it (-end), all in out/bench.
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
    parser.add_argument('--measure', type=float,
                        help='seconds measured (default 60, or the length of --replay)')
    parser.add_argument('--load', type=float, default=40.0,
                        help="at most this many seconds for the save's first view (default 40)")
    parser.add_argument('--move', action='store_true', help='walk and turn the camera first')
    parser.add_argument('--pan', type=int, help='right stick x (0..255) held during the window')
    parser.add_argument('--skip', type=int, default=3, help="X holds to skip the save's cutscene")
    parser.add_argument('--replay', help='a BB_PAD_RECORD file played back during the window')
    parser.add_argument('--cap', type=int, default=0,
                        help='FPS limit (SOTC_FPS_LIMIT, default 0: uncapped); replay a route at the '
                             'limit it was recorded with')
    parser.add_argument('env', nargs='*', help='NAME=VALUE for the game')
    args = parser.parse_args()
    replay_env = []
    if args.replay:
        replay = Path(args.replay).resolve()
        lines = [line.split() for line in replay.read_text().splitlines() if line.strip()]
        if args.measure is None:
            args.measure = int(lines[-1][0]) / 1000 + 1 if lines else 60.0
        replay_env = [f'BB_PAD_REPLAY={replay}']
    if args.measure is None:
        args.measure = 60.0
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
           f'SOTC_FPS_LIMIT={args.cap}', 'SOTC_FPS_DYNAMIC=0', 'SOTC_FRAMEGEN=off', 'SOTC_WINDOW_BEHIND=1',
           f'BB_PAD_FILE={pad}', f'BB_FRAME_DUMP_TRIGGER={shot}', f'SOTC_PROFILE_START={start_file}',
           *replay_env, *args.env]
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

    shot_names = []

    def snap(name):
        """Screenshot of the next frame (BB_FRAME_DUMP_TRIGGER), named after the run."""
        shot.touch()
        shot_names.append(name)
        time.sleep(0.5)

    def screen_commands(since):
        """Commands per frame of each "SOTC SCREEN FPS" second logged after byte `since`."""
        return [int(c) for c in re.findall(r'SOTC SCREEN FPS \d+s: lowest \d+, now \d+, (\d+) cmds/frame',
                                           log_path.read_bytes()[since:].decode('utf-8', 'replace'))]

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
        loaded_at = len(log_path.read_bytes())
        deadline = time.monotonic() + args.load
        while time.monotonic() < deadline and max(screen_commands(loaded_at)[-2:], default=0) < 6000:
            time.sleep(0.5)
        note(f'first view ({max(screen_commands(loaded_at)[-2:], default=0)} commands per frame)')
        snap('loaded')
        if args.skip:
            note(f"holding X {args.skip} times to skip the save's cutscene")
            for _ in range(args.skip):
                press('cross', 2.5)
                time.sleep(2.0)
            snap('skipped')
        if args.move:
            note('walking and turning the camera')
            press('lx=0', 1.5)    # left
            time.sleep(0.3)
            press('ly=0', 1.5)    # forward
            time.sleep(0.3)
            press('rx=255', 1.0)  # camera to the right
            snap('moved')
        time.sleep(3)
        begin = len(log_path.read_bytes())
        start_file.touch()
        if args.replay:
            pad.write_text('replay')
        elif args.pan is not None:
            pad.write_text(f'rx={args.pan}')
        note(f'measuring {args.measure:.0f} s')
        time.sleep(5)
        snap('')
        time.sleep(max(0.0, args.measure - 5.5))
        end = len(log_path.read_bytes())
        pad.write_text('')
        snap('end')  # after the window: the view it ended on
        time.sleep(1.5)
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
    shots = [p for p in shots if p.stat().st_mtime > time.time() - (time.monotonic() - t0)]
    if len(shots) == len(shot_names):
        for path, name in zip(shots, shot_names):
            shutil.copy(path, out / (f'{args.label}-{name}.png' if name else f'{args.label}.png'))
    else:
        note(f'{len(shots)} screenshots for {len(shot_names)} requests: not copied')
    window = log_path.read_bytes()[begin:end].decode('utf-8', 'replace')
    lines = re.findall(r'SOTC FPS ([0-9.]+) at \d+s; (\d+) cmds/frame', window)[1:]
    fps = [float(f) for f, _ in lines]
    commands = [int(c) for _, c in lines]
    threads = [(float(a), float(b)) for a, b in
               re.findall(r'draw busy ([0-9.]+) ms, command parse ([0-9.]+) ms', window)][1:]
    line = f'{args.label}: gameplay {sum(fps) / max(1, len(fps)):.2f} FPS, min {min(fps, default=0):.1f} ({len(fps)} samples)'
    if commands:
        line += f', {sum(commands) / len(commands):.0f} commands/frame'
    seconds = [int(c) for c in re.findall(r'SOTC SCREEN FPS \d+s: lowest \d+, now \d+, (\d+) cmds/frame', window)]
    if seconds:
        # A cutscene: 5 s or more in a row under 5,000 commands per frame (a turning camera looks
        # out of the temple for 2-3 s at a time).
        cutscene = run = 0
        for c in seconds + [99999]:
            if c < 5000:
                run += 1
                continue
            cutscene += run if run >= 5 else 0
            run = 0
        line += f', cutscene {cutscene} s of {len(seconds)}'
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
