"""Verify pinned SSH host key, ARM64 userspace, PTY and SFTP, optionally native PID 1."""
import argparse
import base64
import datetime
import json
from pathlib import Path
import sys
import time
import urllib.request

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'deps'))
import paramiko

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--native', action='store_true')
    p.add_argument('--seconds', type=int, default=100)
    args = p.parse_args()
    manifest = json.loads((HERE / 'armbian-rootfs/manifest.json').read_text())
    out = HERE / 'evidence' / ('armbian_ssh_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
    out.mkdir()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    errors = []
    deadline = time.monotonic() + args.seconds
    while time.monotonic() < deadline:
        client = paramiko.SSHClient()
        host = manifest['ssh_host_public_key'].split()
        client.get_host_keys().add(f"[{manifest['ip']}]:2222", host[0], paramiko.Ed25519Key(data=base64.b64decode(host[1])))
        try:
            if args.native:
                with opener.open(f"http://{manifest['ip']}:18080/", timeout=2) as response:
                    status = response.read(65536).decode()
                (out / 'last_status.txt').write_text(status, encoding='utf-8')
                assert 'W152D_PROBE_TOKEN=' + manifest['token'] in status
                assert 'phase=ARMBIAN_RAM_ROOTFS' in status and '/usr/local/bin/busybox sh /init' in status
                (out / 'native_status.txt').write_text(status, encoding='utf-8')
            client.connect(manifest['ip'], port=2222, username='root', key_filename=str(HERE / 'keys/client_ed25519'), look_for_keys=False, allow_agent=False, timeout=3, banner_timeout=3, auth_timeout=3)
            command = "printf 'W152D_ARMBIAN_SSH_OK\\n'; getconf LONG_BIT; dpkg --print-architecture; cat /etc/os-release; cat /etc/w152d-port.json; tr '\\000' ' ' </proc/1/cmdline; echo; cat /proc/mounts; cat /proc/uptime; head -5 /proc/meminfo; ps -ef; cat /bootstrap.log /run/w152d-userspace.txt /run/w152d-boot.log /run/w152d-sshd.log 2>/dev/null; true"
            _, stdout, stderr = client.exec_command(command, timeout=10)
            text, err = stdout.read().decode(), stderr.read().decode()
            assert stdout.channel.recv_exit_status() == 0
            assert 'W152D_ARMBIAN_SSH_OK\n64\narm64\n' in text and 'Armbian' in text
            if args.native:
                assert '/usr/local/bin/busybox sh /init' in text
                assert ' /data ' not in text
            _, stdout, stderr = client.exec_command('test -t 0 && test -t 1 && printf "W152D_PTY_OK\\n"', get_pty=True, timeout=5)
            pty = stdout.read().decode()
            assert stdout.channel.recv_exit_status() == 0 and 'W152D_PTY_OK' in pty
            with client.open_sftp() as sftp:
                content = b'W152D authenticated SFTP RAM test\n'
                path = '/run/w152d-sftp-check'
                with sftp.open(path, 'wb') as f:
                    f.write(content)
                with sftp.open(path, 'rb') as f:
                    assert f.read() == content
                sftp.remove(path)
            (out / 'ssh_output.txt').write_text(text + '\nSTDERR:\n' + err + '\nPTY:\n' + pty, encoding='utf-8')
            result = {'status': 'NATIVE_ARMBIAN_SSH_PTY_SFTP_PASSED' if args.native else 'CHROOT_ARMBIAN_SSH_PTY_SFTP_PASSED', 'host_key_pinned': True, 'native': args.native, 'errors_before_success': errors}
            (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
            print(json.dumps(result), '\nEvidence:', out, flush=True)
            return
        except (OSError, EOFError, paramiko.SSHException, AssertionError) as exc:
            errors.append(type(exc).__name__ + ': ' + str(exc))
        finally:
            client.close()
        time.sleep(2)
    (out / 'result.json').write_text(json.dumps({'status': 'FAILED', 'errors': errors}, indent=2), encoding='utf-8')
    raise SystemExit('SSH check failed; see ' + str(out))

if __name__ == '__main__':
    main()
