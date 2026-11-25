#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Shadow of the Colossus (CUSA08809 EU 1.01 or CUSA08034 US 1.00) on PC: prepares the game image
and starts it.

    python3 sotc.py                     (or bash run.sh, which builds first)

Settings (environment variables, or sotc.ini beside this script as NAME=value lines):
    SOTC_GAME_DIR     the dumped game folder (the one with eboot.bin); default ../CUSA08809,
                      else ../CUSA08034
    SOTC_SYS_MODULES  folder with YOUR OWN console's decrypted libSceNgs2.sprx and
                      libSceUlt.sprx (shadPS4's user/sys_modules). Without it a built-in mixer plays the sound.
                      These files are Sony firmware: they are never distributed with the port.
    SOTC_USER_DIR     saves, shader/pipeline caches; default ./user
    SOTC_DATA_DIR     the folder of out/, user/ and sotc.ini when the port's is read-only
    SOTC_UPDATE_DIR   optional: the game update; by default <game>-UPDATE or <game>-patch next to
                      the dump (as shadPS4); its files take the place of the base game's
    SOTC_DLC_DIR      optional: the game's DLC (one folder per add-on with sce_sys/param.sfo, the
                      add-ons' .pkg files, or shadPS4's addcont folder holding CUSA08809 /
                      CUSA08034); by default <game>-DLC next to the dump; only DLC of the game's
                      own region is listed
    SOTC_MODES        optional, comma-separated: af16 (16x anisotropic filtering),
                      fps60 (removes the 30 FPS cap; experimental, vblank at 120 Hz),
                      fps60game (the game's own 60 FPS target, as the PS4 Pro Performance mode;
                      with SOTC_FPS_CAP=off)
                      hdr (HDR10 output and the game's HDR rendering; the desktop must offer HDR)
    SOTC_RENDER_RES   optional: the game renders at WxH instead of 1920x1080 (e.g. 2560x1080 for
                      21:9, a wider view); the output follows its aspect; PS4 mode only
    SOTC_CVARS        engine settings, NAME=VALUE separated by spaces (e.g. r_motionBlurEnable=0)
    BB_GAMEPAD        the gamepad to use (its name or part of it), when several are connected
    key.<input>=Keys, pad.<input>=buttons   remap the controls (README.md, Controles)
<user>/settings.json holds the start-up settings the Windows launcher used to keep (FPS mode, texture
quality, output size, upscaler, frame generation, volume, grass, effects...; SETTINGS_DEFAULTS below).
This script creates it and turns it into the game's variables at every start; the in-game menu
saves its changes into it. A variable set in the environment or in sotc.ini wins over the file.
build.sh builds out/bb-probe and its GPU library (out/gpu/libbbgpu.so), which this script starts.
The image is prepared again only when the game, the modules or the scripts change.
Extra arguments go to bb-probe. Run from a console, the session is also saved to
<user>/last_run.log (the 4 before it as last_run.1.log ... last_run.4.log; a crash's log is
copied to <user>/crashes).
"""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

PORT = Path(__file__).resolve().parent
SCRIPTS = PORT / 'scripts'
# SOTC_DATA_DIR: where out/ (the prepared image), user/ (saves, caches) and sotc.ini live when the
# port's own folder is read-only; default the port's folder.
DATA = Path(os.environ.get('SOTC_DATA_DIR') or PORT).resolve()
SYS_MODULES = ('libSceUlt.sprx', 'libSceNgs2.sprx')


def fail(message):
    print(message, file=sys.stderr)
    sys.exit(1)


def load_ini():
    ini = DATA / 'sotc.ini'
    if ini.is_file():
        for line in ini.read_text(encoding='utf-8', errors='replace').splitlines():
            line = line.strip()
            if line and not line.startswith(('#', ';')) and '=' in line:
                name, value = line.split('=', 1)
                os.environ.setdefault(name.strip(), value.strip())


def find_probe():
    probe = PORT / 'out' / 'bb-probe'
    if not (probe.is_file() and os.access(probe, os.X_OK)):
        fail('out/bb-probe not found: build it with build.sh (or start the game with run.sh).')
    return probe


def run_script(name, *args):
    result = subprocess.run([sys.executable, str(SCRIPTS / name), *map(str, args)], stdin=subprocess.DEVNULL)
    if result.returncode:
        sys.exit(result.returncode)


# ---------------------------------------------------------------------------------------------
# Start-up settings: what the Windows launcher passed to the game (its game_environment), kept in
# <user>/settings.json. The in-game menu writes its changes there (SOTC_LAUNCHER_SETTINGS,
# gpu/shim/bbport_overlay.cpp) and they apply at the next start. Every value becomes environment
# variables with setdefault: a variable set in the environment or in sotc.ini wins over the file.

# The shader version of the caches: bump it when a change makes the saved shaders and pipelines
# wrong (shader_recompiler or renderer output); the next start clears the cache once.
SHADER_CACHE_VERSION = '0.77'

SETTINGS_DEFAULTS = {
    'ui_language': '', 'audio_channels': 'auto', 'audio_lfe': True, 'audio_device': '',
    'af16': True, 'textures': 'high', 'hdr': False, 'fps_mode': '30', 'fps_dynamic': True,
    'button_icons': 'ps', 'fullscreen': False, 'present_mode': 'Mailbox', 'language': '',
    'player_name': '', 'show_fps': False, 'readbacks': '', 'debug_menu': False, 'debug_watch': False,
    'rb_hot': True, 'skip_logos': True, 'skip_film': False, 'gamepad': '', 'rumble': True,
    'output_res': '1920x1080', 'upscaler': 'fsr1', 'sharpness': '250', 'mouse': True,
    'mouse_sens': '1.0', 'mouse_invert': False, 'neo': False, 'fx_vignette': True, 'fx_fog': True,
    'fx_ssao': True, 'fx_motionblur': False, 'engine_cvars': '', 'perf_culling': True,
    'perf_record_thread': True, 'perf_dma': True, 'gpu_submit': 'auto', 'vram_use': 'normal',
    'vram_profile': 'auto', 'volume': '100', 'shadow_reuse': '0', 'grass_shadows': '2',
    'grass_distance': '1', 'grass_height': '1', 'weed_distance': '1', 'weed_height': '1',
    'grass_fade': '1', 'grass_detail': '1', 'framegen': 'off', 'fg_hudless': True, 'fg_mult': '2',
    'dlss_mode': 'quality', 'dlss_sharpen': '0', 'dlss_ui_sharpen': '3', 'dlss_sky_sharpen': '2',
    'dlss_compare': False, 'hdr_sdr': False, 'play_mode': 'custom',
}
# Rule: an update turns its improvements on. A default changed for the better goes here with the
# version (VERSION) that changed it; settings saved by an older version get it once, else the saved
# value would keep the old default for good.
DEFAULT_UPGRADES = [
    # HUD and letters steady with frame generation; no shadow trail in dark areas (motion blur);
    # straight to the game.
    ('0.71', {'fg_hudless': True, 'fx_motionblur': False, 'skip_logos': True}),
    # Fast GPU readbacks; the grass as on PS4.
    ('0.72', {'rb_hot': True, 'grass_shadows': '2', 'grass_distance': '1', 'grass_height': '1',
              'weed_distance': '1', 'weed_height': '1', 'grass_fade': '1', 'grass_detail': '1'}),
    # Dynamic FPS in the 60 FPS mode (a steady step below 60 when the game cannot keep it).
    ('0.73', {'fps_dynamic': True}),
]
# Video memory use (#143): texture collection from % of the card's budget, arena release from MB
# (0 = never).
VRAM_LIMITS = {'low': ('50', '1024'), 'normal': ('60', '1536'), 'high': ('75', '4096'), 'max': ('85', '0')}
# The 0.72 texture set (Maximum at mip 0, High at mip 1) used 5-7 GB on an 8 GB card: cards below
# this get the lighter one (vram_profile auto; light / full choose).
LIGHT_VRAM_BELOW_MB = 7500
# Effects switched off through engine cvars when their setting is false.
EFFECT_CVARS = {'fx_vignette': 'r_vignetteOverrideEnable=1 r_vignetteEnable=0', 'fx_fog': 'fog_enable=0',
                'fx_ssao': 'AO_Mode=0', 'fx_motionblur': 'r_motionBlurEnable=0'}
DLSS_FACTORS = {'dlaa': 1.0, 'quality': 1.5, 'balanced': 1.724, 'performance': 2.0, 'ultra': 3.0}


def version_key(text):
    return tuple(int(part) if part.isdigit() else 0 for part in str(text).replace('-', '.').split('.'))


def port_version():
    try:
        return (PORT / 'VERSION').read_text().strip()
    except OSError:
        return ''


def load_settings(path, version):
    """The saved settings over the defaults, with the upgrades of versions newer than the one that
    saved them. Written back complete: the in-game menu only changes keys the file has."""
    import json
    try:
        saved = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        saved = {}
    if not isinstance(saved, dict):
        saved = {}
    settings = {**SETTINGS_DEFAULTS, **saved}
    if saved:
        before = version_key(saved.get('settings_version') or '0')
        for upgrade, values in DEFAULT_UPGRADES:
            if before < version_key(upgrade):
                settings.update(values)
    settings['settings_version'] = version or str(saved.get('settings_version') or '')
    if settings != saved:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        except OSError:
            pass
    return settings


def check_shader_cache(user, version):
    """A port update whose shaders differ (SHADER_CACHE_VERSION) clears the shader and pipeline cache
    once: those built by the previous port can conflict with the new one (wrong or missing effects,
    crashes when one is loaded). <user>/cache/port_version.txt keeps the port version that uses the
    cache and the shader version it holds. A cache without that file (any built before it existed)
    is kept and the file written. SOTC_CACHE_CLEAR_EVERY_UPDATE=1 clears on every port update."""
    marker = user / 'cache' / 'port_version.txt'
    try:
        lines = marker.read_text(encoding='utf-8').split()
    except OSError:
        lines = []
    if lines:
        built_by = lines[0]
        shaders = lines[1].removeprefix('shaders=') if len(lines) > 1 else built_by
        if os.environ.get('SOTC_CACHE_CLEAR_EVERY_UPDATE') == '1':
            stale = built_by != version
        else:
            stale = shaders != SHADER_CACHE_VERSION
        if not stale and built_by == version:
            return
        if stale:
            print('Port update: the shader cache is built again', file=sys.stderr)
            for name in ('cache', 'shader'):
                shutil.rmtree(user / name, ignore_errors=True)
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(f'{version}\nshaders={SHADER_CACHE_VERSION}\n', encoding='utf-8')
    except OSError:
        pass


def gpu_vram_mb():
    """The video memory of the GPU the game will use (out/bb-gpu-capabilities: its largest
    device-local heap, picked as the renderer picks it); 0 when unknown."""
    import re
    try:
        result = subprocess.run([str(PORT / 'out' / 'bb-gpu-capabilities'), '--live-resolution'],
                                capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return 0
    match = re.search(r', (\d+) MiB:', result.stderr)
    return int(match.group(1)) if match else 0


def memory_gb():
    try:
        return os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE') / 2 ** 30
    except (ValueError, OSError):
        return 0


def screen_refresh_hz():
    """The primary screen's refresh rate, from SDL3 (the game's own library); 60 when unknown."""
    import ctypes
    import ctypes.util

    class DisplayMode(ctypes.Structure):
        _fields_ = [('display', ctypes.c_uint32), ('format', ctypes.c_uint32), ('w', ctypes.c_int),
                    ('h', ctypes.c_int), ('pixel_density', ctypes.c_float), ('refresh_rate', ctypes.c_float),
                    ('numerator', ctypes.c_int), ('denominator', ctypes.c_int), ('internal', ctypes.c_void_p)]
    try:
        sdl = ctypes.CDLL(ctypes.util.find_library('SDL3') or 'libSDL3.so.0')
        sdl.SDL_Init.argtypes = [ctypes.c_uint32]
        sdl.SDL_Init.restype = ctypes.c_bool
        sdl.SDL_GetPrimaryDisplay.restype = ctypes.c_uint32
        sdl.SDL_GetCurrentDisplayMode.argtypes = [ctypes.c_uint32]
        sdl.SDL_GetCurrentDisplayMode.restype = ctypes.POINTER(DisplayMode)
    except (OSError, AttributeError):
        return 60
    if not sdl.SDL_Init(0x20):  # SDL_INIT_VIDEO
        return 60
    try:
        mode = sdl.SDL_GetCurrentDisplayMode(sdl.SDL_GetPrimaryDisplay())
        rate = mode.contents.refresh_rate if mode else 0.0
        return int(rate + 0.5) if rate > 1 else 60
    finally:
        sdl.SDL_Quit()


def dynamic_fps_step(hz):
    """The dynamic FPS step (SOTC_FPS_DYNAMIC): the refresh rate divided by the smallest whole number
    that brings it to 50 or less, so every frame lasts the same number of refreshes (48 at 144 Hz, 40
    at 120 Hz, 30 at 60 Hz, 50 at 100 Hz, 37.5 at 75 Hz, 41.25 at 165 Hz). Before #454 a rate that
    48, 40 and 45 do not divide fell to 30, which does not divide 75, 100 or 165 Hz."""
    hz = hz if hz and hz >= 30 else 60
    divisor = 2
    while hz / divisor > 50:
        divisor += 1
    return f'{hz / divisor:.2f}'.rstrip('0').rstrip('.')


def desktop_language():
    """The menu language of the desktop (LANGUAGE, LC_ALL, LC_MESSAGES, LANG): pt, es, zh, ko, ru, else en."""
    for name in ('LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG'):
        code = os.environ.get(name, '')[:2].lower()
        if code:
            return code if code in ('pt', 'es', 'zh', 'ko', 'ru') else 'en'
    return 'en'


def game_version(source):
    """The game's version (APP_VER of its param.sfo, the update's when there is one); '' if unknown."""
    sys.path.insert(0, str(SCRIPTS))
    try:
        from prepare import sfo
        return str(sfo((source / 'sce_sys' / 'param.sfo').read_bytes()).get('APP_VER', ''))
    except (OSError, ValueError, ImportError):
        return ''
    finally:
        sys.path.remove(str(SCRIPTS))


def dlss_render(output, mode):
    """The render size for DLSS / FSR 4 mode at output WxH: multiples of 8, at least 640x360 (DLAA:
    the output size), the exact aspect when a size within 6% of the factor has it."""
    try:
        w, h = map(int, output.split('x'))
    except ValueError:
        return output
    if mode == 'dlaa':
        return output
    target = h / DLSS_FACTORS.get(mode, 1.5)
    exact = [rh for rh in range(360, h + 1, 8) if rh * w % (h * 8) == 0 and abs(rh - target) <= target * 0.06]
    rh = min(exact, key=lambda rh: abs(rh - target)) if exact else max(360, round(target / 8) * 8)
    rw = max(640, round(rh * w / h / 8) * 8)
    return f'{rw}x{rh}'


def is_wide(size):
    """True for a WxH wider than 16:9 (by more than 2%)."""
    try:
        w, h = map(int, str(size).split('x'))
    except ValueError:
        return False
    return w * 9 > h * 16 * 1.02


def settings_env(env, s, settings_file, source):
    """The environment the settings ask for, as the Windows launcher set it (setdefault: what the
    environment or sotc.ini already has wins)."""
    put = env.setdefault
    version = game_version(source)
    if version:
        put('SOTC_GAME_VERSION', version)  # window title
    put('SOTC_LAUNCHER_SETTINGS', str(settings_file))  # the in-game menu writes its changes here
    # The 30 FPS cap is applied or not by bb-probe (sotc_fps_cap.h), F7 switches it in game; above 30
    # the game targets 60 FPS itself (fps60game), so its timing follows (#100, #120, #49). grassbuf:
    # grass buffers 4x larger (the farthest grass popped in patches at longer grass distances).
    fps_mode = str(s.get('fps_mode') or '30')
    modes = ['af16'] if s.get('af16') else []
    if fps_mode != '30':
        modes.append('fps60game')
    modes.append('grassbuf')
    if s.get('hdr'):
        modes.append('hdr')
    put('SOTC_MODES', ','.join(modes))
    put('SOTC_FPS_CAP', '30' if fps_mode == '30' else 'off')
    put('SOTC_FPS_LIMIT', '60' if fps_mode == '60' else '0')
    # Dynamic FPS (videoout driver.cpp): with the 60 FPS limit, frames that cannot keep 60 lower it to
    # a step that divides the screen's refresh (dynamic_fps_step: 48 at 144/240 Hz, 40 at 120 Hz,
    # 30 at 60 Hz, 37.5 at 75 Hz).
    if fps_mode == '60' and s.get('fps_dynamic', True) and 'SOTC_FPS_DYNAMIC' not in env:
        env['SOTC_FPS_DYNAMIC'] = dynamic_fps_step(screen_refresh_hz())
    put('BB_FULLSCREEN', '1' if s.get('fullscreen') else '0')
    put('BB_PRESENT_MODE', str(s.get('present_mode') or 'Mailbox'))
    if s.get('language'):
        put('BB_LANGUAGE', str(s['language']))
    if str(s.get('player_name') or '').strip():
        put('BB_USER_NAME', str(s['player_name']).strip())
    if s.get('show_fps'):
        put('SOTC_FPS', '1')
    if s.get('readbacks'):
        put('BB_READBACKS', str(s['readbacks']))
    if 'SOTC_CVARS' not in env:
        cvars = [off for key, off in EFFECT_CVARS.items() if not s.get(key, True)]
        if s.get('perf_culling', True):
            # From Pink-shadPS4: no GPU index-buffer culling, same image, far fewer GPU results the
            # CPU has to wait for.
            cvars += ['doIndexBufferCulling=0', 'doSunShadowIndexBufferCulling=0']
        grass = str(s.get('grass_shadows') or '2')
        if grass in ('3', '4'):
            cvars += [f'r_virtualGeometryNumShadowCascades{mode}={grass}'
                      for mode in ('', '_BasePS4', '_Perf', '_Cinematic')]
        fade = str(s.get('grass_fade') or '1')
        if fade in ('0.5', '0.75', '2', '3'):
            cvars.append(f'r_virtualGeometryFadeMultiplier={fade}')
        if s.get('skip_logos'):
            cvars.append('skipSplash=1')  # no opening logos and autosave notice (#185)
        if s.get('skip_film'):
            cvars.append('nointro')  # no intro film and no title screen
        cvars += str(s.get('engine_cvars') or '').split()
        cvars += env.get('SOTC_EXTRA_CVARS', '').split()
        env['SOTC_CVARS'] = ' '.join(cvars)
    # Multipliers for the grass shaders' view distances and blade height (vk_rasterizer.cpp).
    put('SOTC_GRASS', ' '.join(str(s.get(k) or '1') for k in
                               ('grass_distance', 'grass_height', 'weed_distance', 'weed_height', 'grass_detail')))
    put('SOTC_RECORD_THREAD', '1' if s.get('perf_record_thread', True) else '0')
    if not s.get('perf_dma', True):
        put('BB_DIRECT_MEMORY_ACCESS', '0')
    # Periodic submits and readbacks ahead: by default only with NVIDIA (vk_rasterizer.cpp).
    if s.get('gpu_submit') == 'on':
        put('SOTC_FLUSH_US', '1000')
        put('SOTC_RB_AHEAD', '1')
    elif s.get('gpu_submit') == 'off':
        put('SOTC_FLUSH_EVERY', '0')
        put('SOTC_RB_AHEAD', '0')
    profile = str(s.get('vram_profile') or 'auto')
    if profile == 'auto':
        mb = gpu_vram_mb()
        light = 0 < mb < LIGHT_VRAM_BELOW_MB
    else:
        light = profile == 'light'
    vram_use = str(s.get('vram_use') or 'normal')
    if light and vram_use in ('high', 'max'):
        vram_use = 'normal'  # High / Maximum hold more than such a card has
    gc_percent, evict_mb = VRAM_LIMITS.get(vram_use, VRAM_LIMITS['normal'])
    put('SOTC_VRAM_GC_PERCENT', gc_percent)
    put('SOTC_ARENA_EVICT_MB', evict_mb)
    if light:
        put('SOTC_STAGING_KEEP_VRAM_MB', '0')
    # Sound (runtime_audio.c).
    put('SOTC_VOLUME', str(s.get('volume') or '100'))
    if str(s.get('audio_channels') or 'auto') in ('2', '6', '8'):
        put('SOTC_AUDIO_CHANNELS', str(s['audio_channels']))
    if not s.get('audio_lfe', True):
        put('SOTC_AUDIO_LFE', '0')
    if str(s.get('audio_device') or '').strip():
        put('SOTC_AUDIO_DEVICE', str(s['audio_device']).strip())
    put('SOTC_SHADOW_REUSE', str(s.get('shadow_reuse') or '0'))
    put('SOTC_OUTPUT_RES', str(s.get('output_res') or '1920x1080'))
    # The PS4 Pro path keeps its 16:9 sizes: a wider screen (21:9, 32:9) wins over it (#142).
    neo = bool(s.get('neo')) and not is_wide(env['SOTC_OUTPUT_RES'])
    put('SOTC_NEO', '1' if neo else '0')
    if s.get('neo') and not neo:
        put('SOTC_NOTE', f"{env['SOTC_OUTPUT_RES']} is wider than 16:9: PS4 Pro mode off (it renders 16:9 only)")
    put('SOTC_FRAMEGEN', str(s.get('framegen') or 'off'))
    if s.get('fg_hudless'):
        put('SOTC_FG_HUDLESS', '1')
    fg_mult = str(s.get('fg_mult') or '2')  # DLSS-G multiplier (#314)
    if fg_mult == 'dynamic':
        put('SOTC_DLSSG_MODE', 'dynamic')
        put('SOTC_DLSSG_FRAMES', '5')  # the most the card allows; Streamline picks the number
    elif fg_mult in ('3', '4', '6'):
        put('SOTC_DLSSG_FRAMES', str(int(fg_mult) - 1))
    # High quality textures (sotc_lod_stats.h): the texture banks sampled since the last report read
    # as sampled, the measured mips, finer mips (High 1, Maximum 0; light set Maximum 1 / High 2).
    textures = str(s.get('textures') or 'high')
    if textures != 'off':
        put('SOTC_LOD_LINGER', '1')
        put('SOTC_LOD_FEEDBACK', '1')
        if light:
            put('SOTC_LOD_LEVEL', '1' if textures == 'max' else '2')
        else:
            put('SOTC_LOD_LEVEL', '0' if textures == 'max' else '1')
    # 0.72.2 (T51): the page pool pages the game returns under textures it still draws stay frozen
    # (stretched textures and flicker at the ending).
    put('SOTC_POOL_FREEZE', '1')
    # 0.72.2 (T48): an unmap's arena release waits for the GPU once it passed the unmap, not for all
    # of its work (28-63 waits a frame at area changes).
    put('SOTC_RELEASE_DEFER', '1')
    # 0.72.2: images of 2048x2048 and more get memory of their own (the shared 64 MiB blocks kept up
    # to 1.8 GB free after an area's textures went).
    put('SOTC_IMAGE_DEDICATED', '1')
    # 0.72.2 / 0.77 (T48): new textures read and gathered by the GPU in the game's memory (no CPU
    # copy at an area's first entry). The game's 10 GB stay imported and pinned: 24 GB of RAM or more.
    if memory_gb() >= 24:
        put('SOTC_PC_MEMORY', '1')
        put('SOTC_PC_MEMORY_PREIMPORT', '1')
        put('SOTC_TEX_DIRECT', '1')
        put('SOTC_TEX_GATHER', '1')
    if s.get('button_icons') == 'xbox' and (PORT / 'glyphs' / 'xbox').is_dir():
        put('SOTC_TEX_REPLACE', str(PORT / 'glyphs' / 'xbox'))
    put('SOTC_UI_LANG', str(s.get('ui_language') or desktop_language()))  # in-game menu, F7/F8 texts
    # The game renders at the output size (720p at 1080p, as on PS4); the PS4 Pro path keeps its own
    # sizes. DLSS / FSR 4 render smaller and upscale.
    output = env['SOTC_OUTPUT_RES']
    upscaler = str(s.get('upscaler') or 'fsr1')
    if 'SOTC_RENDER_RES' not in env and not neo:
        if upscaler in ('dlss', 'fsr4'):
            env['SOTC_RENDER_RES'] = dlss_render(output, s.get('dlss_mode'))
        elif output not in ('1280x720', '1920x1080'):
            env['SOTC_RENDER_RES'] = output
    # FSR 1 stays the upscaler of frames without the game's scene (menus) and the fallback of DLSS.
    put('BB_FSR1', '1' if upscaler in ('fsr1', 'dlss', 'fsr4') else '0')
    if upscaler in ('dlss', 'fsr4'):
        put('SOTC_UPSCALER', upscaler)
        put('SOTC_DLSS_SHARPEN', str(s.get('dlss_sharpen') or '0'))
        put('SOTC_DLSS_UI_SHARPEN', str(s.get('dlss_ui_sharpen') or '3'))
        put('SOTC_DLSS_SKY_SHARPEN', str(s.get('dlss_sky_sharpen') or '2'))
        if s.get('dlss_compare'):
            put('SOTC_DLSS_COMPARE', '1')
    if s.get('hdr_sdr'):
        put('SOTC_HDR', '1')  # upstream's SDR-to-HDR10 output; 'hdr' (SOTC_MODES) is the game's own
    if s.get('sharpness') == 'off':
        put('BB_RCAS', '0')
    else:
        put('BB_RCAS', '1')
        put('BB_RCAS_ATTENUATION', str(s.get('sharpness') or '250'))
    put('SOTC_MOUSE', '1' if s.get('mouse', True) else '0')
    put('SOTC_MOUSE_SENS', str(s.get('mouse_sens') or '1.0'))
    put('SOTC_MOUSE_INVERT', '1' if s.get('mouse_invert') else '0')
    # Hot readbacks (buffer_cache.cpp GatherDownloads): ~25% more FPS at the Shrine.
    put('SOTC_RB_HOT', '1' if s.get('rb_hot', True) else '0')
    if s.get('debug_menu'):
        put('SOTC_DEBUG_MENU', '1')  # Bluepoint's debug menu
    if s.get('debug_watch'):
        put('SOTC_POOL_WATCH', '1')  # the texture memory watch, for bug reports
    if str(s.get('gamepad') or '').strip():
        put('BB_GAMEPAD', str(s['gamepad']).strip())
    if not s.get('rumble', True):
        put('SOTC_RUMBLE', '0')


def fingerprint(game, modules):
    """Inputs of the prepared image: eboot, bundled modules, the user's modules, the scripts."""
    digest = hashlib.sha256()
    files = [game / 'eboot.bin', *sorted((game / 'sce_module').glob('*.prx')), *modules,
             *sorted(SCRIPTS.glob('*.py'))]
    for path in files:
        stat = path.stat()
        digest.update(f'{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}\n'.encode())
    return digest.hexdigest()


