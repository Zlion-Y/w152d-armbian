"""Prepare files on an existing mounted USB; never repartitions or flashes it."""
from pathlib import Path
import argparse,gzip,hashlib,shutil,sys,zipfile,getpass,os
sys.path.insert(0,str(Path(__file__).resolve().parent))
from extract_stock import extract
from configure_usb import configure
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--usb',type=Path,required=True);p.add_argument('--rootfs',type=Path,required=True);p.add_argument('--bootstrap',type=Path,required=True);p.add_argument('--checksums',type=Path,required=True);p.add_argument('--stock-dir',type=Path,required=True);p.add_argument('--vendor-image',type=Path,required=True);p.add_argument('--public-key',type=Path,required=True);p.add_argument('--ssid');a=p.parse_args()
 assert a.usb.is_dir(),'The USB must already be mounted; this tool does not format drives'
 image=a.usb/'w152d/rootfs.ext4'
 assert not image.exists(),'Existing rootfs refused. Choose an empty USB or move it aside yourself.'
 checks={line.split(None,1)[1].lstrip('*').strip():line.split()[0] for line in a.checksums.read_text().splitlines() if line.strip()}
 for path in [a.rootfs,a.bootstrap]:assert checks.get(path.name)==digest(path),path.name+' SHA256 mismatch'
 assert shutil.disk_usage(a.usb).free>3*1024**3,'At least 3 GiB free space is required'
 password=getpass.getpass('Wi-Fi password (not echoed): ') if a.ssid else ''
 with zipfile.ZipFile(a.bootstrap) as z:
  for name in ['aml_autoscript','w152d/initramfs.cpio.gz','w152d/USB_ID']:
   target=a.usb/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(name))
 extract(a.stock_dir,a.vendor_image,a.usb/'w152d')
 partial=image.with_suffix('.ext4.partial')
 assert not partial.exists(),'An unfinished image already exists; inspect it before retrying'
 with gzip.open(a.rootfs,'rb') as src,partial.open('xb') as dst:
  shutil.copyfileobj(src,dst,4*1024*1024);dst.flush();os.fsync(dst.fileno())
 assert partial.stat().st_size==2147483648,'Unexpected rootfs image size'
 with partial.open('rb') as f:f.seek(1080);assert f.read(2)==b'\x53\xef','Not an ext4 filesystem'
 partial.rename(image)
 configure(a.usb,a.public_key,a.ssid,password)
 print('USB files prepared. Boot-order activation is a separate, backup-first step. Eject the USB safely.')
if __name__=='__main__':main()
