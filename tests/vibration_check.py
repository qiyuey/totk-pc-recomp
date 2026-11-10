"""Build/run the synthetic vibration owner test; --device opts into real output."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_game


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--device', action='store_true')
    p.add_argument('--device-log', type=Path)
    a = p.parse_args()
    if os.name != 'nt':
        p.error('This standalone test fixture currently targets Windows')
    out = ROOT / 'build' / 'vibration-check'
    out.mkdir(parents=True, exist_ok=True)
    dependencies = build_game.configure_sdl3([])
    for dependency in dependencies:
        shutil.copy2(dependency, out / dependency.name)
    clang = Path('C:/msys64/ucrt64/bin/clang.exe')
    env = dict(os.environ)
    env['PATH'] = str(clang.parent) + os.pathsep + env.get('PATH', '')
    flags = [str(clang), '-O1', '-g', '-ffunction-sections', '-fdata-sections',
             '-D_WIN32_WINNT=0x0A00', '-I', str(ROOT / 'runtime'),
             '-I', str(build_game.SDL3_INCLUDE), '-I', str(ROOT / 'runtime/third_party/imgui'),
             '-I', 'C:/msys64/ucrt64/include/vma']
    platform = ['runtime/platform/win32.c', 'runtime/platform/common.c']
    link = ['-fuse-ld=lld', '-Wl,--gc-sections', str(build_game.SDL3_LINK),
            '-luser32', '-lwinmm', '-lole32', '-lpsapi', '-lbcrypt']
    unit = out / 'vibration_owner.exe'
    subprocess.run(flags + ['tests/vibration_owner.c'] + platform + link + ['-o', str(unit)],
                   cwd=ROOT, env=env, check=True)
    subprocess.run([str(unit)], cwd=out, env=env, check=True)
    if a.device:
        device = out / 'vibration_device.exe'
        subprocess.run(flags + ['tests/vibration_device.c', 'runtime/input_map.c', 'runtime/cfg.c'] +
                       platform + link + ['-o', str(device)], cwd=ROOT, env=env, check=True)
        if a.device_log:
            a.device_log.parent.mkdir(parents=True, exist_ok=True)
            with a.device_log.open('w', encoding='utf-8') as log:
                result = subprocess.run([str(device), '--play'], cwd=out, env=env,
                                        stdout=log, stderr=subprocess.STDOUT)
        else:
            result = subprocess.run([str(device), '--play'], cwd=out, env=env)
        if result.returncode == 77:
            print('SKIP: supported device not connected')
        elif result.returncode:
            raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