def game_update(game):
    """The game update next to the dump, as shadPS4 uses it (<game>-UPDATE or <game>-patch), or
    SOTC_UPDATE_DIR; None without one."""
    named = os.environ.get('SOTC_UPDATE_DIR')
    if named:
        return Path(named).resolve()
    for suffix in ('-UPDATE', '-patch'):
        folder = game.with_name(game.name + suffix)
        if folder.is_dir():
            return folder
    return None


def merged_source(game, update, out):
    """The files the image is prepared from when an update is present: its eboot.bin, the base
    modules with the update's on top, its param.sfo (out/app-update, refreshed when they change)."""
    merged = out / 'app-update'
    pairs = [(update / 'eboot.bin', merged / 'eboot.bin')]
    for folder in (game / 'sce_module', update / 'sce_module'):
        if folder.is_dir():
            pairs += [(p, merged / 'sce_module' / p.name) for p in folder.iterdir() if p.is_file()]
    for folder in (game / 'sce_sys', update / 'sce_sys'):
        if (folder / 'param.sfo').is_file():
            pairs.append((folder / 'param.sfo', merged / 'sce_sys' / 'param.sfo'))
    for source, target in pairs:
        stat = source.stat()
        current = target.stat() if target.is_file() else None
        if not current or current.st_size != stat.st_size or current.st_mtime_ns != stat.st_mtime_ns:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    return merged


