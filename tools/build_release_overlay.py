"""Package public first-boot files; this tool never reads local credentials."""
from pathlib import Path
import argparse,io,tarfile,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
FILES={
 'init':'usb/init-rootfs',
 'status_service.sh':'src/status_service.sh',
 'usr/local/sbin/w152d-firstboot':'usb/w152d-firstboot',
 'usr/local/sbin/w152d-wifi':'wifi/w152d-wifi',
 'usr/local/libexec/w152d-udhcpc':'wifi/w152d-udhcpc',
 'usr/local/libexec/w152d-time':'wifi/w152d-time',
 'etc/ssh/sshd_config_w152d':'usb/sshd_config_w152d',
 'etc/chrony/chrony-w152d.conf':'usb/chrony-w152d.conf',
}
def build(output):
 with tarfile.open(output,'w') as t:
  for target,source in FILES.items():
   data=(ROOT/source).read_bytes().replace(b'\r\n',b'\n')
   info=tarfile.TarInfo(target);info.size=len(data);info.uid=info.gid=0
   info.mode=0o600 if target.endswith('sshd_config_w152d') else 0o644 if target.endswith('.conf') else 0o755
   t.addfile(info,io.BytesIO(data))
  reboot=b'#!/usr/local/bin/busybox sh\n/usr/local/libexec/w152d-time notify\nsync\nexec /usr/local/bin/busybox reboot -f\n'
  info=tarfile.TarInfo('usr/local/sbin/reboot');info.mode=0o755;info.size=len(reboot);t.addfile(info,io.BytesIO(reboot))
 print('Public overlay:',output,'sha256',hashlib.sha256(Path(output).read_bytes()).hexdigest())
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();build(a.output)
