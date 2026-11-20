"""Back up and patch only the verified two-copy env layout; --execute writes."""
from pathlib import Path
import argparse,subprocess,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--serial',required=True);p.add_argument('--adb',default='adb');p.add_argument('--node',default='node');p.add_argument('--output',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args()
 a.output.mkdir(parents=True,exist_ok=True)
 def adb(*args):
  r=subprocess.run([a.adb,'-s',a.serial,*args],capture_output=True,timeout=30)
  if r.returncode:raise RuntimeError('ADB operation failed: '+args[0])
  return r.stdout
 assert b'uid=0(root)' in adb('shell','id'),'Run adb root and reconnect first'
 assert adb('shell','getprop ro.product.model').strip()==b'W152D','This tool is only validated on W152D'
 before=adb('exec-out','cat /dev/block/env');assert len(before)==8388608
 source=a.output/'env-before.img';assert not source.exists(),'Refusing to overwrite a backup'
 source.write_bytes(before)
 target=a.output/'env-usb-first.img'
 r=subprocess.run([a.node,str(ROOT/'tools/env_boot_order.cjs'),'patch',str(source),str(target)],capture_output=True,text=True)
 if r.returncode:raise RuntimeError(r.stderr.strip())
 report=json.loads(Path(str(target)+'.json').read_text())
 print(json.dumps({'before_sha256':report['before']['sha256'],'after_sha256':report['after']['sha256'],'only_bootcmd_changed':True,'tail_preserved':True,'write_requested':a.execute},indent=2))
 if not a.execute:
  print('DRY RUN: backup and patch prepared; no device writes');return
 prefix=Path(str(target)+'.prefix');remote='/data/local/tmp/w152d-env-patch'
 adb('shell','mkdir -p '+remote);adb('push',str(prefix),remote+'/env.prefix')
 before_sha=hashlib.sha256(before).hexdigest();after_sha=report['after']['sha256'];prefix_sha=hashlib.sha256(prefix.read_bytes()).hexdigest()
 script=f'''set -eu
test "$(sha256sum /dev/block/env | cut -d ' ' -f 1)" = {before_sha}
test "$(sha256sum {remote}/env.prefix | cut -d ' ' -f 1)" = {prefix_sha}
dd if=/dev/block/env of={remote}/env-before.img bs=4096 count=2048
sync
dd if={remote}/env.prefix of=/dev/block/env bs=4096 count=32 conv=notrunc
sync
test "$(sha256sum /dev/block/env | cut -d ' ' -f 1)" = {after_sha}
'''
 script_path=a.output/'apply.sh';script_path.write_bytes(script.encode());adb('push',str(script_path),remote+'/apply.sh');adb('shell','sh '+remote+'/apply.sh')
 result=adb('exec-out','cat /dev/block/env');assert result==target.read_bytes(),'Readback mismatch'
 (a.output/'env-readback.img').write_bytes(result)
 print('USB-first environment written and read back. Bootloader and boot/vendor_boot were not written.')
if __name__=='__main__':main()