def main():
    load_ini()
    env = os.environ
    os.chdir(PORT)
    out = DATA / 'out'
    out.mkdir(parents=True, exist_ok=True)
    # The EU dump (CUSA08809) next to the port, else the US one (CUSA08034).
    default = next((base / g for base in dict.fromkeys((DATA.parent, PORT.parent, DATA))
                    for g in ('CUSA08809', 'CUSA08034') if (base / g / 'eboot.bin').is_file()),
                   DATA.parent / 'CUSA08809')
    game = Path(env.get('SOTC_GAME_DIR', default)).resolve()
    if not (game / 'eboot.bin').is_file():
        fail(f'No eboot.bin in {game}: set SOTC_GAME_DIR (environment or sotc.ini) to the CUSA08809 (EU) '
             'or CUSA08034 (US) dump.')

    modules = []
    sys_modules = env.get('SOTC_SYS_MODULES')
    if sys_modules:
        modules = [Path(sys_modules) / name for name in SYS_MODULES]
        missing = [m.name for m in modules if not m.is_file()]
        if missing:
            print(f'SOTC_SYS_MODULES: {", ".join(missing)} not found in {sys_modules}; the built-in mixer plays the sound', file=sys.stderr)
            modules = []
    else:
        print('SOTC_SYS_MODULES not set: the built-in mixer plays the sound (see sotc.py)', file=sys.stderr)

    # A complete update (shadPS4's <game>-UPDATE): the image comes from its eboot, and its files
    # take the place of the base game's while the game runs (src/runtime_file.c).
    # The DLC next to the dump (<game>-DLC), as the update (<game>-UPDATE), unless SOTC_DLC_DIR.
    dlc = game.with_name(game.name + '-DLC')
    if not env.get('SOTC_DLC_DIR') and dlc.is_dir():
        env['SOTC_DLC_DIR'] = str(dlc)
    update = game_update(game)
    for folder in (game, update):
        if folder and (folder / 'eboot.bin').is_file() and (folder / 'eboot.bin').stat().st_size == 0:
            fail(f'{folder / "eboot.bin"} is empty (0 bytes): the copy was interrupted. Copy the file again.')
    source = game
    if update:
        print(f'Game update: {update}')
        env['SOTC_UPDATE_DIR'] = str(update)
        if (update / 'eboot.bin').is_file():
            source = merged_source(game, update, out)
    stamp = out / 'prepared.txt'
    wanted = fingerprint(source, modules)
    images = [out / name for name in ('boot-linked.bin', 'content.bin', 'sotc-cpu.bin')]
    if not stamp.is_file() or stamp.read_text().strip() != wanted or not all(p.is_file() for p in images):
        print('Preparing the game image...')
        run_script('prepare.py', source, '--out', out)
        link = ['link_modules.py', source, '--out', out]
        if modules:
            link += ['--sys-modules', modules[0].parent]
        run_script(*link)
        run_script('content_profile.py', source, '--out', out)
        run_script('sotc_cpu.py', source, '--out', out)
        stamp.write_text(wanted + '\n')

    # The start-up settings (<user>/settings.json, the in-game menu's), below what the environment
    # and sotc.ini set.
    version = port_version()
    user = Path(env.get('SOTC_USER_DIR', DATA / 'user')).resolve()
    user.mkdir(parents=True, exist_ok=True)
    settings_file = user / 'settings.json'
    settings_env(env, load_settings(settings_file, version), settings_file, source)
    check_shader_cache(user, version)
    modes = env.get('SOTC_MODES', '')
    cvars = env.get('SOTC_CVARS', '')
    if env.get('SOTC_NOTE'):
        print(f"sotc: {env['SOTC_NOTE']}", file=sys.stderr)
    render = env.get('SOTC_RENDER_RES', '').strip()
    if render == '1920x1080':
        # A 16:9 output above 1080p renders at 1080p as before: no patches, no extra memory.
        render = ''
    if render:
        env['SOTC_RENDER_RES'] = render  # the GPU library reads it (bilinear 2D art above 1080p)
    else:
        env.pop('SOTC_RENDER_RES', None)
    run_script('sotc_modes.py', source, '--out', out, '--modes', modes, '--cvars', cvars,
               *(['--render', render] if render else []))
    if render:
        # The output keeps the render size's aspect (a 16:9 output would stretch a 21:9 image).
        try:
            rw, rh = map(int, render.split('x'))
            ow, oh = map(int, env.get('SOTC_OUTPUT_RES', '').split('x'))
            same_aspect = abs(ow * rh - oh * rw) <= oh * rw // 100
        except ValueError:
            same_aspect = False
        if not same_aspect:
            env['SOTC_OUTPUT_RES'] = render
        # Larger render targets: the game's heaps take what direct memory there is (run.sh).
        env.setdefault('BB_DMEM_MB', '9152')
    # The game's direct memory allocator (a 64 KiB page bitmap over all of it) filled up and read
    # past the bitmap (guest offset 0x1a371, read of -1): in PS4 Pro mode with 5696 MiB when a save
    # loaded, and in PS4 mode with 5056 MiB on loading the last colossus' area (user logs, 19
    # Oct; high quality textures keep more fine mips resident than on a PS4). Every mode gets the
    # 9152 MiB the wide render sizes already used.
    env.setdefault('BB_DMEM_MB', '9152')
    # The game waits for vblanks: at 60 Hz an uncapped frame (fps60, or F7 in game) still rounds
    # up to 30 FPS. With the cap, 120 Hz only shows a late frame sooner (and SOTC_FPS_LIMIT counts
    # in 120 Hz vblanks).
    env.setdefault('BB_VBLANK_HZ', '120')
    if 'hdr' in modes.lower():
        # HDR10 swapchain (Rec.2020 PQ, when the desktop offers it); the game then offers HDR too.
        env.setdefault('BB_HDR', '1')

    probe = find_probe()
    if version:
        env.setdefault('SOTC_PORT_VERSION', version)  # window title, in-game menu
    env.setdefault('BB_GPU_USER_DIR', str(user))
    # Controls: key.<input>= / pad.<input>= lines of sotc.ini remap keys and buttons (src/runtime_pad.c).
    env.setdefault('BB_CONFIG', str(DATA / 'sotc.ini'))
    command = [str(probe), str(out / 'boot-linked.bin'), '--content-profile', str(out / 'content.bin'),
               '--sotc-cpu', str(out / 'sotc-cpu.bin'), '--patches', str(out / 'patches.bin'),
               *(['--sotc-cmdline', str(out / 'cmdline.bin')] if (out / 'cmdline.bin').is_file() else []),
               '--app0', str(game), '--user', str(user), *sys.argv[1:]]
    # SOTC_WRAP: a JSON list put in front of the game, e.g. ["gamemoderun"], ["mangohud"] or RenderDoc
    # ["renderdoccmd", "capture", "-w", "-c", "<file>"]; F12 then captures the frame
    # (SOTC_RDOC_SUBMITS submissions).
    if env.get('SOTC_WRAP'):
        import json
        command = json.loads(env['SOTC_WRAP']) + command
    # In a console the session also goes to user/last_run.log; with the output piped (a script that
    # keeps its own log) it is not written here.
    if not sys.stdout.isatty():
        def play():
            return subprocess.run(command, stdin=subprocess.DEVNULL).returncode
        return with_range_retries(env, play)
    with open_session_log(user) as log:
        def play():
            game = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
            try:
                for line in game.stdout:
                    sys.stdout.buffer.write(line)
                    sys.stdout.buffer.flush()
                    log.write(line)
            finally:
                code = game.wait()
            return code
        code = with_range_retries(env, play)
    keep_crash_log(user, code)
    return code


