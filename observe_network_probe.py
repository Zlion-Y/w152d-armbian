"""Observe a read-only RAM-boot status endpoint; does not control the device."""
import argparse
import datetime
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seconds', type=int, default=150)
    args = p.parse_args()
    manifest = json.loads((HERE / 'network-probe/manifest.json').read_text(encoding='utf-8'))
    url = f"http://{manifest['ip']}:{manifest['port']}/"
    out = HERE / 'evidence' / ('native_observer_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
    out.mkdir()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    events = []
    deadline = time.monotonic() + args.seconds
    print('Observing native status endpoint:', url, flush=True)
    while time.monotonic() < deadline:
        try:
            with opener.open(url, timeout=1.5) as response:
                text = response.read(65536).decode(errors='replace')
            phase = next((line for line in text.splitlines() if line.startswith('phase=')), 'unknown')
            events.append({'elapsed_seconds': round(args.seconds - (deadline - time.monotonic()), 1), 'response_phase': phase})
            if ('W152D_PROBE_TOKEN=' + manifest['token']) in text and 'phase=NATIVE_RAM_INIT' in text and '/bin/busybox sh /init' in text:
                (out / 'native_status.txt').write_text(text, encoding='utf-8')
                result = {'status': 'NATIVE_PID1_AND_ETHERNET_OBSERVED', 'url': url, 'token': manifest['token'], 'events': events}
                (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
                print('NATIVE_PID1_AND_ETHERNET_OBSERVED', flush=True)
                print('Evidence:', out, flush=True)
                return
        except (OSError, urllib.error.URLError) as exc:
            events.append({'elapsed_seconds': round(args.seconds - (deadline - time.monotonic()), 1), 'error': str(exc)})
        time.sleep(1.5)
    (out / 'result.json').write_text(json.dumps({'status': 'NO_NATIVE_STATUS_OBSERVED', 'url': url, 'events': events}, indent=2) + '\n', encoding='utf-8')
    print('NO_NATIVE_STATUS_OBSERVED; this alone does not distinguish kernel and network failure', flush=True)
    print('Evidence:', out, flush=True)


if __name__ == '__main__':
    main()
