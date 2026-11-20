"""Build a credential-free USB bootstrap with Debian ARM64 static BusyBox."""
from pathlib import Path
import argparse,sys,stat,gzip,hashlib,struct,zlib,json,zipfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import build_probe as bp
def script_image(script):
 data=struct.pack('>II',len(script),0)+script
 h=struct.pack('>7I4B32s',0x27051956,0,0,len(data),0,0,zlib.crc32(data),5,2,6,0,b'W152D USB Linux preview')
 h=h[:4]+struct.pack('>I',zlib.crc32(h))+h[8:]
 return h+data
def build(binary,out):
 bb=binary.read_bytes();assert bb[:6]==b'\x7fELF\x02\x01'
 entries={p:(stat.S_IFDIR|0o755,b'',0,0) for p in ['bin','dev','proc','sys','run','usb','newroot']}
 entries.update({'bin/busybox':(stat.S_IFREG|0o755,bb,0,0),'dev/console':(stat.S_IFCHR|0o600,b'',5,1),'dev/null':(stat.S_IFCHR|0o666,b'',1,3)})
 for name,path in [('init','usb/init-bootstrap'),('status_service.sh','src/status_service.sh')]:
  entries[name]=(stat.S_IFREG|0o755,(ROOT/path).read_bytes().replace(b'\r\n',b'\n'),0,0)
 entries['modules.order']=(stat.S_IFREG|0o644,b'',0,0)
 entries['probe.conf']=(stat.S_IFREG|0o644,b'PROBE_TOKEN=release-diagnostics\nPORT=18080\n',0,0)
 entries=dict(sorted(entries.items(),key=lambda x:(x[0].count('/'),not stat.S_ISDIR(x[1][0]),x[0])))
 ram=gzip.compress(bp.cpio_build(entries),compresslevel=9,mtime=0)
 assert bp.cpio_parse(gzip.decompress(ram))==entries
 files={'aml_autoscript':script_image((ROOT/'usb/boot.cmd').read_bytes().replace(b'\r\n',b'\n')),'w152d/initramfs.cpio.gz':ram,'w152d/USB_ID':b'W152D_ARMBIAN_USB_DIRECT_V1\n'}
 out.mkdir(parents=True,exist_ok=True)
 for name,data in files.items():
  p=out/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
 manifest={n:{'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()} for n,b in files.items()}
 (out/'bootstrap-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps(manifest,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--busybox',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.busybox,a.output)