RANGE_BUSY_EXIT = 87  # src/runtime_memory.c: the guest's address range was taken at start
RANGE_RETRIES = 10


def with_range_retries(env, play):
    """Runs play() and starts it again while the game reports its address range taken (error 487,
    issue #110). What sits there usually differs per process, so a new start gets through."""
    for attempt in range(RANGE_RETRIES):
        env['SOTC_RANGE_RETRY'] = str(attempt)
        code = play()
        if code != RANGE_BUSY_EXIT:
            return code
        print(f'sotc: address range taken, starting again ({attempt + 1}/{RANGE_RETRIES})', flush=True)
        time.sleep(0.5)
    print('sotc: the address range stayed taken. The lines above name what sits there; closing '
          'overlays and hooking tools (recording, RGB, tuning, antivirus exceptions) should free it.',
          flush=True)
    return code


LOGS_KEPT = 5        # last_run.log and last_run.1.log ... last_run.4.log
CRASH_LOGS_KEPT = 20


def open_session_log(user):
    """A fresh user/last_run.log; the previous sessions' logs move to last_run.1.log (the one
    before) ... last_run.4.log."""
    for i in range(LOGS_KEPT - 1, 0, -1):
        older = user / ('last_run.log' if i == 1 else f'last_run.{i - 1}.log')
        if older.is_file():
            try:
                os.replace(older, user / f'last_run.{i}.log')
            except OSError:
                pass
    return open(user / 'last_run.log', 'wb', buffering=0)


def keep_crash_log(user, code):
    """After a session that ended with an error code, copies its log to
    user/crashes/<date>_<time>_<code>.log (the last 20 are kept)."""
    if code == 0:
        return
    import time
    crashes = user / 'crashes'
    try:
        crashes.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime('%Y-%m-%d_%H-%M-%S')
        shutil.copy2(user / 'last_run.log', crashes / f'{stamp}_{code & 0xffffffff:#x}.log')
        for old in sorted(crashes.glob('*.log'))[:-CRASH_LOGS_KEPT]:
            old.unlink()
    except OSError:
        pass


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
