"""Test kexec RAM loading and immediately unload. NEVER executes a new kernel."""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
REMOTE = '/data/local/tmp/w152d-linux-probe'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--runtime-dtb', type=Path, required=True)
    parser.add_argument('--adb', default=os.environ.get('ADB', 'adb'))
    args = parser.parse_args()
    records = []
    report_path = HERE / 'evidence' / ('kexec_load_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '.json')

    def adb(*argv):
        p = subprocess.run([args.adb, '-s', args.serial, *argv], capture_output=True, timeout=45)
        records.append({'args': list(argv), 'returncode': p.returncode, 'stdout': p.stdout.decode(errors='replace'), 'stderr': p.stderr.decode(errors='replace')})
        report_path.write_text(json.dumps({'commands': records}, ensure_ascii=False, indent=2), encoding='utf-8')
        return p

    assert 'uid=0(root)' in adb('shell', 'id').stdout.decode(), 'Root ADB required'
    before = adb('shell', 'cat /sys/kernel/kexec_loaded')
    assert before.returncode == 0 and before.stdout.strip() == b'0', 'Existing kexec target; leaving it untouched'
    assert args.runtime_dtb.read_bytes()[:4] == bytes.fromhex('d00dfeed')
    for local, name in ((HERE / 'out/Image', 'Image'), (HERE / 'out/initramfs-probe.cpio.gz', 'initramfs-probe.cpio.gz'), (args.runtime_dtb, 'runtime.dtb')):
        result = adb('push', str(local), REMOTE + '/' + name)
        assert result.returncode == 0, 'ADB push failed'
    result = None
    loaded = False
    unload_ok = False
    try:
        result = adb('shell', f'kexec --load {REMOTE}/Image --type=Image --dtb={REMOTE}/runtime.dtb --initrd={REMOTE}/initramfs-probe.cpio.gz --reuse-cmdline')
        state = adb('shell', 'cat /sys/kernel/kexec_loaded')
        loaded = state.returncode == 0 and state.stdout.strip() == b'1'
    finally:
        # Only clear the normal target we just attempted to load, never a crash kernel.
        state = adb('shell', 'cat /sys/kernel/kexec_loaded')
        if state.returncode == 0 and state.stdout.strip() == b'1':
            adb('shell', 'kexec --unload')
        final = adb('shell', 'cat /sys/kernel/kexec_loaded')
        unload_ok = final.returncode == 0 and final.stdout.strip() == b'0'
        report = {'status': 'LOAD_AND_UNLOAD_PASSED' if result and result.returncode == 0 and loaded and unload_ok else 'LOAD_NOT_CONFIRMED', 'loaded_observed': loaded, 'final_kexec_loaded_is_zero': unload_ok, 'kernel_executed': False, 'device_rebooted': False, 'commands': records, 'limits': ['Only RAM loading was tested', 'Actual kexec transfer, hardware reinitialization and remote control remain untested', 'Reused Android command line is not a validated final Linux boot configuration']}
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({k: v for k, v in report.items() if k != 'commands'}, ensure_ascii=False, indent=2))
        print('Evidence:', report_path)
    assert unload_ok, 'Check the kexec target state; cleanup was not confirmed'
    if result.returncode != 0 or not loaded:
        print(result.stdout.decode(errors='replace'), result.stderr.decode(errors='replace'))


if __name__ == '__main__':
    main()
