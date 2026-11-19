"""Observe the expected return to Android after the timed RAM probe."""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--serial', action='append', required=True)
    p.add_argument('--seconds', type=int, default=180)
    p.add_argument('--adb', default=os.environ.get('ADB', 'adb'))
    args = p.parse_args()
    latest = sorted((HERE / 'evidence').glob('ram_boot_*.json'))[-1]
    original = json.loads(latest.read_text(encoding='utf-8'))
    deadline = time.monotonic() + args.seconds
    print('Waiting for Android boot completion on the known addresses...', flush=True)
    while time.monotonic() < deadline:
        for serial in args.serial:
            try:
                subprocess.run([args.adb, 'connect', serial], capture_output=True, timeout=4)
                r = subprocess.run([args.adb, '-s', serial, 'shell', 'getprop sys.boot_completed; getprop ro.boot.slot_suffix; cat /proc/sys/kernel/random/boot_id; cat /proc/1/cmdline; cat /sys/kernel/kexec_loaded'], capture_output=True, timeout=4)
                lines = r.stdout.decode(errors='replace').replace('\r', '').splitlines()
                if r.returncode == 0 and len(lines) >= 4 and lines[0] == '1' and '/system/bin/init' in r.stdout.decode(errors='replace'):
                    result = {'status': 'ANDROID_RETURN_CONFIRMED', 'serial': serial, 'boot_completed': True, 'slot': lines[1], 'boot_id': lines[2], 'boot_id_changed': lines[2] != original['original_boot_id'], 'slot_unchanged': lines[1] == original['original_slot'], 'output': r.stdout.decode(errors='replace')}
                    assert result['boot_id_changed'] and result['slot_unchanged']
                    out = HERE / 'evidence' / ('android_return_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '.json')
                    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
                    print('Evidence:', out, flush=True)
                    return
            except subprocess.TimeoutExpired:
                pass
        time.sleep(3)
    print('ANDROID_RETURN_NOT_YET_CONFIRMED', flush=True)


if __name__ == '__main__':
    main()
